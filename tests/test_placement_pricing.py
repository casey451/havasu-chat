"""Phase F §8 — placement price-book lookup (serving.price_for) fallback."""

from __future__ import annotations

import uuid

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.monetization_models import PlacementPrice, PlacementType
from app.monetization import serving


def test_price_for_specific_and_category_default_fallback() -> None:
    suf = uuid.uuid4().hex[:8]
    cat = f"testcat-{suf}"
    with SessionLocal() as db:
        db.add_all(
            [
                PlacementPrice(
                    placement_type=PlacementType.category_rank.value,
                    category_slug=cat,
                    rank_tier=1,
                    price_cents=14900,
                    active=True,
                ),
                PlacementPrice(
                    placement_type=PlacementType.category_rank.value,
                    category_slug=cat,
                    rank_tier=None,  # category default for any tier without a row
                    price_cents=9900,
                    active=True,
                ),
            ]
        )
        db.commit()
        try:
            # Exact (type, category, tier) wins.
            assert (
                serving.price_for(
                    db, PlacementType.category_rank.value, category_slug=cat, rank_tier=1
                )
                == 14900
            )
            # No tier-3 row → falls back to the (category, NULL-tier) default.
            assert (
                serving.price_for(
                    db, PlacementType.category_rank.value, category_slug=cat, rank_tier=3
                )
                == 9900
            )
        finally:
            db.execute(
                delete(PlacementPrice).where(PlacementPrice.category_slug == cat)
            )
            db.commit()


def test_price_for_skips_inactive_rows() -> None:
    suf = uuid.uuid4().hex[:8]
    cat = f"testcat-{suf}"
    with SessionLocal() as db:
        db.add_all(
            [
                PlacementPrice(
                    placement_type=PlacementType.category_rank.value,
                    category_slug=cat,
                    rank_tier=1,
                    price_cents=5000,
                    active=False,  # retired exact price — must be ignored
                ),
                PlacementPrice(
                    placement_type=PlacementType.category_rank.value,
                    category_slug=cat,
                    rank_tier=None,
                    price_cents=8000,
                    active=True,  # active category default
                ),
            ]
        )
        db.commit()
        try:
            # The exact (cat, tier=1) row is inactive, so the lookup skips it and
            # falls through to the active (cat, NULL-tier) default.
            assert (
                serving.price_for(
                    db, PlacementType.category_rank.value, category_slug=cat, rank_tier=1
                )
                == 8000
            )
        finally:
            db.execute(
                delete(PlacementPrice).where(PlacementPrice.category_slug == cat)
            )
            db.commit()
