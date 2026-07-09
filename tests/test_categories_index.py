"""``GET /categories`` index page (Q2, rebuilt on the A.3 taxonomy 2026-06-09).

The index lists the live taxonomy departments (level-0 ``categories`` rows
owning >=1 gate-clearing leaf) with leaf-summed, non-overlapping counts — the
retired flat ``CATEGORY_FILTERS`` buckets no longer appear anywhere.

Coverage:

1. Data-shape invariants on ``_build_index_payload`` — seeded departments
   appear with the documented row shape, dept-name labels, and counts equal to
   the sum of their gate-clearing leaves' renderable listings (sub-gate leaves
   excluded).
2. Defensive DB error handling — ``_dept_peek_provider`` swallows a DB
   exception to None; ``all_departments`` swallows to [].
3. Cache behavior — identity within the TTL window; ``reset_index_cache()``
   forces a rebuild.
4. End-to-end — GET /categories 200s, renders the seeded department card with
   its live count and /categories/{department} link, lights the Explore tab.

Autouse cache-reset fixture mirrors
``tests/test_robots_and_sitemap.py::_clear_sitemap_cache`` so module state
never leaks across cases.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categories import leaf_pages
from app.categories import router as cat_router
from app.db.database import SessionLocal
from app.db.models import Category, Entity, EntityCategory, Provider
from app.main import app

_SOURCE = "test-categories-index"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_index_cache() -> Iterator[None]:
    """Reset the module-level /categories cache between tests."""
    cat_router.reset_index_cache()
    yield
    cat_router.reset_index_cache()


def _seed_leaf(db: Session, dept: Category, *, slug: str, name: str, n: int) -> None:
    leaf = Category(slug=slug, name=name, sort_order=0, level=1, parent_id=dept.id)
    db.add(leaf)
    db.flush()
    for i in range(n):
        ent = Entity(
            entity_type="commercial",
            slug=f"idx-ent-{uuid4().hex[:10]}",
            name=f"{name} Biz {i}",
            source=_SOURCE,
        )
        db.add(ent)
        db.flush()
        db.add(
            Provider(
                provider_name=f"{name} Biz {i}",
                category="x",
                slug=f"idx-prov-{uuid4().hex[:10]}",
                is_active=True,
                draft=False,
                source=_SOURCE,
                entity_id=ent.id,
                google_rating=4.5,
                google_review_count=20,
            )
        )
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))


@pytest.fixture
def seeded_departments() -> Iterator[dict]:
    """Two departments: one with two gate-clearing leaves + one sub-gate leaf
    (counts must exclude the sub-gate one), one with a single shipping leaf."""
    suf = uuid4().hex[:6]
    gate = leaf_pages.LEAF_PAGE_MIN_PROVIDERS
    dept_a = f"idx-dept-a-{suf}"
    dept_b = f"idx-dept-b-{suf}"
    slugs = [
        dept_a,
        dept_b,
        f"idx-leaf-a1-{suf}",
        f"idx-leaf-a2-{suf}",
        f"idx-leaf-a3-{suf}",
        f"idx-leaf-b1-{suf}",
    ]
    with SessionLocal() as db:
        a = Category(slug=dept_a, name=f"Idx Dept A {suf}", sort_order=90, level=0)
        b = Category(slug=dept_b, name=f"Idx Dept B {suf}", sort_order=91, level=0)
        db.add_all([a, b])
        db.flush()
        _seed_leaf(db, a, slug=f"idx-leaf-a1-{suf}", name="Idx Leaf A1", n=gate + 1)
        _seed_leaf(db, a, slug=f"idx-leaf-a2-{suf}", name="Idx Leaf A2", n=gate)
        # Sub-gate leaf: must not count toward the department total.
        _seed_leaf(db, a, slug=f"idx-leaf-a3-{suf}", name="Idx Leaf A3", n=gate - 1)
        _seed_leaf(db, b, slug=f"idx-leaf-b1-{suf}", name="Idx Leaf B1", n=gate)
        db.commit()
    try:
        yield {
            "dept_a": dept_a,
            "dept_a_name": f"Idx Dept A {suf}",
            "dept_a_count": (gate + 1) + gate,
            "dept_b": dept_b,
            "dept_b_name": f"Idx Dept B {suf}",
            "dept_b_count": gate,
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
            for cat in db.scalars(
                select(Category).where(Category.slug.in_(slugs))
            ).all():
                db.delete(cat)
            db.commit()


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _BoomDB:
    """Minimal DB stub whose ``query()`` always raises.

    Exercises the try/except in ``_dept_peek_provider`` and
    ``leaf_pages.all_departments`` without spinning up a session.
    """

    def query(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated DB outage")


# ---------------------------------------------------------------------------
# Data-shape invariants
# ---------------------------------------------------------------------------


def test_build_index_payload_rows_are_departments(seeded_departments: dict) -> None:
    """Seeded departments appear as rows keyed by department slug, with the
    department's live name as the label."""
    with SessionLocal() as db:
        payload = cat_router._build_index_payload(db)
    by_slug = {row["slug"]: row for row in payload}
    assert seeded_departments["dept_a"] in by_slug
    assert seeded_departments["dept_b"] in by_slug
    assert by_slug[seeded_departments["dept_a"]]["label"] == seeded_departments["dept_a_name"]


