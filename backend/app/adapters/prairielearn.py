"""PrairieLearn adapter.

Same situation as Gradescope: no public student API, and the user's school
routes login through the same institutional SSO used for Canvas/Gradescope.
Reuses `app.browser_login` unchanged - same interactive login, same
cookie-file session handoff (a fresh browser per call, cookies saved right
before closing and re-injected right after opening), same per-platform lock.
See `browser_login`'s module docstring for why that design exists; it isn't
repeated here since nothing platform-specific changes about it.

Everything below (URLs, markup, date format) was confirmed against
PrairieLearn's actual open-source template source
(github.com/PrairieLearn/PrairieLearn), not guessed from memory.

**Due dates are the tricky part here.** Canvas and Gradescope both expose a
machine-readable `<time datetime=...>`. PrairieLearn's main visible column
only shows a human-formatted, year-less "next deadline" string, and for a
multi-tier assessment (e.g. 100% credit until X, 50% until Y) that string
shows only the *next* tier - not the final cutoff. The real, complete
Credit/Start/End timeline is instead embedded in a `data-bs-content`
attribute on that row's "access details" popover button (present in the raw
HTML even without clicking it, since PrairieLearn renders popover content
server-side), using a fully-qualified `"YYYY-MM-DD HH:MM:SS (TZ)"` format.
This adapter parses that popover table and takes the LAST row's End date as
the assessment's true final due date.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from app import browser_login
from app.adapters.base import Adapter, SyncedCourse, SyncedTask, extract_course_code

PRAIRIELEARN_BASE = "https://us.prairielearn.com"
# Illinois's institution SSO id on PrairieLearn (confirmed live at /pl/login) -
# a direct SAML entry point, so login goes straight there instead of clicking
# a link. If this is ever used for a different school, this is the one thing
# to change.
LOGIN_URL = f"{PRAIRIELEARN_BASE}/pl/auth/institution/3/saml/login"

_COURSE_INSTANCE_RE = re.compile(r"^/pl/course_instance/(\d+)$")

# Each abbreviation already encodes its own DST state, so no separate DST
# logic is needed - just a fixed offset per abbreviation. Minutes, to cleanly
# support the half-hour Newfoundland zones.
_TZ_OFFSET_MINUTES = {
    "EST": -5 * 60, "EDT": -4 * 60,
    "CST": -6 * 60, "CDT": -5 * 60,
    "MST": -7 * 60, "MDT": -6 * 60,
    "PST": -8 * 60, "PDT": -7 * 60,
    "AKST": -9 * 60, "AKDT": -8 * 60,
    "HST": -10 * 60, "HDT": -9 * 60,
    "AST": -4 * 60, "ADT": -3 * 60,
    "NST": -3 * 60 - 30, "NDT": -2 * 60 - 30,
    "UTC": 0, "GMT": 0,
}

_POPOVER_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}) \(([A-Za-z]+)\)")


def _is_logged_out_html(html: str) -> bool:
    """Mirrors Gradescope's approach, applied proactively this time: a
    positive marker only the authenticated navbar renders."""
    return 'href="/pl/logout"' not in html


def _is_login_success(url: str, html: str) -> bool:
    """Only trust login success once we've actually settled back on
    PrairieLearn's own domain (not still mid-SSO-flow on the school's IdP or
    a Duo prompt) AND the page shows the same positive "Log out" proof used
    for session-expiry detection."""
    if not url.startswith(PRAIRIELEARN_BASE):
        return False
    return not _is_logged_out_html(html)


def is_logged_in(page) -> bool:
    """Success check used by the interactive login flow - thin wrapper of
    `_is_login_success` around a live Playwright page (kept separate so the
    real logic can be unit-tested against plain url/html fixtures)."""
    return _is_login_success(page.url, page.content())


def _parse_popover_datetime(text: str) -> Optional[datetime]:
    match = _POPOVER_DATE_RE.search(text)
    if not match:
        return None
    year, month, day, hour, minute, second, tz_abbrev = match.groups()
    offset_minutes = _TZ_OFFSET_MINUTES.get(tz_abbrev.upper())
    if offset_minutes is None:
        raise ValueError(
            f"Unrecognized PrairieLearn timezone abbreviation '{tz_abbrev}' - "
            "add it to _TZ_OFFSET_MINUTES in app/adapters/prairielearn.py."
        )
    naive = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
    aware = naive.replace(tzinfo=timezone(timedelta(minutes=offset_minutes)))
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def _due_date_from_popover(popover_html: str) -> Optional[datetime]:
    """Parses the Credit/Start/End mini-table embedded in a row's access-
    details popover, returning the LAST row's End date - the final,
    longest-lived credit tier's cutoff, i.e. the true final due date. Rows
    with no real End value ('—') are skipped.
    """
    soup = BeautifulSoup(popover_html, "html.parser")
    last_due: Optional[datetime] = None
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue  # header row
        end_text = cells[2].get_text(strip=True)
        parsed = _parse_popover_datetime(end_text)
        if parsed is not None:
            last_due = parsed
    return last_due


def parse_courses(html: str) -> list[SyncedCourse]:
    soup = BeautifulSoup(html, "html.parser")
    courses: list[SyncedCourse] = []
    for link in soup.find_all("a", href=True):
        if not _COURSE_INSTANCE_RE.match(link["href"]):
            continue
        external_id = _COURSE_INSTANCE_RE.match(link["href"]).group(1)
        # React SSR splits "{short}: {title}, {long_name}" into separate
        # sibling text nodes (comment-marked for hydration) around each
        # interpolation. get_text(strip=True) strips each node's OWN
        # whitespace independently before joining, silently eating the space
        # after ": " and around ", " - use get_text() (preserves each node's
        # original text) and strip only the combined result's outer edges.
        text = link.get_text().strip()
        # Link text is "SHORT: Title, Long Name" (e.g. "CS 101: Intro, Fall 2026").
        name, term, code = text, None, None
        if ": " in text:
            short, rest = text.split(": ", 1)
            code = extract_course_code(short)  # already clean, but normalize like every other adapter
            if ", " in rest:
                title, term = rest.rsplit(", ", 1)
                name = f"{short}: {title}"
            else:
                name = f"{short}: {rest}"
        courses.append(SyncedCourse(external_id=external_id, name=name, term=term, code=code))
    return courses


def parse_assessments(html: str, course_external_id: str) -> list[SyncedTask]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", attrs={"aria-label": "Assessments"})
    if table is None:
        # Could genuinely be a course with no assessments posted yet.
        return []

    tasks: list[SyncedTask] = []
    for row in table.find_all("tr"):
        badge = row.find(attrs={"data-testid": "assessment-set-badge"})
        if badge is None:
            continue  # a group-heading row, not an assessment row
        label = badge.get_text(strip=True)
        cells = row.find_all("td")
        title_cell = cells[1] if len(cells) > 1 else None
        link = title_cell.find("a", href=True) if title_cell else None
        if link is not None:
            title = link.get_text(strip=True)
            href = link["href"]
            url = f"{PRAIRIELEARN_BASE}{href}" if href.startswith("/") else href
        else:
            title = title_cell.get_text(strip=True) if title_cell else label
            url = None

        popover = row.find(attrs={"data-bs-content": True})
        due_at = _due_date_from_popover(popover["data-bs-content"]) if popover else None

        tasks.append(
            SyncedTask(
                external_id=f"{course_external_id}:{label}",
                course_external_id=course_external_id,
                title=title or label,
                type="assessment",
                due_at=due_at,
                url=url,
            )
        )
    return tasks


class PrairieLearnAdapter(Adapter):
    source = "prairielearn"

    def __init__(self, profile_dir: str):
        self._profile_dir = profile_dir
        self._lock = browser_login.launch_lock(self.source)
        self._lock.acquire()
        try:
            self._pw = sync_playwright().start()
            self._context = self._pw.chromium.launch_persistent_context(
                user_data_dir=profile_dir, headless=True
            )
            saved_cookies = browser_login.load_cookies(self.source)
            if saved_cookies:
                self._context.add_cookies(saved_cookies)
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        except Exception:
            self._lock.release()
            raise

    def close(self) -> None:
        try:
            try:
                browser_login.save_cookies(self.source, self._context.cookies())
            except Exception:  # noqa: BLE001 - saving is best-effort, never block a real close
                pass
            self._context.close()
        finally:
            self._pw.stop()
            self._lock.release()

    def _goto(self, path: str) -> str:
        self._page.goto(f"{PRAIRIELEARN_BASE}{path}")
        html = self._page.content()
        if _is_logged_out_html(html):
            raise ValueError(
                "PrairieLearn session expired. Reconnect PrairieLearn in Settings to log in again."
            )
        return html

    def test_connection(self) -> None:
        self._goto("/pl")

    def fetch_courses(self) -> list[SyncedCourse]:
        html = self._goto("/pl")
        return parse_courses(html)

    def fetch_tasks(self, courses: list[SyncedCourse]) -> list[SyncedTask]:
        tasks: list[SyncedTask] = []
        for course in courses:
            html = self._goto(f"/pl/course_instance/{course.external_id}/assessments")
            tasks.extend(parse_assessments(html, course.external_id))
        return tasks
