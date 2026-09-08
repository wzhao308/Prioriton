"""Database models.

Single-user for now (one `User` row), but the shape doesn't preclude adding
multi-user support later. `Course`, `Task`, `Integration`, `Reminder` are
ported from ManaPeer's sync engine (see app.adapters / app.sync_service) -
that's what powers the Assignment Tracker (Home, Calendar, Courses).
`StudySession` and `Recommendation` are Prioriton-specific.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

# Default reminder lead times, in minutes before a task's due date: 3 days, 1 day, 3 hours.
DEFAULT_REMINDER_LEAD_MINUTES = [4320, 1440, 180]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)


class Integration(SQLModel, table=True):
    """One connected assignment-source account (Canvas, Gradescope, PrairieLearn)."""

    __table_args__ = (UniqueConstraint("type", name="uq_integration_type"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    type: str  # "canvas" | "gradescope" | "prairielearn"
    base_url: Optional[str] = None
    encrypted_credentials: str
    status: str = "pending"  # pending | connected | error
    last_error: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)


class Course(SQLModel, table=True):
    """A class/subject. Either synced from a platform (source = "canvas" /
    "gradescope" / "prairielearn") or added by hand (source = "manual") so the
    Study Timer and manual grade entry work fully without any integration
    connected. Study sessions, tasks, and grades all join on `course_id`,
    which is what lets Analytics correlate study time against grades per
    class regardless of where the course came from.
    """

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_course_source_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str
    external_id: str
    name: str
    term: Optional[str] = None
    # Best-effort "subject + number" course code (e.g. "PHYS 213"), used to
    # recognize the same real class tracked on two different platforms - see
    # app.adapters.base.extract_course_code.
    code: Optional[str] = None
    archived: bool = False
    # Set when this row is the same real class as another course, tracked on
    # a different platform (e.g. Gradescope's own row for a class also
    # synced via PrairieLearn) - points at whichever row is the canonical
    # one for that class. None for a standalone/canonical course. Recomputed
    # every sync - see app.course_merge.apply_course_merging. A course with
    # this set is filtered out of every list/aggregation; only the canonical
    # row is ever shown, so the same real class never appears twice.
    merged_into_id: Optional[int] = Field(default=None, foreign_key="course.id")
    created_at: datetime = Field(default_factory=_utcnow)


class Task(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_task_source_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str
    external_id: str
    course_id: Optional[int] = Field(default=None, foreign_key="course.id")
    title: str
    type: str = "assignment"  # assignment | quiz | exam | project
    due_at: Optional[datetime] = None
    # Hard late-submission cutoff, if the platform offers one beyond due_at
    # (Gradescope's "Late Due Date:"). None everywhere it doesn't apply.
    late_due_at: Optional[datetime] = None
    url: Optional[str] = None
    status: str = "pending"  # pending | done | dismissed

    # Grade fields - populated for Canvas via `include[]=submission` on the
    # assignments call (see app.adapters.canvas). None until graded, and
    # always None for platforms that don't expose grades this way yet.
    points_possible: Optional[float] = None
    score: Optional[float] = None
    graded_at: Optional[datetime] = None

    # Set manually by the student via "Start working on this" - Canvas/
    # Gradescope/PrairieLearn have no concept of this, so it can only ever be
    # local, student-reported data. Feeds the early-start-vs-grade analytic.
    started_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Reminder(SQLModel, table=True):
    """One lead-time alert for a task (e.g. '3 hours before Homework 2 is due').

    Regenerated on every sync from the task's current due_at and the current
    reminder-lead-time settings - see `app.reminders.sync_reminders_for_task`.
    """

    __table_args__ = (UniqueConstraint("task_id", "lead_minutes", name="uq_reminder_task_lead"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id")
    lead_minutes: int
    remind_at: datetime
    status: str = "pending"  # pending | dismissed
    created_at: datetime = Field(default_factory=_utcnow)


class StudySession(SQLModel, table=True):
    """One timed study block for a course, started/stopped from the Study
    Timer. `ended_at`/`duration_seconds` stay null while the timer is
    actively running - see app.routers.study_sessions."""

    id: Optional[int] = Field(default=None, primary_key=True)
    course_id: int = Field(foreign_key="course.id")
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    created_at: datetime = Field(default_factory=_utcnow)


class Recommendation(SQLModel, table=True):
    """One AI-generated batch of study recommendations. `items_json` is a
    JSON-encoded list of {course_id, course_name, kind, message, priority}
    dicts - see app.recommendation_service."""

    id: Optional[int] = Field(default=None, primary_key=True)
    generated_at: datetime = Field(default_factory=_utcnow)
    period_start: datetime
    period_end: datetime
    summary_json: str
    items_json: str
    model: str


class AppSettings(SQLModel, table=True):
    """Single-row table of app-wide settings (single-user app)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    reminder_lead_minutes_json: str = Field(
        default_factory=lambda: json.dumps(DEFAULT_REMINDER_LEAD_MINUTES)
    )
    # Stamped the first time any StudySession or synced Task is created -
    # the AI Recommendation System stays quiet until 7+ days past this, so
    # it has enough real activity to say something useful. See
    # app.recommendation_service.is_eligible.
    data_collection_started_at: Optional[datetime] = None

    @property
    def reminder_lead_minutes(self) -> list[int]:
        return json.loads(self.reminder_lead_minutes_json)

    @reminder_lead_minutes.setter
    def reminder_lead_minutes(self, value: list[int]) -> None:
        self.reminder_lead_minutes_json = json.dumps(value)
