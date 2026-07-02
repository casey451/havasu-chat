"""Tests for the shared scraper ingest contract (dup-prevention funnel).

Run: python -m pytest tests/test_scraper_ingest.py -q
"""

from __future__ import annotations

import pytest

from app.contrib.ingest_base import EntityPayload
from app.contrib.scraper_ingest import (
    decide_ingest,
    normalize_payload,
)
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.db.seed_helpers import derive_provider_slug

_LAT = 34.4839
_LNG = -114.3225


@pytest.fixture
def db_session():
    with SessionLocal() as s:
        yield s
        s.rollback()


def _payload(name, **kw):
    base = dict(entity_type="place", source="go_lake_havasu")
    base.update(kw)
    return EntityPayload(name=name, **base)


def test_normalize_strips_and_blanks_to_none():
    p = _payload("  Joe's   Bar  ", website="  ", phone="", address=" 1 Main St ")
    n = normalize_payload(p)
    assert n.name == "Joe's Bar"  # collapsed internal whitespace
    assert n.website is None  # "" / whitespace -> None
    assert n.phone is None
    assert n.address == "1 Main St"


def test_normalize_is_nondestructive_to_real_values():
    p = _payload("Lobster 3 Ways", website="https://www.Lobster3Ways.com/", phone="(702) 787-9568")
    n = normalize_payload(p)
    # stored values stay human-readable; matching canonicalization is internal
    assert n.website == "https://www.Lobster3Ways.com/"
    assert n.phone == "(702) 787-9568"


def _make_google_provider(s, name, **kw):
    prov = Provider(
        provider_name=name,
        category="eat-drink",
        slug=derive_provider_slug(s, name),
        source="google_places",
        google_place_id=kw.pop("gpid", "ChIJ-test-0001"),
        lat=kw.pop("lat", _LAT),
        lng=kw.pop("lng", _LNG),
        draft=False,
        is_active=True,
        **kw,
    )
    s.add(prov)
    create_provider_and_entity(s, prov)
    s.flush()
    return prov


def test_decide_insert_when_no_match(db_session):
    d = decide_ingest(db_session, _payload("Brand New Cafe XYZ", lat=34.9, lng=-114.9))
    assert d.action == "insert"
    assert d.should_hide is False
    assert d.existing_id is None


def test_decide_update_on_google_place_id(db_session):
    prov = _make_google_provider(db_session, "Existing Grill", gpid="ChIJ-match-123")
    d = decide_ingest(
        db_session,
        _payload("Existing Grill", google_place_id="ChIJ-match-123", lat=_LAT, lng=_LNG),
    )
    assert d.action == "update"
    assert d.existing_id == prov.entity_id
    assert d.should_hide is False


def test_ambiguous_sets_should_hide(db_session):
    # A nearby existing row with a DIFFERENT name -> reconciler returns ambiguous
    # (geo within 50m, name differs) -> the contract must flag should_hide.
    _make_google_provider(db_session, "Riverside Tacos", gpid="ChIJ-amb-1")
    d = decide_ingest(
        db_session,
        _payload("Completely Different Name", lat=_LAT, lng=_LNG),
    )
    assert d.action == "ambiguous"
    assert d.should_hide is True


def test_decision_carries_normalized_payload(db_session):
    d = decide_ingest(db_session, _payload("  Spaced   Name  ", lat=34.95, lng=-114.95))
    # caller should persist d.payload (normalized), not the raw input
    assert d.payload.name == "Spaced Name"


def _suppress(monkeypatch, name):
    from app.contrib import ingest_suppression
    from app.contrib.ingest_reconciler import slugify

    monkeypatch.setattr(
        ingest_suppression,
        "SUPPRESSED_BUSINESS_SLUGS",
        frozenset({slugify(name)}),
    )


def test_suppressed_identity_is_skipped_before_insert(db_session, monkeypatch):
    # The durable blocklist must be enforced INSIDE the funnel so every
    # decide_ingest source inherits it (it used to live only in the
    # golakehavasu partners loader — a suppressed identity could re-enter
    # via Places/OSM/pickleball/golf).
    _suppress(monkeypatch, "Wake Surf Adventures")
    d = decide_ingest(db_session, _payload("Wake Surf Adventures", lat=34.9, lng=-114.9))
    assert d.action == "skip"
    assert d.should_hide is False
    assert d.existing_id is None
    assert "suppressed" in (d.reason or "")


def test_suppressed_identity_cannot_match_and_reactivate(db_session, monkeypatch):
    # Even with an exact google_place_id match on an existing row, a
    # suppressed name must return skip — never "update" (which loaders use to
    # merge and set is_active=True, undoing the deactivation).
    prov = _make_google_provider(db_session, "Wake Surf Adventures", gpid="ChIJ-wsa-1")
    assert prov is not None
    _suppress(monkeypatch, "Wake Surf Adventures")
    d = decide_ingest(
        db_session,
        _payload("Wake Surf Adventures", google_place_id="ChIJ-wsa-1", lat=_LAT, lng=_LNG),
    )
    assert d.action == "skip"


def test_suppression_matches_normalized_name(db_session, monkeypatch):
    # Blocklist keys on slugify(name), so spacing/case variants still skip.
    _suppress(monkeypatch, "Wake Surf Adventures")
    d = decide_ingest(db_session, _payload("  WAKE  surf   Adventures ", lat=34.9, lng=-114.9))
    assert d.action == "skip"
