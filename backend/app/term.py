"""Parses a course's `term` string into a sortable (year, season) rank -
mirrors `frontend/src/lib/term.ts` exactly, so the backend's auto-archiving
(app.sync_service._apply_current_semester_archiving) and anything the
frontend does with term text agree on what "the same semester" means, even
across platforms that phrase it differently (Gradescope: "Fall 2026";
PrairieLearn: sometimes "PHYS 214 Fall 2026" with the course name folded in,
sometimes unparseable text like "Proficiency Exam Practice: PHYS 213").
"""
import re
from typing import Optional

SEASON_RANK = {"spring": 0, "summer": 1, "fall": 2, "winter": 3}
_TERM_RE = re.compile(r"\b(spring|summer|fall|winter)\b\D{0,3}(\d{4})\b", re.IGNORECASE)

# (year, season_rank) - comparable/sortable as a plain tuple.
TermRank = tuple[int, int]


def parse_term_rank(term: Optional[str]) -> Optional[TermRank]:
    """None for text with no recognizable season+year - callers should leave
    those courses alone rather than guess them into "not current semester"."""
    if not term:
        return None
    match = _TERM_RE.search(term)
    if not match:
        return None
    season, year = match.groups()
    return (int(year), SEASON_RANK[season.lower()])
