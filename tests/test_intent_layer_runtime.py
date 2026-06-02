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
    monkeypatch.delenv("USE_INTENT_LAYER", raising=False)
    assert try_intent_layer("i need a plumber", db) is None


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


def test_honest_empty_offers_contribute(db, monkeypatch):
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    # No plumber seeded -> honest empty, never fabricated.
    ans = try_intent_layer("i need a plumber", db)
    assert ans is not None
    assert ans.result_count == 0
    assert "/contribute" in ans.text
    assert "don't have" in ans.text.lower()

    row = _latest_query_log(db, "find_service")
    assert row is not None
    assert row.result_count == 0


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
