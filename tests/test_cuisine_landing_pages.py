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


def _seed_mexican(db, suf: str, n: int) -> list[str]:
    """Create ``n`` active Eat & Drink providers that classify as Mexican."""
    pids: list[str] = []
    for i in range(n):
        p = Provider(
            provider_name=f"A3 Cantina {i} {suf}",
            category="restaurant",
            google_primary_category="mexican_restaurant",
            slug=f"a3-cantina-{i}-{suf}",
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
        pids = _seed_mexican(db, suf, cuisine_pages.CUISINE_PAGE_MIN_PROVIDERS)
        try:
            assert (
                cuisine_pages.cuisine_provider_count(db, "mexican")
                >= cuisine_pages.CUISINE_PAGE_MIN_PROVIDERS
            )
            assert cuisine_pages.is_publishable_cuisine(db, "mexican") is True
            assert cuisine_pages.is_publishable_cuisine(db, "not-a-cuisine") is False
            slugs = {s for s, _label, _n in cuisine_pages.qualifying_cuisines(db)}
            assert "mexican" in slugs
        finally:
            _cleanup(db, pids)


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
