"""Gradescope adapter.

Gradescope has no public student API, and (per the user) this school routes
its login through the same institutional SSO as Canvas. So instead of a
scripted login, this adapter reuses a browser profile that was populated by
one interactive login (see app.browser_login) - it opens that same profile
and parses the rendered HTML of the two pages that matter.

If Gradescope's markup has drifted from what's parsed here, prefer failing
loudly (raising) over silently returning wrong/empty data - a broken parser
should show up as a visible sync error, not a mysteriously-empty dashboard.

**Why the session is carried forward as a saved cookie file, not a kept-open
browser:** real end-to-end testing (with a real account) ruled out both more
obvious designs - see `app.browser_login`'s module docstring for the full
story. In short: Gradescope's true session cookie doesn't survive a closed
browser, and keeping one open across calls hits Playwright's per-thread
session binding instead. So every open here is fresh (matching Canvas's
pattern), but injects the cookie jar `browser_login` saved from the last
login/sync right after launching, and saves a fresh jar right before closing.
"""
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from app import browser_login
from app.adapters.base import Adapter, SyncedCourse, SyncedTask, extract_course_code

GRADESCOPE_BASE = "https://www.gradescope.com"
LOGIN_URL = f"{GRADESCOPE_BASE}/login"


def _is_logged_out_html(html: str) -> bool:
    """Gradescope doesn't redirect an unauthenticated visitor to a distinct
    `/login` URL - the homepage itself (`/`) just renders a login form in
    place, at the *same* URL a logged-in dashboard would use. So the only
    reliable signal is the login form itself: it renders a `#session_email`
    input that a logged-in dashboard never has.
    """
    return 'id="session_email"' in html


def _is_login_success(url: str, html: str) -> bool:
    """The real check for "has the user finished logging in", used by the
    interactive login flow.

    While completing SSO the user passes through several intermediate,
    *unauthenticated* pages that are NOT proof of failure: Gradescope's own
    "pick your school" chooser at `/saml`, their institution's identity
    provider, a Duo prompt, and so on. Naively treating "no login form" as
    success is wrong - `/saml` (confirmed by fetching it directly) has no
    `#session_email` field either, so that check alone reports success
    without any authentication having happened at all.

    Only trust it once BOTH hold: the browser has settled back on
    Gradescope's own dashboard/account area (not still mid-SSO-flow), AND the
    page shows positive proof of an authenticated session - a real "Log Out"
    link, which every logged-out and intermediate page (home, /login, /saml)
    consistently lacks.
    """
    if not url.startswith(GRADESCOPE_BASE):
        return False
    path = url[len(GRADESCOPE_BASE):].split("?")[0].split("#")[0]
    if path not in ("", "/", "/account"):
        return False
    return '/logout' in html


def is_logged_in(page) -> bool:
    """Success check used by the interactive login flow - thin wrapper of
    `_is_login_success` around a live Playwright page (kept separate so the
    real logic can be unit-tested against plain url/html fixtures)."""
    return _is_login_success(page.url, page.content())


def _parse_time(tag) -> Optional[datetime]:
    """Gradescope's <time datetime=...> includes an explicit offset (e.g.
    "-05:00" for school-local time) - this MUST be converted to true UTC
    before being handed off (matching every other adapter's convention, see
    SyncedTask.due_at's docstring), otherwise the stored value silently keeps
    the local wall-clock numbers instead of the correct UTC instant."""
    if tag is None or not tag.get("datetime"):
        return None
    aware = datetime.fromisoformat(tag["datetime"])
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def _due_dates_from_row(row) -> tuple[Optional[datetime], Optional[datetime]]:
    """Gradescope assignment rows show up to three <time> tags: release date,
    regular due date, and (when the instructor allows late submission) a
    "Late Due Date:" hard cutoff - confirmed directly against a real course's
    page. With 3 tags that's [release, due, late_due]; with exactly 2 it's
    [release, due] (no late option); with exactly 1, that's the only date
    available (used as the due date, no late date). Returns (due_at, late_due_at).
    """
    times = row.find_all("time")
    if not times:
        return None, None
    if len(times) == 1:
        return _parse_time(times[0]), None
    if len(times) == 2:
        return _parse_time(times[1]), None
    return _parse_time(times[1]), _parse_time(times[-1])


