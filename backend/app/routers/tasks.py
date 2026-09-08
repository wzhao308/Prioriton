from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.course_merge import build_course_index
from app.db import get_session
from app.models import Task
from app.schemas import TaskRead, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUSES = {"pending", "done", "dismissed"}


def _to_read(task: Task, canonical_course_id: dict[int, int]) -> TaskRead:
    """Never mutates `task.course_id` itself (that's a tracked ORM attribute
    on a row headed for `session.commit()` elsewhere in these handlers) -
    just reports the canonical id in the response, same as every other course
    reference in the API (see app.course_merge)."""
    return TaskRead(
        id=task.id,
        source=task.source,
        course_id=canonical_course_id.get(task.course_id, task.course_id) if task.course_id is not None else None,
        title=task.title,
        type=task.type,
        due_at=task.due_at,
        late_due_at=task.late_due_at,
        url=task.url,
        status=task.status,
        points_possible=task.points_possible,
        score=task.score,
        graded_at=task.graded_at,
        started_at=task.started_at,
    )


@router.get("", response_model=list[TaskRead])
def list_tasks(
    course_id: Optional[int] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session),
):
    index = build_course_index(session)
    query = select(Task)
    if course_id is not None:
        # `course_id` here is a canonical id - broaden to every platform-
        # specific row folded into it (see app.course_merge), so a task
        # synced under the merged-away sibling's own id still matches.
        query = query.where(Task.course_id.in_(index.members.get(course_id, [course_id])))
    if status is not None:
        query = query.where(Task.status == status)
    query = query.order_by(Task.due_at.is_(None), Task.due_at)
    return [_to_read(t, index.canonical_id) for t in session.exec(query)]


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(task_id: int, body: TaskUpdate, session: Session = Depends(get_session)):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(VALID_STATUSES)}")
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = body.status
    task.updated_at = datetime.now(timezone.utc)
    session.add(task)
    session.commit()
    session.refresh(task)
    index = build_course_index(session)
    return _to_read(task, index.canonical_id)


@router.post("/{task_id}/start", response_model=TaskRead)
def start_task(task_id: int, session: Session = Depends(get_session)):
    """Marks "I'm starting work on this now" - Canvas/Gradescope/PrairieLearn
    have no such concept, so this is the only source for the Analytics
    Dashboard's early-start-vs-grade chart and the recommendation system's
    "start now" nudges. Idempotent: calling it again doesn't reset the clock."""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.started_at is None:
        task.started_at = datetime.now(timezone.utc)
        session.add(task)
        session.commit()
        session.refresh(task)
    index = build_course_index(session)
    return _to_read(task, index.canonical_id)
