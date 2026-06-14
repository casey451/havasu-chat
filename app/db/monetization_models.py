"""Phase F1 — monetization placement data model (additive).

These are NEW tables; the legacy ``Sponsor`` / ``AdSlot`` system in
``app/db/models.py`` is left untouched and will be retired in a later pass once
serving + portal read from here.

Three paid surfaces, straight from the brief §7:
  * ``homepage_rotating`` — a pool of businesses, one shown per page load
    (random rotation); the brief's single homepage ad block.
  * ``category_rank``     — per-category/niche paid ranking, sticky tiers 1..5
    (#1 always renders first; #5 is guaranteed somewhere in the top-5 and
    floats). The float logic lives in the serving/ranking layer, not here.
  * ``page_ad``           — the single paid ad slot on a category/niche page.

Pricing is DATA, not code (``PlacementPrice``), so the admin panel edits every
price/threshold without a deploy (brief §7 "build prices as configurable
values, not hardcoded").

Billing:
  * ``monthly``   — month-to-month; a lapse moves the row to ``released`` and
    frees the spot for someone else.
  * ``recurring`` — holds the spot as long as it keeps paying.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PlacementType(str, Enum):
    homepage_rotating = "homepage_rotating"
    category_rank = "category_rank"
    page_ad = "page_ad"


class PlacementStatus(str, Enum):
    pending = "pending"      # purchased, awaiting payment / approval
    active = "active"        # live
    expired = "expired"      # ended naturally (ends_at passed)
    released = "released"    # month-to-month lapsed — spot freed for re-sale


class BillingType(str, Enum):
    monthly = "monthly"      # month-to-month; a lapse releases the spot
    recurring = "recurring"  # holds the spot while paid


_PLACEMENT_TYPES = "('homepage_rotating', 'category_rank', 'page_ad')"
_PLACEMENT_STATUSES = "('pending', 'active', 'expired', 'released')"
_BILLING_TYPES = "('monthly', 'recurring')"


class Placement(Base):
    """One purchased placement held by a provider."""

    __tablename__ = "placements"
    __table_args__ = (
        CheckConstraint(f"placement_type IN {_PLACEMENT_TYPES}", name="ck_placements_type"),
        CheckConstraint(f"status IN {_PLACEMENT_STATUSES}", name="ck_placements_status"),
        CheckConstraint(f"billing_type IN {_BILLING_TYPES}", name="ck_placements_billing_type"),
        CheckConstraint("rank_tier IS NULL OR (rank_tier BETWEEN 1 AND 5)",
                        name="ck_placements_rank_tier"),
        Index("ix_placements_type_category", "placement_type", "category_slug"),
        Index("ix_placements_status", "status"),
        Index("ix_placements_provider_id", "provider_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider_id: Mapped[str] = mapped_column(
        String, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    placement_type: Mapped[str] = mapped_column(String(24), nullable=False)
    # category/niche slug for category_rank + page_ad; NULL for homepage_rotating.
    category_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 1..5 for category_rank sticky tiers; NULL for other types.
    rank_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PlacementStatus.pending.value
    )
    billing_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BillingType.monthly.value
    )
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_through: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Links to a future AdCreative row (table added with the portal phase).
    creative_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC), nullable=False,
    )


class AdCreative(Base):
    """A reusable ad creative a merchant attaches to a placement (F2).

    URL-based for now (the merchant supplies hosted image URLs, the same shape
    the legacy ``Sponsor`` rows use) — binary upload + storage is a later
    increment. ``Placement.creative_id`` references one of these by id (no DB-level
    FK, mirroring the existing nullable column). When a served placement has a
    creative, the surface prefers its copy/art; otherwise it falls back to the
    provider's own name/description/photo."""

    __tablename__ = "ad_creatives"
    __table_args__ = (
        Index("ix_ad_creatives_provider_id", "provider_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider_id: Mapped[str] = mapped_column(
        String, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cta_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_url_mobile: Mapped[str | None] = mapped_column(String(512), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC), nullable=False,
    )


class PlacementPrice(Base):
    """Admin-editable price book. A row sets the price for a
    (placement_type, category_slug, rank_tier) key; NULL category/tier act as
    defaults so the admin can set a global default and override per category."""

    __tablename__ = "placement_prices"
    __table_args__ = (
        CheckConstraint(f"placement_type IN {_PLACEMENT_TYPES}", name="ck_placement_prices_type"),
        CheckConstraint("rank_tier IS NULL OR (rank_tier BETWEEN 1 AND 5)",
                        name="ck_placement_prices_rank_tier"),
        UniqueConstraint("placement_type", "category_slug", "rank_tier",
                         name="uq_placement_prices_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    placement_type: Mapped[str] = mapped_column(String(24), nullable=False)
    category_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rank_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC), nullable=False,
    )
