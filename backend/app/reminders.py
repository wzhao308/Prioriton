"""Reminder generation and settings.

Reminders are pre-computed rows (one per task per configured lead time) with
a `remind_at` timestamp. There's no background "fire" job - the frontend just
asks "which reminders have remind_at in the past and are still pending?" on a
short poll interval, which keeps this in-app-only design simple (no
websockets, no push).
"""
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.models import AppSettings, Reminder, Task


def get_settings(session: Session) -> AppSettings:
    settings = session.exec(select(AppSettings)).first()
    if settings is None:
        settings = AppSettings()
        session.add(settings)
        session.flush()
    return settings


def set_reminder_lead_minutes(session: Session, lead_minutes: list[int]) -> AppSettings:
    settings = get_settings(session)
    settings.reminder_lead_minutes = sorted(set(lead_minutes), reverse=True)
    session.add(settings)
    session.flush()

    # Immediately re-derive reminders for every task against the new lead times,
    # rather than waiting for the next sync.
    for task in session.exec(select(Task)):
        sync_reminders_for_task(session, task, settings.reminder_lead_minutes)
    session.commit()
    session.refresh(settings)
    return settings


def sync_reminders_for_task(session: Session, task: Task, lead_minutes_list: list[int]) -> None:
    """Create/update/remove this task's Reminder rows to match its current
    due_at and the currently configured lead times. Called after every task
    upsert during sync, and whenever lead-time settings change.
    """
    existing = {
        r.lead_minutes: r
        for r in session.exec(select(Reminder).where(Reminder.task_id == task.id))
    }
    valid_leads = set(lead_minutes_list)

    # Drop reminders for lead times no longer configured.
    for lead, reminder in list(existing.items()):
        if lead not in valid_leads:
            session.delete(reminder)
            del existing[lead]

    if task.due_at is None:
        return

    # Don't generate reminders the first time a task is ever seen if its due
    # date has already passed - every configured lead time would already be
    # simultaneously "active" (backlog noise from importing old assignments,
    # e.g. a past semester), not a useful nudge. A task already being tracked
    # (it already has reminder rows) keeps updating normally even once its due
    # date has since passed - this only guards a task's very first sync.
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)  # matches due_at's naive-UTC storage
    if not existing and task.due_at < now_naive:
        return

    for lead in lead_minutes_list:
        remind_at = task.due_at - timedelta(minutes=lead)
        reminder = existing.get(lead)
        if reminder is None:
            session.add(Reminder(task_id=task.id, lead_minutes=lead, remind_at=remind_at, status="pending"))
        elif reminder.status == "pending":
            # Keep already-dismissed reminders dismissed even if the due date shifts a bit;
            # only slide the still-pending ones to the task's current due date.
            reminder.remind_at = remind_at
            session.add(reminder)
