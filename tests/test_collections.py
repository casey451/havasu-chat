"""Curated editorial collections — loader + ``GET /collection/{slug}`` route.

Covers the ``app.home.collections`` loader (load, lookup, unknown slug,
defensive bad-data handling) and the landing route (200 known slug, 404
unknown slug, 404 for a structurally-valid-but-absent slug).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.home import collections as cc
from app.main import app


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the LRU caches around each test so monkeypatching is clean."""
    cc.reset_cache()
    yield
    cc.reset_cache()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# Loader -----------------------------------------------------------------------


def test_list_collections_returns_entries() -> None:
    colls = cc.list_collections()
    assert len(colls) >= 2
    for c in colls:
        assert c["slug"]
        assert c["title"]
        assert isinstance(c["places"], list)


def test_get_collection_known_slug() -> None:
    coll = cc.get_collection("dog-friendly-patios")
    assert coll is not None
    assert coll["title"] == "Dog-friendly patios"
    assert coll["places"], "collection should carry at least one place"


def test_get_collection_normalises_slug() -> None:
    assert cc.get_collection("  Dog-Friendly-Patios  ") is not None


def test_get_collection_unknown_slug_returns_none() -> None:
    assert cc.get_collection("no-such-collection") is None


def test_get_collection_empty_slug_returns_none() -> None:
    assert cc.get_collection("") is None


def test_is_collection_slug() -> None:
    assert cc.is_collection_slug("best-sunset-spots") is True
    assert cc.is_collection_slug("nope") is False


def test_place_keys_present_for_template() -> None:
    coll = cc.get_collection("dog-friendly-patios")
    assert coll is not None
    place = coll["places"][0]
    for key in ("slug", "name", "where", "image_url", "blurb", "meta_line"):
        assert key in place


def test_accent_falls_back_to_neutral_on_bad_value(monkeypatch) -> None:
    """A bad ``accent`` in the JSON collapses to 'neutral', never leaks raw."""
    monkeypatch.setattr(
        cc,
        "_load_raw",
        lambda: {
            "collections": [
                {"slug": "x", "title": "X", "accent": "bogus", "places": []}
            ]
        },
    )
    cc._index.cache_clear()
    coll = cc.get_collection("x")
    assert coll is not None
    assert coll["accent"] == "neutral"


def test_malformed_collection_is_skipped(monkeypatch) -> None:
    """Entries missing slug or title are dropped, not raised on."""
    monkeypatch.setattr(
        cc,
        "_load_raw",
        lambda: {
            "collections": [
                {"title": "no slug"},
                {"slug": "ok", "title": "OK", "places": []},
            ]
        },
    )
    cc._index.cache_clear()
    assert cc.get_collection("ok") is not None
    assert len(cc.list_collections()) == 1


def test_corrupt_file_degrades_to_empty(monkeypatch) -> None:
    monkeypatch.setattr(cc, "_load_raw", lambda: {})
    cc._index.cache_clear()
    assert cc.list_collections() == []
    assert cc.get_collection("dog-friendly-patios") is None


# Route ------------------------------------------------------------------------


def test_route_200_known_slug(client: TestClient) -> None:
    r = client.get("/collection/dog-friendly-patios")
    assert r.status_code == 200
    assert "Dog-friendly patios" in r.text


def test_route_renders_place_names(client: TestClient) -> None:
    r = client.get("/collection/best-sunset-spots")
    assert r.status_code == 200
    assert "London Bridge" in r.text


def test_route_404_unknown_slug(client: TestClient) -> None:
    r = client.get("/collection/not-a-real-collection")
    assert r.status_code == 404


def test_route_delinks_stale_provider_slugs(client: TestClient) -> None:
    """A place whose slug no longer resolves to a live provider renders as a
    non-link card (no dead /provider/<slug> link), while a resolving one stays
    linked. Prevents the prod issue where stale editorial slugs 404'd on click."""
    from sqlalchemy import delete

    from app.db.database import SessionLocal
    from app.db.models import Entity, Provider

    ids: list[str] = []
    with SessionLocal() as db:
        # Seed only ONE of the dog-friendly-patios providers.
        p = Provider(
            provider_name="Javelina Cantina",
            category="restaurant",
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-coll",
            slug="javelina-cantina",
        )
        db.add(p)
        db.commit()
        ids.append(p.entity_id)
    try:
        body = client.get("/collection/dog-friendly-patios").text
        # Resolving provider keeps its link...
        assert "/provider/javelina-cantina" in body
        # ...stale slugs are de-linked (no dead link)...
        assert "/provider/barley-brothers-brewery" not in body
        assert "/provider/mudshark-brewery-and-public-house" not in body
        # ...but every card still renders.
        assert "Barley Brothers" in body
        assert "Mudshark" in body
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id.in_(ids)))
            db.execute(delete(Entity).where(Entity.id.in_(ids)))
            db.commit()
