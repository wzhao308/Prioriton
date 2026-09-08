"""Encryption helpers for credentials stored at rest - the Canvas token, and
the Gradescope/PrairieLearn session cookie jar (see app.browser_login).

The Fernet key itself no longer has to live in a plaintext .env file: by
default it's auto-provisioned into the OS's own credential store (Windows
Credential Manager / macOS Keychain / the Secret Service on Linux, via the
`keyring` package) the first time it's needed, and reused from there after
that. This matters specifically for a project kept in a cloud-synced folder
(OneDrive, Dropbox, ...): .gitignore keeps the key and the encrypted database
out of a shared git repo, but it does nothing about the sync client itself,
which uploads everything in that folder regardless of git status. Moving the
*key* into the OS keyring takes it out of the synced folder entirely - so
even if the encrypted database or cookie-jar file does get synced somewhere,
the key that unlocks them doesn't travel with it.

Setting PRIORITON_SECRET_KEY explicitly (env var or .env) still works and
always takes priority over the keyring - useful for Docker/CI, where there's
often no OS keyring available at all - but isn't required for normal local
use.
"""
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger("prioriton.security")

_KEYRING_SERVICE = "prioriton"
_KEYRING_USERNAME = "secret_key"

_cached_key: Optional[str] = None


class DecryptionError(Exception):
    pass


def _keyring_backend():
    try:
        import keyring

        return keyring
    except ImportError:  # pragma: no cover - keyring is a normal dependency; only missing in odd installs
        return None


def get_or_create_secret_key() -> str:
    """Resolution order: explicit PRIORITON_SECRET_KEY env var > an existing
    OS keyring entry > a freshly generated key, stored in the keyring for
    next time. Only raises if neither an env var nor a working keyring
    backend is available (e.g. a headless Linux container with no secret
    service running) - there's no safe fallback past that."""
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    env_key = get_settings().secret_key
    if env_key:
        _cached_key = env_key
        return _cached_key

    keyring = _keyring_backend()
    if keyring is not None:
        try:
            existing = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
            if existing:
                _cached_key = existing
                return _cached_key
            new_key = Fernet.generate_key().decode()
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, new_key)
            logger.info("No encryption key found - generated one and stored it in the OS keyring.")
            _cached_key = new_key
            return _cached_key
        except Exception:  # noqa: BLE001 - no usable keyring backend on this system
            logger.warning("OS keyring unavailable; falling back to requiring PRIORITON_SECRET_KEY.", exc_info=True)

    raise RuntimeError(
        "No encryption key available. Either set PRIORITON_SECRET_KEY in backend/.env "
        '(generate one with: python -c "from cryptography.fernet import Fernet; '
        "print(Fernet.generate_key().decode())\"), or run somewhere with a working OS "
        "credential store (Windows Credential Manager, macOS Keychain, or a Linux Secret "
        "Service) so one can be generated automatically."
    )


def _fernet() -> Fernet:
    return Fernet(get_or_create_secret_key().encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError(
            "Could not decrypt stored credentials. The encryption key changed (a "
            "different PRIORITON_SECRET_KEY, or a different OS keyring entry) - "
            "reconnect your integrations."
        ) from exc
