"""GET /api/events* (master spec §4.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.db.models import Event
from app.events.queries import event_window_for_chip, events_in_window
from app.v1.serializers import event_from_row

router = APIRouter()


@router.get("/api/events")
def list_events(
    db: Session = Depends(get_db),
    group: str | None = Query(None, description="today|weekend|next-week"),
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    today = now_lake_havasu().date()
    if group:
        w_start, w_end = event_window_for_chip(group.replace("_", "-"), today=today)
    else:
        # Default API window is broad so non-filtered `/api/events` gives
        # useful upcoming inventory even when there are no same-day rows.
        from datetime import timedelta

        w_start, w_end = today, today + timedelta(days=14)
    pairs = events_in_window(db, window_start=w_start, window_end=w_end, limit=limit + offset)
    items = [event_from_row(ev, occurrence_date=occ) for ev, occ in pairs[offset : offset + limit]]
    grouped: dict[str, list] = {}
    if group:
        grouped[group] = items
    return {
        "items": items,
        "grouped": grouped or None,
        "total": len(pairs),
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/events/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(Event, event_id)
    if row is None or row.status != "live":
        raise HTTPException(status_code=404, detail="not_found")
    return event_from_row(row)
