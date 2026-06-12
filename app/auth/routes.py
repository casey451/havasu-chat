"""Magic-link auth routes (Phase 2A.2)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as SqlSession

from app.auth.claims import (
    create_pending_claim,
    entity_is_claimable,
    find_existing_claim,
    get_entity_by_slug,
)
from app.auth.dependencies import get_current_user
from app.auth.email_helpers import (
    generate_magic_link_token,
    hash_optional_fingerprint,
    hash_request_ip,
    hash_token,
    is_valid_email,
    normalize_email,
)
from app.auth.favorites import (
    entity_is_favoritable,
    list_user_favorites,
    toggle_favorite,
)
from app.auth.session import (
    COOKIE_NAME,
    MAX_AGE_SECONDS,
    SESSION_LIFETIME_SECONDS,
    cookie_secure_in_prod,
    sign_session_cookie,
)
from app.core.background import (
    OUTBOX_KIND_MAGIC_LINK,
    deliver_outbox_row,
    enqueue_outbox,
)
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import AuthSession, Entity, MagicLinkToken, Provider, User

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

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
    background_tasks: BackgroundTasks,
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
            context={"email": normalized, "next_path": safe_next},
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
    # Phase 4.1: enqueue the magic-link send onto the Outbox in the same
    # transaction as the MagicLinkToken row. Commit, then hand off
    # delivery to BackgroundTasks. If the BackgroundTasks slot drops
    # the call (process crash, queue full), the redrive cron sweep
    # (scripts/outbox_redrive.py) picks the row up and retries. The
    # email body + recipient + Resend API call semantics are unchanged
    # from the pre-4.1 inline path — see app/auth/email_sender.py.
    outbox_payload = {
        "email": normalized,
        "token": plaintext,
        "next_path": safe_next,
    }
    outbox_id = enqueue_outbox(db, kind=OUTBOX_KIND_MAGIC_LINK, payload=outbox_payload)
    db.commit()

    background_tasks.add_task(deliver_outbox_row, outbox_id)

    return templates.TemplateResponse(
        request=request,
        name="login_check_email.html",
        context={"email": normalized, "next_path": safe_next},
    )


@router.get("/auth/callback", response_class=HTMLResponse)
def auth_callback(
    request: Request,
    token: str,
    db: SqlSession = Depends(get_db),
) -> Response:
    token_hash_val = hash_token(token)
    row = db.query(MagicLinkToken).filter(MagicLinkToken.token_hash == token_hash_val).first()
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
        user_agent_hash=hash_optional_fingerprint(request.headers.get("user-agent")),
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


class FavoriteToggleBody(BaseModel):
    entity_id: str


class BoatModePreferenceBody(BaseModel):
    enabled: bool


def _profile_href_for_entity(db: SqlSession, ent: Entity) -> str | None:
    if ent.entity_type == ENTITY_TYPE_COMMERCIAL:
        p = (
            db.query(Provider)
            .filter(
                Provider.entity_id == ent.id,
                Provider.is_active.is_(True),
            )
            .first()
        )
        if p is not None and p.slug:
            return f"/provider/{p.slug}"
    return None


@router.post("/api/users/me/boat_mode_preference")
def api_boat_mode_preference(
    request: Request,
    body: BoatModePreferenceBody,
    db: SqlSession = Depends(get_db),
) -> JSONResponse:
    """Persist boat-access mode for logged-in users (maps to ``users.preferred_mode``)."""
    user = get_current_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "login_required"})
    row = db.get(User, user.id)
    if row is None:
        return JSONResponse(status_code=401, content={"detail": "login_required"})
    row.preferred_mode = "boat" if body.enabled else "default"
    db.commit()
    return JSONResponse(
        content={
            "boat_mode_preference": body.enabled,
            "preferred_mode": user.preferred_mode,
        }
    )


@router.get("/api/users/me/boat_mode_preference")
def api_boat_mode_preference_get(request: Request) -> JSONResponse:
    user = get_current_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "login_required"})
    enabled = getattr(user, "preferred_mode", "default") == "boat"
    return JSONResponse(content={"boat_mode_preference": enabled})


@router.post("/api/favorites/toggle")
def api_favorites_toggle(
    request: Request,
    body: FavoriteToggleBody,
    db: SqlSession = Depends(get_db),
) -> JSONResponse:
    user = get_current_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "login_required"})
    ent = db.get(Entity, body.entity_id)
    if ent is None:
        return JSONResponse(status_code=404, content={"detail": "entity_not_found"})
    if not entity_is_favoritable(ent.entity_type):
        return JSONResponse(status_code=400, content={"detail": "not_favoritable"})
    action, favorite_count = toggle_favorite(db, user.id, body.entity_id)
    db.commit()
    return JSONResponse(content={"action": action, "favorite_count": favorite_count})


@router.get("/api/favorites")
def api_favorites_list(request: Request, db: SqlSession = Depends(get_db)) -> JSONResponse:
    user = get_current_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "login_required"})
    entities = list_user_favorites(db, user.id)
    payload = []
    for ent in entities:
        payload.append(
            {
                "entity_id": ent.id,
                "slug": ent.slug,
                "name": ent.name,
                "entity_type": ent.entity_type,
                "profile_href": _profile_href_for_entity(db, ent),
            }
        )
    return JSONResponse(content={"favorites": payload})


@router.get("/account/favorites", response_class=HTMLResponse)
def account_favorites_page(request: Request, db: SqlSession = Depends(get_db)) -> Response:
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(
            url=f"/login?next={quote('/account/favorites', safe='')}",
            status_code=303,
        )
    entities = list_user_favorites(db, user.id)
    rows: list[dict[str, object]] = []
    for ent in entities:
        rows.append(
            {
                "name": ent.name or ent.slug or ent.id,
                "href": _profile_href_for_entity(db, ent),
            }
        )
    return templates.TemplateResponse(
        request=request,
        name="account_favorites.html",
        context={"user": user, "favorites": rows},
    )


@router.get("/claim/{slug}", response_class=HTMLResponse)
def claim_get(slug: str, request: Request, db: SqlSession = Depends(get_db)) -> Response:
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(
            url=f"/login?next={quote(f'/claim/{slug}', safe='')}",
            status_code=303,
        )
    ent = get_entity_by_slug(db, slug)
    if ent is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if not entity_is_claimable(ent.entity_type):
        raise HTTPException(status_code=400, detail="not_claimable")
    existing = find_existing_claim(db, user.id, ent.id)
    if existing is not None:
        return templates.TemplateResponse(
            request=request,
            name="claim_status.html",
            context={"entity": ent, "claim": existing},
        )
    return templates.TemplateResponse(
        request=request,
        name="claim_form.html",
        context={"entity": ent},
    )


@router.post("/claim/{slug}", response_class=HTMLResponse)
def claim_post(
    slug: str,
    request: Request,
    db: SqlSession = Depends(get_db),
    notes: str | None = Form(default=None),
) -> Response:
    del notes  # V1 optional field — no column; reserved for a future migration
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(
            url=f"/login?next={quote(f'/claim/{slug}', safe='')}",
            status_code=303,
        )
    ent = get_entity_by_slug(db, slug)
    if ent is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if not entity_is_claimable(ent.entity_type):
        raise HTTPException(status_code=400, detail="not_claimable")
    prior = find_existing_claim(db, user.id, ent.id)
    if prior is not None:
        return templates.TemplateResponse(
            request=request,
            name="claim_status.html",
            context={"entity": ent, "claim": prior},
        )
    try:
        create_pending_claim(db, user.id, ent.id)
        db.commit()
    except IntegrityError as err:
        db.rollback()
        existing = find_existing_claim(db, user.id, ent.id)
        if existing is None:
            raise err
        return templates.TemplateResponse(
            request=request,
            name="claim_status.html",
            context={"entity": ent, "claim": existing},
        )
    return templates.TemplateResponse(
        request=request,
        name="claim_submitted.html",
        context={"entity": ent},
    )
