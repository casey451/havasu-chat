"""Workstream B.1 — generalized taxonomy leaf pages.

Covers resolve_leaf (department/leaf slug resolution against the level-0/level-1
tree), the category_id + is_primary listing join, the >=3 thin-page gate, the
route 404 matrix, and the leaf JSON-LD (BreadcrumbList + ItemList, no
AggregateRating per D4).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.categories import leaf_pages
from app.db.database import Base, SessionLocal
from app.db.models import Category, Entity, EntityCategory, Provider
from app.main import app

_SOURCE = "test-leaf-pages"
_JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


# --- resolve_leaf unit (isolated in-memory DB) ------------------------------


@pytest.fixture
def mem_db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_tree(db: Session) -> tuple[Category, Category]:
    dept = Category(slug="home-and-property-services", name="Home & Property Services",
                    sort_order=0, level=0)
    db.add(dept)
    db.flush()
    leaf = Category(slug="plumbing", name="Plumbing", sort_order=0, level=1,
                    parent_id=dept.id)
    db.add(leaf)
    db.commit()
    return dept, leaf


def test_resolve_leaf_valid(mem_db: Session) -> None:
    _make_tree(mem_db)
    leaf = leaf_pages.resolve_leaf(mem_db, "home-and-property-services", "plumbing")
    assert leaf is not None
    assert leaf.slug == "plumbing" and leaf.name == "Plumbing"
    assert leaf.department_slug == "home-and-property-services"


def test_resolve_leaf_case_insensitive(mem_db: Session) -> None:
    _make_tree(mem_db)
    assert leaf_pages.resolve_leaf(mem_db, "Home-And-Property-Services", "PLUMBING")


def test_resolve_leaf_wrong_department_is_none(mem_db: Session) -> None:
    _make_tree(mem_db)
    # Right leaf slug, wrong department parent.
    assert leaf_pages.resolve_leaf(mem_db, "eat-and-drink", "plumbing") is None


def test_resolve_leaf_unknown_leaf_is_none(mem_db: Session) -> None:
    _make_tree(mem_db)
    assert leaf_pages.resolve_leaf(mem_db, "home-and-property-services", "nope") is None


def test_resolve_leaf_department_slug_is_not_a_leaf(mem_db: Session) -> None:
    _make_tree(mem_db)
    # The department (level 0) is not itself resolvable as a leaf.
    assert leaf_pages.resolve_leaf(mem_db, "home-and-property-services",
                                   "home-and-property-services") is None


# --- route + listing + gate (app DB) ----------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed_leaf_with_providers(db: Session, *, dept_slug: str, leaf_slug: str,
                              leaf_name: str, n: int) -> list[str]:
    """Seed a dept+leaf and ``n`` active providers primary-linked at the leaf."""
    dept = Category(slug=dept_slug, name=leaf_name + " Dept", sort_order=0, level=0)
    db.add(dept)
    db.flush()
    leaf = Category(slug=leaf_slug, name=leaf_name, sort_order=0, level=1,
                    parent_id=dept.id)
    db.add(leaf)
    db.flush()
    names: list[str] = []
    for i in range(n):
        name = f"{leaf_name} Biz {i} {uuid4().hex[:6]}"
        ent = Entity(entity_type="commercial", slug=f"leaf-ent-{uuid4().hex[:10]}",
                     name=name, source=_SOURCE)
        db.add(ent)
        db.flush()
        db.add(Provider(provider_name=name, category="x", slug=f"leaf-prov-{uuid4().hex[:10]}",
                        is_active=True, draft=False, source=_SOURCE, entity_id=ent.id,
                        google_rating=4.5, google_review_count=20))
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
        names.append(name)
    db.commit()
    return names


@pytest.fixture
def seeded_leaves() -> Iterator[dict]:
    """A gate-clearing leaf (3 providers) and a below-gate leaf (2)."""
    suf = uuid4().hex[:6]
    ship_dept = f"ship-dept-{suf}"
    ship_leaf = f"ship-leaf-{suf}"
    thin_dept = f"thin-dept-{suf}"
    thin_leaf = f"thin-leaf-{suf}"
    cat_slugs = [ship_dept, ship_leaf, thin_dept, thin_leaf]
    with SessionLocal() as db:
        ship_names = _seed_leaf_with_providers(
            db, dept_slug=ship_dept, leaf_slug=ship_leaf, leaf_name="Plumbing",
            n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS)
        thin_names = _seed_leaf_with_providers(
            db, dept_slug=thin_dept, leaf_slug=thin_leaf, leaf_name="Falconry",
            n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS - 1)
    try:
        yield {
            "ship_dept": ship_dept, "ship_leaf": ship_leaf, "ship_names": ship_names,
            "thin_dept": thin_dept, "thin_leaf": thin_leaf, "thin_names": thin_names,
        }
    finally:
        with SessionLocal() as db:
            for prov in db.scalars(select(Provider).where(Provider.source == _SOURCE)).all():
                db.delete(prov)
            for ent in db.scalars(select(Entity).where(Entity.source == _SOURCE)).all():
                for ec in db.scalars(
                    select(EntityCategory).where(EntityCategory.entity_id == ent.id)
                ).all():
                    db.delete(ec)
                db.delete(ent)
            for cat in db.scalars(select(Category).where(Category.slug.in_(cat_slugs))).all():
                db.delete(cat)
            db.commit()


def test_leaf_page_resolves_and_lists_primary_entities(
    client: TestClient, seeded_leaves: dict
) -> None:
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 200
    body = r.text
    for name in seeded_leaves["ship_names"]:
        assert name in body
    # H1 carries the live count and the leaf label.
    n = len(seeded_leaves["ship_names"])
    assert f"<h1>{n} Best Plumbing in Lake Havasu City, AZ</h1>" in body


def test_leaf_below_gate_404s(client: TestClient, seeded_leaves: dict) -> None:
    assert len(seeded_leaves["thin_names"]) < leaf_pages.LEAF_PAGE_MIN_PROVIDERS
    r = client.get(f"/categories/{seeded_leaves['thin_dept']}/{seeded_leaves['thin_leaf']}")
    assert r.status_code == 404


def test_leaf_unknown_department_404s(client: TestClient, seeded_leaves: dict) -> None:
    r = client.get(f"/categories/no-such-dept/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 404


def test_leaf_wrong_department_for_leaf_404s(client: TestClient, seeded_leaves: dict) -> None:
    # ship_leaf is real but not under thin_dept.
    r = client.get(f"/categories/{seeded_leaves['thin_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 404


def test_leaf_page_jsonld_breadcrumb_itemlist_no_aggregate_rating(
    client: TestClient, seeded_leaves: dict
) -> None:
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 200
    body = r.text
    blocks = [json.loads(m) for m in _JSONLD_RE.findall(body)]
    types = {b.get("@type") for b in blocks}
    assert "BreadcrumbList" in types
    assert "ItemList" in types
    ilist = next(b for b in blocks if b["@type"] == "ItemList")
    assert ilist["numberOfItems"] == len(seeded_leaves["ship_names"])
    for entry in ilist["itemListElement"]:
        assert entry["url"].startswith("http")
        assert "/provider/" in entry["url"]
    # D4: no self-serving structured ratings anywhere.
    assert "AggregateRating" not in body
    assert "aggregateRating" not in body


def test_leaf_listing_keys_on_primary_only(
    client: TestClient, seeded_leaves: dict
) -> None:
    """A non-primary entity_categories link at the leaf must NOT list."""
    extra_name = f"Secondary Co {uuid4().hex[:6]}"
    with SessionLocal() as db:
        leaf = db.scalars(
            select(Category).where(Category.slug == seeded_leaves["ship_leaf"])
        ).one()
        ent = Entity(entity_type="commercial", slug=f"leaf-ent-{uuid4().hex[:10]}",
                     name=extra_name, source=_SOURCE)
        db.add(ent)
        db.flush()
        db.add(Provider(provider_name=extra_name, category="x",
                        slug=f"leaf-prov-{uuid4().hex[:10]}", is_active=True, draft=False,
                        source=_SOURCE, entity_id=ent.id, google_rating=4.0,
                        google_review_count=10))
        # is_primary=False -> should be excluded from the leaf listing.
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=False))
        db.commit()
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 200
    assert extra_name not in r.text


# --- B.2: department landings + breadcrumb upgrade + sitemap -----------------


@pytest.fixture(autouse=True)
def _clear_sitemap_cache() -> Iterator[None]:
    from app import main as main_module

    main_module._sitemap_cache.clear()
    yield
    main_module._sitemap_cache.clear()


def test_department_landing_lists_gate_clearing_leaves(
    client: TestClient, seeded_leaves: dict
) -> None:
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}")
    assert r.status_code == 200
    body = r.text
    # The gate-clearing child leaf is linked with its live count.
    assert f'href="/categories/{seeded_leaves["ship_dept"]}/{seeded_leaves["ship_leaf"]}"' in body
    assert "Plumbing" in body
    n = len(seeded_leaves["ship_names"])
    assert f"{n} listed" in body


def test_department_landing_all_subgate_404s(
    client: TestClient, seeded_leaves: dict
) -> None:
    # thin_dept's only child leaf is below the gate -> nothing shippable -> 404.
    r = client.get(f"/categories/{seeded_leaves['thin_dept']}")
    assert r.status_code == 404


def test_leaf_breadcrumb_links_department(
    client: TestClient, seeded_leaves: dict
) -> None:
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 200
    # Three-level crumb now links the department landing.
    assert f'href="/categories/{seeded_leaves["ship_dept"]}"' in r.text
    blocks = [json.loads(m) for m in _JSONLD_RE.findall(r.text)]
    crumb = next(b for b in blocks if b.get("@type") == "BreadcrumbList")
    assert [it["position"] for it in crumb["itemListElement"]] == [1, 2, 3]


def test_sitemap_includes_gate_leaf_and_department_excludes_thin(
    client: TestClient, seeded_leaves: dict
) -> None:
    from app import main as main_module

    r = client.get("/sitemap-pages.xml")
    assert r.status_code == 200
    xml = r.text
    base = main_module._base_url()
    assert f"{base}/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}" in xml
    assert f"{base}/categories/{seeded_leaves['ship_dept']}" in xml
    # Sub-gate leaf + its (empty) department are excluded.
    assert f"{base}/categories/{seeded_leaves['thin_dept']}/{seeded_leaves['thin_leaf']}" not in xml


def test_qualifying_and_department_leaves(mem_db: Session) -> None:
    dept, leaf = _make_tree(mem_db)
    # 3 providers at the leaf -> clears the gate.
    for _ in range(leaf_pages.LEAF_PAGE_MIN_PROVIDERS):
        ent = Entity(entity_type="commercial", slug=f"e-{uuid4().hex[:8]}",
                     name="X", source=_SOURCE)
        mem_db.add(ent)
        mem_db.flush()
        mem_db.add(Provider(provider_name="X", category="x", slug=f"p-{uuid4().hex[:8]}",
                            is_active=True, draft=False, entity_id=ent.id))
        mem_db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
    mem_db.commit()
    qual = leaf_pages.qualifying_leaves(mem_db)
    assert any(lf.slug == "plumbing" and n == 3 for lf, n in qual)
    assert leaf_pages.resolve_department(mem_db, "home-and-property-services") is not None
    dleaves = leaf_pages.department_leaves(mem_db, dept)
    assert [(lf.slug, n) for lf, n in dleaves] == [("plumbing", 3)]


# --- B.2: Wave-1 curated per-leaf copy --------------------------------------


def test_wave1_leaf_copy_intros_and_faq_counts() -> None:
    from app.categories.leaf_copy import LEAF_COPY

    assert len(LEAF_COPY) == 14
    for slug, copy in LEAF_COPY.items():
        words = len(copy.intro.split())
        assert 40 <= words <= 100, f"{slug}: intro is {words} words"
        assert 4 <= len(copy.faqs) <= 6, f"{slug}: {len(copy.faqs)} FAQs"


def test_copy_for_leaf_unknown_is_none() -> None:
    from app.categories.leaf_copy import copy_for_leaf

    assert copy_for_leaf("definitely-not-a-leaf") is None
    assert copy_for_leaf(None) is None
    assert copy_for_leaf("plumbing") is not None


def test_curated_leaf_page_renders_intro_and_faqs(client: TestClient) -> None:
    """A Wave-1 leaf (slug 'plumbing') renders its curated intro + FAQ block."""

    suf = uuid4().hex[:6]
    dept_slug = f"hps-{suf}"
    cat_slugs = [dept_slug, "plumbing"]
    with SessionLocal() as db:
        # Skip if a 'plumbing' leaf already exists in this DB (avoid slug clash).
        if db.scalars(select(Category).where(Category.slug == "plumbing")).first():
            pytest.skip("'plumbing' leaf already present in this DB")
        names = _seed_leaf_with_providers(
            db, dept_slug=dept_slug, leaf_slug="plumbing", leaf_name="Plumbing",
            n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS)
    try:
        r = client.get(f"/categories/{dept_slug}/plumbing")
        assert r.status_code == 200
        body = r.text
        # Curated intro fragment present (not the generic fallback).
        assert "Desert water is hard on pipes" in body
        assert "The {n} listings below are ranked" not in body
        # FAQ block rendered (4-6 items), with the live count interpolated.
        n_faq = body.count('class="faq-item"')
        assert 4 <= n_faq <= 6
        assert f"lists {len(names)} plumbing" in body
    finally:
        with SessionLocal() as db:
            for prov in db.scalars(select(Provider).where(Provider.source == _SOURCE)).all():
                db.delete(prov)
            for ent in db.scalars(select(Entity).where(Entity.source == _SOURCE)).all():
                for ec in db.scalars(
                    select(EntityCategory).where(EntityCategory.entity_id == ent.id)
                ).all():
                    db.delete(ec)
                db.delete(ent)
            for cat in db.scalars(select(Category).where(Category.slug.in_(cat_slugs))).all():
                db.delete(cat)
            db.commit()
