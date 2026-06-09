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
