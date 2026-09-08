from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.activity import stamp_data_collection_start
from app.course_merge import build_course_index
from app.db import get_session
from app.models import Course, StudySession
from app.schemas import StudySessionRead, StudySessionStart

router = APIRouter(prefix="/study-sessions", tags=["study-sessions"])


def _to_read(s: StudySession, course_name: str) -> StudySessionRead:
    return StudySessionRead(
        id=s.id,
        course_id=s.course_id,
        course_name=course_name,
        started_at=s.started_at,
        ended_at=s.ended_at,
        duration_seconds=s.duration_seconds,
    )


@router.get("", response_model=list[StudySessionRead])
def list_study_sessions(
    course_id: Optional[int] = None,
    since: Optional[datetime] = None,
    session: Session = Depends(get_session),
):
    index = build_course_index(session)
    query = select(StudySession)
    if course_id is not None:
        # `course_id` here is a canonical id (that's all the Study Timer's
        # picker ever offers) - broaden to every platform-specific row
        # folded into it, same reasoning as analytics_service.grade_trends.
        query = query.where(StudySession.course_id.in_(index.members.get(course_id, [course_id])))
    if since is not None:
        query = query.where(StudySession.started_at >= since)
    rows = session.exec(query.order_by(StudySession.started_at.desc())).all()
    return [
        _to_read(s, index.display_name.get(index.canonical_id.get(s.course_id, s.course_id), "Unknown course"))
        for s in rows
    ]


@router.get("/active", response_model=Optional[StudySessionRead])
def active_study_session(session: Session = Depends(get_session)):
    """The currently-running session, if any - lets the Study Timer resume
    its live elapsed-time display correctly after a page refresh instead of
    losing track of an in-progress timer."""
    row = session.exec(select(StudySession).where(StudySession.ended_at.is_(None))).first()
    if row is None:
        return None
    index = build_course_index(session)
    name = index.display_name.get(index.canonical_id.get(row.course_id, row.course_id), "Unknown course")
    return _to_read(row, name)


@router.post("/start", response_model=StudySessionRead)
def start_study_session(body: StudySessionStart, session: Session = Depends(get_session)):
    running = session.exec(select(StudySession).where(StudySession.ended_at.is_(None))).first()
    if running is not None:
        raise HTTPException(
            status_code=409,
            detail="A study session is already running. Stop it before starting another.",
        )
    course = session.get(Course, body.course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.merged_into_id is not None:
        # The Study Timer's picker only ever lists canonical courses (see
        # GET /courses), so this shouldn't be reachable in normal use - but
        # guard it anyway rather than silently recording time against a
        # course id that analytics will just re-canonicalize elsewhere.
        raise HTTPException(
            status_code=409,
            detail="This class was merged with another platform's version of it - use that one instead.",
        )

    study_session = StudySession(course_id=body.course_id, started_at=datetime.now(timezone.utc))
    session.add(study_session)
    stamp_data_collection_start(session)
    session.commit()
    session.refresh(study_session)
    return _to_read(study_session, course.name)


@router.post("/{session_id}/stop", response_model=StudySessionRead)
def stop_study_session(session_id: int, session: Session = Depends(get_session)):
    study_session = session.get(StudySession, session_id)
    if not study_session:
        raise HTTPException(status_code=404, detail="Study session not found")
    if study_session.ended_at is not None:
        raise HTTPException(status_code=409, detail="This study session was already stopped.")

    now = datetime.now(timezone.utc)
    study_session.ended_at = now
    study_session.duration_seconds = int((now - study_session.started_at.replace(tzinfo=timezone.utc)).total_seconds())
    session.add(study_session)
    session.commit()
    session.refresh(study_session)
    index = build_course_index(session)
    name = index.display_name.get(index.canonical_id.get(study_session.course_id, study_session.course_id), "Unknown course")
    return _to_read(study_session, name)
