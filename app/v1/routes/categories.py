"""GET /api/categories — seven buckets + counts (master spec §4.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Event, Provider
from app.v1.categories import MASTER_BUCKETS, bucket_for_legacy_category

router = APIRouter()


@router.get("/api/categories")
def list_categories(db: Session = Depends(get_db)) -> dict:
    providers = list(
        db.scalars(
            select(Provider.category).where(
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
        ).all()
    )
    bucket_counts: dict[str, int] = {b["id"]: 0 for b in MASTER_BUCKETS}
    for cat in providers:
        bid = bucket_for_legacy_category(cat)
        bucket_counts[bid] = bucket_counts.get(bid, 0) + 1
    live_events = int(
        db.scalar(select(func.count()).select_from(Event).where(Event.status == "live")) or 0
    )
    bucket_counts["events"] = bucket_counts.get("events", 0) + live_events
    buckets = []
    for b in MASTER_BUCKETS:
        buckets.append({**b, "count": bucket_counts.get(b["id"], 0)})
    return {"buckets": buckets}
