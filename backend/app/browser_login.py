"""Generic interactive-login mechanism, shared by every platform whose login
can't be scripted (Gradescope now, PrairieLearn later - both route through
school SSO + Duo at the user's institution).

The approach: open a real, visible Chromium window backed by a *persistent*
on-disk profile, let the user complete SSO/Duo themselves, then detect success
by watching where the page ends up.

**Why sessions are carried forward as a saved cookie file, not a kept-open
browser**: two real bugs, found via actual end-to-end testing, ruled out the
more obvious designs.

1. Gradescope's real authenticated session is carried by a true session-only
   cookie, which Chromium correctly discards the moment its browser context
   is closed. A `remember_me` cookie is also set and does persist to disk,
   but on its own it does NOT silently restore full access on the next
   launch (confirmed directly against a real account). So "close after each
   sync and just relaunch from the on-disk profile" loses the session.
2. The seemingly obvious fix - keep ONE browser context open across every
   sync instead of closing it - hits a *different* wall: Playwright's sync
   API binds a session to the exact OS thread that created it. A background
   login thread, APScheduler's job thread, and a FastAPI request-handler
   thread are all different threads, so a session created on one and reused
   from another fails with "cannot switch to a different thread" (confirmed
   directly - a manual sync from a fresh HTTP request broke a session that
   had just been created during login).

The design that survives both problems: never hold a browser open between
calls at all. Every login or sync opens its own context, does its work, and
closes normally - but right before closing, the live cookie jar (including
the session-only cookie) is captured and saved to a small file
(`save_cookies`/`load_cookies`), encrypted at rest with the same Fernet setup
that protects the Canvas token (app.security) - this is real session data,
not just a file path, so it gets the same protection. The next open injects
it back via `context.add_cookies()` before navigating anywhere. A
per-platform lock (`launch_lock`) serializes access to a profile directory,
since Chromium still won't let two processes open the same one at the same
time.

Runs in a plain background thread. FastAPI's sync path-operations already run
in a thread pool and APScheduler's job runs in its own thread, so nothing else
needs to change to make a blocking Playwright call safe here.
"""
import json
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import sync_playwright

from app import security

logger = logging.getLogger("prioriton.browser_login")

PROFILE_ROOT = Path(__file__).resolve().parent.parent / ".browser_profiles"
LOGIN_TIMEOUT_SECONDS = 600  # 10 minutes to finish SSO + Duo

_active_logins: dict[str, threading.Thread] = {}
_login_lock = threading.Lock()

_launch_locks: dict[str, threading.Lock] = {}
_launch_locks_guard = threading.Lock()


def profile_dir(platform: str) -> Path:
    d = PROFILE_ROOT / platform
    d.mkdir(parents=True, exist_ok=True)
    return d


def delete_profile(platform: str) -> None:
    d = PROFILE_ROOT / platform
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def is_login_running(platform: str) -> bool:
    with _login_lock:
        thread = _active_logins.get(platform)
        return thread is not None and thread.is_alive()


def launch_lock(platform: str) -> threading.Lock:
    """One lock per platform, shared by the login flow and every adapter that
    opens this profile directory - Chromium refuses to let two processes hold
    the same persistent-context profile open at once, so callers should hold
    this for their entire open-use-close span."""
    with _launch_locks_guard:
        if platform not in _launch_locks:
            _launch_locks[platform] = threading.Lock()
        return _launch_locks[platform]


def _cookies_path(platform: str) -> Path:
    return PROFILE_ROOT / f"{platform}.cookies.json"


def save_cookies(platform: str, cookies: list[dict]) -> None:
    """Encrypted at rest with the same Fernet key that protects the Canvas
    token (app.security) - this file holds real session cookies (Gradescope's
    true session-only cookie included), not just a profile-directory path
    like Integration.encrypted_credentials does for these platforms."""
    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    _cookies_path(platform).write_text(security.encrypt(json.dumps(cookies)))


def load_cookies(platform: str) -> Optional[list[dict]]:
    path = _cookies_path(platform)
    if not path.exists():
        return None
    raw = path.read_text()
    try:
        return json.loads(security.decrypt(raw))
    except security.DecryptionError:
        # Defensive fallback: if this file ever ends up as plain JSON (e.g.
        # hand-restored from a backup, or ported from an app version that
        # didn't encrypt it), adopt it and immediately re-save it encrypted,
        # rather than treating the session as gone and forcing a reconnect
        # just because of a storage-format mismatch.
        try:
            cookies = json.loads(raw)
        except (ValueError, TypeError):
            return None
        save_cookies(platform, cookies)
        return cookies
    except Exception:  # noqa: BLE001 - a corrupt/missing cookie file just means "nothing saved yet"
        return None


def delete_cookies(platform: str) -> None:
    path = _cookies_path(platform)
    if path.exists():
        path.unlink()


def start_interactive_login(
    platform: str,
    login_url: str,
    success_check: Callable[[object], bool],
    on_result: Callable[[bool, Optional[str]], None],
) -> None:
    """Open a headed browser at `login_url`. Polls `success_check(page)` once a
    second until it returns True or `LOGIN_TIMEOUT_SECONDS` elapses. On
    success, saves the live cookie jar (see module docstring) for the next
    adapter to pick up. Calls `on_result(ok, error_message)` exactly once,
    after all of that browser work is done. Runs entirely in a background
    thread - returns immediately.
    """

    def _run() -> None:
        ok = False
        error: Optional[str] = None
        cookies: Optional[list[dict]] = None
        with launch_lock(platform):
            pw = sync_playwright().start()
            login_context = None
            try:
                login_context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir(platform)),
                    headless=False,
                )
                page = login_context.pages[0] if login_context.pages else login_context.new_page()
                page.goto(login_url)
                deadline = time.time() + LOGIN_TIMEOUT_SECONDS
                while time.time() < deadline:
                    if page.is_closed():
                        error = "The browser window was closed before login finished."
                        break
                    try:
                        if success_check(page):
                            ok = True
                            break
                    except Exception:  # noqa: BLE001 - page mid-navigation, just retry
                        pass
                    time.sleep(1)
                else:
                    error = "Timed out waiting for login to complete (10 minutes)."

                if ok:
                    # Capture cookies (including the true session-only one) from
                    # the still-open, already-authenticated window, before it closes.
                    cookies = login_context.cookies()
            except Exception as exc:  # noqa: BLE001 - surface any Playwright failure to the UI
                logger.exception("Interactive login failed for %s", platform)
                ok, error = False, str(exc)
            finally:
                if login_context is not None:
                    try:
                        login_context.close()
                    except Exception:  # noqa: BLE001 - already closed by the user, that's fine
                        pass
                try:
                    pw.stop()
                except Exception:  # noqa: BLE001
                    pass

        if ok and cookies is not None:
            save_cookies(platform, cookies)

        on_result(ok, None if ok else error)

    thread = threading.Thread(target=_run, name=f"login-{platform}", daemon=True)
    with _login_lock:
        _active_logins[platform] = thread
    thread.start()
