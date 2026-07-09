"""A3 — cuisine SEO landing pages (/lake-havasu/{cuisine}).

Covers the thin-page gate, the route render + <h1>, and the key isolation that
makes a cuisine page independently monetizable: a placement sold on the
``cuisine:{slug}`` key pins + labels its holder on the cuisine page, while the
parent Eat & Drink overlay (keyed on the route) does NOT pin it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.categories import cuisine_pages
from app.categories.queries import CategoryFacets, category_listing
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.db.monetization_models import Placement, PlacementStatus, PlacementType
from app.main import app

_NOW = datetime(2026, 1, 5, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed_cuisine(db, suf: str, n: int, *, primary: str, prefix: str) -> list[str]:
    """Create ``n`` active Eat & Drink providers of one Google cuisine type."""
    pids: list[str] = []
    for i in range(n):
        p = Provider(
            provider_name=f"{prefix} {i} {suf}",
            category="restaurant",
            google_primary_category=primary,
            slug=f"{prefix.lower().replace(' ', '-')}-{i}-{suf}",
            is_active=True,
            draft=False,
            pending_review=False,
            source="test-a3",
            google_rating=4.5,
            google_review_count=25,
        )
        db.add(p)
        db.commit()
        pids.append(p.id)
    return pids


def _seed_mexican(db, suf: str, n: int) -> list[str]:
    """Create ``n`` active Eat & Drink providers that classify as Mexican."""
    return _seed_cuisine(db, suf, n, primary="mexican_restaurant", prefix="A3 Cantina")


def _cleanup(db, pids: list[str]) -> None:
    ents = [
        e for (e,) in db.query(Provider.entity_id).filter(Provider.id.in_(pids)).all()
    ]
    db.execute(delete(Placement).where(Placement.provider_id.in_(pids)))
    db.execute(delete(Provider).where(Provider.id.in_(pids)))
    if ents:
        db.execute(delete(Entity).where(Entity.id.in_([e for e in ents if e])))
    db.commit()


def test_placement_key_for_is_namespaced() -> None:
    assert cuisine_pages.placement_key_for("Mexican") == "cuisine:mexican"
    assert cuisine_pages.placement_key_for(" pizza ") == "cuisine:pizza"


def test_gate_counts_and_qualifies() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        # Seed to the (higher) sitemap bar so both gates are exercised live.
        pids = _seed_mexican(db, suf, cuisine_pages.CUISINE_SITEMAP_MIN_PROVIDERS)
        try:
            assert (
                cuisine_pages.cuisine_provider_count(db, "mexican")
                >= cuisine_pages.CUISINE_SITEMAP_MIN_PROVIDERS
            )
            assert cuisine_pages.is_publishable_cuisine(db, "mexican") is True
            assert cuisine_pages.is_publishable_cuisine(db, "not-a-cuisine") is False
            slugs = {s for s, _label, _n in cuisine_pages.qualifying_cuisines(db)}
            assert "mexican" in slugs
        finally:
            _cleanup(db, pids)


def test_render_gate_splits_from_sitemap_gate(monkeypatch) -> None:
    """2026-07-01 audit A4: a 2-provider cuisine RENDERS (and search routes to
    it) but does NOT join the sitemap; a 1-provider cuisine does neither."""
    monkeypatch.setattr(
        cuisine_pages,
        "_eat_drink_cuisine_counts",
        lambda db: {"italian": 2, "thai": 1, "mexican": 26},
    )
    assert cuisine_pages.is_publishable_cuisine(None, "italian") is True
    assert cuisine_pages.is_publishable_cuisine(None, "thai") is False
    slugs = {s for s, _label, _n in cuisine_pages.qualifying_cuisines(None)}
    assert "mexican" in slugs
    assert "italian" not in slugs  # renders, but stays out of the sitemap
    assert "thai" not in slugs


def test_route_renders_with_headline(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        pids = _seed_mexican(db, suf, cuisine_pages.CUISINE_PAGE_MIN_PROVIDERS)
    try:
        resp = client.get("/lake-havasu/mexican")
        assert resp.status_code == 200
        assert "Mexican Restaurants in Lake Havasu City" in resp.text
    finally:
        with SessionLocal() as db:
            _cleanup(db, pids)


def test_two_provider_cuisine_renders_and_search_routes(client: TestClient) -> None:
    """2026-07-01 audit A4: a real-but-thin cuisine (2 spots) renders its landing
    and the search bar 302s the cuisine query to it instead of the generic
    Restaurants fallback."""
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        pids = _seed_cuisine(
            db, suf, cuisine_pages.CUISINE_PAGE_MIN_PROVIDERS,
            primary="italian_restaurant", prefix="A4 Trattoria",
        )
    try:
        resp = client.get("/lake-havasu/italian")
        assert resp.status_code == 200
        assert "Italian Restaurants in Lake Havasu City" in resp.text

        r = client.get("/chat?q=italian food", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/lake-havasu/italian"
    finally:
        with SessionLocal() as db:
            _cleanup(db, pids)


def test_one_provider_cuisine_shows_no_chip(client: TestClient) -> None:
    """A single-provider cuisine renders no chip (chips gate on the render
    gate, not bare presence)."""
    from app.categories.queries import available_cuisines_for_route

    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        pre = cuisine_pages.cuisine_provider_count(db, "indian")
        pids = _seed_cuisine(
            db, suf, 1, primary="indian_restaurant", prefix="A4 Curry House"
        )
    try:
        with SessionLocal() as db:
            if pre == 0:  # guard against unrelated seeded rows in the shared DB
                chips = {c["slug"] for c in available_cuisines_for_route(db, "eat-drink")}
                assert "indian" not in chips
                assert cuisine_pages.is_publishable_cuisine(db, "indian") is False
    finally:
        with SessionLocal() as db:
            _cleanup(db, pids)


def test_unknown_cuisine_token_is_not_a_landing(client: TestClient) -> None:
    # An unknown token is neither a subcategory nor a cuisine nor a provider slug.
    resp = client.get(f"/lake-havasu/zzz-not-real-{uuid.uuid4().hex[:6]}")
    assert resp.status_code == 404


def test_cuisine_placement_key_isolates_from_parent_route() -> None:
    """A placement sold on ``cuisine:mexican`` pins + labels on the cuisine
    surface, but the same provider is NOT pinned on the bare Eat & Drink route."""
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        pids = _seed_mexican(db, suf, cuisine_pages.CUISINE_PAGE_MIN_PROVIDERS)
        paid = pids[0]
        paid_name = db.get(Provider, paid).provider_name
        db.add(
            Placement(
                provider_id=paid,
                placement_type=PlacementType.category_rank.value,
                category_slug=cuisine_pages.placement_key_for("mexican"),
                rank_tier=1,
                status=PlacementStatus.active.value,
                billing_type="monthly",
                price_cents=0,
            )
        )
        db.commit()
        try:
            facets = CategoryFacets(cuisine="mexican")
            # On the cuisine surface (keyed on cuisine:mexican): pinned + labeled.
            cards, _ = category_listing(
                db, "eat-drink", now=_NOW, facets=facets,
                placement_key=cuisine_pages.placement_key_for("mexican"),
            )
            assert cards and cards[0]["name"] == paid_name
            assert cards[0]["is_sponsored"] is True

            # On the bare Eat & Drink route (no cuisine key): NOT pinned/labeled.
            cards_parent, _ = category_listing(db, "eat-drink", now=_NOW, facets=facets)
            assert not (
                cards_parent
                and cards_parent[0]["name"] == paid_name
                and cards_parent[0]["is_sponsored"] is True
            )
        finally:
            _cleanup(db, pids)
