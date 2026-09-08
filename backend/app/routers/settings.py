from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app import reminders
from app.db import get_session
from app.schemas import SettingsRead, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsRead)
def get_settings_endpoint(session: Session = Depends(get_session)):
    settings = reminders.get_settings(session)
    session.commit()
    return SettingsRead(reminder_lead_minutes=settings.reminder_lead_minutes)


@router.put("", response_model=SettingsRead)
def update_settings(body: SettingsUpdate, session: Session = Depends(get_session)):
    if not body.reminder_lead_minutes:
        raise HTTPException(status_code=422, detail="reminder_lead_minutes must not be empty")
    if any(m <= 0 for m in body.reminder_lead_minutes):
        raise HTTPException(status_code=422, detail="lead times must be positive minutes")
    settings = reminders.set_reminder_lead_minutes(session, body.reminder_lead_minutes)
    return SettingsRead(reminder_lead_minutes=settings.reminder_lead_minutes)
