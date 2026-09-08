"""The AI Recommendation System: builds a compact weekly analytics summary,
sends it to the LLM (app.llm_client), and stores the result as a
Recommendation row. Only starts producing anything once at least
`recommendation_period_days` (default 7) have passed since the first task was
ever synced or the first study session was ever started - see `is_eligible`.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from app import llm_client, reminders
from app.analytics_service import course_overview, early_start_vs_grade, weekly_productivity
from app.config import get_settings
from app.course_merge import build_course_index
from app.models import Recommendation, Task
from app.schemas import RecommendationItem, RecommendationRead

logger = logging.getLogger("prioriton.recommendations")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def is_eligible(session: Session) -> tuple[bool, Optional[float]]:
    """Returns (eligible, days_until_eligible). `days_until_eligible` is None
    when there's no tracked activity at all yet (nothing to count down from)."""
    settings = reminders.get_settings(session)
    session.commit()
    if settings.data_collection_started_at is None:
        return False, None
    start = _aware(settings.data_collection_started_at)
    period_days = get_settings().recommendation_period_days
    elapsed_days = (datetime.now(timezone.utc) - start).total_seconds() / 86400
    if elapsed_days >= period_days:
        return True, 0.0
    return False, round(period_days - elapsed_days, 1)


def current_period(session: Session) -> tuple[datetime, datetime]:
    """The [period_start, period_end) window "now" falls into, counting in
    fixed `recommendation_period_days`-long blocks from when data collection
    started. Returned naive, matching the rest of the app's naive-but-true-UTC
    storage convention."""
    settings = reminders.get_settings(session)
    period_days = get_settings().recommendation_period_days
    start = _aware(settings.data_collection_started_at or datetime.now(timezone.utc))
    now = datetime.now(timezone.utc)
    elapsed_days = (now - start).total_seconds() / 86400
    period_index = int(elapsed_days // period_days)
    period_start = start + timedelta(days=period_index * period_days)
    period_end = period_start + timedelta(days=period_days)
    return period_start.replace(tzinfo=None), period_end.replace(tzinfo=None)


def _early_start_grade_note(points: list) -> Optional[dict]:
    """A small derived signal the LLM can lean on for "start earlier" advice:
    average grade for assignments started 2+ days early vs. started same-day/
    late. Omitted entirely if there isn't enough data in both buckets to say
    anything meaningful."""
    early = [p.grade_pct for p in points if p.days_before_due >= 2]
    late = [p.grade_pct for p in points if p.days_before_due < 1]
    if len(early) < 2 or len(late) < 2:
        return None
    return {
        "avg_grade_started_2plus_days_early": round(sum(early) / len(early), 1),
        "avg_grade_started_same_day_or_late": round(sum(late) / len(late), 1),
        "sample_size_early": len(early),
        "sample_size_late": len(late),
    }


def build_summary(session: Session) -> dict:
    overview = course_overview(session)
    esg = early_start_vs_grade(session)
    productivity = weekly_productivity(session, weeks=4)

    weekly_hours_values = [c.study_hours_this_week for c in overview]
    avg_weekly_hours_all_courses = (
        round(sum(weekly_hours_values) / len(weekly_hours_values), 2) if weekly_hours_values else 0.0
    )

    courses_payload = []
    for c in overview:
        avg_hours_per_task = round(c.study_hours_total / c.tasks_completed, 2) if c.tasks_completed else None
        courses_payload.append(
            {
                "course_name": c.course_name,
                "avg_grade_pct": c.avg_grade_pct,
                "study_hours_this_week": c.study_hours_this_week,
                "study_hours_total": c.study_hours_total,
                "hours_vs_average_across_other_courses": round(
                    c.study_hours_this_week - avg_weekly_hours_all_courses, 2
                ),
                "avg_hours_per_completed_assignment": avg_hours_per_task,
                "tasks_pending": c.tasks_pending,
                "tasks_completed": c.tasks_completed,
            }
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    upcoming_tasks = session.exec(
        select(Task)
        .where(
            Task.status == "pending",
            Task.due_at.is_not(None),
            Task.due_at >= now,
            Task.due_at <= now + timedelta(days=14),
        )
        .order_by(Task.due_at)
    ).all()
    index = build_course_index(session)
    upcoming_payload = [
        {
            "course_name": index.display_name.get(index.canonical_id.get(t.course_id, t.course_id))
            if t.course_id is not None
            else None,
            "title": t.title,
            "due_in_days": round((t.due_at - now).total_seconds() / 86400, 1),
            "already_started": t.started_at is not None,
        }
        for t in upcoming_tasks[:10]
    ]

    return {
        "courses": courses_payload,
        "avg_weekly_study_hours_all_courses": avg_weekly_hours_all_courses,
        "upcoming_assignments": upcoming_payload,
        "early_start_vs_grade_note": _early_start_grade_note(esg),
        "recent_weekly_productivity": [
            {"week_start": p.week_start.isoformat(), "study_hours": p.study_hours, "tasks_completed": p.tasks_completed}
            for p in productivity
        ],
    }


def generate(session: Session) -> Recommendation:
    """Calls the LLM and stores a new Recommendation row. Raises
    llm_client.LLMNotConfiguredError / LLMResponseError on failure - callers
    (the router, the scheduler) decide how to surface that."""
    summary = build_summary(session)
    raw_items = llm_client.generate_recommendations(summary)

    index = build_course_index(session)
    course_id_by_name = {index.display_name[c.id]: c.id for c in index.canonical_courses}
    items: list[dict] = []
    for raw in raw_items:
        message = str(raw.get("message") or "").strip()
        if not message:
            continue
        course_name = raw.get("course_name")
        try:
            priority = int(raw.get("priority", 2))
        except (TypeError, ValueError):
            priority = 2
        item = RecommendationItem(
            course_id=course_id_by_name.get(course_name),
            course_name=course_name,
            kind=str(raw.get("kind") or "general"),
            message=message,
            priority=max(1, min(3, priority)),
        )
        items.append(item.model_dump(mode="json"))

    period_start, period_end = current_period(session)
    recommendation = Recommendation(
        period_start=period_start,
        period_end=period_end,
        summary_json=json.dumps(summary),
        items_json=json.dumps(items),
        model=get_settings().anthropic_model,
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)
    return recommendation


def maybe_generate_weekly(session: Session) -> Optional[Recommendation]:
    """The eligibility + idempotency gate shared by the daily scheduler job
    and the manual "Generate now" button. Returns None (without calling the
    LLM) when not yet eligible or a recommendation already exists for the
    current period."""
    eligible, _ = is_eligible(session)
    if not eligible:
        return None
    period_start, _period_end = current_period(session)
    existing = session.exec(
        select(Recommendation).where(Recommendation.period_start == period_start)
    ).first()
    if existing is not None:
        return None
    return generate(session)


def latest_read(session: Session) -> RecommendationRead:
    eligible, days_until = is_eligible(session)
    latest = session.exec(select(Recommendation).order_by(Recommendation.generated_at.desc())).first()
    if latest is None:
        return RecommendationRead(eligible=eligible, days_until_eligible=days_until, items=[])
    items = [RecommendationItem(**item) for item in json.loads(latest.items_json)]
    return RecommendationRead(
        id=latest.id,
        generated_at=latest.generated_at,
        period_start=latest.period_start,
        period_end=latest.period_end,
        items=items,
        eligible=eligible,
        days_until_eligible=days_until,
    )
