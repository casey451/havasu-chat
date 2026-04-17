from __future__ import annotations

import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

COOKIE_NAME = "admin_session"
MAX_AGE_SECONDS = 86400  # 24 hours

_LOCAL_DEFAULT = "changeme"
# TEMP: remove after Railway ADMIN_PASSWORD is confirmed readable in-process
_FALLBACK_ADMIN_PASSWORD = "havasu2026"


def _admin_password_from_env() -> str:
    """Read ADMIN_PASSWORD at call time (not import time) for correct Railway/runtime values."""
    raw = os.getenv("ADMIN_PASSWORD")
    if raw is None:
        return _LOCAL_DEFAULT
    stripped = raw.strip()
    return stripped if stripped else _LOCAL_DEFAULT


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_admin_password_from_env(), salt="havasu-admin-session")


def sign_admin_cookie() -> str:
    return _serializer().dumps({"ok": True})


def verify_admin_cookie(value: str | None) -> bool:
    if not value:
        return False
    try:
        data = _serializer().loads(value, max_age=MAX_AGE_SECONDS)
        return data.get("ok") is True
    except (BadSignature, SignatureExpired):
        return False


def admin_password_ok(password: str) -> bool:
    p = password.strip()
    if p == _FALLBACK_ADMIN_PASSWORD:
        return True
    return p == _admin_password_from_env()


def admin_password_debug_info() -> dict[str, bool | int]:
    """Non-secret probe for ops (e.g. Railway env visibility)."""
    raw = os.getenv("ADMIN_PASSWORD")
    if raw is None:
        return {"pw_set": False, "pw_length": 0}
    stripped = raw.strip()
    if not stripped:
        return {"pw_set": False, "pw_length": 0}
    return {"pw_set": True, "pw_length": len(stripped)}
