"""GET /api/feed — home feed JSON (master spec §4.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.events.queries import events_in_window, intent_window_for_when
from app.home import pullquote, queries_c
from app.v1.serializers import event_from_row

router = APIRouter()


@router.get("/api/feed")
def get_feed(db: Session = Depends(get_db)) -> dict:
    from datetime import timedelta

    now = now_lake_havasu()
    today = now.date()
    w_start, w_end = intent_window_for_when("tonight", today=today)
    soon = [
        event_from_row(ev, occurrence_date=occ)
        for ev, occ in events_in_window(db, window_start=w_start, window_end=w_end, limit=12)
    ]
    if not soon:
        soon = [
            event_from_row(ev, occurrence_date=occ)
            for ev, occ in events_in_window(
                db,
                window_start=today,
                window_end=today + timedelta(days=14),
                limit=12,
            )
        ]
    discover = queries_c.discover_grid(db, now=now)
    eat = queries_c.eat_row(db, now=now)
    services = queries_c.services_grid(db)
    return {
        "events_soon": soon,
        "featured": discover,
        "things_to_do": discover[:6],
        "eat_open_now": eat,
        "services": services,
        "categories": [c.get("slug") for c in services if c.get("slug")],
        "hava_read": pullquote.get_quote(db),
        "generated_at": now.isoformat(),
    }
