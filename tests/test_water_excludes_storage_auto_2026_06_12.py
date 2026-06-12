"""The on-the-water / boat-rental listing must not surface storage / auto rows.

QA diagnostic 2026-06-12 (P0-1): "which launch ramp is best for a 28-foot boat?"
led with a detailing shop + two storage yards + two auto-repair shops. Root
cause: the broad legacy ``lake_recreation`` tag is a 260-row catch-all full of
storage / auto / RV businesses, and the rating-sorted water listing surfaced the
high-review ones. Fix: exclude definitely-non-water Google primary categories
(storage, car_repair, rv_park, …) from the water bucket. NULL Google category is
kept; ``boat_repair`` is exempt. This test guards the Google-category exclusion
specifically (a row whose NAME would not trip the existing storage name-token
exclusion, only its Google type).
"""

from __future__ import annotations

import uuid

import pytest

from app.chat.intents.runtime import try_intent_layer
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.db.seed_helpers import derive_provider_slug

_LAT, _LNG = 34.4839, -114.3225


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _seed_provider(
    session, name, *, category, subcategory=None, google_primary_category=None, google_rating=None
):
    prov = Provider(
        provider_name=name,
        category=category,
        subcategory=subcategory,
        google_primary_category=google_primary_category,
        google_rating=google_rating,
        slug=derive_provider_slug(session, name),
        source="test",
        lat=_LAT,
        lng=_LNG,
        draft=False,
        is_active=True,
    )
    session.add(prov)
    create_provider_and_entity(session, prov)
    session.commit()
    return prov


def _cleanup(db, *provs):
    from sqlalchemy import delete

    from app.db.models import Entity, EntityCategory, Location

    for p in provs:
        eid = p.entity_id
        db.execute(delete(Provider).where(Provider.id == p.id))
        if eid:
            db.execute(delete(Location).where(Location.entity_id == eid))
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
    db.commit()


def test_boat_rental_excludes_storage_and_auto_by_google_type(db, monkeypatch):
    """A storage yard whose NAME wouldn't trip the storage name-token exclusion
    (no 'storage'/'repair' in the name) must still be dropped via its Google
    primary category, while a genuine rental surfaces."""
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    suf = uuid.uuid4().hex[:8]
    # Name carries the rental token "boat" but Google type is storage -> excluded
    # only by the new Google-category filter, not the name-token filter.
    storage = _seed_provider(
        db,
        f"Lakeside Boat Holdings {suf}",
        category="lake_recreation",
        subcategory="on-the-water",
        google_primary_category="storage",
        google_rating=5.0,
    )
    auto = _seed_provider(
        db,
        f"Channel Boat Works {suf}",
        category="lake_recreation",
        subcategory="on-the-water",
        google_primary_category="car_repair",
        google_rating=5.0,
    )
    rental = _seed_provider(
        db,
        f"Havasu RoadRunner Boat Rentals {suf}",
        category="boat_rental",
        subcategory="on-the-water",
        google_primary_category=None,
        google_rating=4.5,
    )
    try:
        ans = try_intent_layer("where can i rent a boat", db)
        assert ans is not None
        assert ans.intent_key == "boat_rental"
        names = [it.get("name") for it in ans.component_data.get("items", [])]
        assert f"Havasu RoadRunner Boat Rentals {suf}" in names
        assert f"Lakeside Boat Holdings {suf}" not in names
        assert f"Channel Boat Works {suf}" not in names
    finally:
        _cleanup(db, storage, auto, rental)
