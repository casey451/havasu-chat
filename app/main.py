from __future__ import annotations

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from app.admin.router import router as admin_router
from app.chat.router import router as chat_router
from app.core.event_quality import friendly_errors
from app.core.rate_limit import RATE_LIMIT_MESSAGE, limiter
from app.db.database import SessionLocal, get_db, init_db
from app.db.seed import run_seed_if_empty
from app.db.models import Event
from app.schemas.event import EventCreate, EventRead

logger = logging.getLogger(__name__)


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

_STATIC_DIR = Path(__file__).resolve().parent / "static"


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
@limiter.limit("10/minute")
def create_event(request: Request, payload: EventCreate, db: Session = Depends(get_db)) -> Event:
    event = Event.from_create(payload)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@app.get("/events", response_model=list[EventRead])
def list_events(db: Session = Depends(get_db)) -> list[Event]:
    return db.query(Event).order_by(Event.created_at.desc()).all()
