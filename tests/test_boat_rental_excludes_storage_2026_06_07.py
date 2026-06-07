"""boat_rental must not surface storage / repair yards.

After USE_INTENT_LAYER went live (2026-06-07), "where can i rent a boat" led with
"Boat Storage of Lake Havasu": the boat_rental name-token narrowing matches any
"boat", so storage and repair yards outranked actual rentals. See
docs/cowork/HANDOFF_INTENT_FLAG.md ("Quality note"). Fix excludes storage/repair-
type names from the rental narrowing.
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


def _seed_provider(session, name, *, category, subcategory=None, google_rating=None):
    prov = Provider(
        provider_name=name,
        category=category,
        subcategory=subcategory,
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


def test_boat_rental_excludes_storage_and_repair(db, monkeypatch):
    """The rentals list must not contain storage/repair businesses.

    "Boat Storage of Lake Havasu" matches the boat_rental name token "boat" and,
    with a high rating, led the list. Storage/repair-type names are excluded from
    the rental narrowing while a genuine rental still surfaces.
    """
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    suf = uuid.uuid4().hex[:8]
    storage = _seed_provider(
        db, f"Boat Storage of Lake Havasu {suf}", category="boat_rental",
        subcategory="on-the-water", google_rating=4.9,
    )
    repair = _seed_provider(
        db, f"Havasu Boat Repair {suf}", category="boat_repair",
        subcategory="on-the-water", google_rating=4.8,
    )
    rental = _seed_provider(
        db, f"Havasu RoadRunner Boat Rentals {suf}", category="boat_rental",
        subcategory="on-the-water", google_rating=4.5,
    )
    try:
        ans = try_intent_layer("where can i rent a boat", db)
        assert ans is not None
        assert ans.intent_key == "boat_rental"
        names = [it.get("name") for it in ans.component_data.get("items", [])]
        assert f"Havasu RoadRunner Boat Rentals {suf}" in names
        assert f"Boat Storage of Lake Havasu {suf}" not in names
        assert f"Havasu Boat Repair {suf}" not in names
    finally:
        _cleanup(db, storage, repair, rental)
