"""robots.txt + sitemap.xml routes (v48 launch hardening)."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import uuid4
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.categories.queries import CATEGORY_FILTERS
from app.db.database import SessionLocal
from app.db.models import Entity, Event, Provider
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_sitemap_cache() -> None:
    """Reset the module-level sitemap cache between tests."""
    main_module._sitemap_cache.clear()
    yield
    main_module._sitemap_cache.clear()


def _make_entity(db, *, source: str) -> Entity:
    ent = Entity(
        entity_type="commercial",
        slug=f"sitemap-ent-{uuid4().hex[:8]}",
        name="Sitemap Test Entity",
        source=source,
    )
    db.add(ent)
    db.flush()
    return ent


def _seed_provider(*, slug: str, is_active: bool = True, draft: bool = False) -> str:
    with SessionLocal() as db:
        ent = _make_entity(db, source="test-sitemap")
        prov = Provider(
            provider_name="Sitemap Test Provider",
            category="home_services",
            slug=slug,
            is_active=is_active,
            draft=draft,
            source="test-sitemap",
            entity_id=ent.id,
        )
        db.add(prov)
        db.commit()
        return prov.id


def _seed_event(*, status: str = "live") -> str:
    with SessionLocal() as db:
        ent = _make_entity(db, source="test-sitemap")
        ev = Event(
            title="Sitemap Test Event",
            normalized_title="sitemap test event",
            date=date(2030, 6, 1),
            start_time=time(10, 0),
            location_name="Test Location",
            location_normalized="test location",
            description="Test description.",
            event_url="https://example.com/event",
            tags=[],
            status=status,
            source="test-sitemap",
            created_at=datetime(2030, 5, 1, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None),
            entity_id=ent.id,
        )
        db.add(ev)
        db.commit()
        return ev.id


def _cleanup_sitemap_rows() -> None:
    from sqlalchemy import select

    with SessionLocal() as db:
        for prov in db.scalars(select(Provider).where(Provider.source == "test-sitemap")).all():
            db.delete(prov)
        for ev in db.scalars(select(Event).where(Event.source == "test-sitemap")).all():
            db.delete(ev)
        for ent in db.scalars(select(Entity).where(Entity.source == "test-sitemap")).all():
            db.delete(ent)
        db.commit()


@pytest.fixture
def sitemap_rows() -> dict[str, str]:
    """Seed a known Provider + Event for sitemap assertions, then clean up."""
    slug = f"sitemap-test-{uuid4().hex[:8]}"
    provider_id = _seed_provider(slug=slug)
    event_id = _seed_event()
    try:
        yield {"provider_slug": slug, "provider_id": provider_id, "event_id": event_id}
    finally:
        _cleanup_sitemap_rows()


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------


def test_robots_txt_returns_plain_text(client: TestClient) -> None:
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "User-agent: *" in body
    assert "Allow: /" in body
    assert "Sitemap:" in body
    assert "/sitemap.xml" in body


def test_robots_txt_uses_default_base_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """askhava.com is the canonical production domain (2026-06)."""
    monkeypatch.delenv("BASE_URL", raising=False)
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "Sitemap: https://askhava.com/sitemap.xml" in r.text


def test_robots_txt_honors_base_url_env(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASE_URL", "https://example.test")
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "Sitemap: https://example.test/sitemap.xml" in r.text


# ---------------------------------------------------------------------------
# sitemap.xml
# ---------------------------------------------------------------------------


_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _parse_sitemap_locs(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    return [loc.text for loc in root.findall("sm:url/sm:loc", _SITEMAP_NS) if loc.text is not None]


def _all_locs_via_index(client: TestClient) -> list[str]:
    """Fetch the index, then every child sitemap; return all page locs."""
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    root = ET.fromstring(r.text)
    child_locs = [
        loc.text
        for loc in root.findall("sm:sitemap/sm:loc", _SITEMAP_NS)
        if loc.text is not None
    ]
    assert child_locs, "sitemap index referenced no child sitemaps"
    locs: list[str] = []
    for child in child_locs:
        path = "/" + child.split("/", 3)[-1]
        cr = client.get(path)
        assert cr.status_code == 200, f"{path} -> {cr.status_code}"
        locs.extend(_parse_sitemap_locs(cr.text))
    return locs


def test_sitemap_xml_returns_valid_xml(client: TestClient, sitemap_rows: dict[str, str]) -> None:
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "xml" in r.headers["content-type"]
    # P1.6: the root document is now a sitemap *index*.
    root = ET.fromstring(r.text)
    assert root.tag.endswith("sitemapindex")


def test_sitemap_includes_static_pages(client: TestClient, sitemap_rows: dict[str, str]) -> None:
    locs = _all_locs_via_index(client)
    # At least one of the static surfaces should appear.
    assert any(loc.endswith("/privacy") for loc in locs)
    assert any(loc.endswith("/terms") for loc in locs)
    assert any(loc.endswith("/contribute") for loc in locs)
    assert any(loc.endswith("/chat") for loc in locs)


def test_sitemap_excludes_retired_flat_category_routes(
    client: TestClient, sitemap_rows: dict[str, str]
) -> None:
    """A.3 nav rewire: the retired flat /categories/{slug} buckets 301 to
    taxonomy departments, so the sitemap must never advertise them. The two
    slugs shared with the new tree (on-the-water, pets) are department
    landings now and MAY appear via the leaf/department enumeration."""
    locs = _all_locs_via_index(client)
    for slug in set(CATEGORY_FILTERS) - {"on-the-water", "pets"}:
        assert not any(loc.endswith(f"/categories/{slug}") for loc in locs), (
            f"retired flat route /categories/{slug} still in sitemap"
        )


def test_sitemap_includes_active_provider(client: TestClient, sitemap_rows: dict[str, str]) -> None:
    locs = _all_locs_via_index(client)
    expected = f"/provider/{sitemap_rows['provider_slug']}"
    assert any(loc.endswith(expected) for loc in locs)


def test_sitemap_includes_live_event(client: TestClient, sitemap_rows: dict[str, str]) -> None:
    locs = _all_locs_via_index(client)
    expected = f"/events/{sitemap_rows['event_id']}"
    assert any(loc.endswith(expected) for loc in locs)


def test_sitemap_entries_have_lastmod(client: TestClient, sitemap_rows: dict[str, str]) -> None:
    """Providers and events carry real <lastmod>; static pages may omit it."""
    for section in ("providers", "events"):
        r = client.get(f"/sitemap-{section}.xml")
        root = ET.fromstring(r.text)
        url_nodes = root.findall("sm:url", _SITEMAP_NS)
        assert url_nodes, f"sitemap-{section} had zero <url> entries"
        for node in url_nodes:
            lastmod = node.find("sm:lastmod", _SITEMAP_NS)
            assert lastmod is not None and lastmod.text, (
                f"every {section} <url> needs a <lastmod>"
            )


def test_sitemap_unknown_section_404s(client: TestClient) -> None:
    assert client.get("/sitemap-bogus.xml").status_code == 404


def test_sitemap_caches_for_one_hour(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Second request inside the TTL window should reuse the cached XML."""
    calls = {"n": 0}
    real_build = main_module._build_sitemap_pages_xml

    def _counting_build() -> str:
        calls["n"] += 1
        return real_build()

    monkeypatch.setitem(main_module._SITEMAP_BUILDERS, "pages", _counting_build)
    main_module._sitemap_cache.clear()

    r1 = client.get("/sitemap-pages.xml")
    r2 = client.get("/sitemap-pages.xml")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert calls["n"] == 1, "second request should hit the in-process cache"
