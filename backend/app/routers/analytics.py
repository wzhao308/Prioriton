from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import analytics_service
from app.db import get_session
from app.schemas import (
    CourseOverview,
    EarlyStartVsGradePoint,
    GradeTrendPoint,
    StudyVsGradePoint,
    WeeklyProductivityPoint,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=list[CourseOverview])
def overview(session: Session = Depends(get_session)):
    return analytics_service.course_overview(session)


@router.get("/grade-trends", response_model=list[GradeTrendPoint])
def grade_trends(course_id: Optional[int] = None, session: Session = Depends(get_session)):
    return analytics_service.grade_trends(session, course_id)


@router.get("/study-vs-grade", response_model=list[StudyVsGradePoint])
def study_vs_grade(session: Session = Depends(get_session)):
    return analytics_service.study_vs_grade(session)


@router.get("/early-start-vs-grade", response_model=list[EarlyStartVsGradePoint])
def early_start_vs_grade(session: Session = Depends(get_session)):
    return analytics_service.early_start_vs_grade(session)


@router.get("/weekly-productivity", response_model=list[WeeklyProductivityPoint])
def weekly_productivity(weeks: int = 8, session: Session = Depends(get_session)):
    weeks = max(1, min(weeks, 52))
    return analytics_service.weekly_productivity(session, weeks)
