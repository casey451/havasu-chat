from __future__ import annotations

# Force redeploy 2026-04-16
from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

import asyncio
import html
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from app.admin.router import router as admin_router
from app.api.routes.admin_contributions import router as admin_contributions_router
from app.api.routes.admin_mentions import router as admin_mentions_router
from app.api.routes.chat import router as concierge_chat_router
from app.api.routes.contribute import router as contribute_router
from app.auth.routes import router as auth_router
from app.auth.session import SessionMiddleware
from app.core.event_quality import friendly_errors
from app.core.rate_limit import RATE_LIMIT_MESSAGE, limiter
from app.db.database import SessionLocal, get_db, init_db
from app.db.models import Event
from app.home.chat_route import router as new_chat_ui_router
from app.home.router import router as home_router
from app.programs.router import router as programs_router
from app.providers.router import router as providers_router
from app.schemas.event import EventRead

logger = logging.getLogger(__name__)

_DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
_PRIVACY_MD_PATH = _DOCS_DIR / "privacy.md"
_TOS_MD_PATH = _DOCS_DIR / "tos.md"
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
_SENSITIVE_EVENT_KEYS = frozenset({"query", "message", "normalized_query"})


def _is_chat_post_request_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        path = urlparse(url).path.rstrip("/") or "/"
    except Exception:
        path = url
    return path.endswith("/api/chat")


def _scrub_mapping_keys_inplace(d: dict[str, Any]) -> None:
    for k in list(d.keys()):
        if str(k).lower() in _SENSITIVE_EVENT_KEYS:
            d[k] = "<scrubbed>"


def scrub_sentry_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Strip chat bodies from Sentry events before upload."""
    req = event.get("request")
    if isinstance(req, dict) and _is_chat_post_request_url(str(req.get("url") or "")):
        req["data"] = "<scrubbed>"
        if "json" in req:
            req["json"] = "<scrubbed>"
    for bag in ("extra", "contexts"):
        bagv = event.get(bag)
        if isinstance(bagv, dict):
            _scrub_mapping_keys_inplace(bagv)
    crumbs = event.get("breadcrumbs")
    if isinstance(crumbs, dict):
        values = crumbs.get("values")
        if isinstance(values, list):
            for c in values:
                if isinstance(c, dict):
                    scrub_sentry_breadcrumb(c, hint)
    return event


def scrub_sentry_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Remove bodies from HTTP-related breadcrumbs that may echo POST payloads."""
    data = crumb.get("data")
    if isinstance(data, dict):
        for k in ("body", "data", "json", "state"):
            if k in data:
                data[k] = "<scrubbed>"
    return crumb


def _privacy_inline_formats(text: str) -> str:
    parts = re.split(r"(\*\*.+?\*\*)", text)
    chunks: list[str] = []
    for p in parts:
        if len(p) >= 4 and p.startswith("**") and p.endswith("**"):
            inner = html.escape(p[2:-2])
            chunks.append(f"<strong>{inner}</strong>")
        else:
            chunks.append(html.escape(p))
    s = "".join(chunks)

    def _link(m: re.Match[str]) -> str:
        u = m.group(1)
        safe = html.escape(u, quote=True)
        return f'<a href="{safe}" rel="noopener noreferrer">{html.escape(u)}</a>'

    s = re.sub(r"(https?://[^\s<>]+)", _link, s)

    def _path_link(m: re.Match[str]) -> str:
        label, path = m.group(1), m.group(2)
        p = html.escape(path, quote=True)
        return f'<a href="{p}">{html.escape(label)}</a>'

    return re.sub(r"\[([^\]]+)\]\((/[^)]+)\)", _path_link, s)


