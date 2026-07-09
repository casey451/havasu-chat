"""SEO P1.0/P1.3 — absolute-https canonical + og:url across page types.

Every indexable page must emit exactly one self-canonical built from the
configurable BASE_URL origin, always https (the old provider page leaked a bare
``request.url`` -> http:// canonical behind Railway's TLS-terminating proxy).
"""

from __future__ import annotations

import re
from datetime import time, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Entity, Event, Provider
from app.main import app
from app.seo.urls import absolute_url, base_url, canonical_url

_CANON_RE = re.compile(r'<link rel="canonical" href="([^"]+)"')
_BASE = "https://hava.example.com"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _canonicals(html: str) -> list[str]:
    return _CANON_RE.findall(html)


# --- unit: helper logic ---------------------------------------------------


def test_base_url_honors_env_and_coerces_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_URL", "http://hava.example.com/")
    assert base_url() == _BASE


def test_absolute_url_joins_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    assert absolute_url("/provider/foo") == f"{_BASE}/provider/foo"
    assert absolute_url("provider/foo") == f"{_BASE}/provider/foo"


def test_absolute_url_passes_through_already_absolute_and_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    # Already-absolute URLs return UNCHANGED — no doubled origin
    # ("https://hava.example.com/https://x.com/y"). This is the F4 follow-up:
    # a caller handing over a full external URL can't break the structured data.
    assert absolute_url("https://x.com/y") == "https://x.com/y"
    assert absolute_url("http://x.com/y") == "http://x.com/y"
    assert absolute_url("HTTPS://X.com/Y") == "HTTPS://X.com/Y"  # case-insensitive
    # Protocol-relative + non-path schemes also pass through untouched.
    assert absolute_url("//cdn.example.com/a.png") == "//cdn.example.com/a.png"
    assert absolute_url("mailto:hi@askhava.com") == "mailto:hi@askhava.com"
    assert absolute_url("tel:+19285551234") == "tel:+19285551234"
    # None / empty are graceful — never mangled into the bare site root.
    assert absolute_url(None) == ""
    assert absolute_url("") == ""
    # Relative paths still domain-prefixed exactly as before (no behavior change).
    assert absolute_url("/events/1") == f"{_BASE}/events/1"
    assert absolute_url("events/1") == f"{_BASE}/events/1"


class _FakeURL:
    def __init__(self, path: str) -> None:
        self.path = path


class _FakeReq:
    def __init__(self, path: str) -> None:
        self.url = _FakeURL(path)


def test_canonical_url_drops_query_and_is_absolute_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    # Path only — query string intentionally dropped (facets canonical to clean).
    assert canonical_url(_FakeReq("/category/eat-drink")) == f"{_BASE}/category/eat-drink"


# --- integration: one self-canonical per page type ------------------------


def test_home_page_canonical(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    r = client.get("/home")
    assert r.status_code == 200
    assert _canonicals(r.text) == [f"{_BASE}/home"]
    assert f'property="og:url" content="{_BASE}/home"' in r.text


def test_category_page_canonical_drops_facets(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A.3 rewire: the flat /categories/{slug} pages are retired; the facet
    # canonical contract lives on the /lake-havasu/{subcategory} landings,
    # which render the same listing template.
    monkeypatch.setenv("BASE_URL", _BASE)
    r = client.get("/lake-havasu/restaurants?cuisine=mexican")
    assert r.status_code == 200
    assert _canonicals(r.text) == [f"{_BASE}/lake-havasu/restaurants"]


def test_provider_page_canonical_is_https_absolute(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    slug = f"seo-canon-{uuid4().hex[:8]}"
    with SessionLocal() as db:
        db.add(
            Provider(
                provider_name=f"Canon Co {slug}",
                category="home_services",
                source="test-seo-canon",
                slug=slug,
                draft=False,
                is_active=True,
                verified=True,
                description="A trustworthy local shop serving Lake Havasu City.",
            )
        )
        db.commit()
    try:
        r = client.get(f"/provider/{slug}")
        assert r.status_code == 200
        canon = _canonicals(r.text)
        assert canon == [f"{_BASE}/provider/{slug}"]
        assert "http://" not in canon[0]  # no leaked non-secure canonical
        assert 'property="og:url"' in r.text
        # Regression guard (F4 follow-up): no rendered URL doubles the origin
        # onto an already-absolute value (the absolute_url() hardening). The
        # provider JSON-LD/OG URLs are built from relative paths, so this stays
        # clean — this asserts it can't regress.
        assert f"{_BASE}/http" not in r.text
        assert f"{_BASE}/https" not in r.text
    finally:
        with SessionLocal() as db:
            p = db.query(Provider).filter(Provider.slug == slug).first()
            if p is not None:
                eid = p.entity_id
                db.execute(delete(Provider).where(Provider.id == p.id))
                db.execute(delete(Entity).where(Entity.id == eid))
                db.commit()


def test_event_page_canonical_matches_permalink(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    with SessionLocal() as db:
        ent = Entity(
            entity_type="commercial",
            slug=f"seo-ev-{uuid4().hex[:8]}",
            name="SEO Ev Entity",
            source="test-seo-canon",
        )
        db.add(ent)
        db.flush()
        soon = now_lake_havasu().date() + timedelta(days=2)
        ev = Event(
            title="SEO Canon Event",
            normalized_title="seo canon event",
            date=soon,
            start_time=time(10, 0),
            location_name="Test Location",
            location_normalized="test location",
            description="A long enough description for the canonical event page test.",
            event_url="https://example.com/event",
            tags=[],
            status="live",
            source="test-seo-canon",
            entity_id=ent.id,
        )
        db.add(ev)
        db.commit()
        eid = ev.id
    try:
        r = client.get(f"/events/{eid}")
        assert r.status_code == 200
        assert _canonicals(r.text) == [f"{_BASE}/events/{eid}"]
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.source == "test-seo-canon"))
            db.execute(delete(Entity).where(Entity.source == "test-seo-canon"))
            db.commit()


def test_category_canonical_keeps_page_param(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1.4: pages 2+ self-canonicalize with ?page=N; page 1 stays clean."""
    monkeypatch.setenv("BASE_URL", _BASE)
    r = client.get("/lake-havasu/restaurants?page=2&cuisine=mexican")
    assert r.status_code == 200
    assert _canonicals(r.text) == [f"{_BASE}/lake-havasu/restaurants?page=2"]
    assert "Page 2" in r.text  # page-2 indicator in the <title>/heading

    r1 = client.get("/lake-havasu/restaurants?page=1")
    assert _canonicals(r1.text) == [f"{_BASE}/lake-havasu/restaurants"]


def test_canonical_page_param_ignores_garbage(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    # The landing parses ?page= defensively -> non-numeric falls back to page 1
    # with a clean self-canonical (no garbage echoed).
    r = client.get("/lake-havasu/restaurants?page=banana")
    assert r.status_code == 200
    assert _canonicals(r.text) == [f"{_BASE}/lake-havasu/restaurants"]

    from app.seo.urls import canonical_url

    class _Req:
        class url:
            path = "/lake-havasu/restaurants"

        query_params = {"page": "banana"}

    assert canonical_url(_Req()) == f"{_BASE}/lake-havasu/restaurants"
