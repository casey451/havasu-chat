"""Item B -- contact (website/phone) identity tier in reconcile_hit.

The reconciler grows a tier between google_place_id and geo: when a payload's
normalized website domain or phone uniquely matches an existing active Provider,
it merges onto that entity even with no geo/name overlap (identity beats geo).

The tier is gated behind INGEST_CONTACT_TIER_ENABLED (default OFF) because it
changes dedup behavior for EVERY provider source; tests set the env via
monkeypatch.setenv to exercise it.

Uses the real Postgres session + dual-write helper (mirroring
tests/test_phase4_ingest_reconciler.py and tests/test_golakehavasu_partners.py)
so the before_flush promotion + Location rows exist exactly as in production.
"""

from __future__ import annotations

import pytest

from app.contrib.ingest_base import EntityPayload
from app.contrib.ingest_reconciler import reconcile_hit
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.db.seed_helpers import derive_provider_slug

# A Lake Havasu City anchor; the "contact beats geo" case puts a candidate far
# from this so only the contact tier (not geo) could resolve the merge.
_LAT = 34.4839
_LNG = -114.3225


@pytest.fixture
def db_session():
    """Transactional session, rolled back after each test (no committed writes)."""
    with SessionLocal() as session:
        yield session
        session.rollback()


def create_provider_and_entity_row(
    session,
    name: str,
    *,
    lat: float | None = None,
    lng: float | None = None,
    website: str | None = None,
    phone: str | None = None,
    source: str = "google_places",
    google_place_id: str | None = None,
) -> Provider:
    """Create a Provider (+ Entity + Location via the dual-write before_flush).

    Mirrors the _mk_provider / _google_provider helpers in the existing
    reconciler/partner tests.
    """
    prov = Provider(
        provider_name=name,
        category="eat-drink",
        slug=derive_provider_slug(session, name),
        source=source,
        google_place_id=google_place_id,
        lat=lat,
        lng=lng,
        website=website,
        phone=phone,
        draft=False,
        is_active=True,
    )
    session.add(prov)
    create_provider_and_entity(session, prov)
    session.flush()
    return prov


def _payload(
    name: str,
    *,
    lat: float | None = None,
    lng: float | None = None,
    website: str | None = None,
    phone: str | None = None,
    source: str = "osm",
) -> EntityPayload:
    return EntityPayload(
        name=name,
        entity_type="place",
        source=source,
        lat=lat,
        lng=lng,
        website=website,
        phone=phone,
    )


def test_contact_tier_website_unique_match_updates(db_session, monkeypatch) -> None:
    monkeypatch.setenv("INGEST_CONTACT_TIER_ENABLED", "1")
    prov = create_provider_and_entity_row(
        db_session,
        "Lobster 3 Ways Food Truck",
        website="http://www.lobster3ways.com",
    )
    # Different name, no geo, no google_place_id -- only the website matches.
    payload = _payload("Lobster 3 Ways", website="https://lobster3ways.com/menu")
    rec = reconcile_hit(db_session, payload)
    assert rec.action == "update"
    assert rec.existing_id == prov.entity_id
    assert rec.reason == "contact (website/phone) exact match"


def test_contact_tier_phone_unique_match_updates(db_session, monkeypatch) -> None:
    monkeypatch.setenv("INGEST_CONTACT_TIER_ENABLED", "1")
    prov = create_provider_and_entity_row(
        db_session,
        "Barley Brothers Brewery",
        phone="(928) 505-7837",
    )
    payload = _payload("Barley Brothers Restaurant & Brewery", phone="+1 928-505-7837")
    rec = reconcile_hit(db_session, payload)
    assert rec.action == "update"
    assert rec.existing_id == prov.entity_id


def test_contact_tier_ambiguous_website_does_not_uniquely_merge(db_session, monkeypatch) -> None:
    monkeypatch.setenv("INGEST_CONTACT_TIER_ENABLED", "1")
    # Two active providers share the website -> the contact tier finds >1 match
    # and must NOT resolve here. With no geo/name overlap the result falls
    # through to the insert tier; assert it did NOT contact-merge onto either.
    a = create_provider_and_entity_row(db_session, "Plaza Unit A", website="http://sharedplaza.com")
    b = create_provider_and_entity_row(db_session, "Plaza Unit B", website="http://sharedplaza.com")
    payload = _payload("Some Unrelated Tenant", website="https://sharedplaza.com/")
    rec = reconcile_hit(db_session, payload)
    assert rec.reason != "contact (website/phone) exact match"
    assert not (rec.action == "update" and rec.existing_id in {a.entity_id, b.entity_id})
    assert rec.action == "insert"


def test_contact_tier_disabled_by_default_inserts(db_session, monkeypatch) -> None:
    # Same setup as the website-match case but the flag is FORCED off: the tier
    # must not run, so with no geo/name overlap we get an insert. delenv (not just
    # "leave it unset") so this default-behavior assertion holds even when the
    # whole suite is run with INGEST_CONTACT_TIER_ENABLED=1 in the ambient env
    # (the blast-radius check) -- the flag is read at call time, so without this
    # the test would flip to "update" purely from the ambient flag.
    monkeypatch.delenv("INGEST_CONTACT_TIER_ENABLED", raising=False)
    create_provider_and_entity_row(
        db_session,
        "Lobster 3 Ways Food Truck",
        website="http://www.lobster3ways.com",
    )
    payload = _payload("Lobster 3 Ways", website="https://lobster3ways.com/menu")
    rec = reconcile_hit(db_session, payload)
    assert rec.action == "insert"


def test_contact_tier_beats_geo(db_session, monkeypatch) -> None:
    monkeypatch.setenv("INGEST_CONTACT_TIER_ENABLED", "1")
    # Existing provider matches by website but is ~1.1 km away (0.01 deg lat)
    # with a totally different name -- geo (50m + name) could never merge it.
    # The contact tier runs ABOVE geo, so it still updates onto that entity.
    prov = create_provider_and_entity_row(
        db_session,
        "Far Away Diner",
        lat=_LAT + 0.01,
        lng=_LNG,
        website="http://contactbeatsgeo.example",
    )
    payload = _payload(
        "Completely Different Name",
        lat=_LAT,
        lng=_LNG,
        website="https://contactbeatsgeo.example/",
    )
    rec = reconcile_hit(db_session, payload)
    assert rec.action == "update"
    assert rec.existing_id == prov.entity_id
    assert rec.reason == "contact (website/phone) exact match"
