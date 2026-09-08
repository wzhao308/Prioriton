from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app import recommendation_service
from app.config import get_settings
from app.db import get_session
from app.llm_client import LLMNotConfiguredError, LLMResponseError
from app.models import Recommendation
from app.schemas import RecommendationRead

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationRead)
def get_latest_recommendation(session: Session = Depends(get_session)):
    return recommendation_service.latest_read(session)


def _demo_cooldown_remaining_minutes(session: Session) -> Optional[float]:
    """Real generation is still a real, billable Anthropic call in demo mode
    - not blocked outright (the whole point is letting visitors see it
    actually work), just rate-limited so one shared public instance can't
    have its API budget run up by repeated clicks. Cooldown is measured off
    the most recent Recommendation row for anyone - including the one
    app.demo seeds on every reset - so a fresh reset starts a fresh cooldown
    window rather than allowing an immediate burst."""
    latest = session.exec(select(Recommendation).order_by(Recommendation.generated_at.desc())).first()
    if latest is None:
        return None
    generated_at = latest.generated_at
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    elapsed_minutes = (datetime.now(timezone.utc) - generated_at).total_seconds() / 60
    remaining = get_settings().demo_recommendation_cooldown_minutes - elapsed_minutes
    return remaining if remaining > 0 else None


@router.post("/generate", response_model=RecommendationRead)
def generate_recommendation(session: Session = Depends(get_session)):
    if get_settings().demo_mode:
        remaining = _demo_cooldown_remaining_minutes(session)
        if remaining is not None:
            raise HTTPException(
                status_code=429,
                detail=f"This public demo rate-limits live AI generation - try again in "
                f"about {max(1, round(remaining))} minute(s).",
            )

    eligible, days_until = recommendation_service.is_eligible(session)
    if not eligible:
        detail = (
            "Not enough tracked activity yet - check back in "
            f"{days_until} day(s)."
            if days_until is not None
            else "No activity tracked yet - sync an assignment source or start a study session first."
        )
        raise HTTPException(status_code=409, detail=detail)
    try:
        recommendation_service.generate(session)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return recommendation_service.latest_read(session)
