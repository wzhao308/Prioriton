"""Public-demo mode: seeds realistic-looking sample data and periodically
resets it, so a shared, publicly-reachable deployment stays interactive and
self-heals from visitors clicking around. "Connecting" Canvas/Gradescope/
PrairieLearn is simulated (see `simulate_connect` below) rather than either
fully working or fully blocked - a stranger's real account has no business
landing on a public shared instance, but the connect flow itself, and what a
successful sync looks like, is worth actually being able to see. Live AI
recommendation generation is real (a real Anthropic call), just rate-limited
- see the `demo_mode` checks in app.routers.integrations and
app.routers.recommendations.

`seed_demo_data()` is also used standalone by scripts/seed_demo_data.py for
trying the app locally with sample data - that path is additive and never
wipes anything. `reset_demo()` (wipe + reseed) is demo-mode-only.
"""
import json
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlmodel import Session, delete, select

from app.models import (
    AppSettings,
    Course,
    Integration,
    Recommendation,
    Reminder,
    StudySession,
    Task,
)

DEMO_COURSES = [
    {"name": "MATH 241 - Calculus III", "avg_hours_per_week": 2.0, "grade_center": 78},
    {"name": "CS 225 - Data Structures", "avg_hours_per_week": 6.5, "grade_center": 91},
    {"name": "ECON 302 - Microeconomics", "avg_hours_per_week": 3.5, "grade_center": 85},
    {"name": "ENGL 100 - Composition", "avg_hours_per_week": 1.5, "grade_center": 88},
]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def wipe_all(session: Session) -> None:
    """Deletes every row from every table - only ever called in demo mode
    (see app.scheduler's demo-reset job), never on a real local/VPS
    deployment's data."""
    for model in (Reminder, Recommendation, Task, StudySession, Course, Integration, AppSettings):
        session.exec(delete(model))
    session.commit()


def seed_demo_data(session: Session, random_seed: int = 7) -> dict:
    """Seeds ~2 weeks of sample courses, graded tasks (varying start-lead-
    time and scores), and study sessions - additive, doesn't touch anything
    that's already there. Also backdates `data_collection_started_at` so
    Recommendations is immediately eligible. Returns the created courses
    keyed by name, for callers (like _seed_demo_recommendation) that need them."""
    rng = random.Random(random_seed)
    now = _now()

    settings = session.exec(select(AppSettings)).first()
    if settings is None:
        settings = AppSettings()
    settings.data_collection_started_at = now - timedelta(days=8)
    session.add(settings)
    session.commit()

    courses: dict[str, Course] = {}
    for spec in DEMO_COURSES:
        course = Course(source="manual", external_id=str(uuid4()), name=spec["name"], term="Fall 2026")
        session.add(course)
        session.flush()
        courses[spec["name"]] = course
    session.commit()

    # Study sessions: past 10 days, a few per course per day, biased by each
    # course's target weekly hours so the study-vs-grade chart shows a real
    # spread.
    for spec in DEMO_COURSES:
        course = courses[spec["name"]]
        for day_offset in range(10, 0, -1):
            if rng.random() > 0.6:
                continue  # not every course gets studied every day
            day = now - timedelta(days=day_offset)
            session_hours = max(0.25, rng.gauss(spec["avg_hours_per_week"] / 7, 0.3))
            start = day.replace(hour=rng.randint(9, 20), minute=rng.choice([0, 15, 30, 45]))
            end = start + timedelta(hours=session_hours)
            session.add(
                StudySession(
                    course_id=course.id,
                    started_at=start,
                    ended_at=end,
                    duration_seconds=int(session_hours * 3600),
                )
            )
    session.commit()

    # Tasks: a mix of completed-and-graded (varying how early they were
    # started) and still-pending assignments due in the next couple weeks.
    task_titles = ["Homework", "Problem Set", "Project Milestone", "Quiz", "Essay Draft", "Lab Report"]
    for spec in DEMO_COURSES:
        course = courses[spec["name"]]
        for i in range(6):
            title = f"{rng.choice(task_titles)} {i + 1}"
            points_possible = rng.choice([20, 50, 100])
            if i < 4:
                # Completed and graded, in the past, with a randomized
                # start-lead-time that skews grade (started earlier -> a
                # somewhat better grade, with noise) so the early-start-vs-
                # grade chart has a real relationship to show.
                due_at = now - timedelta(days=rng.randint(1, 9))
                lead_days = rng.choice([0.2, 0.5, 1, 2, 3, 5])
                started_at = due_at - timedelta(days=lead_days)
                grade_center = spec["grade_center"] + min(lead_days * 1.5, 8)
                score_pct = max(55, min(100, rng.gauss(grade_center, 6)))
                task = Task(
                    source="manual",
                    external_id=str(uuid4()),
                    course_id=course.id,
                    title=title,
                    type="assignment",
                    due_at=due_at,
                    status="done",
                    points_possible=points_possible,
                    score=round(points_possible * score_pct / 100, 1),
                    graded_at=due_at + timedelta(days=1),
                    started_at=started_at,
                    updated_at=due_at + timedelta(hours=rng.randint(1, 20)),
                )
            else:
                # Still pending, due in the next 2 weeks - some already
                # started, some not, so Home/Recommendations have something
                # current to react to.
                due_at = now + timedelta(days=rng.randint(1, 14))
                started = rng.random() < 0.4
                task = Task(
                    source="manual",
                    external_id=str(uuid4()),
                    course_id=course.id,
                    title=title,
                    type="assignment",
                    due_at=due_at,
                    status="pending",
                    points_possible=points_possible,
                    started_at=(now - timedelta(days=1)) if started else None,
                )
            session.add(task)
    session.commit()

    return courses


