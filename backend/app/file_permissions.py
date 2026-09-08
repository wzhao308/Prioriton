"""Best-effort file-permission hardening for the local files that hold
sensitive data: the SQLite database (the encrypted Canvas token and the
Gradescope/PrairieLearn cookie jar live inside it), .env (if a secret key or
the Anthropic key is set there), and the browser profile directory. Restricts
each to the current OS user only, so another account on a shared machine
can't read them without also having that account's own login.

Purely defense-in-depth - this narrows an already-encrypted file's
readability, it isn't what makes the contents unreadable (the Fernet key
does, see app.security). Deliberately never raises: a failure here just
means this one extra layer didn't apply this run, not that anything else is
broken - called once at startup and logged, not surfaced to the user.
"""
import logging
import os
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger("prioriton.file_permissions")


def _restrict_windows(path: Path) -> None:
    user = os.environ.get("USERNAME") or os.environ.get("USER")
    if not user:
        return
    args = ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F", "/C", "/Q"]
    if path.is_dir():
        args.insert(-2, "/T")  # recurse into the profile directory's contents
    subprocess.run(args, check=False, capture_output=True)


def _restrict_posix(path: Path) -> None:
    os.chmod(path, 0o700 if path.is_dir() else 0o600)
    if path.is_dir():
        for child in path.rglob("*"):
            try:
                os.chmod(child, 0o700 if child.is_dir() else 0o600)
            except OSError:
                pass


def restrict_to_current_user(*paths: Path) -> None:
    for path in paths:
        if not path.exists():
            continue
        try:
            if platform.system() == "Windows":
                _restrict_windows(path)
            else:
                _restrict_posix(path)
        except Exception:  # noqa: BLE001 - defense-in-depth only, never fatal
            logger.warning("Could not restrict permissions on %s", path, exc_info=True)
