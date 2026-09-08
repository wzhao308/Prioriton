"""Canvas adapter — uses Canvas's official REST API with a personal access
token (Account -> Settings -> New Access Token in Canvas). No scraping, no
computer vision: Canvas's JSON is structured and stable, which is exactly why
this is the adapter to build first.

Also pulls grades: `include[]=submission` on the assignments call returns
each assignment's own `points_possible` plus a nested `submission` object
with `score`/`graded_at` for the logged-in user, in the same request - no
extra endpoint needed. This is what feeds the Analytics Dashboard's
grade-related charts and the AI Recommendation System's grade context.
"""
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

import httpx

from app.adapters.base import Adapter, SyncedCourse, SyncedTask, extract_course_code


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Canvas's due_at/graded_at are always UTC ("Z"), so this is a no-op
    conversion in practice - but every adapter normalizes to naive-but-true-UTC
    the same way (see SyncedTask.due_at's docstring), so a naive DB column
    round-trips a genuinely correct UTC value no matter which platform a task
    came from."""
    if not value:
        return None
    aware = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


class CanvasAdapter(Adapter):
    source = "canvas"

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20.0,
        )

    def close(self) -> None:
        self._client.close()

    def test_connection(self) -> None:
        resp = self._client.get("/api/v1/users/self")
        if resp.status_code == 401:
            raise ValueError("Canvas rejected this token. Generate a new one and try again.")
        resp.raise_for_status()

    def _paginate(self, path: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        url: str | None = path
        first = True
        while url:
            resp = self._client.get(url, params=params if first else None)
            resp.raise_for_status()
            first = False
            yield from resp.json()
            next_link = resp.links.get("next")
            url = next_link["url"] if next_link else None
            if url:
                # httpx needs the path+query relative/absolute form it can follow directly.
                url = url.replace(self.base_url, "")

    def fetch_courses(self) -> list[SyncedCourse]:
        courses = []
        for raw in self._paginate(
            "/api/v1/courses",
            {"enrollment_state": "active", "per_page": 100, "include[]": "term"},
        ):
            courses.append(
                SyncedCourse(
                    external_id=str(raw["id"]),
                    name=raw.get("name") or raw.get("course_code") or f"Course {raw['id']}",
                    term=(raw.get("term") or {}).get("name") if isinstance(raw.get("term"), dict) else None,
                    code=extract_course_code(raw.get("course_code")),
                )
            )
        return courses

    def fetch_tasks(self, courses: list[SyncedCourse]) -> list[SyncedTask]:
        tasks: list[SyncedTask] = []
        for course in courses:
            for raw in self._paginate(
                f"/api/v1/courses/{course.external_id}/assignments",
                {"per_page": 100, "include[]": "submission"},
            ):
                submission = raw.get("submission") or {}
                tasks.append(
                    SyncedTask(
                        external_id=str(raw["id"]),
                        course_external_id=course.external_id,
                        title=raw.get("name", "Untitled assignment"),
                        type="assignment",
                        due_at=_parse_dt(raw.get("due_at")),
                        url=raw.get("html_url"),
                        points_possible=raw.get("points_possible"),
                        score=submission.get("score"),
                        graded_at=_parse_dt(submission.get("graded_at")),
                    )
                )
        return tasks
