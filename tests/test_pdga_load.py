"""PDGA disc-golf loader: parse + proximity filter + payload + decide_ingest.

Run: python -m pytest tests/test_pdga_load.py -q

Same shape as tests/test_usapickleball_load.py: fixture-driven parse, an injected
httpx.MockTransport client, decide_ingest routing on a rolled-back session, and
leak-free loader integration (SessionLocal -> db_session, commit -> flush).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

import scripts.pdga_load as loader
from app.contrib import pdga_courses as pdga
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.db.seed_helpers import derive_provider_slug

FIXTURES = Path(__file__).resolve().parent.parent / "scripts" / "fixtures"

# Remote course baked into the directory fixture, used for collision-free loader
# integration (well away from any seeded Havasu row).
_REMOTE_LAT = 45.5
_REMOTE_LNG = -120.5


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def db_session():
    with SessionLocal() as s:
        yield s
        s.rollback()


def _mock_client() -> httpx.Client:
    directory_html = _fixture("pdga_course_directory.html")
    detail_html = _fixture("pdga_course_detail.html")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/course-directory/course/" in url:
            return httpx.Response(200, text=detail_html)
        if "/course-directory" in url:
            return httpx.Response(200, text=directory_html)
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
    class _Shim:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(loader, "SessionLocal", lambda: _Shim())
    monkeypatch.setattr(session, "commit", session.flush)


# --- parsing ----------------------------------------------------------------
def test_parse_courses_from_leaflet_blob() -> None:
    courses = pdga.parse_courses(_fixture("pdga_course_directory.html"))
    slugs = {c.slug for c in courses}
    assert "bridgewater-links-disc-golf-course" in slugs
    assert "sara-park-discgolfcourse" in slugs
    bridge = next(c for c in courses if c.slug == "bridgewater-links-disc-golf-course")
    assert bridge.name == "Bridgewater Links Disc Golf Course"
    assert bridge.lat == pytest.approx(34.469977755523)
    assert bridge.lng == pytest.approx(-114.34547212008)


def test_filter_near_havasu_keeps_local_drops_far() -> None:
    courses = pdga.parse_courses(_fixture("pdga_course_directory.html"))
    near = pdga.filter_near(courses)  # default Havasu center, 80km
    slugs = [c.slug for c in near]
    assert "george-ward-park" not in slugs  # Alabama -> dropped
    assert "remote-test-course" not in slugs  # Oregon -> dropped
    # nearest first
    assert slugs[0] == "bridgewater-links-disc-golf-course"
    assert "sara-park-discgolfcourse" in slugs


def test_parse_course_detail() -> None:
    d = pdga.parse_course_detail(_fixture("pdga_course_detail.html"))
    assert d["street"] == "7260 Sara Parkway"
    assert d["city"] == "Lake Havasu City"
    assert d["state"] == "AZ"
    assert d["postal"] == "86406"
    assert d["holes"] == 18
    assert d["course_type"] == "Permanent / Free"
    assert d["year_established"] == "2015"


def test_course_to_entity_payload_source_website_category() -> None:
    course = pdga.DiscGolfCourse(
        slug="sara-park-discgolfcourse", name="SARA Park", lat=34.44, lng=-114.24, holes=18
    )
    payload = pdga.course_to_entity_payload(course)
    assert payload.source == "pdga"
    assert payload.category_slug == "classes-sports-recreation"
    assert payload.legacy_category == "disc_golf"
    assert payload.phone is None
    assert payload.website == "https://www.pdga.com/course-directory/course/sara-park-discgolfcourse"
    assert payload.description and "18-hole" in payload.description


# --- fetch via mock transport -----------------------------------------------
def test_fetch_courses_and_enrich() -> None:
    with _mock_client() as client:
        courses = pdga.fetch_courses(client=client)
        assert len(courses) == 4
        bridge = next(c for c in courses if c.slug.startswith("bridgewater"))
        pdga.enrich_course(bridge, client=client)
    assert bridge.holes == 18
    assert bridge.city == "Lake Havasu City"


# --- decide_ingest funnel routing -------------------------------------------
def test_decide_insert_when_no_match(db_session) -> None:
    from app.contrib.scraper_ingest import decide_ingest

    payload = pdga.course_to_entity_payload(
        pdga.DiscGolfCourse(slug="novel-zzz", name="Novel Course ZZZ", lat=_REMOTE_LAT, lng=_REMOTE_LNG)
    )
    d = decide_ingest(db_session, payload)
    assert d.action == "insert"
    assert d.should_hide is False


def test_decide_ambiguous_held_on_geo_name_mismatch(db_session) -> None:
    _google_provider(db_session, "Some Other Park", lat=_REMOTE_LAT, lng=_REMOTE_LNG)
    from app.contrib.scraper_ingest import decide_ingest

    payload = pdga.course_to_entity_payload(
        pdga.DiscGolfCourse(slug="x", name="Disc Golf Course X", lat=_REMOTE_LAT, lng=_REMOTE_LNG)
    )
    d = decide_ingest(db_session, payload)
    assert d.action == "ambiguous"
    assert d.should_hide is True


# --- loader integration (leak-free) -----------------------------------------
def test_ingest_inserts_new_with_subcategory(db_session, monkeypatch) -> None:
    _patch_session(monkeypatch, db_session)
    with _mock_client() as client:
        counts = loader.ingest_courses(
            category_slug="classes-sports-recreation",
            dry_run=False,
            limit=None,
            center_lat=_REMOTE_LAT,
            center_lng=_REMOTE_LNG,
            radius_km=10.0,
            enrich=True,
            http_client=client,
        )
    assert counts["directory_total"] == 4
    assert counts["near"] == 1  # only the remote course within 10km
    assert counts["inserted"] == 1
    assert counts["inserted_pending"] == 0
    row = db_session.scalars(select(Provider).where(Provider.source == "pdga")).first()
    assert row is not None
    assert row.subcategory == "disc-golf"
    assert row.category == "disc_golf"
    assert row.draft is False
    assert row.website.endswith("/course/remote-test-course")


def test_ingest_holds_ambiguous_match(db_session, monkeypatch) -> None:
    _google_provider(db_session, "Unrelated Remote Neighbor", lat=_REMOTE_LAT, lng=_REMOTE_LNG)
    _patch_session(monkeypatch, db_session)
    with _mock_client() as client:
        counts = loader.ingest_courses(
            category_slug="classes-sports-recreation",
            dry_run=False,
            limit=None,
            center_lat=_REMOTE_LAT,
            center_lng=_REMOTE_LNG,
            radius_km=10.0,
            enrich=True,
            http_client=client,
        )
    assert counts["inserted_pending"] == 1
    assert counts["inserted"] == 0
    held = db_session.scalars(select(Provider).where(Provider.source == "pdga")).first()
    assert held is not None
    assert held.draft is True
    assert held.pending_review is True


def test_ingest_dry_run_writes_nothing(db_session, monkeypatch) -> None:
    _patch_session(monkeypatch, db_session)
    with _mock_client() as client:
        counts = loader.ingest_courses(
            category_slug="classes-sports-recreation",
            dry_run=True,
            limit=None,
            center_lat=_REMOTE_LAT,
            center_lng=_REMOTE_LNG,
            radius_km=10.0,
            enrich=False,
            http_client=client,
        )
    assert counts["payloads_ready"] == 1
    assert counts["inserted"] == 0
    assert db_session.scalars(select(Provider).where(Provider.source == "pdga")).first() is None
