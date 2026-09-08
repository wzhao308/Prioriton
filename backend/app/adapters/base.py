"""The extensibility point: every platform (Canvas, and later Gradescope /
PrairieLearn) implements this same interface. The sync engine and the rest of
the app only ever deal with `SyncedCourse` / `SyncedTask` and don't need to
know how a given adapter got its data (REST API vs. an authenticated scraping
session).
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Matches a leading "subject + number" course code, e.g. "PHYS 213" out of
# "PHYS 213 Fall 2026", "ECE 210/211" out of "ECE 210/211 Fall 2026 - HW and
# Lab", "ECE 110" out of "ECE 110-ABA". Used to recognize the *same real
# class* tracked on two different platforms (Gradescope's shortname and
# PrairieLearn's short_name usually agree on this even when their full
# course names/descriptions are phrased completely differently) - see
# Course.code's docstring in app/models.py for how this is used.
_COURSE_CODE_RE = re.compile(r"^\s*([A-Za-z]{2,10})\s*(\d{2,4}[A-Za-z]?(?:\s*/\s*\d{2,4}[A-Za-z]?)?)")


def extract_course_code(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = _COURSE_CODE_RE.match(text)
    if not match:
        return None
    subject, number = match.groups()
    return f"{subject.upper()} {re.sub(r'\s+', '', number)}"


@dataclass
class SyncedCourse:
    external_id: str
    name: str
    term: Optional[str] = None
    # Best-effort "subject + number" course code (see extract_course_code),
    # used only to recognize the same real class across different platforms -
    # never to distinguish otherwise-identical entries within ONE platform
    # (e.g. Gradescope's "ECE 110-ABA" / "-ABE" / "-HOMEWORK" all extract to
    # "ECE 110" but are legitimately separate rosters/sections, not the same
    # tracked course twice - see frontend/src/lib/courseGroups.ts).
    code: Optional[str] = None


@dataclass
class SyncedTask:
    external_id: str
    course_external_id: str
    title: str
    type: str  # assignment | quiz | exam | project
    # Naive datetime that MUST already represent true UTC (convert with
    # `.astimezone(timezone.utc).replace(tzinfo=None)` before returning it from
    # any adapter, however the source expressed its own timestamp - Canvas's
    # "Z", Gradescope's explicit school-local offset, PrairieLearn's named TZ
    # abbreviation, whatever's next). The DB column is naive (SQLite has no
    # real timezone support and silently drops tzinfo on write), so an
    # inconsistent adapter would store a wrong absolute instant that just
    # happens to look plausible - exactly what happened before Gradescope's
    # parser was fixed to normalize like this too. The frontend also depends
    # on this: it appends "Z" itself before parsing any date from the API
    # (see frontend/src/lib/date.ts), since a naive ISO string is otherwise
    # ambiguous to JavaScript.
    due_at: Optional[datetime]
    url: Optional[str]
    # Hard late-submission cutoff, when a platform offers one beyond the
    # regular due date (confirmed on Gradescope: assignments allowing late
    # submission show a separate "Late Due Date:" <time> tag). Same naive-UTC
    # convention as due_at. None everywhere it doesn't apply.
    late_due_at: Optional[datetime] = None
    # Grade fields - only Canvas populates these today (see
    # app.adapters.canvas), via the same request that fetches the task
    # itself. None everywhere a platform doesn't expose grades this way yet.
    points_possible: Optional[float] = None
    score: Optional[float] = None
    graded_at: Optional[datetime] = None


class Adapter(ABC):
    """One connected platform account."""

    source: str  # e.g. "canvas"

    @abstractmethod
    def test_connection(self) -> None:
        """Raise an exception (with a human-readable message) if credentials are invalid."""

    @abstractmethod
    def fetch_courses(self) -> list[SyncedCourse]:
        ...

    @abstractmethod
    def fetch_tasks(self, courses: list[SyncedCourse]) -> list[SyncedTask]:
        ...

    def close(self) -> None:
        """Release any held resources (HTTP client, browser process, ...).

        Default no-op; adapters holding onto something (a browser process, in
        particular) MUST override this. The sync engine always calls it.
        """
