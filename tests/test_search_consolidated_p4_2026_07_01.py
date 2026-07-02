"""2026-07-01 consolidated Phase 4 — rental categories.

Routing terms for the new bikes-and-e-bikes / utv-and-offroad-rentals leaves
(created by scripts/backfill_rentals_2026_07_01.py, declared in the taxonomy
seed), the rental-intent remaps off the dealer leaf, the specialty lake-rental
terms, the Wake Surf Adventures unblocklist ([ASK #7]), and the out-of-area
``is_local`` guard on the chat bucket queries ([ASK #8]).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.categories.leaf_query import (
    _QUERY_TO_LEAF,
    _QUERY_TO_LEAF_RENTALS_2026_07_01,
    _normalize,
)
from app.chat.intents import queries as q
from app.chat.intents.resolver import resolve
from app.contrib.ingest_suppression import is_suppressed_business
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.db.seed_helpers import derive_provider_slug

_SEED = Path(__file__).resolve().parents[1] / "docs" / "proposals" / "taxonomy-seed.json"

_ROUTING_CASES = {
    "golf cart rental": "golf-carts",
    "golf cart rentals": "golf-carts",
    "bike shop": "bikes-and-e-bikes",
    "bike rental": "bikes-and-e-bikes",
    "bike rentals": "bikes-and-e-bikes",
    "e-bike rental": "bikes-and-e-bikes",
    "ebike rental": "bikes-and-e-bikes",
    "bicycle shop": "bikes-and-e-bikes",
    "bike repair": "bikes-and-e-bikes",
    "atv rental": "utv-and-offroad-rentals",
    "atv rentals": "utv-and-offroad-rentals",
    "utv rental": "utv-and-offroad-rentals",
    "utv rentals": "utv-and-offroad-rentals",
    "side by side rental": "utv-and-offroad-rentals",
    "rzr rental": "utv-and-offroad-rentals",
    "off road rentals": "utv-and-offroad-rentals",
    "atv tours": "utv-and-offroad-rentals",
    "utv tours": "utv-and-offroad-rentals",
    "houseboat rental": "boat-and-watercraft-rentals",
    "houseboats": "boat-and-watercraft-rentals",
    "party boat rental": "boat-and-watercraft-rentals",
    "beach chair rental": "boat-and-watercraft-rentals",
    "yacht rental": "boat-tours-and-charters",
    "yacht charter": "boat-tours-and-charters",
    "rv rental": "rv-sales-and-service",
    "rv rentals": "rv-sales-and-service",
}


def test_rental_terms_route_to_expected_leaf():
    for raw, slug in _ROUTING_CASES.items():
        norm = _normalize(raw)
        assert norm in _QUERY_TO_LEAF, (raw, norm)
        assert _QUERY_TO_LEAF[norm] == slug, (raw, norm, _QUERY_TO_LEAF[norm])


def test_rental_keys_normalize_to_themselves():
    for terms in _QUERY_TO_LEAF_RENTALS_2026_07_01.values():
        for term in terms:
            assert _normalize(term) == term, (term, _normalize(term))


def test_bare_vehicle_nouns_and_trails_unchanged():
    # Dealers keep the bare vehicle nouns; trails keep the -ing forms.
    assert _QUERY_TO_LEAF["powersports"] == "powersports-and-atv"
    assert _QUERY_TO_LEAF["atv"] == "powersports-and-atv"
    assert _QUERY_TO_LEAF["utv"] == "powersports-and-atv"
    assert _QUERY_TO_LEAF["side by side"] == "powersports-and-atv"
    assert _QUERY_TO_LEAF["off roading"] == "off-road-and-ohv"
    assert _QUERY_TO_LEAF["off road"] == "off-road-and-ohv"
    assert _QUERY_TO_LEAF["golf carts"] == "golf-carts"
    assert _QUERY_TO_LEAF["golf"] == "golf-courses"


def test_new_leaves_declared_in_seed():
    seed = json.loads(_SEED.read_text(encoding="utf-8"))
    leaves = seed["things-to-do-and-attractions"]["leaves"]
    assert "bikes-and-e-bikes" in leaves
    assert "utv-and-offroad-rentals" in leaves


def test_wake_surf_adventures_unblocklisted():
    # [ASK #7] approved: WSA is active — the reinstate rides the gated script,
    # the durable blocklist entry is gone so the re-scrape can't re-kill it.
    assert not is_suppressed_business("Wake Surf Adventures")
    # The genuinely-dead entries stay.
    assert is_suppressed_business(
        "Lake Havasu Marine Association Designated Operator Program"
    )


def test_rental_terms_dont_corrupt_spell_vocab():
    from app.chat.normalizer import spell_correct

    for phrase in ("hike rental", "bake shop", "cart repair", "yacht club"):
        assert spell_correct(phrase) == phrase, (phrase, spell_correct(phrase))


# --- [ASK #8] is_local guard on the chat bucket query --------------------------

_LAT, _LNG = 34.4839, -114.3225


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _seed(session, name, *, is_local):
    prov = Provider(
        provider_name=name,
        category="retail",
        subcategory="specialty",
        slug=derive_provider_slug(session, name),
        source="test",
        lat=_LAT,
        lng=_LNG,
        draft=False,
        is_active=True,
        is_local=is_local,
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


def test_chat_bucket_query_excludes_out_of_area(db):
    suf = uuid.uuid4().hex[:8]
    local = _seed(db, f"Main Street Gun Gallery {suf}", is_local=True)
    ooa = _seed(db, f"Kingman Gun Gallery {suf}", is_local=False)
    unknown = _seed(db, f"Mystery Gun Gallery {suf}", is_local=None)
    try:
        resolved = resolve("gun gallery store")
        assert resolved is not None and resolved.intent_key == "shopping_find"
        result = q.run_query(resolved, db, raw_query="gun gallery store")
        names = {r["name"] for r in result.rows}
        assert local.provider_name in names
        assert unknown.provider_name in names  # NULL is kept, never assumed far
        assert ooa.provider_name not in names
    finally:
        _cleanup(db, local, ooa, unknown)
