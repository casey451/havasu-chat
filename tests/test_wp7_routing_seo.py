"""WP-7: routing / SEO plumbing, redirects, and public-payload hygiene.

Covers:
- Route status matrix: / and /events are permanent (301) redirects; /advertise
  301s to /sponsor; GET /logout redirects instead of 405ing.
- The public /api/events + /api/businesses JSON never leaks internal scraper
  provenance (``source``) or an ``embedding`` field.
- Sitemap gains /map, /events-ui, /categories and the WP-1 trust pages while
  dropping the bare / (which now 301s to /home).
- og:url is https-coerced and og:description truncates on a word boundary.
"""

from __future__ import annotations

from datetime import time, timedelta
from uuid import uuid4
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.main import _coerce_https, _truncate_for_og, app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_sitemap_cache():
    main_module._sitemap_cache = None
    yield
    main_module._sitemap_cache = None


# ---------------------------------------------------------------------------
# Route status matrix
# ---------------------------------------------------------------------------


def test_root_permanent_redirects_to_home(client: TestClient) -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/home"


def test_events_permanent_redirects_to_events_ui(client: TestClient) -> None:
    r = client.get("/events", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/events-ui"


def test_advertise_permanent_redirects_to_sponsor(client: TestClient) -> None:
    r = client.get("/advertise", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/sponsor"


def test_logout_get_redirects_not_405(client: TestClient) -> None:
    r = client.get("/logout", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/"


# ---------------------------------------------------------------------------
# Public payload hygiene -- no internal fields
# ---------------------------------------------------------------------------

_INTERNAL_KEYS = {"embedding", "source", "normalized_title", "location_normalized"}


def _seed_live_event() -> str:
    with SessionLocal() as db:
        ent = Entity(
            entity_type="commercial",
            slug=f"wp7-ent-{uuid4().hex[:8]}",
            name="WP7 Test Entity",
            source="test-wp7",
        )
        db.add(ent)
        db.flush()
        # Land inside the default /api/events window (today .. today+14d).
        soon = now_lake_havasu().date() + timedelta(days=2)
        ev = Event(
            title="WP7 Sample Event",
            normalized_title="wp7 sample event",
            date=soon,
            start_time=time(10, 0),
            location_name="Test Location",
            location_normalized="test location",
            description="A long enough description for the event payload test.",
            event_url="https://example.com/event",
            tags=[],
            status="live",
            source="test-wp7",
            entity_id=ent.id,
        )
        db.add(ev)
        db.commit()
        return ev.id


def _cleanup_wp7_rows() -> None:
    from sqlalchemy import select

    with SessionLocal() as db:
        for ev in db.scalars(select(Event).where(Event.source == "test-wp7")).all():
            db.delete(ev)
        for ent in db.scalars(select(Entity).where(Entity.source == "test-wp7")).all():
            db.delete(ent)
        db.commit()


def test_api_events_omits_internal_fields(client: TestClient) -> None:
    _seed_live_event()
    try:
        r = client.get("/api/events")
        assert r.status_code == 200
        items = r.json()["items"]
        assert items, "expected at least one seeded live event"
        for item in items:
            leaked = _INTERNAL_KEYS.intersection(item.keys())
            assert not leaked, f"/api/events leaked internal fields: {leaked}"
    finally:
        _cleanup_wp7_rows()


def test_api_businesses_omits_internal_fields(client: TestClient) -> None:
    r = client.get("/api/businesses", params={"limit": 25})
    assert r.status_code == 200
    for item in r.json()["items"]:
        leaked = _INTERNAL_KEYS.intersection(item.keys())
        assert not leaked, f"/api/businesses leaked internal fields: {leaked}"


# ---------------------------------------------------------------------------
# Sitemap surfaces
# ---------------------------------------------------------------------------

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _sitemap_locs(client: TestClient) -> list[str]:
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    root = ET.fromstring(r.text)
    return [loc.text for loc in root.findall("sm:url/sm:loc", _SITEMAP_NS) if loc.text]


def test_sitemap_adds_new_static_surfaces(client: TestClient) -> None:
    locs = _sitemap_locs(client)
    for path in ("/map", "/events-ui", "/categories", "/about", "/help", "/contact"):
        assert any(loc.endswith(path) for loc in locs), f"sitemap missing {path}"


def test_sitemap_drops_bare_root(client: TestClient) -> None:
    locs = _sitemap_locs(client)
    base = main_module._base_url()
    assert base not in locs, "bare / (301 -> /home) should not be in the sitemap"
    # /home itself stays.
    assert f"{base}/home" in locs


# ---------------------------------------------------------------------------
# og:url + og:description helpers
# ---------------------------------------------------------------------------


def test_coerce_https_upgrades_http() -> None:
    assert _coerce_https("http://example.com") == "https://example.com"
    assert _coerce_https("https://example.com") == "https://example.com"
    assert _coerce_https("example.com") == "https://example.com"


def test_coerce_https_leaves_localhost() -> None:
    assert _coerce_https("http://localhost:8000") == "http://localhost:8000"
    assert _coerce_https("http://127.0.0.1:8000") == "http://127.0.0.1:8000"


def test_base_url_is_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_URL", "http://prod.example.com")
    assert main_module._base_url() == "https://prod.example.com"


def test_truncate_for_og_word_boundary() -> None:
    text = "Lake Havasu City " + "word " * 60
    out = _truncate_for_og(text, limit=40)
    # Never cuts a token in half: the trimmed body ends on a whole word.
    body = out[:-3] if out.endswith("...") else out
    assert not body.endswith("wor")
    assert out.endswith("...")
    # Short strings pass through untouched.
    assert _truncate_for_og("Short and sweet", limit=160) == "Short and sweet"
