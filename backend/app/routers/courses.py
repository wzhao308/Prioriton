from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.course_merge import build_course_index
from app.db import get_session
from app.models import Course, Reminder, StudySession, Task
from app.schemas import CourseCreate, CourseRead, CourseUpdate

router = APIRouter(prefix="/courses", tags=["courses"])


def _to_read(course: Course, session: Session) -> CourseRead:
    """Single-row read, computing display_name/sources fresh - used by the
    write endpoints below, where a full-list index build is cheap at this
    app's data volumes and keeps this always correct rather than guessing a
    freshly-touched course's merge state."""
    index = build_course_index(session)
    return CourseRead(
        id=course.id,
        source=course.source,
        external_id=course.external_id,
        name=course.name,
        term=course.term,
        code=course.code,
        archived=course.archived,
        display_name=index.display_name.get(course.id, course.name),
        sources=index.sources.get(course.id, [course.source]),
    )


@router.get("", response_model=list[CourseRead])
def list_courses(include_archived: bool = False, session: Session = Depends(get_session)):
    """Only ever returns one row per real class - a class synced from more
    than one platform (e.g. Gradescope + PrairieLearn) is folded into a
    single canonical row by app.course_merge, so this is what every course
    picker (Study Timer, Settings) and the Analytics/Recommendations
    pipelines all read from."""
    index = build_course_index(session)
    courses = index.canonical_courses
    if not include_archived:
        courses = [c for c in courses if not c.archived]
    courses.sort(key=lambda c: index.display_name.get(c.id, c.name))
    return [
        CourseRead(
            id=c.id,
            source=c.source,
            external_id=c.external_id,
            name=c.name,
            term=c.term,
            code=c.code,
            archived=c.archived,
            display_name=index.display_name.get(c.id, c.name),
            sources=index.sources.get(c.id, [c.source]),
        )
        for c in courses
    ]


@router.post("", response_model=CourseRead)
def create_course(body: CourseCreate, session: Session = Depends(get_session)):
    """Manually add a class/subject - lets the Study Timer and grade entry
    work fully even before any Canvas/Gradescope/PrairieLearn integration is
    connected (or for a subject that's never going to be, e.g. MCAT prep)."""
    course = Course(source="manual", external_id=str(uuid4()), name=body.name, term=body.term)
    session.add(course)
    session.commit()
    session.refresh(course)
    return _to_read(course, session)


@router.patch("/{course_id}", response_model=CourseRead)
def update_course(course_id: int, body: CourseUpdate, session: Session = Depends(get_session)):
    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if body.name is not None:
        course.name = body.name
    if body.term is not None:
        course.term = body.term
    if body.archived is not None:
        course.archived = body.archived
    session.add(course)
    session.commit()
    session.refresh(course)
    return _to_read(course, session)


@router.delete("/{course_id}", status_code=204)
def delete_course(course_id: int, session: Session = Depends(get_session)):
    """Only manually-added classes can be deleted - a synced one would just
    come back on the next sync, so archiving (PATCH) is the right tool there
    instead. Cascades to the course's tasks (and their reminders) and study
    sessions, since SQLite here doesn't enforce foreign keys on its own -
    see app.db.init_db."""
    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.source != "manual":
        raise HTTPException(
            status_code=400,
            detail="Only manually-added classes can be deleted. Archive a synced class instead.",
        )

    tasks = session.exec(select(Task).where(Task.course_id == course_id)).all()
    task_ids = [t.id for t in tasks]
    if task_ids:
        for reminder in session.exec(select(Reminder).where(Reminder.task_id.in_(task_ids))):
            session.delete(reminder)
        for task in tasks:
            session.delete(task)
    for study_session in session.exec(select(StudySession).where(StudySession.course_id == course_id)):
        session.delete(study_session)

    session.delete(course)
    session.commit()
