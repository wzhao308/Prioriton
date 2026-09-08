"""Consolidates the same real class synced from more than one platform into
a single canonical Course - e.g. Gradescope's "University Physics: Thermal
Physics" and PrairieLearn's "PHYS 213: Thermal Physics" are the same class,
just phrased differently by each platform. Ported from what ManaPeer's
frontend (`courseGroups.ts`) did purely at display time; here it's persisted
on the Course row itself (`merged_into_id`) so every part of the app - the
Study Timer's picker, Settings, Analytics, Recommendations - agrees on "one
course" without each having to re-derive it, and a new StudySession/Task
naturally lands on the same canonical row going forward.

Only merges rows sharing the same extracted `code` AND coming from different
sources - two same-source rows sharing a code (e.g. Gradescope's own
"ECE 110-ABA" / "-ABE" / "-HOMEWORK", genuinely different lab sections) are
never merged, same rule ManaPeer used.
"""
from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.models import Course

SYNCED_SOURCES = {"canvas", "gradescope", "prairielearn"}

# Which row of a merged group is canonical, when it matters (its own name/
# term/archived state is what the rest of the app reads). Canvas's official
# REST API is the most reliable source, so it wins when present; otherwise
# lowest id (i.e. whichever was synced first) breaks the tie deterministically.
_SOURCE_PRIORITY = {"canvas": 0, "gradescope": 1, "prairielearn": 2, "manual": 3}


def apply_course_merging(session: Session) -> int:
    """Recomputes `merged_into_id` for every synced course. Re-run on every
    sync (same pattern as `sync_service._apply_current_semester_archiving`),
    so a newly-connected platform's matching course gets folded in
    automatically, and a group that no longer has a cross-platform match
    (e.g. a course code changed) gets un-merged rather than stuck. Returns
    how many courses' `merged_into_id` changed."""
    courses = session.exec(select(Course).where(Course.source.in_(SYNCED_SOURCES))).all()
    by_code: dict[str, list[Course]] = defaultdict(list)
    for course in courses:
        if course.code:
            by_code[course.code].append(course)

    changed = 0
    for group in by_code.values():
        sources = {c.source for c in group}
        if len(sources) < 2:
            # Same-source-only duplicates (different sections/rosters) - never merged.
            for course in group:
                if course.merged_into_id is not None:
                    course.merged_into_id = None
                    session.add(course)
                    changed += 1
            continue

        canonical = min(group, key=lambda c: (_SOURCE_PRIORITY.get(c.source, 99), c.id))
        for course in group:
            new_value = None if course.id == canonical.id else canonical.id
            if course.merged_into_id != new_value:
                course.merged_into_id = new_value
                session.add(course)
                changed += 1
    return changed


def canonical_id(course: Course) -> int:
    return course.merged_into_id if course.merged_into_id is not None else course.id


@dataclass
class CourseIndex:
    """A per-request snapshot of every course's merge state, so every reader
    (analytics, study sessions, recommendations) canonicalizes the same way
    without re-querying per row."""

    canonical_id: dict[int, int]  # raw course id -> canonical course id
    members: dict[int, list[int]]  # canonical course id -> every raw id folded into it (incl. itself)
    display_name: dict[int, str]  # canonical course id -> name to show
    sources: dict[int, list[str]]  # canonical course id -> distinct platform(s) behind it
    canonical_courses: list[Course] = field(default_factory=list)  # rows where merged_into_id is None


def build_course_index(session: Session) -> CourseIndex:
    courses = session.exec(select(Course)).all()
    courses_by_id = {c.id: c for c in courses}

    canonical_ids = {c.id: canonical_id(c) for c in courses}
    members: dict[int, list[int]] = defaultdict(list)
    for c in courses:
        members[canonical_ids[c.id]].append(c.id)

    follower_count: dict[int, int] = defaultdict(int)
    for c in courses:
        if c.merged_into_id is not None:
            follower_count[c.merged_into_id] += 1

    display_name: dict[int, str] = {}
    sources: dict[int, list[str]] = {}
    canonical_courses: list[Course] = []
    for c in courses:
        if c.merged_into_id is not None:
            continue  # not shown standalone - resolved through its canonical row
        canonical_courses.append(c)
        # A merged group's canonical row shows its shared `code` (e.g.
        # "PHYS 213") instead of either platform's own phrasing, since
        # neither is more "correct" than the other - same convention
        # ManaPeer's frontend used for the same reason.
        display_name[c.id] = c.code if follower_count[c.id] > 0 and c.code else c.name
        sources[c.id] = sorted({courses_by_id[member_id].source for member_id in members[c.id]})

    return CourseIndex(
        canonical_id=canonical_ids,
        members=dict(members),
        display_name=display_name,
        sources=sources,
        canonical_courses=canonical_courses,
    )
