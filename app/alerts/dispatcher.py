"""Alert dispatch orchestration (Phase 8a)."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.dedup import is_duplicate
from app.alerts.evaluator import evaluate_alert_type
from app.alerts.render import render_alert_email
from app.alerts.thresholds import ALERT_TYPES_V1, EVENT_TRAFFIC_DEFERRED
from app.alerts.venue_context import indoor_favorites_for_user, land_favorites_for_user
from app.auth.email_sender import send_alert_email
from app.db.models import AlertDispatched, AlertSubscription, User

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _alerts_manage_url() -> str:
    base = (os.environ.get("AUTH_MAGIC_LINK_BASE_URL") or "").rstrip("/")
    return f"{base}/account/alerts" if base else "/account/alerts"


def _favorites_for_alert(db: Session, user_id: str, alert_type: str) -> list:
    if alert_type in ("heat_advisory", "aqi_alert"):
        return indoor_favorites_for_user(db, user_id)
    if alert_type == "lake_hazard":
        return land_favorites_for_user(db, user_id)
    return []


def _record_dispatch(
    db: Session,
    *,
    subscription_id: str,
    alert_type: str,
    trigger_data: dict[str, Any],
    delivery_status: str,
    body_snippet: str | None = None,
    now: datetime,
) -> None:
    db.add(
        AlertDispatched(
            id=str(uuid4()),
            subscription_id=subscription_id,
            alert_type=alert_type,
            trigger_data=trigger_data,
            dispatched_at=now,
            delivery_status=delivery_status,
            body_snippet=(body_snippet or "")[:280] or None,
        )
    )


def dispatch_alerts(
    db: Session,
    *,
    dry_run: bool = False,
    alert_type_filter: str | None = None,
    user_id_filter: str | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or _utc_now()
    stats = {"evaluated": 0, "sent": 0, "suppressed_dedupe": 0, "suppressed_paused": 0, "failed": 0}

    types = [alert_type_filter] if alert_type_filter else list(ALERT_TYPES_V1)
    for alert_type in types:
        if alert_type == EVENT_TRAFFIC_DEFERRED:
            continue
        evaluation = evaluate_alert_type(db, alert_type)
        stats["evaluated"] += 1
        if not evaluation.fired:
            continue

        q = (
            select(AlertSubscription)
            .join(User, User.id == AlertSubscription.user_id)
            .where(AlertSubscription.alert_type == alert_type)
            .where(AlertSubscription.delivery_channel == "email")
            .where(User.is_active.is_(True))
        )
        if user_id_filter:
            q = q.where(AlertSubscription.user_id == user_id_filter)
        subscriptions = list(db.scalars(q).all())

        for sub in subscriptions:
            if sub.paused_until is not None and sub.paused_until > now:
                stats["suppressed_paused"] += 1
                if not dry_run:
                    _record_dispatch(
                        db,
                        subscription_id=sub.id,
                        alert_type=alert_type,
                        trigger_data=evaluation.trigger_data,
                        delivery_status="suppressed_paused",
                        now=now,
                    )
                continue

            if is_duplicate(db, sub.id, alert_type, now):
                stats["suppressed_dedupe"] += 1
                if not dry_run:
                    _record_dispatch(
                        db,
                        subscription_id=sub.id,
                        alert_type=alert_type,
                        trigger_data=evaluation.trigger_data,
                        delivery_status="suppressed_dedupe",
                        now=now,
                    )
                continue

            user = db.get(User, sub.user_id)
            if user is None or not user.email:
                continue

            favorites = _favorites_for_alert(db, sub.user_id, alert_type)
            subject, html_body, text_body = render_alert_email(
                alert_type,
                trigger=evaluation.trigger_data,
                favorites=favorites,
                alerts_url=_alerts_manage_url(),
            )

            if dry_run:
                logger.info(
                    "alerts.dry_run",
                    extra={
                        "alert_type": alert_type,
                        "user_id": sub.user_id,
                        "subject": subject,
                    },
                )
                stats["sent"] += 1
                continue

            try:
                send_alert_email(
                    to_email=user.email,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                )
                _record_dispatch(
                    db,
                    subscription_id=sub.id,
                    alert_type=alert_type,
                    trigger_data=evaluation.trigger_data,
                    delivery_status="sent",
                    body_snippet=text_body[:280],
                    now=now,
                )
                stats["sent"] += 1
            except Exception:
                logger.exception(
                    "alerts.send_failed",
                    extra={"alert_type": alert_type, "user_id": sub.user_id},
                )
                _record_dispatch(
                    db,
                    subscription_id=sub.id,
                    alert_type=alert_type,
                    trigger_data=evaluation.trigger_data,
                    delivery_status="failed",
                    now=now,
                )
                stats["failed"] += 1

    if not dry_run:
        db.commit()
    return stats
