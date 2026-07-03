"""Alerts + weekend-digest opt-in ORM models, sliced out of app/db/models.py
(audit 2026-07-01 decomposition): AlertSubscription, AlertDispatched,
DigestSubscription.

Registered with ``Base.metadata`` like ``monetization_models`` — imports only
``Base`` (+ SQLAlchemy), never ``app.db.models`` or ``entity_dual_write``, so it
is cycle-free regardless of load order. The ``User`` link is a string
relationship resolved lazily from the mapper registry. ``app.db.models``
re-exports these so existing imports keep resolving.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models import User


class AlertSubscription(Base):
    """User opt-in for conditions / traffic alerts (Phase 3.1 storage; dispatcher Phase 8)."""

    __tablename__ = "alert_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('heat_advisory', 'aqi_alert', 'lake_hazard', 'event_traffic')",
            name="ck_alert_subscriptions_alert_type",
        ),
        CheckConstraint(
            "delivery_channel IN ('email', 'sms')",
            name="ck_alert_subscriptions_delivery_channel",
        ),
        UniqueConstraint(
            "user_id",
            "alert_type",
            "delivery_channel",
            name="uq_alert_subscriptions_user_type_channel",
        ),
        Index("ix_alert_subscriptions_user_id", "user_id"),
        Index("ix_alert_subscriptions_alert_type", "alert_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="email", server_default="email"
    )
    paused_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    user: Mapped["User"] = relationship(
        "User", back_populates="alert_subscriptions", foreign_keys=[user_id]
    )
    dispatches: Mapped[list["AlertDispatched"]] = relationship(
        "AlertDispatched", back_populates="subscription", passive_deletes=True
    )


class AlertDispatched(Base):
    """Audit trail for alert sends (Phase 3.1)."""

    __tablename__ = "alerts_dispatched"
    __table_args__ = (
        CheckConstraint(
            "delivery_status IN ('queued', 'sent', 'failed', 'bounced')",
            name="ck_alerts_dispatched_delivery_status",
        ),
        Index("ix_alerts_dispatched_subscription_id", "subscription_id"),
        Index("ix_alerts_dispatched_dispatched_at", "dispatched_at"),
        Index("ix_alerts_dispatched_delivery_status", "delivery_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    subscription_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alert_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_data: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False)
    body_snippet: Mapped[str | None] = mapped_column(String(280), nullable=True)

    subscription: Mapped["AlertSubscription"] = relationship(
        "AlertSubscription", back_populates="dispatches", foreign_keys=[subscription_id]
    )


class DigestSubscription(Base):
    """User opt-in for the "This weekend in Havasu" digest (Phase A3).

    Deliberately separate from :class:`AlertSubscription` (conditions/traffic
    alerts, owned by a sibling lane). This row is purely an opt-in record;
    the digest *builder* (:mod:`app.digest.builder`) and dry-run *render*
    (:mod:`app.digest.render`) are decoupled from delivery — actual send
    cadence/cron is a flagged Casey product decision and is NOT wired here.

    Opt-in posture: a row exists only when the user has explicitly opted in
    (``enabled`` defaults True on insert; toggling off sets it False rather
    than deleting, to preserve the opt-in history). No auto-enrollment.
    """

    __tablename__ = "digest_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "delivery_channel IN ('email')",
            name="ck_digest_subscriptions_delivery_channel",
        ),
        UniqueConstraint(
            "user_id",
            "delivery_channel",
            name="uq_digest_subscriptions_user_channel",
        ),
        Index("ix_digest_subscriptions_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    delivery_channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="email", server_default="email"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
