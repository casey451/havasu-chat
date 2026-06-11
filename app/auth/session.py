"""Signed session cookie + middleware (Phase 2A.2)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.admin.auth import _LOCAL_DEFAULT, _admin_password_from_env
from app.bootstrap_env import ensure_dotenv_loaded
from app.db.database import SessionLocal
from app.db.models import AuthSession, User

ensure_dotenv_loaded()

logger = logging.getLogger(__name__)

COOKIE_NAME = "hava_session"
COOKIE_SALT = "havasu-session"
MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days
SESSION_LIFETIME_SECONDS = 60 * 60 * 24 * 30
LAST_SEEN_DEBOUNCE_SECONDS = 60

# T2.2: the debounce map only needs ~LAST_SEEN_DEBOUNCE_SECONDS of memory, but it
# was never pruned — it grew one entry per unique session id over the whole
# process lifetime (unbounded leak). Prune expired entries once the map crosses
# this soft cap so its size is bounded by concurrent active sessions, not history.
_LAST_SEEN_MAX_ENTRIES = 10_000

_LAST_SEEN_MONO: dict[str, float] = {}


def _session_secret() -> str:
    """Resolve the session-cookie signing secret.

    Fail-closed in production and decoupled from the admin password (T1.3):
    prod (``RAILWAY_ENVIRONMENT`` set, via ``cookie_secure_in_prod()``) requires
    a distinct, non-default ``HAVA_SESSION_SECRET`` and refuses to fall back to
    the admin password or the ``changeme`` default — otherwise user session
    cookies would be forgeable. Local/test keeps the admin-password fallback
    for convenience (unchanged behavior).
    """
    raw = (os.environ.get("HAVA_SESSION_SECRET") or "").strip()
    if cookie_secure_in_prod():
        if not raw or raw == _LOCAL_DEFAULT:
            raise RuntimeError(
                "HAVA_SESSION_SECRET must be set to a distinct, non-default value "
                "in production (RAILWAY_ENVIRONMENT is set); refusing to sign "
                "session cookies with the admin password or the 'changeme' default."
            )
        return raw
    if raw:
        return raw
    return _admin_password_from_env()


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_session_secret(), salt=COOKIE_SALT)


def sign_session_cookie(session_id: str) -> str:
    return _serializer().dumps(session_id)


def verify_session_cookie(value: str | None) -> str | None:
    if not value:
        return None
    try:
        sid = _serializer().loads(value, max_age=MAX_AGE_SECONDS)
        if isinstance(sid, str) and sid:
            return sid
        return None
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None


def cookie_secure_in_prod() -> bool:
    return bool((os.environ.get("RAILWAY_ENVIRONMENT") or "").strip())


def _prune_last_seen(now_mono: float) -> None:
    """Drop debounce entries older than the window — they can never debounce again."""
    cutoff = now_mono - LAST_SEEN_DEBOUNCE_SECONDS
    stale = [sid for sid, ts in _LAST_SEEN_MONO.items() if ts < cutoff]
    for sid in stale:
        del _LAST_SEEN_MONO[sid]


def _should_bump_last_seen(session_id: str) -> bool:
    mono = time.monotonic()
    last = _LAST_SEEN_MONO.get(session_id)
    if last is not None and mono - last < LAST_SEEN_DEBOUNCE_SECONDS:
        return False
    if len(_LAST_SEEN_MONO) >= _LAST_SEEN_MAX_ENTRIES:
        _prune_last_seen(mono)
    _LAST_SEEN_MONO[session_id] = mono
    return True


def _utc_naive_wall() -> datetime:
    """Match DateTime columns that store naive UTC wall time."""
    return datetime.now(UTC).replace(tzinfo=None)


def _load_session_user(session_id: str) -> tuple[User | None, AuthSession | None, bool]:
    """Sync DB lookup for :class:`SessionMiddleware` — returns ``(user, session, clear_cookie)``.

    Runs via ``asyncio.to_thread`` (PERF-4, audit :95-99): 2-3 blocking SQLAlchemy
    round-trips (plus the occasional last-seen bump commit) per cookied request
    used to run directly on the event loop, serializing all in-flight requests
    on every stall. Logic is byte-for-byte the previous inline block.
    """
    db = SessionLocal()
    try:
        now_aware = datetime.now(timezone.utc)
        sess = db.get(AuthSession, session_id)
        if sess is None:
            return None, None, True
        if sess.expires_at < now_aware:
            return None, None, True
        user = db.get(User, sess.user_id)
        if user is None or not user.is_active:
            return None, None, True
        bumped = False
        if _should_bump_last_seen(sess.id):
            sess.last_seen_at = _utc_naive_wall()
            db.add(sess)
            db.commit()
            bumped = True
        if bumped:
            db.refresh(user)
            db.refresh(sess)
        db.expunge(user)
        db.expunge(sess)
        return user, sess, False
    except Exception:
        logger.exception("session middleware DB error")
        db.rollback()
        return None, None, True
    finally:
        db.close()


class SessionMiddleware(BaseHTTPMiddleware):
    """Attach ``current_user`` / ``current_session`` from ``hava_session`` cookie."""

    async def dispatch(self, request: Request, call_next) -> Response:
        cookie_val = request.cookies.get(COOKIE_NAME)
        session_id = verify_session_cookie(cookie_val)
        clear_cookie = False
        current_user: User | None = None
        current_session: AuthSession | None = None

        if session_id:
            current_user, current_session, clear_cookie = await asyncio.to_thread(
                _load_session_user, session_id
            )

        request.state.current_user = current_user
        request.state.current_session = current_session

        response = await call_next(request)
        if clear_cookie and cookie_val:
            response.delete_cookie(
                key=COOKIE_NAME,
                path="/",
                secure=cookie_secure_in_prod(),
                httponly=True,
                samesite="lax",
            )
        return response
