from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.db import get_session
from app.models import Reminder, Task
from app.schemas import ReminderRead, ReminderUpdate

router = APIRouter(prefix="/reminders", tags=["reminders"])

VALID_STATUSES = {"pending", "dismissed"}


def _to_read(reminder: Reminder, task: Task) -> ReminderRead:
    return ReminderRead(
        id=reminder.id,
        task_id=reminder.task_id,
        lead_minutes=reminder.lead_minutes,
        remind_at=reminder.remind_at,
        status=reminder.status,
        task_title=task.title,
        task_url=task.url,
        task_due_at=task.due_at,
        task_source=task.source,
    )


def _collapse_superseded(session: Session) -> list[tuple[Reminder, Task]]:
    """If a task's due date is close enough that multiple lead-time thresholds
    have elapsed at once (e.g. a task due in 2 hours makes the '3 days before'
    AND '1 day before' AND '3 hours before' reminders all technically past
    due), only the most urgent one is worth showing - the rest are redundant
    noise for the same task. Those redundant ones are auto-dismissed as
    "superseded" so they don't clutter the list or reappear later.
    """
    query = (
        select(Reminder, Task)
        .join(Task, Reminder.task_id == Task.id)
        .where(
            Reminder.status == "pending",
            Reminder.remind_at <= datetime.now(timezone.utc),
            Task.status == "pending",
        )
    )
    rows = session.exec(query).all()

    most_urgent_by_task: dict[int, tuple[Reminder, Task]] = {}
    for reminder, task in rows:
        current = most_urgent_by_task.get(reminder.task_id)
        if current is None or reminder.lead_minutes < current[0].lead_minutes:
            most_urgent_by_task[reminder.task_id] = (reminder, task)

    winners = set(id(r) for r, _ in most_urgent_by_task.values())
    for reminder, _task in rows:
        if id(reminder) not in winners:
            reminder.status = "dismissed"
            session.add(reminder)
    session.commit()

    return sorted(most_urgent_by_task.values(), key=lambda pair: pair[0].remind_at)


@router.get("", response_model=list[ReminderRead])
def list_reminders(
    active_only: bool = Query(
        default=True,
        description="Only the single most urgent reminder per task whose remind_at has "
        "passed, is still pending, and whose task is still pending (not done/dismissed).",
    ),
    session: Session = Depends(get_session),
):
    if active_only:
        return [_to_read(reminder, task) for reminder, task in _collapse_superseded(session)]
    rows = session.exec(select(Reminder, Task).join(Task, Reminder.task_id == Task.id).order_by(Reminder.remind_at)).all()
    return [_to_read(reminder, task) for reminder, task in rows]


@router.patch("/{reminder_id}", response_model=ReminderRead)
def update_reminder(reminder_id: int, body: ReminderUpdate, session: Session = Depends(get_session)):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(VALID_STATUSES)}")
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    reminder.status = body.status
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    task = session.get(Task, reminder.task_id)
    return _to_read(reminder, task)


@router.post("/dismiss-active", response_model=list[int])
def dismiss_active(session: Session = Depends(get_session)):
    """Dismiss every currently-active (i.e. currently shown) reminder in one shot
    ("clear notifications")."""
    active = _collapse_superseded(session)  # also dismisses any now-redundant duplicates
    ids = []
    for reminder, _task in active:
        reminder.status = "dismissed"
        session.add(reminder)
        ids.append(reminder.id)
    session.commit()
    return ids
