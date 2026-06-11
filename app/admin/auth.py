from __future__ import annotations

import os
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

COOKIE_NAME = "admin_session"
MAX_AGE_SECONDS = 86400  # 24 hours

_LOCAL_DEFAULT = "changeme"


def _is_prod() -> bool:
    """True on Railway (prod). Mirrors ``session.cookie_secure_in_prod``."""
    return bool((os.getenv("RAILWAY_ENVIRONMENT") or "").strip())


def _admin_password_from_env() -> str:
    """Read ADMIN_PASSWORD at call time (not import time) for correct Railway/runtime values.

    Fail-closed in production (T1.3): if ``RAILWAY_ENVIRONMENT`` is set but
    ``ADMIN_PASSWORD`` is unset or still the well-known ``changeme`` default,
    raise rather than accept it — otherwise admin login would work with
    ``changeme`` and the admin cookie would be forgeable. Local/test
    (``RAILWAY_ENVIRONMENT`` unset) keeps the default for convenience.
    """
    raw = os.getenv("ADMIN_PASSWORD")
    stripped = (raw or "").strip()
    if _is_prod() and (not stripped or stripped == _LOCAL_DEFAULT):
        raise RuntimeError(
            "ADMIN_PASSWORD must be set to a non-default value in production "
            "(RAILWAY_ENVIRONMENT is set); refusing to use the 'changeme' default."
        )
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
    return secrets.compare_digest(password.strip(), _admin_password_from_env())