def _render_doc_markdown_to_html(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    in_ul = False
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if stripped.startswith("<!--") and "-->" in stripped:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(stripped)
            i += 1
            continue
        if stripped.startswith("# ") and not stripped.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h1>{html.escape(stripped[2:].strip())}</h1>")
            i += 1
            continue
        if stripped.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
            i += 1
            continue
        if stripped.startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = stripped[2:].lstrip()
            out.append(f"<li>{_privacy_inline_formats(item)}</li>")
            i += 1
            continue
        if not stripped:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            i += 1
            continue
        if in_ul:
            out.append("</ul>")
            in_ul = False
        para_parts: list[str] = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt:
                i += 1
                break
            if lines[i].lstrip().startswith("- ") or lines[i].lstrip().startswith("##"):
                break
            if lines[i].strip().startswith("<!--"):
                break
            para_parts.append(nxt)
            i += 1
        out.append(f"<p>{_privacy_inline_formats(' '.join(para_parts))}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


def _render_static_doc(request: Request, *, path: Path, head_title: str) -> HTMLResponse:
    md = path.read_text(encoding="utf-8")
    body = _render_doc_markdown_to_html(md)
    return templates.TemplateResponse(
        request=request,
        name="privacy_doc.html",
        context={"head_title": head_title, "body": body},
    )


def _init_sentry() -> None:
    """Initialize Sentry if SENTRY_DSN is set. Never raise — monitoring is best-effort."""
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        environment = "production" if os.getenv("RAILWAY_ENVIRONMENT") else "development"
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=0.1,
            integrations=[FastApiIntegration(), StarletteIntegration()],
            before_send=scrub_sentry_event,
            before_breadcrumb=scrub_sentry_breadcrumb,
        )
        logger.info("Sentry initialized (environment=%s)", environment)
    except Exception as exc:  # pragma: no cover — best-effort init
        logger.warning("Sentry initialization failed: %s", exc)


_init_sentry()


def run_expired_review_cleanup() -> int:
    """Mark expired pending_review events as deleted. Returns number of rows updated."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        expired = (
            db.query(Event)
            .filter(
                Event.status == "pending_review",
                Event.admin_review_by.isnot(None),
                Event.admin_review_by < now,
            )
            .all()
        )
        for ev in expired:
            ev.status = "deleted"
        db.commit()
        return len(expired)


async def _hourly_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        await asyncio.to_thread(run_expired_review_cleanup)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("ADMIN_PASSWORD loaded: %s", bool(os.getenv("ADMIN_PASSWORD")))
    init_db()
    task = asyncio.create_task(_hourly_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Havasu Chat", lifespan=lifespan)
app.add_middleware(SessionMiddleware)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_: Request, __: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"message": RATE_LIMIT_MESSAGE},
    )


app.include_router(concierge_chat_router)
app.include_router(contribute_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(admin_contributions_router)
app.include_router(admin_mentions_router)
app.include_router(programs_router)
# BUILD.md step 1: new /home page lives alongside the existing static / chat
# UI during dogfooding. Cuts over to / once we're confident.
app.include_router(home_router)
# Directory pivot V1 (2026-05-13): per-provider profile page at
# /provider/<slug>. Gates the Verified Presence sponsor package.
app.include_router(providers_router)
# BUILD.md step 5: new /chat surface that renders chat turns by
# component.type. Lives alongside the existing static / chat UI
# during dogfooding.
app.include_router(new_chat_ui_router)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def _format_event_datetime(event: Event) -> str:
    weekday = event.date.strftime("%A")
    month = event.date.strftime("%B")
    day = event.date.day
    hour_24 = event.start_time.hour
    minute = event.start_time.minute
    suffix = "AM" if hour_24 < 12 else "PM"
    hour_12 = hour_24 % 12 or 12
    return f"{weekday}, {month} {day}, {hour_12}:{minute:02d} {suffix}"


def _truncate_for_og(value: str, limit: int = 160) -> str:
    clean = " ".join(value.split()).strip()
    return clean[:limit]


def _render_not_found_response(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="event_not_found.html",
        context={},
        status_code=404,
    )


def _render_permalink_response(
    request: Request, *, event: Event, permalink_url: str
) -> HTMLResponse:
    contact_html = ""
    if event.contact_name or event.contact_phone:
        parts = [
            html.escape(p) for p in [event.contact_name, event.contact_phone] if p
        ]
        contact_html = f"<p><strong>Contact:</strong> {' | '.join(parts)}</p>"

    event_link_html = ""
    if event.event_url:
        escaped_url = html.escape(event.event_url)
        event_link_html = (
            f'<p><strong>Event Link:</strong> '
            f'<a href="{escaped_url}" target="_blank" rel="noopener noreferrer">{escaped_url}</a></p>'
        )

    tags_html = ""
    if event.tags:
        tag_nodes = "".join(
            f'<span class="tag">{html.escape(tag)}</span>' for tag in event.tags
        )
        tags_html = (
            f'<div class="tags"><h2>Tags</h2><div class="tag-wrap">{tag_nodes}</div></div>'
        )

    return templates.TemplateResponse(
        request=request,
        name="event_permalink.html",
        context={
            "event_title": event.title,
            "og_description": _truncate_for_og(event.description),
            "og_url": permalink_url,
            "formatted_datetime": _format_event_datetime(event),
            "location_name": event.location_name,
            "description": event.description,
            "contact_html": contact_html,
            "event_link_html": event_link_html,
            "tags_html": tags_html,
        },
    )


@app.get("/")
def serve_chat_ui() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request) -> HTMLResponse:
    return _render_static_doc(
        request, path=_PRIVACY_MD_PATH, head_title="Privacy — Havasu Chat"
    )


@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request) -> HTMLResponse:
    return _render_static_doc(
        request, path=_TOS_MD_PATH, head_title="Terms — Havasu Chat"
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"message": friendly_errors(exc.errors())},
    )


@app.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        count = db.query(Event).count()
        return {"status": "ok", "db_connected": True, "event_count": count}
    except Exception:
        return {"status": "ok", "db_connected": False, "event_count": 0}


@app.get("/events", response_model=list[EventRead])
def list_events(db: Session = Depends(get_db)) -> list[Event]:
    return db.query(Event).order_by(Event.created_at.desc()).all()


@app.get("/events/{event_id}", response_class=HTMLResponse)
def event_permalink(event_id: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None or event.status == "pending_review":
        return _render_not_found_response(request)
    return _render_permalink_response(request, event=event, permalink_url=str(request.url))
