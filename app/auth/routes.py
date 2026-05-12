"""Magic-link auth routes (Phase 2A.2)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session as SqlSession

from app.auth.dependencies import get_current_user
from app.auth.email_helpers import (
    generate_magic_link_token,
    hash_optional_fingerprint,
    hash_request_ip,
    hash_token,
    is_valid_email,
    normalize_email,
)
from app.auth.email_sender import send_magic_link
from app.auth.session import (
    COOKIE_NAME,
    MAX_AGE_SECONDS,
    SESSION_LIFETIME_SECONDS,
    cookie_secure_in_prod,
    sign_session_cookie,
)
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.db.models import AuthSession, MagicLinkToken, User

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["auth"])


def _safe_next(raw: str | None) -> str | None:
    """Allow only same-origin relative paths (open-redirect guard)."""
    if not raw:
        return None
    s = unquote(raw).strip()
    if not s.startswith("/"):
        return None
    if s.startswith("//"):
        return None
    if "://" in s:
        return None
    if ".." in s:
        return None
    return s


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


def _naive_utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _email_rate_limit_exceeded(db: SqlSession, email: str, *, limit: int = 5) -> bool:
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    cnt = (
        db.query(func.count(MagicLinkToken.id))
        .filter(MagicLinkToken.email == email, MagicLinkToken.created_at > cutoff)
        .scalar()
    )
    return int(cnt or 0) >= limit


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    next_path = _safe_next(request.query_params.get("next"))
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "next_path": next_path},
    )


@router.post("/api/auth/request-link")
@limiter.limit("10/hour")
def request_link(
    request: Request,
    email: str = Form(...),
    next_path: str = Form("", alias="next"),
    db: SqlSession = Depends(get_db),
) -> HTMLResponse:
    normalized = normalize_email(email)
    safe_next = _safe_next(next_path) if next_path else None
    if not is_valid_email(normalized):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Please enter a valid email address.",
                "next_path": safe_next,
            },
            status_code=400,
        )
    if _email_rate_limit_exceeded(db, normalized):
        return templates.TemplateResponse(
            request=request,
            name="login_check_email.html",
            context={"email": normalized},
        )

    plaintext, token_hash = generate_magic_link_token()
    now_aware = datetime.now(timezone.utc)
    db.add(
        MagicLinkToken(
            email=normalized,
            token_hash=token_hash,
            expires_at=now_aware + timedelta(minutes=15),
            requested_from_ip_hash=hash_request_ip(_client_ip(request)),
        )
    )
    db.commit()

    try:
        send_magic_link(normalized, plaintext, next_path=safe_next)
    except Exception:
        logger.exception("magic-link send failed for %s", normalized)

    return templates.TemplateResponse(
        request=request,
        name="login_check_email.html",
        context={"email": normalized},
    )


@router.get("/auth/callback", response_class=HTMLResponse)
def auth_callback(
    request: Request,
    token: str,
    db: SqlSession = Depends(get_db),
) -> Response:
    token_hash_val = hash_token(token)
    row = (
        db.query(MagicLinkToken)
        .filter(MagicLinkToken.token_hash == token_hash_val)
        .first()
    )
    now_aware = datetime.now(timezone.utc)

    if row is None or row.consumed_at is not None or row.expires_at < now_aware:
        return templates.TemplateResponse(
            request=request,
            name="login_expired.html",
            status_code=400,
            context={},
        )

    row.consumed_at = now_aware
    user = db.query(User).filter(User.email == row.email).first()
    if user is None:
        user = User(email=row.email, role="end_user")
        db.add(user)
        db.flush()
    user.last_login_at = _naive_utc_now()

    session_row = AuthSession(
        user_id=user.id,
        expires_at=now_aware + timedelta(seconds=SESSION_LIFETIME_SECONDS),
        ip_hash=hash_request_ip(_client_ip(request)),
        user_agent_hash=hash_optional_fingerprint(
            request.headers.get("user-agent")
        ),
    )
    db.add(session_row)
    db.commit()

    signed = sign_session_cookie(session_row.id)
    next_path = _safe_next(request.query_params.get("next")) or "/account"
    response = RedirectResponse(url=next_path, status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=signed,
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        secure=cookie_secure_in_prod(),
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout")
def logout(request: Request, db: SqlSession = Depends(get_db)) -> Response:
    sess = getattr(request.state, "current_session", None)
    if sess is not None:
        row = db.get(AuthSession, sess.id)
        if row is not None:
            db.delete(row)
            db.commit()
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=cookie_secure_in_prod(),
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/account", response_class=HTMLResponse)
def account_page(request: Request) -> Response:
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=%2Faccount", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="account.html",
        context={"user": user},
    )
