"""Admin demand dashboard — read-only view over the query log (Phase 2 §5a).

Both an ops tool and the sales deck for the business portal: what locals ask
for, and — critically — what they ask for that we have *nothing* to serve
(``result_count == 0``), which is the acquisition list. Pure reads; no writes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import QueryLog


def build_demand_view(db: Session, *, now: datetime, days: int = 30, limit: int = 20) -> dict[str, Any]:
    """Assemble the demand dashboard context from QueryLog. Never raises on an
    empty/young log — every section degrades to an empty list."""
    since = now - timedelta(days=days)

    base = db.query(QueryLog).filter(QueryLog.created_at >= since)
    total = base.with_entities(func.count(QueryLog.id)).scalar() or 0

    def _grouped(query) -> list[dict[str, Any]]:
        return [
            {"label": (row[0] or "(unlabeled)"), "count": int(row[1])}
            for row in query
            if row[1]
        ]

    top_intents = _grouped(
        db.query(QueryLog.normalized_intent, func.count(QueryLog.id))
        .filter(QueryLog.created_at >= since)
        .group_by(QueryLog.normalized_intent)
        .order_by(func.count(QueryLog.id).desc())
        .limit(limit)
    )

    # The acquisition list: searched for, nothing to serve.
    unserved = _grouped(
        db.query(QueryLog.normalized_intent, func.count(QueryLog.id))
        .filter(QueryLog.created_at >= since, QueryLog.result_count == 0)
        .group_by(QueryLog.normalized_intent)
        .order_by(func.count(QueryLog.id).desc())
        .limit(limit)
    )
    unserved_total = (
        base.filter(QueryLog.result_count == 0)
        .with_entities(func.count(QueryLog.id))
        .scalar()
        or 0
    )

    by_category = _grouped(
        db.query(QueryLog.category, func.count(QueryLog.id))
        .filter(QueryLog.created_at >= since)
        .group_by(QueryLog.category)
        .order_by(func.count(QueryLog.id).desc())
        .limit(limit)
    )

    # 14-day volume trend (most recent last).
    trend_since = now - timedelta(days=14)
    trend_rows = (
        db.query(func.date(QueryLog.created_at), func.count(QueryLog.id))
        .filter(QueryLog.created_at >= trend_since)
        .group_by(func.date(QueryLog.created_at))
        .order_by(func.date(QueryLog.created_at).asc())
        .all()
    )
    trend = [{"day": str(d), "count": int(c)} for d, c in trend_rows]
    trend_max = max((t["count"] for t in trend), default=0)

    return {
        "days": days,
        "total": total,
        "top_intents": top_intents,
        "unserved": unserved,
        "unserved_total": unserved_total,
        "by_category": by_category,
        "trend": trend,
        "trend_max": trend_max,
    }
