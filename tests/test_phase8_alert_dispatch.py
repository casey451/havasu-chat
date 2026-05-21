"""Phase 8a — alert dispatch + dedup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.alerts.dedup import is_duplicate
from app.alerts.dispatcher import dispatch_alerts
from app.conditions.cache import upsert_source
from app.conditions.constants import SOURCE_NWS_ALERTS
from app.db.database import SessionLocal
from app.db.models import AlertDispatched, AlertSubscription, User


def _user_and_sub(db, alert_type: str = "heat_advisory") -> tuple[User, AlertSubscription]:
    user = User(
        id=str(uuid4()),
        email=f"alert-{uuid4().hex[:8]}@example.com",
        is_active=True,
    )
    db.add(user)
    sub = AlertSubscription(
        id=str(uuid4()),
        user_id=user.id,
        alert_type=alert_type,
        delivery_channel="email",
    )
    db.add(sub)
    db.flush()
    return user, sub


def test_dedup_blocks_repeat_send() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _, sub = _user_and_sub(db)
        db.add(
            AlertDispatched(
                id=str(uuid4()),
                subscription_id=sub.id,
                alert_type="heat_advisory",
                trigger_data={},
                dispatched_at=now - timedelta(hours=1),
                delivery_status="sent",
            )
        )
        db.commit()
        assert is_duplicate(db, sub.id, "heat_advisory", now) is True


def test_dispatch_dry_run_counts_candidates(monkeypatch) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _user_and_sub(db)
        upsert_source(
            db,
            SOURCE_NWS_ALERTS,
            {"alerts": [{"event": "Heat Advisory"}]},
            now=now,
        )
        db.commit()
        stats = dispatch_alerts(db, dry_run=True)
    assert stats["sent"] >= 1
