"""Phase 2B.3 — ``GET /api/search`` + search bar surface (template smoke)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, Provider
from app.main import app
from app.search.routes import _decode_offset, _encode_offset


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


def _entity(*, name: str, slug: str | None = None) -> Entity:
    s = slug or f"ent-{uuid.uuid4().hex[:12]}"
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=s,
        name=name,
        description=f"{name} description",
        source="test-search-route",
    )


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_api_search_plumber_returns_ranked_json_top_20(db: Session) -> None:
    suf = _suffix()
    mark = f"PipeFix {suf}"
    ent = _entity(name=f"{mark} Plumbing Services")
    p = Provider(
        provider_name=ent.name,
        slug=f"pipefix-{suf}",
        category="home_services",
        google_primary_category="plumber",
        source="test-search-route",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/api/search", params={"q": "plumber", "limit": 20})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data and "next_cursor" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) <= 20
    names = [row["name"] for row in data["results"]]
    assert any(mark in n for n in names), names


def test_leaf_link_predicate_none_for_non_category(monkeypatch: pytest.MonkeyPatch) -> None:
    """A query that resolves to no leaf yields no leaf-link branch (None)."""
    from app.categories import leaf_query
    from app.search import routes

    monkeypatch.setattr(leaf_query, "match_leaf_query", lambda _db, _q: None)
    monkeypatch.setattr(leaf_query, "match_leaf_service_intent", lambda _db, _q: None)
    assert (
        routes._leaf_link_exists_predicate(None, q_raw="zxqw", entity_type_filter=None)
        is None
    )


def test_leaf_link_predicate_skips_non_commercial() -> None:
    """Non-commercial entity-type filters short-circuit before resolving a leaf."""
    from app.db.entity_types import ENTITY_TYPE_EVENT
    from app.search import routes

    assert (
        routes._leaf_link_exists_predicate(
            None, q_raw="roofer", entity_type_filter=ENTITY_TYPE_EVENT
        )
        is None
    )


def test_api_search_category_query_via_leaf_link(db: Session) -> None:
    """A trade query ("roofer") reaches providers through the canonical EntityCategory
    leaf link even when their legacy category columns are generic AND the name lacks
    the trade word — i.e. the intent bridge, not name/synonym matching."""
    from app.categories import leaf_pages
    from app.categories import router as cat_router
    from app.db.models import Category, EntityCategory

    suf = _suffix()
    from sqlalchemy import select as _select

    dept = db.scalars(
        _select(Category).where(
            Category.slug == "home-and-property-services", Category.level == 0
        )
    ).first()
    created_cat_ids: list[int] = []
    if dept is None:
        dept = Category(
            slug="home-and-property-services",
            name="Home & Property Services",
            level=0,
            sort_order=8,
        )
        db.add(dept)
        db.flush()
        created_cat_ids.append(dept.id)
    leaf = Category(slug="roofing", name="Roofing", level=1, sort_order=0, parent_id=dept.id)
    db.add(leaf)
    db.flush()
    created_cat_ids.append(leaf.id)
    gate = max(leaf_pages.LEAF_PAGE_MIN_PROVIDERS, 1)
    marks = [f"ApexCrew{suf}{i}" for i in range(gate)]
    ents: list[Entity] = []
    for i, mark in enumerate(marks):
        ent = _entity(name=f"{mark} Contracting")  # deliberately NO "roof" in the name
        p = Provider(
            provider_name=ent.name,
            slug=f"apex-{suf}-{i}",
            category="home_services",  # generic legacy columns — synonym needles can't hit
            google_primary_category="general_contractor",
            source="test-search-route",
            draft=False,
            is_active=True,
            entity_id=ent.id,
        )
        db.add_all([ent, p])
        db.flush()
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
        ents.append(ent)
    db.commit()
    cat_router.reset_index_cache()
    try:
        with TestClient(app) as client:
            r = client.get("/api/search", params={"q": "roofer", "limit": 50})
        assert r.status_code == 200
        names = [row["name"] for row in r.json()["results"]]
        assert any(any(m in n for m in marks) for n in names), names
    finally:
        for ent in ents:
            for ec in (
                db.query(EntityCategory).filter(EntityCategory.entity_id == ent.id).all()
            ):
                db.delete(ec)
        db.query(Category).filter(Category.id.in_(created_cat_ids)).delete(
            synchronize_session=False
        )
        db.commit()
        cat_router.reset_index_cache()


def test_api_search_anonymous_no_auth_gate() -> None:
    with TestClient(app) as client:
        r = client.get("/api/search", params={"q": "test"})
    assert r.status_code == 200
    assert isinstance(r.json().get("results"), list)


def test_api_search_missing_q_400() -> None:
    with TestClient(app) as client:
        r = client.get("/api/search")
    assert r.status_code == 400


def test_api_search_filter_coffee_commercial(db: Session) -> None:
    suf = _suffix()
    mark = f"BeanWave {suf}"
    ent = _entity(name=f"{mark} Coffee House")
    p = Provider(
        provider_name=ent.name,
        slug=f"beanwave-{suf}",
        category="food_drink",
        google_primary_category="cafe",
        source="test-search-route",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get(
            "/api/search",
            params={"q": "coffee", "entity_type": "commercial"},
        )
    assert r.status_code == 200
    names = [row["name"] for row in r.json()["results"]]
    assert any(mark in n for n in names), names


def test_api_search_pagination_cursor_round_trip(db: Session) -> None:
    suf = _suffix()
    ents: list[Entity] = []
    provs: list[Provider] = []
    for i in range(3):
        name = f"CursorCat {suf} {i}"
        ent = _entity(name=name, slug=f"cursorcat-{suf}-{i}")
        p = Provider(
            provider_name=name,
            slug=ent.slug,
            category="misc",
            source="test-search-route",
            draft=False,
            is_active=True,
            entity_id=ent.id,
        )
        ents.append(ent)
        provs.append(p)
    db.add_all(ents + provs)
    db.commit()

    with TestClient(app) as client:
        r1 = client.get("/api/search", params={"q": f"CursorCat {suf}", "limit": 1})
        assert r1.status_code == 200
        d1 = r1.json()
        assert len(d1["results"]) == 1
        cur = d1.get("next_cursor")
        assert cur
        r2 = client.get(
            "/api/search",
            params={"q": f"CursorCat {suf}", "limit": 1, "cursor": cur},
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert len(d2["results"]) == 1
        assert d1["results"][0]["entity_id"] != d2["results"][0]["entity_id"]


def test_api_search_result_includes_hero_url(db: Session) -> None:
    suf = _suffix()
    mark = f"HeroPin {suf}"
    ent = _entity(name=f"{mark} Shop")
    p = Provider(
        provider_name=ent.name,
        slug=f"heropin-{suf}",
        category="misc",
        source="test-search-route",
        draft=False,
        is_active=True,
        entity_id=ent.id,
        attributes={"hero_pin_photo_url": "https://example.com/hero.jpg"},
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/api/search", params={"q": mark})
    assert r.status_code == 200
    row = next(x for x in r.json()["results"] if mark in x.get("name", ""))
    assert row.get("hero_url") == "https://example.com/hero.jpg"


def test_api_search_barbershop_synonym_finds_barber_primary(db: Session) -> None:
    suf = _suffix()
    mark = f"ClipJoint {suf}"
    ent = _entity(name=f"{mark} Cuts")
    p = Provider(
        provider_name=ent.name,
        slug=f"clipjoint-{suf}",
        category="beauty_personal_care",
        google_primary_category="barber_shop",
        source="test-search-route",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/api/search", params={"q": "barbershop"})
    assert r.status_code == 200
    names = [x["name"] for x in r.json()["results"]]
    assert any(mark in n for n in names), names


def test_search_bar_ui_home_and_provider_templates(db: Session) -> None:
    suf = _suffix()
    slug = f"tplsmoke-{suf}"
    ent = _entity(name=f"Tpl Smoke {suf}", slug=slug)
    p = Provider(
        provider_name=ent.name,
        slug=slug,
        category="misc",
        source="test-search-route",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        h = client.get("/home")
        assert h.status_code == 200
        t = h.text
        assert 'name="q"' in t
        assert "/static/styles/lake_redesign.css" in t  # v4 home
        assert 'id="rd-search"' in t

        pr = client.get(f"/provider/{slug}")
        assert pr.status_code == 200
        pt = pr.text
        assert "/chat?q=" in pt
        assert "Ask Hava about this business" in pt


def test_cursor_helpers_round_trip() -> None:
    assert _decode_offset(None) == 0
    c = _encode_offset(5)
    assert _decode_offset(c) == 5
