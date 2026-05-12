"""Signed session cookie + middleware (Phase 2A.2)."""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.admin.auth import _admin_password_from_env
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

_LAST_SEEN_MONO: dict[str, float] = {}


def _session_secret() -> str:
    raw = (os.environ.get("HAVA_SESSION_SECRET") or "").strip()
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


def _should_bump_last_seen(session_id: str) -> bool:
    mono = time.monotonic()
    last = _LAST_SEEN_MONO.get(session_id)
    if last is not None and mono - last < LAST_SEEN_DEBOUNCE_SECONDS:
        return False
    _LAST_SEEN_MONO[session_id] = mono
    return True


def _utc_naive_wall() -> datetime:
    """Match DateTime columns that store naive UTC wall time."""
    return datetime.now(UTC).replace(tzinfo=None)


class SessionMiddleware(BaseHTTPMiddleware):
    """Attach ``current_user`` / ``current_session`` from ``hava_session`` cookie."""

    async def dispatch(self, request: Request, call_next) -> Response:
        cookie_val = request.cookies.get(COOKIE_NAME)
        session_id = verify_session_cookie(cookie_val)
        clear_cookie = False
        current_user: User | None = None
        current_session: AuthSession | None = None

        if session_id:
            db = SessionLocal()
            try:
                now_aware = datetime.now(timezone.utc)
                sess = db.get(AuthSession, session_id)
                if sess is None:
                    clear_cookie = True
                elif sess.expires_at < now_aware:
                    clear_cookie = True
                else:
                    user = db.get(User, sess.user_id)
                    if user is None or not user.is_active:
                        clear_cookie = True
                    else:
                        current_user = user
                        current_session = sess
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
            except Exception:
                logger.exception("session middleware DB error")
                db.rollback()
                clear_cookie = True
                current_user = None
                current_session = None
            finally:
                db.close()

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