def parse_courses(html: str) -> list[SyncedCourse]:
    soup = BeautifulSoup(html, "html.parser")
    courses: list[SyncedCourse] = []
    current_term: Optional[str] = None

    # The term header is a plain <div class="courseList--term">Fall 2026</div>
    # (confirmed against the real page - not an <h2>, which was the original,
    # wrong guess here and the reason term always came out empty).
    for el in soup.find_all(["div", "a"]):
        if el.name == "div" and "courseList--term" in (el.get("class") or []):
            current_term = el.get_text(strip=True)
            continue
        if el.name == "a" and "courseBox" in (el.get("class") or []):
            href = el.get("href", "")
            if not href.startswith("/courses/"):
                continue
            external_id = href.rstrip("/").split("/")[-1]
            name_el = el.select_one(".courseBox--name")
            short_el = el.select_one(".courseBox--shortname")
            name = (name_el.get_text(strip=True) if name_el else None) or (
                short_el.get_text(strip=True) if short_el else None
            ) or el.get_text(strip=True) or f"Course {external_id}"
            # The code lives in the shortname (e.g. "PHYS 213 Fall 2026"), not
            # the descriptive name used above - extracted separately so it can
            # cross-reference the same real class on another platform.
            code = extract_course_code(short_el.get_text(strip=True) if short_el else None)
            courses.append(SyncedCourse(external_id=external_id, name=name, term=current_term, code=code))

    return courses


def parse_assignments(html: str, course_external_id: str) -> list[SyncedTask]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find(id="assignments-student-table")
    if table is None:
        # Could genuinely be a course with no assignments posted yet - don't treat
        # that as an error, just nothing to sync for this course.
        return []

    tasks: list[SyncedTask] = []
    body = table.find("tbody") or table
    for row in body.find_all("tr"):
        link = row.select_one(".table--primaryLink a") or row.find("a", href=True)
        if link is None:
            continue
        href = link.get("href", "")
        title = link.get_text(strip=True)
        parts = href.rstrip("/").split("/")
        external_id = parts[-1] if parts else title
        due_at, late_due_at = _due_dates_from_row(row)
        tasks.append(
            SyncedTask(
                external_id=external_id,
                course_external_id=course_external_id,
                title=title or f"Assignment {external_id}",
                type="assignment",
                due_at=due_at,
                late_due_at=late_due_at,
                url=f"{GRADESCOPE_BASE}{href}" if href.startswith("/") else href,
            )
        )
    return tasks


class GradescopeAdapter(Adapter):
    source = "gradescope"

    def __init__(self, profile_dir: str):
        self._profile_dir = profile_dir
        # Held for this adapter's whole open-use-close span - see launch_lock's
        # docstring for why (Chromium won't share one profile across processes).
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
        self._page.goto(f"{GRADESCOPE_BASE}{path}")
        html = self._page.content()
        if _is_logged_out_html(html):
            raise ValueError(
                "Gradescope session expired. Reconnect Gradescope in Settings to log in again."
            )
        return html

    def test_connection(self) -> None:
        self._goto("/")

    def fetch_courses(self) -> list[SyncedCourse]:
        html = self._goto("/")
        return parse_courses(html)

    def fetch_tasks(self, courses: list[SyncedCourse]) -> list[SyncedTask]:
        tasks: list[SyncedTask] = []
        for course in courses:
            html = self._goto(f"/courses/{course.external_id}")
            tasks.extend(parse_assignments(html, course.external_id))
        return tasks
