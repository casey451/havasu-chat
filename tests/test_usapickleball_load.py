"""USA Pickleball / Places2Play loader: parse + payload + decide_ingest funnel.

Run: python -m pytest tests/test_usapickleball_load.py -q

Mirrors tests/test_scraper_ingest.py (decide_ingest routing on a rolled-back
session) and tests/test_golakehavasu_partners.py (fixture-driven parse + an
injected httpx.MockTransport client). The loader's DB writes are exercised
leak-free by pointing its ``SessionLocal`` at the rollback ``db_session`` and
turning ``commit`` into ``flush``.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

import scripts.usapickleball_load as loader
from app.contrib import usapickleball as up
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.db.seed_helpers import derive_provider_slug

FIXTURES = Path(__file__).resolve().parent.parent / "scripts" / "fixtures"

# Remote coords baked into the place fixture (well away from any seeded Havasu
# row, so an insert test cannot accidentally reconcile against session seed data).
_PLACE_LAT = 41.234567
_PLACE_LNG = -120.876543


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def db_session():
    with SessionLocal() as s:
        yield s
        s.rollback()


def _mock_client() -> httpx.Client:
    search_html = _fixture("places2play_search.html")
    place_html = _fixture("places2play_place.html")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/search" in url:
            return httpx.Response(200, text=search_html)
        if "/place" in url:
            return httpx.Response(200, text=place_html)
        return httpx.Response(404, text="not found")

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def _google_provider(session, name, *, lat, lng):
    prov = Provider(
        provider_name=name,
        category="eat-drink",
        slug=derive_provider_slug(session, name),
        source="google_places",
        google_place_id=f"ChIJ-{uuid.uuid4().hex[:16]}",
        lat=lat,
        lng=lng,
        draft=False,
        is_active=True,
    )
    session.add(prov)
    create_provider_and_entity(session, prov)
    session.flush()
    return prov


def _patch_session(monkeypatch, session) -> None:
    """Route the loader's SessionLocal at the test session; commit -> flush."""

    class _Shim:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(loader, "SessionLocal", lambda: _Shim())
    monkeypatch.setattr(session, "commit", session.flush)


# --- parsing ----------------------------------------------------------------
def test_parse_search_results_extracts_rows() -> None:
    places = up.parse_search_results(_fixture("places2play_search.html"))
    assert [p.place_id for p in places] == ["12598", "169"]
    ark = places[0]
    assert ark.name == "The Ark Center Stonebridge Christian Center"
    assert ark.street == "2700 Jamaica Blvd. South"
    assert ark.city == "LAKE HAVASU CITY"
    assert ark.state == "AZ"
    assert ark.postal == "86406"
    assert ark.website == "http://www.lakehavasupickleball.com"
    assert ark.phone == "(775)848-5418"
    assert ark.indoor_courts == 3
    assert ark.outdoor_courts == 0


def test_parse_search_second_row_minimal() -> None:
    london = up.parse_search_results(_fixture("places2play_search.html"))[1]
    assert london.name == "London Bridge Pickleball Courts"
    assert london.website is None  # no Website link in that row
    assert london.phone is None
    assert london.outdoor_courts == 8


def test_parse_place_latlng() -> None:
    lat, lng = up.parse_place_latlng(_fixture("places2play_place.html"))
    assert lat == pytest.approx(_PLACE_LAT)
    assert lng == pytest.approx(_PLACE_LNG)


def test_format_address() -> None:
    place = up.PickleballPlace(
        place_id="1", name="X", street="1 Main St", city="LAKE HAVASU CITY",
        state="AZ", postal="86403",
    )
    assert up.format_address(place) == "1 Main St, LAKE HAVASU CITY, AZ 86403"


def test_place_to_entity_payload_source_category_legacy() -> None:
    place = up.parse_search_results(_fixture("places2play_search.html"))[0]
    payload = up.place_to_entity_payload(place)
    assert payload.source == "usapickleball"
    assert payload.entity_type == "place"
    assert payload.category_slug == "classes-sports-recreation"
    assert payload.legacy_category == "pickleball"
    assert payload.website == "http://www.lakehavasupickleball.com"


