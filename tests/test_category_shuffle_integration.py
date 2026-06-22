"""§2.1/§2.2 integration: the default category page renders ≤cap paid cards
pinned + a daily-shuffled >gate pool + a labeled "New / Not yet rated" tail,
driven through ``category_listing`` (not the pure helper).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete

from app.categories.queries import CategoryFacets, category_listing
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.db.monetization_models import Placement, PlacementStatus, PlacementType

_NOW = datetime(2026, 1, 5, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ)


def _provider(name: str, rating: float | None, reviews: int | None) -> Provider:
    return Provider(
        provider_name=name,
        category="restaurant",
        subcategory="restaurants",
        google_primary_category="restaurant",
        google_rating=rating,
        google_review_count=reviews,
        is_active=True,
        draft=False,
        pending_review=False,
        source="test-shuffle",
    )


def test_default_listing_tail_labels_no_review_business_below_rated() -> None:
    suf = uuid.uuid4().hex[:8]
    rated_name = f"Rated Grill {suf}"   # 4.6 / 80 → quality pool
    new_name = f"Brand New Eatery {suf}"  # no reviews → tail
    with SessionLocal() as db:
        rated = _provider(rated_name, 4.6, 80)
        new = _provider(new_name, None, None)
        db.add_all([rated, new])
        db.commit()
        eids = [rated.entity_id, new.entity_id]

    try:
        cards, total = category_listing(
            db_session_factory(), "eat-drink", now=_NOW, facets=CategoryFacets(), limit=500
        )
        by_name = {c["name"]: c for c in cards}
        assert rated_name in by_name and new_name in by_name  # never excluded
        # The no-review business is flagged for the tail; the rated one is not.
        assert by_name[new_name]["is_new_unrated"] is True
        assert by_name[rated_name]["is_new_unrated"] is False
        # Tail sits below the rated pool.
        order = [c["name"] for c in cards]
        assert order.index(rated_name) < order.index(new_name)
        assert total >= 2
    finally:
        _cleanup(eids)


def test_active_placement_pins_and_labels_sponsored_on_default_listing() -> None:
    suf = uuid.uuid4().hex[:8]
    paid_name = f"Paid Pin Cafe {suf}"
    other_name = f"Organic Cafe {suf}"
    with SessionLocal() as db:
        paid = _provider(paid_name, 4.5, 60)
        other = _provider(other_name, 4.7, 200)
        db.add_all([paid, other])
        db.commit()
        eids = [paid.entity_id, other.entity_id]
        pid = paid.id
        # Seed a Placement row directly (no live purchase) so the "Sponsored"
        # rendering can be exercised — exactly the brief's seed-a-row hook.
        db.add(
            Placement(
                provider_id=pid,
                placement_type=PlacementType.category_rank.value,
                category_slug="eat-drink",
                rank_tier=1,
                status=PlacementStatus.active.value,
                billing_type="monthly",
                price_cents=0,
            )
        )
        db.commit()

    try:
        cards, _total = category_listing(
            db_session_factory(), "eat-drink", now=_NOW, facets=CategoryFacets(), limit=500
        )
        assert cards[0]["name"] == paid_name           # tier-1 pinned to the top
        assert cards[0]["is_sponsored"] is True         # labeled "Sponsored"
        by_name = {c["name"]: c for c in cards}
        assert by_name[other_name]["is_sponsored"] is False
    finally:
        with SessionLocal() as db:
            db.execute(delete(Placement).where(Placement.provider_id == pid))
            db.commit()
        _cleanup(eids)


def db_session_factory() -> SessionLocal:  # type: ignore[valid-type]
    return SessionLocal()


def _cleanup(entity_ids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_(entity_ids)))
        db.execute(delete(Entity).where(Entity.id.in_(entity_ids)))
        db.commit()