def test_build_index_payload_counts_sum_gate_clearing_leaves(
    seeded_departments: dict,
) -> None:
    """A department's count is the sum of its gate-clearing leaves' renderable
    listings; sub-gate leaves are excluded (matching the landing page)."""
    with SessionLocal() as db:
        payload = cat_router._build_index_payload(db)
    by_slug = {row["slug"]: row for row in payload}
    row_a = by_slug[seeded_departments["dept_a"]]
    assert row_a["count"] == seeded_departments["dept_a_count"]
    assert row_a["leaf_count"] == 2  # the sub-gate third leaf is excluded
    row_b = by_slug[seeded_departments["dept_b"]]
    assert row_b["count"] == seeded_departments["dept_b_count"]


def test_build_index_payload_row_shape(seeded_departments: dict) -> None:
    """Every row carries the documented keys with the documented types."""
    with SessionLocal() as db:
        payload = cat_router._build_index_payload(db)
    assert payload, "expected at least the seeded departments"
    for row in payload:
        assert isinstance(row, dict)
        assert isinstance(row["slug"], str) and row["slug"]
        assert isinstance(row["label"], str) and row["label"]
        assert isinstance(row["blurb"], str) and row["blurb"]
        assert isinstance(row["count"], int)
        assert row["count"] >= 0
        assert isinstance(row["leaf_count"], int)
        assert isinstance(row["peek_images"], list)
        for peek in row["peek_images"]:
            assert isinstance(peek, dict)
            assert "url" in peek and "name" in peek
        assert isinstance(row["empty_blurb"], str) and row["empty_blurb"]


def test_build_index_payload_excludes_retired_flat_buckets(
    seeded_departments: dict,
) -> None:
    """The retired flat CATEGORY_FILTERS slugs never appear as index rows."""
    from app.categories.queries import CATEGORY_FILTERS

    with SessionLocal() as db:
        payload = cat_router._build_index_payload(db)
    flat_only = set(CATEGORY_FILTERS) - {"on-the-water", "pets"}
    assert not ({row["slug"] for row in payload} & flat_only)


# ---------------------------------------------------------------------------
# Defensive DB error handling
# ---------------------------------------------------------------------------


def test_dept_peek_provider_swallows_db_exception_to_none() -> None:
    """A DB outage during the peek query must return None, not 500."""
    assert cat_router._dept_peek_provider(_BoomDB(), 12345) is None


def test_all_departments_swallows_db_exception_to_empty() -> None:
    """A DB outage during department aggregation degrades to [] (the index
    renders empty rather than 500ing)."""
    assert leaf_pages.all_departments(_BoomDB()) == []


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


def test_get_index_payload_caches_within_ttl_window() -> None:
    """Two calls in the TTL window must return the same object.

    Identity check (``is``) -- a fresh list with identical contents
    would still pass an equality check but would prove the cache was
    bypassed, so we want the stronger guarantee.
    """
    with SessionLocal() as db:
        first = cat_router._get_index_payload(db)
        second = cat_router._get_index_payload(db)
    assert first is second


def test_get_index_payload_rebuilds_after_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reset_index_cache() forces the next call to rebuild.

    We count invocations of _build_index_payload to prove the cache
    actually clears -- a no-op reset would let the second call hit
    the cached payload and the counter would stay at 1.
    """
    calls = {"n": 0}
    real_build = cat_router._build_index_payload

    def _counting_build(db):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real_build(db)

    monkeypatch.setattr(cat_router, "_build_index_payload", _counting_build)

    with SessionLocal() as db:
        cat_router._get_index_payload(db)
        assert calls["n"] == 1
        # Second call inside the window: cached -> still 1.
        cat_router._get_index_payload(db)
        assert calls["n"] == 1
        # After reset, next call rebuilds.
        cat_router.reset_index_cache()
        cat_router._get_index_payload(db)
        assert calls["n"] == 2


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def test_get_categories_index_returns_200(client: TestClient) -> None:
    r = client.get("/categories")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_get_categories_index_renders_department_card(
    client: TestClient, seeded_departments: dict
) -> None:
    """The seeded department renders a card: label, live count badge, and a
    /categories/{department} link."""
    r = client.get("/categories")
    assert r.status_code == 200
    body = r.text
    assert seeded_departments["dept_a_name"] in body
    assert f'href="/categories/{seeded_departments["dept_a"]}"' in body
    # Lake tile renders the live count as a bare badge (<span class="c">N</span>),
    # the word "listings" is no longer printed per the count-clause removal.
    assert f'<span class="c">{seeded_departments["dept_a_count"]}</span>' in body


def test_get_categories_index_has_all_categories_topbar_link(
    client: TestClient,
) -> None:
    """Categories index highlights the Directory location in its chrome.

    Lake Ink & Brass: the index marks its place via the breadcrumb's
    ``<span aria-current="page">Directory</span>`` (the desert bottom-nav
    /categories aria-current link was retired with the desert chrome).
    """
    r = client.get("/categories")
    assert r.status_code == 200
    body = r.text
    assert '<span aria-current="page">Directory</span>' in body
