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


def admin_guard(request):  # -> RedirectResponse | None
    """THE admin guard: allow the admin session cookie OR a logged-in user with
    role="admin"; 403 a logged-in non-admin; 302 anonymous users to /admin/login.

    Consolidated 2026-07-02 (audit): ~14 per-module ``_guard`` copies had
    drifted into two semantics — the cookie-only copies bounced legitimate
    role-admin users (who could moderate events on /admin) from
    /admin/contributions, /admin/jobs, the whole portal, etc. Every admin
    surface now imports this one.

    Imported lazily-typed (no fastapi import at module scope) so this auth
    module stays framework-light for scripts.
    """
    from fastapi import HTTPException
    from fastapi.responses import RedirectResponse

    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    current_user = getattr(request.state, "current_user", None)
    if current_user is not None and getattr(current_user, "role", None) == "admin":
        return None
    if current_user is not None:
        raise HTTPException(status_code=403, detail="admin_only")
    return RedirectResponse(url="/admin/login", status_code=302)
