"""Per-subscription alert dedup (Phase 8a)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.alerts.thresholds import ALERT_DEDUPE_WINDOW_HOURS
from app.db.models import AlertDispatched


def is_duplicate(
    db: Session,
    subscription_id: str,
    alert_type: str,
    now: datetime,
) -> bool:
    cutoff = now - timedelta(hours=ALERT_DEDUPE_WINDOW_HOURS)
    return (
        db.query(AlertDispatched)
        .filter(
            AlertDispatched.subscription_id == subscription_id,
            AlertDispatched.alert_type == alert_type,
            AlertDispatched.delivery_status == "sent",
            AlertDispatched.dispatched_at > cutoff,
        )
        .first()
        is not None
    )
