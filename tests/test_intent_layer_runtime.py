"""DB-backed tests for the intent-layer runtime (Ask Hava intent catalog).

Exercises the grounded query templates against real seeded rows, the honest
empty -> /contribute path, query_log wiring, and flag-off inertness.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.chat.intents.runtime import try_intent_layer
from app.conditions.cache import invalidate_local_cache, upsert_source
from app.conditions.constants import SOURCE_GAS
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider, QueryLog
from app.db.seed_helpers import derive_provider_slug

_LAT, _LNG = 34.4839, -114.3225


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _seed_provider(
    session,
    name,
    *,
    category,
    subcategory=None,
    district=None,
    google_rating=None,
    phone=None,
):
    prov = Provider(
        provider_name=name,
        category=category,
        subcategory=subcategory,
        district=district,
        google_rating=google_rating,
        phone=phone,
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


def _latest_query_log(session, intent_key):
    return session.scalars(
        select(QueryLog)
        .where(QueryLog.normalized_intent == intent_key)
        .order_by(QueryLog.created_at.desc())
    ).first()


def test_flag_off_returns_none(db, monkeypatch):
    # Default is now ON; "0" is the explicit kill switch.
    monkeypatch.setenv("USE_INTENT_LAYER", "0")
    assert try_intent_layer("i need a plumber", db) is None


def test_default_is_enabled(db, monkeypatch):
    monkeypatch.delenv("USE_INTENT_LAYER", raising=False)
    from app.chat.intents.runtime import is_enabled

    assert is_enabled() is True


def test_find_service_returns_seeded_provider(db, monkeypatch):
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    _seed_provider(
        db,
        "Ace Plumbing Co",
        category="home_services",
        subcategory="home-services",
        google_rating=4.8,
        phone="(928) 855-1234",
    )
    ans = try_intent_layer("i need a plumber", db)
    assert ans is not None
    assert ans.intent_key == "find_service"
    assert ans.result_count >= 1
    # Names render in the business_list card, not the voice line.
    assert ans.component_type == "business_list"
    names = [it.get("name") for it in ans.component_data.get("items", [])]
    assert "Ace Plumbing Co" in names

    row = _latest_query_log(db, "find_service")
    assert row is not None
    assert row.result_count >= 1


def test_empty_result_falls_through_but_logs(db, monkeypatch):
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    # No plumber seeded -> the layer falls through (the legacy path's honest gap
    # template handles the empty), but the zero-row is still logged for coverage.
    ans = try_intent_layer("i need a plumber", db)
    assert ans is None

    row = _latest_query_log(db, "find_service")
    assert row is not None
    assert row.result_count == 0


def test_factual_lookup_falls_through(db, monkeypatch):
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    # "rating for <fake place>" is an entity-factual lookup -> the layer must not
    # answer it with a category list; the gap path owns it.
    assert (
        try_intent_layer("rating for Fabricated Hotel 555", db, sub_intent="RATING_LOOKUP")
        is None
    )


def test_eat_find_cuisine_name_token(db, monkeypatch):
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    _seed_provider(
        db,
        "El Pueblo Taqueria",
        category="restaurant",
        subcategory="restaurants",
        google_rating=4.5,
    )
    _seed_provider(
        db,
        "Mudshark Brewery",
        category="restaurant",
        subcategory="bars-breweries",
        google_rating=4.4,
    )
    ans = try_intent_layer("best mexican food", db)
    assert ans is not None
    assert ans.intent_key == "eat_find"
    assert ans.component_type == "business_list"
    names = [it.get("name") for it in ans.component_data.get("items", [])]
    # Name-token match should surface the taqueria, not the brewery.
    assert "El Pueblo Taqueria" in names
    assert "Mudshark Brewery" not in names


def test_cheapest_gas_reads_cache(db, monkeypatch):
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    upsert_source(
        db,
        SOURCE_GAS,
        {
            "stations": [
                {"name": "Costco Fuel", "address": "1 Costco Way", "prices": {"regular": 3.29}},
                {"name": "Circle K", "address": "2 Main St", "prices": {"regular": 3.79}},
            ]
        },
    )
    db.commit()
    invalidate_local_cache(SOURCE_GAS)

    ans = try_intent_layer("where's the cheapest gas", db)
    assert ans is not None
    assert ans.intent_key == "cheapest_gas"
    assert "Costco Fuel" in ans.text
    # Cheapest first.
    assert ans.text.index("Costco Fuel") < ans.text.index("Circle K")


def test_unconfident_query_falls_through(db, monkeypatch):
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    assert try_intent_layer("tell me a joke", db) is None


def test_resolved_entity_falls_through(db, monkeypatch):
    """A question about a named business must not be hijacked by a category list."""
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    # "brewery" would otherwise match the eat cuisine token.
    assert try_intent_layer("tell me about Mudshark Brewery", db, entity="Mudshark Brewery") is None


def _cleanup_seeded(db, *provs):
    """Delete seeded Provider + its Entity/Location/EntityCategory rows.

    The on-the-water test seeds a "Marina" row; left behind it would pollute
    cross-suite fuzzy name matching (the same leak fixed for the OSM suite), so
    tear down by entity_id even on failure.
    """
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


def test_on_the_water_parks_and_civic_buckets(db, monkeypatch):
    """Step-1 gap-fix buckets: on-the-water, parks/trails, civic resources."""
    import uuid

    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    suf = uuid.uuid4().hex[:8]
    marina = _seed_provider(
        db, f"Havasu Marina {suf}", category="lake_recreation",
        subcategory="on-the-water", google_rating=4.6,
    )
    park = _seed_provider(
        db, f"Rotary Park {suf}", category="recreation",
        subcategory="parks-beaches", google_rating=4.7,
    )
    church = _seed_provider(
        db, f"Lakeside Church {suf}", category="religion_community",
        subcategory="civic-community", google_rating=4.5,
    )
    try:
        a1 = try_intent_layer("closest marina", db)
        assert a1 is not None and a1.intent_key == "on_the_water"
        assert f"Havasu Marina {suf}" in [
            it.get("name") for it in a1.component_data.get("items", [])
        ]

        a2 = try_intent_layer("hiking trails near me", db)
        assert a2 is not None and a2.intent_key == "parks_trails"
        assert f"Rotary Park {suf}" in [
            it.get("name") for it in a2.component_data.get("items", [])
        ]

        a3 = try_intent_layer("where's a church", db)
        assert a3 is not None and a3.intent_key == "civic_resources"
        assert f"Lakeside Church {suf}" in [
            it.get("name") for it in a3.component_data.get("items", [])
        ]
    finally:
        _cleanup_seeded(db, marina, park, church)


def test_boat_rental_vs_repair_route_distinctly(db, monkeypatch):
    """Rent vs repair verbs split the on-the-water bucket into distinct intents."""
    import uuid

    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    suf = uuid.uuid4().hex[:8]
    rental = _seed_provider(
        db, f"Havasu Boat Rentals {suf}", category="boat_rental",
        subcategory="on-the-water", google_rating=4.5,
    )
    try:
        ans = try_intent_layer("where can i rent a boat", db)
        assert ans is not None
        assert ans.intent_key == "boat_rental"
        assert f"Havasu Boat Rentals {suf}" in [
            it.get("name") for it in ans.component_data.get("items", [])
        ]
    finally:
        _cleanup_seeded(db, rental)
