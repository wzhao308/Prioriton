from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ConnectCanvasRequest(BaseModel):
    base_url: str = Field(description="e.g. https://yourschool.instructure.com")
    token: str = Field(description="Canvas personal access token")


class IntegrationRead(BaseModel):
    id: int
    type: str
    base_url: Optional[str]
    status: str
    last_error: Optional[str]
    last_synced_at: Optional[datetime]


class CourseRead(BaseModel):
    id: int
    source: str
    external_id: str
    name: str
    term: Optional[str]
    code: Optional[str] = None
    archived: bool = False
    # display_name is what every UI should render - it's `code` instead of
    # this row's own `name` when this course is the canonical row for a
    # class synced on more than one platform (see app.course_merge), so
    # neither platform's own phrasing wins arbitrarily. `sources` lists every
    # platform folded into it (len > 1 only for a merged course).
    display_name: str = ""
    sources: list[str] = []


class CourseCreate(BaseModel):
    name: str
    term: Optional[str] = None


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    term: Optional[str] = None
    archived: Optional[bool] = None


class TaskRead(BaseModel):
    id: int
    source: str
    course_id: Optional[int]
    title: str
    type: str
    due_at: Optional[datetime]
    late_due_at: Optional[datetime] = None
    url: Optional[str]
    status: str
    points_possible: Optional[float] = None
    score: Optional[float] = None
    graded_at: Optional[datetime] = None
    started_at: Optional[datetime] = None


class TaskUpdate(BaseModel):
    status: str  # pending | done | dismissed


class SyncResult(BaseModel):
    integrations_synced: int
    courses_upserted: int
    tasks_upserted: int
    tasks_auto_dismissed: int = 0
    courses_archive_changed: int = 0
    courses_merged: int = 0
    errors: list[str]


class ReminderRead(BaseModel):
    id: int
    task_id: int
    lead_minutes: int
    remind_at: datetime
    status: str
    task_title: str
    task_url: Optional[str]
    task_due_at: Optional[datetime]
    task_source: str


class ReminderUpdate(BaseModel):
    status: str  # pending | dismissed


class SettingsRead(BaseModel):
    reminder_lead_minutes: list[int]


class SettingsUpdate(BaseModel):
    reminder_lead_minutes: list[int]


# --- Study Time Tracker ---


class StudySessionRead(BaseModel):
    id: int
    course_id: int
    course_name: str
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]


class StudySessionStart(BaseModel):
    course_id: int


# --- Analytics Dashboard ---


class CourseOverview(BaseModel):
    course_id: int
    course_name: str
    avg_grade_pct: Optional[float]
    graded_task_count: int
    study_hours_this_week: float
    study_hours_total: float
    tasks_pending: int
    tasks_completed: int


class GradeTrendPoint(BaseModel):
    task_id: int
    task_title: str
    graded_at: datetime
    grade_pct: float


class StudyVsGradePoint(BaseModel):
    course_id: int
    course_name: str
    avg_weekly_study_hours: float
    avg_grade_pct: Optional[float]


class EarlyStartVsGradePoint(BaseModel):
    task_id: int
    task_title: str
    course_id: Optional[int]
    course_name: Optional[str]
    days_before_due: float
    grade_pct: float


class WeeklyProductivityPoint(BaseModel):
    week_start: datetime
    study_hours: float
    tasks_completed: int


# --- AI Recommendation System ---


class RecommendationItem(BaseModel):
    course_id: Optional[int] = None
    course_name: Optional[str] = None
    kind: str  # "study_time" | "grade" | "assignment_start" | "productivity" | "general"
    message: str
    priority: int = 2  # 1 = high, 2 = normal, 3 = low


class RecommendationRead(BaseModel):
    id: Optional[int] = None
    generated_at: Optional[datetime] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    items: list[RecommendationItem] = []
    eligible: bool
    days_until_eligible: Optional[float] = None
