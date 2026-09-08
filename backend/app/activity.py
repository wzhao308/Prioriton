"""Tracks when real activity first started, for the AI Recommendation
System's 7-day eligibility gate (see app.recommendation_service.is_eligible).
Called from both the sync engine (first task ever synced) and the Study
Timer (first study session ever started) - whichever happens first starts
the clock.
"""
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import AppSettings


def stamp_data_collection_start(session: Session) -> None:
    settings = session.exec(select(AppSettings)).first()
    if settings is None:
        settings = AppSettings()
        session.add(settings)
        session.flush()
    if settings.data_collection_started_at is None:
        settings.data_collection_started_at = datetime.now(timezone.utc)
        session.add(settings)