# Hand-written, not LLM-generated - grounded in the exact numbers
# seed_demo_data() above produces, in the same voice/format the real AI
# Recommendation System uses (see app.llm_client.SYSTEM_PROMPT). This is what
# lets the Recommendations page show real-looking content in demo mode
# without ever making a live (and costly, since it's a shared public
# instance) Anthropic API call.
_DEMO_RECOMMENDATION_ITEMS = [
    {
        "course_name": "MATH 241 - Calculus III",
        "kind": "study_time",
        "message": "You're spending noticeably less weekly time on MATH 241 than on CS 225 - "
        "consider shifting an hour or two over before the next problem set is due.",
        "priority": 1,
    },
    {
        "course_name": "CS 225 - Data Structures",
        "kind": "grade",
        "message": "Your CS 225 average is the strongest of your four courses right now - whatever "
        "you're doing there (consistent study sessions, starting assignments early) is working.",
        "priority": 3,
    },
    {
        "course_name": None,
        "kind": "assignment_start",
        "message": "Across your graded assignments, the ones you started 2+ days before the due "
        "date scored meaningfully higher on average than the ones started the same day - "
        "starting early is paying off, keep it up.",
        "priority": 2,
    },
    {
        "course_name": "ENGL 100 - Composition",
        "kind": "productivity",
        "message": "ENGL 100 has the lightest weekly time commitment of your courses - a good one "
        "to knock out early in the week while you have momentum.",
        "priority": 2,
    },
]


def _seed_demo_recommendation(session: Session) -> None:
    now = _now()
    period_start = now - timedelta(days=7)
    session.add(
        Recommendation(
            generated_at=now,
            period_start=period_start,
            period_end=now,
            summary_json=json.dumps({"note": "hand-written demo example - see app/demo.py"}),
            items_json=json.dumps(_DEMO_RECOMMENDATION_ITEMS),
            model="demo-sample",
        )
    )
    session.commit()


def reset_demo(session: Session) -> None:
    """Wipe everything and reseed fresh sample data + one example
    recommendation. Only ever called in demo mode (startup, and the
    recurring demo-reset job in app.scheduler)."""
    wipe_all(session)
    seed_demo_data(session)
    _seed_demo_recommendation(session)


# One small "just synced" fixture per platform - what simulate_connect() drops
# in, so a demo visitor sees new, platform-labeled content actually appear
# right after "connecting", the same way a real first sync feels.
_SIMULATED_SYNC_FIXTURES = {
    "canvas": {
        "course_name": "PHYS 214 - Quantum Physics",
        "code": "PHYS 214",
        "tasks": ["Problem Set 3", "Midterm Review Questions", "Lab Report 2"],
    },
    "gradescope": {
        "course_name": "CS 341 - System Programming",
        "code": "CS 341",
        "tasks": ["MP3: Shell", "MP4: Malloc", "Written HW2"],
    },
    "prairielearn": {
        "course_name": "STAT 400 - Statistics",
        "code": "STAT 400",
        "tasks": ["HW5", "Quiz 4", "Practice Exam"],
    },
}


def simulate_connect(platform: str, session: Session) -> Integration:
    """Demo mode's stand-in for a real Canvas/Gradescope/PrairieLearn
    connection. Never touches whatever the visitor actually submitted (a
    Canvas form's token, say) - it isn't validated, used, or stored, full
    stop. Gradescope/PrairieLearn's real flow needs a headed browser to
    complete SSO, which the lightweight demo image never has (see
    Dockerfile.demo vs. the real backend/Dockerfile's Xvfb/noVNC chain), so
    this is also the only way those two can be shown here at all.

    Marks the integration connected and drops in one small fixture course +
    a few tasks tagged with that platform's `source`, so the connect flow
    has something real to point at - Courses/Calendar/Analytics all pick it
    up exactly like a real sync's results, because it's the same Course/Task
    rows a real one would produce. Idempotent per platform - connecting
    twice doesn't duplicate the fixture data, just refreshes last_synced_at.
    """
    integration = session.exec(select(Integration).where(Integration.type == platform)).first()
    if integration is None:
        integration = Integration(type=platform, encrypted_credentials="demo-simulated")
    integration.status = "connected"
    integration.last_error = None
    integration.last_synced_at = _now()
    session.add(integration)

    fixture = _SIMULATED_SYNC_FIXTURES[platform]
    external_id = f"demo-{platform}"
    course = session.exec(
        select(Course).where(Course.source == platform, Course.external_id == external_id)
    ).first()
    if course is None:
        course = Course(
            source=platform,
            external_id=external_id,
            name=fixture["course_name"],
            term="Fall 2026",
            code=fixture["code"],
        )
        session.add(course)
        session.flush()
        now = _now()
        for i, title in enumerate(fixture["tasks"]):
            session.add(
                Task(
                    source=platform,
                    external_id=f"{external_id}-t{i}",
                    course_id=course.id,
                    title=title,
                    type="assignment",
                    due_at=now + timedelta(days=3 + i * 4),
                    status="pending",
                )
            )

    session.commit()
    session.refresh(integration)
    return integration
