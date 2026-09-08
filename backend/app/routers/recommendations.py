from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app import recommendation_service
from app.config import get_settings
from app.db import get_session
from app.llm_client import LLMNotConfiguredError, LLMResponseError
from app.schemas import RecommendationRead

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationRead)
def get_latest_recommendation(session: Session = Depends(get_session)):
    return recommendation_service.latest_read(session)


@router.post("/generate", response_model=RecommendationRead)
def generate_recommendation(session: Session = Depends(get_session)):
    if get_settings().demo_mode:
        # A shared public instance triggering real Anthropic API calls on
        # demand would be an open-ended cost anyone could run up - the demo
        # ships with a pre-written example instead (see app.demo) and resets
        # on its own schedule rather than on request.
        raise HTTPException(
            status_code=403,
            detail="This is a public demo - recommendations are pre-generated, not made on demand here.",
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
