"""T2.2 — dedupe-on-ingest guard in decide_ingest.

A re-scraped listing that shares a NAME plus a street address or phone with an
existing active provider is a confident duplicate. The guard upgrades what the
reconciler would otherwise leave ``ambiguous`` (hidden) or ``insert`` (a second
slug) into an ``update`` onto the existing entity. Unique-match only.

Uses the real Postgres session + dual-write helper (mirrors
tests/test_ingest_reconciler_contact_tier.py) rolled back per test.
"""

from __future__ import annotations

import pytest

from app.contrib.ingest_base import EntityPayload
from app.contrib.scraper_ingest import decide_ingest
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.db.seed_helpers import derive_provider_slug


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session
        session.rollback()


def _mk(session, name, *, address=None, phone=None) -> Provider:
    prov = Provider(
        provider_name=name, category="eat-drink", slug=derive_provider_slug(session, name),
        source="google_places", address=address, phone=phone, draft=False, is_active=True,
    )
    session.add(prov)
    create_provider_and_entity(session, prov)
    session.flush()
    return prov


def _payload(name, *, address=None, phone=None) -> EntityPayload:
    return EntityPayload(name=name, entity_type="place", source="osm", address=address, phone=phone)


def test_name_plus_address_upgrades_to_update(db_session) -> None:
    prov = _mk(db_session, "Joe's Bar", address="100 Main St, Lake Havasu City, AZ")
    # Same name, same street (suite differs, folds equal), no geo/place_id.
    d = decide_ingest(db_session, _payload("Joe's Bar", address="100 Main St Ste 5, Lake Havasu City AZ"))
    assert d.action == "update"
    assert d.existing_id == prov.entity_id
    assert "dedupe guard" in (d.reason or "")


def test_name_plus_phone_upgrades_to_update(db_session) -> None:
    prov = _mk(db_session, "Barley Brothers", phone="(928) 505-7837")
    d = decide_ingest(db_session, _payload("Barley Brothers", phone="+1 928-505-7837"))
    assert d.action == "update"
    assert d.existing_id == prov.entity_id


def test_genuinely_new_business_still_inserts(db_session) -> None:
    _mk(db_session, "Joe's Bar", address="100 Main St")
    d = decide_ingest(db_session, _payload("Brand New Taco Truck", address="999 Nowhere Rd"))
    assert d.action == "insert"


def test_name_only_match_is_not_auto_merged(db_session) -> None:
    # Same name but different address AND phone -> the guard must NOT fire (it needs
    # a shared address or phone); the reconciler's ambiguous decision stands.
    _mk(db_session, "Twin Cafe", address="100 Main St", phone="928-111-1111")
    d = decide_ingest(db_session, _payload("Twin Cafe", address="500 Other Ave", phone="928-222-2222"))
    assert d.action != "update"


def test_ambiguous_non_unique_match_does_not_merge(db_session) -> None:
    # Two active providers share name+address -> not a unique match -> no auto-merge.
    _mk(db_session, "Plaza Nails", address="200 Plaza Way")
    _mk(db_session, "Plaza Nails", address="200 Plaza Way")
    d = decide_ingest(db_session, _payload("Plaza Nails", address="200 Plaza Way"))
    assert d.action != "update"
