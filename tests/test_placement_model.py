"""Phase F1: the monetization placement tables register correctly and a price
row round-trips. (Placement itself FKs providers, so the DB-write check uses the
FK-free PlacementPrice; registration is checked via metadata.)"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from app.db.database import Base, SessionLocal
from app.db.monetization_models import (
    BillingType,
    PlacementPrice,
    PlacementStatus,
    PlacementType,
)


def test_placement_tables_registered() -> None:
    assert "placements" in Base.metadata.tables
    assert "placement_prices" in Base.metadata.tables
    cols = set(Base.metadata.tables["placements"].columns.keys())
    assert {
        "provider_id", "placement_type", "category_slug", "rank_tier",
        "status", "billing_type", "price_cents",
    } <= cols


def test_placement_enum_values() -> None:
    assert PlacementType.category_rank.value == "category_rank"
    assert PlacementType.homepage_rotating.value == "homepage_rotating"
    assert PlacementStatus.released.value == "released"
    assert BillingType.recurring.value == "recurring"


def test_placement_price_roundtrip() -> None:
    slug = f"zz-test-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        db.add(PlacementPrice(
            placement_type="category_rank", category_slug=slug,
            rank_tier=1, price_cents=50000,
        ))
        db.commit()
    try:
        with SessionLocal() as db:
            row = db.scalars(
                select(PlacementPrice).where(PlacementPrice.category_slug == slug)
            ).one()
            assert row.rank_tier == 1
            assert row.price_cents == 50000
            assert row.active is True
    finally:
        with SessionLocal() as db:
            db.execute(delete(PlacementPrice).where(PlacementPrice.category_slug == slug))
            db.commit()