# --- fetch via mock transport -----------------------------------------------
def test_fetch_search_and_enrich_latlng() -> None:
    with _mock_client() as client:
        places = up.fetch_search("Lake Havasu City", client=client)
        assert len(places) == 2
        up.enrich_latlng(places[0], client=client)
    assert places[0].lat == pytest.approx(_PLACE_LAT)
    assert places[0].lng == pytest.approx(_PLACE_LNG)


# --- decide_ingest funnel routing -------------------------------------------
def test_decide_insert_when_no_match(db_session) -> None:
    from app.contrib.scraper_ingest import decide_ingest

    payload = up.place_to_entity_payload(
        up.PickleballPlace(place_id="9", name="Brand New Courts ZZZ", lat=_PLACE_LAT, lng=_PLACE_LNG)
    )
    d = decide_ingest(db_session, payload)
    assert d.action == "insert"
    assert d.should_hide is False


def test_decide_ambiguous_held_on_geo_name_mismatch(db_session) -> None:
    _google_provider(db_session, "Totally Other Place", lat=_PLACE_LAT, lng=_PLACE_LNG)
    from app.contrib.scraper_ingest import decide_ingest

    payload = up.place_to_entity_payload(
        up.PickleballPlace(place_id="9", name="Ark Pickleball Courts", lat=_PLACE_LAT, lng=_PLACE_LNG)
    )
    d = decide_ingest(db_session, payload)
    assert d.action == "ambiguous"
    assert d.should_hide is True


# --- loader integration (leak-free: commit -> flush on rollback session) -----
def test_ingest_inserts_new_with_subcategory(db_session, monkeypatch) -> None:
    _patch_session(monkeypatch, db_session)
    with _mock_client() as client:
        counts = loader.ingest_places(
            query="Lake Havasu City",
            category_slug="classes-sports-recreation",
            dry_run=False,
            limit=1,
            enrich=True,
            http_client=client,
        )
    assert counts["found"] == 1
    assert counts["inserted"] == 1
    assert counts["inserted_pending"] == 0
    row = db_session.scalars(
        select(Provider).where(Provider.source == "usapickleball")
    ).first()
    assert row is not None
    assert row.subcategory == "racquet-sports"
    assert row.category == "pickleball"
    assert row.draft is False
    assert row.lat == pytest.approx(_PLACE_LAT)


def test_ingest_holds_ambiguous_match(db_session, monkeypatch) -> None:
    # A different-named provider at the SAME coords the place enriches to -> the
    # funnel must HOLD the scraped row (draft + pending_review), not insert a dup.
    _google_provider(db_session, "Unrelated Neighbor Place", lat=_PLACE_LAT, lng=_PLACE_LNG)
    _patch_session(monkeypatch, db_session)
    with _mock_client() as client:
        counts = loader.ingest_places(
            query="Lake Havasu City",
            category_slug="classes-sports-recreation",
            dry_run=False,
            limit=1,
            enrich=True,
            http_client=client,
        )
    assert counts["inserted_pending"] == 1
    assert counts["inserted"] == 0
    held = db_session.scalars(
        select(Provider).where(Provider.source == "usapickleball")
    ).first()
    assert held is not None
    assert held.draft is True
    assert held.pending_review is True


def test_ingest_dry_run_writes_nothing(db_session, monkeypatch) -> None:
    _patch_session(monkeypatch, db_session)
    with _mock_client() as client:
        counts = loader.ingest_places(
            query="Lake Havasu City",
            category_slug="classes-sports-recreation",
            dry_run=True,
            limit=None,
            enrich=False,
            http_client=client,
        )
    assert counts["payloads_ready"] == 2
    assert counts["inserted"] == 0
    assert (
        db_session.scalars(select(Provider).where(Provider.source == "usapickleball")).first()
        is None
    )
