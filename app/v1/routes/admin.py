"""Admin JSON under /api/admin/* (master spec §4.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, admin_password_ok, sign_admin_cookie
from app.api.routes.admin_contributions import require_admin
from app.conditions.cache import read_source
from app.conditions.constants import SOURCE_GAS
from app.conditions.staleness import staleness_label
from app.contrib.gas_prices import run_pull
from app.contrib.golakehavasu_pull import run_pull as golake_pull
from app.contrib.river_scene_pull import run_pull as river_scene_pull
from app.core.timezone import now_lake_havasu
from app.db.contribution_store import list_contributions
from app.db.database import get_db
from app.db.models import Contribution, Event, Provider, QueryLog
from app.schemas.contribution import ContributionResponse

router = APIRouter(prefix="/api/admin", tags=["v1-admin"])

DbSession = Annotated[Session, Depends(get_db)]


def _require_admin(request: Request) -> None:
    require_admin(request)


AdminAuth = Annotated[None, Depends(_require_admin)]


@router.post("/login")
def admin_login(
    email: str = Form(...),
    password: str = Form(...),
):
    """Email is accepted for spec compatibility; v1 uses single ADMIN_PASSWORD."""
    _ = email
    if not admin_password_ok(password):
        raise HTTPException(status_code=401, detail="invalid_credentials")
    from fastapi.responses import JSONResponse

    resp = JSONResponse(content={"ok": True})
    resp.set_cookie(COOKIE_NAME, sign_admin_cookie(), httponly=True, samesite="lax", max_age=86400)
    return resp


@router.get("/queue")
def admin_queue(_: AdminAuth, db: DbSession) -> dict:
    rows = list_contributions(db, status="pending", limit=100, offset=0)
    return {
        "items": [ContributionResponse.model_validate(r).model_dump() for r in rows],
        "total": len(rows),
    }


@router.post("/sync")
def admin_sync(_: AdminAuth, db: DbSession) -> dict:
    today = now_lake_havasu().date()
    summary: dict[str, str | int] = {}
    try:
        summary["gas"] = run_pull(dry_run=False)
    except Exception as exc:
        summary["gas"] = f"error: {exc}"
    try:
        summary["river_scene"] = river_scene_pull(today, dry_run=False)
    except Exception as exc:
        summary["river_scene"] = f"error: {exc}"
    try:
        summary["golakehavasu"] = golake_pull(today, dry_run=False)
    except Exception as exc:
        summary["golakehavasu"] = f"error: {exc}"
    return {"ok": True, "summary": summary}


@router.get("/stats")
def admin_stats(_: AdminAuth, db: DbSession) -> dict:
    now = datetime.now(UTC).replace(tzinfo=None)
    pending = int(
        db.scalar(
            select(func.count()).select_from(Contribution).where(Contribution.status == "pending")
        )
        or 0
    )
    businesses = int(
        db.scalar(
            select(func.count())
            .select_from(Provider)
            .where(Provider.is_active.is_(True), Provider.draft.is_(False))
        )
        or 0
    )
    events = int(
        db.scalar(select(func.count()).select_from(Event).where(Event.status == "live")) or 0
    )
    gas_row = read_source(db, SOURCE_GAS, now=now)
    gas_fresh = gas_row.fetched_at.isoformat() if gas_row and gas_row.fetched_at else None
    week_ago = now - timedelta(days=7)
    recent_queries = list(
        db.scalars(
            select(QueryLog)
            .where(QueryLog.created_at >= week_ago)
            .order_by(desc(QueryLog.created_at))
            .limit(20)
        ).all()
    )
    return {
        "pending_contributions": pending,
        "businesses": businesses,
        "events": events,
        "gas_last_sync": gas_fresh,
        "recent_queries": [
            {
                "intent": q.normalized_intent,
                "category": q.category,
                "result_count": q.result_count,
                "at": q.created_at.isoformat(),
            }
            for q in recent_queries
        ],
    }


@router.get("/gas")
def admin_gas(_: AdminAuth, db: DbSession) -> dict:
    now = datetime.now(UTC).replace(tzinfo=None)
    row = read_source(db, SOURCE_GAS, now=now)
    if row is None or not isinstance(row.data, dict):
        return {"stations": [], "staleness_label": None, "is_stale": True}
    label, stale = staleness_label(row.fetched_at, now)
    return {**row.data, "staleness_label": label, "is_stale": bool(stale or row.is_stale)}
