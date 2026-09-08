"""Aggregation queries backing the Analytics Dashboard (app.routers.analytics)
and the AI Recommendation System's context (app.recommendation_service).

Deliberately computed on the fly rather than cached in tables - the data
volumes here (one student's courses/tasks/sessions) are small enough that a
handful of Python-side aggregations over already-indexed queries stay fast,
and it avoids a whole cache-invalidation story for something this size.

Every grouping-by-course here goes through app.course_merge's CourseIndex
first, so a class synced from more than one platform (e.g. Gradescope +
PrairieLearn both tracking the same real course) is counted once under its
canonical course, not split across two bars/points with different names.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from app.course_merge import CourseIndex, build_course_index
from app.models import StudySession, Task
from app.schemas import (
    CourseOverview,
    EarlyStartVsGradePoint,
    GradeTrendPoint,
    StudyVsGradePoint,
    WeeklyProductivityPoint,
)

SECONDS_PER_HOUR = 3600.0


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _week_start(dt: datetime) -> datetime:
    """Monday 00:00 of the week containing `dt` (naive, matching the rest of
    the app's naive-but-true-UTC storage convention - see
    app.adapters.base.SyncedTask.due_at)."""
    d = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=d.weekday())


def _grade_pct(score: Optional[float], points_possible: Optional[float]) -> Optional[float]:
    if score is None or not points_possible:
        return None
    return round((score / points_possible) * 100, 1)


def _session_hours(sessions: list[StudySession], now: datetime, since: Optional[datetime] = None) -> float:
    total_seconds = 0.0
    for s in sessions:
        if since is not None and s.started_at < since:
            # Partial credit for a session that started before the window but
            # is still running/ended inside it would be more precise, but for
            # a personal weekly-hours view whole-session bucketing by start
            # time is simple and matches how the Study Timer already buckets
            # "this week" for display.
            continue
        end = s.ended_at if s.ended_at is not None else now
        total_seconds += (end - s.started_at).total_seconds()
    return total_seconds / SECONDS_PER_HOUR


def _canonicalize(items: list, get_course_id, index: CourseIndex) -> dict[int, list]:
    """Groups a list of Task/StudySession rows by their CANONICAL course id
    (resolving a merged-away platform-specific course_id through the index),
    skipping rows with no course at all."""
    by_canonical: dict[int, list] = defaultdict(list)
    for item in items:
        raw_id = get_course_id(item)
        if raw_id is None:
            continue
        by_canonical[index.canonical_id.get(raw_id, raw_id)].append(item)
    return by_canonical


def course_overview(session: Session) -> list[CourseOverview]:
    index = build_course_index(session)
    tasks = session.exec(select(Task)).all()
    study_sessions = session.exec(select(StudySession)).all()

    tasks_by_course = _canonicalize(tasks, lambda t: t.course_id, index)
    sessions_by_course = _canonicalize(study_sessions, lambda s: s.course_id, index)

    now = _now()
    week_start = _week_start(now)

    overview: list[CourseOverview] = []
    for course in index.canonical_courses:
        if course.archived:
            continue
        course_tasks = tasks_by_course.get(course.id, [])
        course_sessions = sessions_by_course.get(course.id, [])

        grades = [
            _grade_pct(t.score, t.points_possible)
            for t in course_tasks
            if t.score is not None and t.points_possible
        ]
        grades = [g for g in grades if g is not None]

        overview.append(
            CourseOverview(
                course_id=course.id,
                course_name=index.display_name.get(course.id, course.name),
                avg_grade_pct=round(sum(grades) / len(grades), 1) if grades else None,
                graded_task_count=len(grades),
                study_hours_this_week=round(_session_hours(course_sessions, now, since=week_start), 2),
                study_hours_total=round(_session_hours(course_sessions, now), 2),
                tasks_pending=sum(1 for t in course_tasks if t.status == "pending"),
                tasks_completed=sum(1 for t in course_tasks if t.status == "done"),
            )
        )
    return overview


def grade_trends(session: Session, course_id: Optional[int] = None) -> list[GradeTrendPoint]:
    query = select(Task).where(Task.score.is_not(None), Task.points_possible.is_not(None), Task.graded_at.is_not(None))
    if course_id is not None:
        # A canonical course id may have other platforms' rows folded into
        # it - their tasks still carry the platform-specific course_id, so
        # the filter has to cover every member of the group, not just the
        # canonical id itself.
        index = build_course_index(session)
        query = query.where(Task.course_id.in_(index.members.get(course_id, [course_id])))
    tasks = session.exec(query.order_by(Task.graded_at)).all()
    points = []
    for t in tasks:
        pct = _grade_pct(t.score, t.points_possible)
        if pct is None:
            continue
        points.append(GradeTrendPoint(task_id=t.id, task_title=t.title, graded_at=t.graded_at, grade_pct=pct))
    return points


def study_vs_grade(session: Session) -> list[StudyVsGradePoint]:
    index = build_course_index(session)
    tasks = session.exec(select(Task)).all()
    study_sessions = session.exec(select(StudySession)).all()

    tasks_by_course = _canonicalize(tasks, lambda t: t.course_id, index)
    sessions_by_course = _canonicalize(study_sessions, lambda s: s.course_id, index)

    now = _now()
    points: list[StudyVsGradePoint] = []
    for course in index.canonical_courses:
        if course.archived:
            continue
        course_sessions = sessions_by_course.get(course.id, [])
        course_tasks = tasks_by_course.get(course.id, [])

        grades = [g for g in (_grade_pct(t.score, t.points_possible) for t in course_tasks) if g is not None]

        if course_sessions:
            first_started = min(s.started_at for s in course_sessions)
            weeks_tracked = max((now - first_started).total_seconds() / (7 * 86400), 1 / 7)
            avg_weekly_hours = _session_hours(course_sessions, now) / weeks_tracked
        else:
            avg_weekly_hours = 0.0

        points.append(
            StudyVsGradePoint(
                course_id=course.id,
                course_name=index.display_name.get(course.id, course.name),
                avg_weekly_study_hours=round(avg_weekly_hours, 2),
                avg_grade_pct=round(sum(grades) / len(grades), 1) if grades else None,
            )
        )
    return points


def early_start_vs_grade(session: Session) -> list[EarlyStartVsGradePoint]:
    index = build_course_index(session)
    tasks = session.exec(
        select(Task).where(
            Task.started_at.is_not(None),
            Task.due_at.is_not(None),
            Task.score.is_not(None),
            Task.points_possible.is_not(None),
        )
    ).all()

    points = []
    for t in tasks:
        pct = _grade_pct(t.score, t.points_possible)
        if pct is None:
            continue
        days_before_due = (t.due_at - t.started_at).total_seconds() / 86400
        canonical_cid = index.canonical_id.get(t.course_id) if t.course_id is not None else None
        points.append(
            EarlyStartVsGradePoint(
                task_id=t.id,
                task_title=t.title,
                course_id=canonical_cid,
                course_name=index.display_name.get(canonical_cid) if canonical_cid is not None else None,
                days_before_due=round(days_before_due, 2),
                grade_pct=pct,
            )
        )
    return points


def weekly_productivity(session: Session, weeks: int = 8) -> list[WeeklyProductivityPoint]:
    now = _now()
    current_week_start = _week_start(now)
    week_starts = [current_week_start - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]

    study_sessions = session.exec(select(StudySession)).all()
    tasks = session.exec(select(Task).where(Task.status == "done")).all()

    points = []
    for i, ws in enumerate(week_starts):
        we = ws + timedelta(weeks=1)
        hours = sum(
            (min(s.ended_at or now, we) - max(s.started_at, ws)).total_seconds() / SECONDS_PER_HOUR
            for s in study_sessions
            if s.started_at < we and (s.ended_at or now) > ws
        )
        completed = sum(1 for t in tasks if t.updated_at is not None and ws <= t.updated_at < we)
        points.append(WeeklyProductivityPoint(week_start=ws, study_hours=round(max(hours, 0.0), 2), tasks_completed=completed))
    return points
