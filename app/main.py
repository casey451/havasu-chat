from __future__ import annotations

# Force redeploy 2026-04-16

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

import asyncio
import html
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from app.admin.router import router as admin_router
from app.chat.router import router as chat_router
from app.programs.router import router as programs_router
from app.core.event_quality import friendly_errors
from app.core.rate_limit import RATE_LIMIT_MESSAGE, limiter
from app.db.database import SessionLocal, get_db, init_db
from app.db.seed import run_seed_if_empty
from app.db.models import Event
from app.schemas.event import EventCreate, EventRead

logger = logging.getLogger(__name__)


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
    # Auto-seed empty DB on Railway only (local/tests use manual seed or fixtures).
    if os.getenv("RAILWAY_ENVIRONMENT"):
        await asyncio.to_thread(run_seed_if_empty)
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
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_: Request, __: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"message": RATE_LIMIT_MESSAGE},
    )


app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(programs_router)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


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


def _render_not_found_page() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>Event not found - Havasu Chat</title>
  <style>
    :root {
      --bg: #ffffff;
      --border: #dee2e6;
      --text: #212529;
      --muted: #6c757d;
      --link: #0d6efd;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }
    body { margin: 0; background: var(--bg); color: var(--text); }
    .wrap { max-width: 720px; margin: 0 auto; padding: 48px 20px; }
    .card {
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 20px;
      background: #fff;
    }
    h1 { margin: 0 0 10px; font-size: 1.4rem; }
    p { margin: 0 0 16px; color: var(--muted); line-height: 1.5; }
    a { color: var(--link); font-weight: 600; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Event not found</h1>
      <p>This event is unavailable. It may have been removed, is still under review, or never existed.</p>
      <a href="/">Back to Havasu Chat</a>
    </section>
  </main>
</body>
</html>
"""


def _render_permalink_page(event: Event, permalink_url: str) -> str:
    escaped_title = html.escape(event.title)
    escaped_description = html.escape(event.description)
    escaped_location = html.escape(event.location_name)
    escaped_datetime = html.escape(_format_event_datetime(event))
    escaped_back = html.escape("/")
    escaped_url = html.escape(event.event_url or "")
    escaped_contact_name = html.escape(event.contact_name or "")
    escaped_contact_phone = html.escape(event.contact_phone or "")
    og_description = html.escape(_truncate_for_og(event.description))
    og_url = html.escape(permalink_url)

    tags_html = ""
    if event.tags:
        tag_nodes = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in event.tags)
        tags_html = f'<div class="tags"><h2>Tags</h2><div class="tag-wrap">{tag_nodes}</div></div>'

    contact_html = ""
    if event.contact_name or event.contact_phone:
        parts = [p for p in [escaped_contact_name, escaped_contact_phone] if p]
        contact_html = f"<p><strong>Contact:</strong> {' | '.join(parts)}</p>"

    event_link_html = ""
    if event.event_url:
        event_link_html = f'<p><strong>Event Link:</strong> <a href="{escaped_url}" target="_blank" rel="noopener noreferrer">{escaped_url}</a></p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{escaped_title} - Havasu Chat</title>
  <meta property="og:title" content="{escaped_title}" />
  <meta property="og:description" content="{og_description}" />
  <meta property="og:url" content="{og_url}" />
  <style>
    :root {{
      --bg: #ffffff;
      --surface: #f4f6f8;
      --border: #dee2e6;
      --text: #212529;
      --muted: #6c757d;
      --link: #0d6efd;
      --radius: 16px;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); }}
    .wrap {{ max-width: 720px; margin: 0 auto; padding: 24px 16px 40px; }}
    .card {{
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: #fff;
      padding: 20px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }}
    h1 {{ margin: 0 0 10px; font-size: 1.5rem; line-height: 1.3; }}
    .meta {{ margin: 0 0 14px; color: var(--muted); font-size: 0.95rem; }}
    p {{ margin: 0 0 12px; line-height: 1.55; }}
    a {{ color: var(--link); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    h2 {{
      margin: 0 0 8px;
      font-size: 0.9rem;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: var(--muted);
    }}
    .tags {{ margin-top: 16px; }}
    .tag-wrap {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .tag {{
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border: 1px solid var(--border);
      background: var(--surface);
      border-radius: 999px;
      font-size: 0.85rem;
      color: #495057;
    }}
    .back-link {{
      display: inline-block;
      margin-bottom: 14px;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <a class="back-link" href="{escaped_back}">Back to Havasu Chat</a>
    <article class="card">
      <h1>{escaped_title}</h1>
      <p class="meta">{escaped_datetime} • {escaped_location}</p>
      <p>{escaped_description}</p>
      {contact_html}
      {event_link_html}
      {tags_html}
    </article>
  </main>
</body>
</html>
"""


@app.get("/")
def serve_chat_ui() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


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


@app.post("/events", response_model=EventRead)
@limiter.limit("5/minute")
def create_event(request: Request, payload: EventCreate, db: Session = Depends(get_db)) -> Event:
    event = Event.from_create(payload)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@app.get("/events", response_model=list[EventRead])
def list_events(db: Session = Depends(get_db)) -> list[Event]:
    return db.query(Event).order_by(Event.created_at.desc()).all()


@app.get("/events/{event_id}", response_class=HTMLResponse)
def event_permalink(event_id: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None or event.status == "pending_review":
        return HTMLResponse(content=_render_not_found_page(), status_code=404)
    return HTMLResponse(content=_render_permalink_page(event, str(request.url)), status_code=200)
