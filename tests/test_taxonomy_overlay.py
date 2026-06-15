"""Phase E §3.1 — kids/family-first department ordering overlay (behind a flag).

Unit tests for the pure :func:`reorder_departments` partition, plus one
integration test proving ``all_departments`` actually flips order when the flag
is on (and is unchanged when off).
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from app.categories import leaf_pages, taxonomy_overlay
from app.db.database import SessionLocal
from app.db.models import Category, Entity, EntityCategory, Provider


def _slug(row) -> str:
    return row[0] if isinstance(row, tuple) else row


def test_reorder_is_identity_when_flag_off(monkeypatch) -> None:
    monkeypatch.delenv(taxonomy_overlay.TAXONOMY_REORG_FLAG, raising=False)
    items = ["eat-and-drink", "family-and-education", "lodging"]
    assert taxonomy_overlay.reorder_departments(items, slug_of=_slug) == items


def test_reorder_promotes_priority_in_order_when_flag_on(monkeypatch) -> None:
    monkeypatch.setenv(taxonomy_overlay.TAXONOMY_REORG_FLAG, "true")
    # Input order is deliberately NOT kids-first.
    items = [
        "lodging",
        "eat-and-drink",            # priority (last in KIDS_FIRST_DEPT_ORDER)
        "pets",
        "family-and-education",     # priority (first in KIDS_FIRST_DEPT_ORDER)
        "on-the-water",             # priority
    ]
    out = taxonomy_overlay.reorder_departments(items, slug_of=_slug)
    # Promoted block first, in KIDS_FIRST_DEPT_ORDER sequence...
    assert out[:3] == ["family-and-education", "on-the-water", "eat-and-drink"]
    # ...then the non-priority items in their original relative order.
    assert out[3:] == ["lodging", "pets"]
    # No drops or duplicates.
    assert sorted(out) == sorted(items)


def test_reorder_unchanged_when_no_priority_present(monkeypatch) -> None:
    monkeypatch.setenv(taxonomy_overlay.TAXONOMY_REORG_FLAG, "true")
    items = ["lodging", "pets", "shopping-and-retail"]
    assert taxonomy_overlay.reorder_departments(items, slug_of=_slug) == items


def _dept_with_leaf_and_provider(db, *, dept_slug: str, sort_order: int, suf: str) -> list[int]:
    """Create a level-0 dept + one gate-clearing leaf + one active provider.
    Returns the created Category ids for cleanup."""
    dept = Category(slug=dept_slug, name=f"Dept {suf}", sort_order=sort_order, level=0)
    db.add(dept)
    db.flush()
    leaf = Category(
        slug=f"leaf-{dept_slug}", name=f"Leaf {suf}", sort_order=0, level=1, parent_id=dept.id
    )
    db.add(leaf)
    db.flush()
    ent = Entity(
        entity_type="commercial", slug=f"tax-ent-{uuid.uuid4().hex[:10]}",
        name=f"Biz {suf}", source=f"test-tax-{suf}",
    )
    db.add(ent)
    db.flush()
    db.add(
        Provider(
            provider_name=f"Biz {suf}", category="x", slug=f"tax-prov-{uuid.uuid4().hex[:10]}",
            is_active=True, draft=False, source=f"test-tax-{suf}", entity_id=ent.id,
        )
    )
    db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
    return [dept.id, leaf.id]


def test_all_departments_flips_order_with_flag(monkeypatch) -> None:
    suf = uuid.uuid4().hex[:8]
    slug_a = f"tax-promoted-{suf}"   # will be the promoted (priority) department
    slug_b = f"tax-plain-{suf}"      # non-priority
    # Make ONLY slug_a a priority department, and give it the HIGHER sort_order
    # so flag-off lists it AFTER slug_b — then flag-on must flip them.
    monkeypatch.setattr(taxonomy_overlay, "KIDS_FIRST_DEPT_ORDER", (slug_a,))

    created: list[int] = []
    with SessionLocal() as db:
        created += _dept_with_leaf_and_provider(db, dept_slug=slug_b, sort_order=1, suf=suf)
        created += _dept_with_leaf_and_provider(db, dept_slug=slug_a, sort_order=50, suf=suf)
        db.commit()
        try:
            monkeypatch.delenv(taxonomy_overlay.TAXONOMY_REORG_FLAG, raising=False)
            off = [d.slug for d, _n, _t in leaf_pages.all_departments(db)]
            assert off.index(slug_b) < off.index(slug_a)  # sort_order order

            monkeypatch.setenv(taxonomy_overlay.TAXONOMY_REORG_FLAG, "true")
            on = [d.slug for d, _n, _t in leaf_pages.all_departments(db)]
            assert on.index(slug_a) < on.index(slug_b)  # promoted to the top
        finally:
            ent_ids = list(
                db.scalars(select(Entity.id).where(Entity.source == f"test-tax-{suf}")).all()
            )
            db.execute(delete(Provider).where(Provider.source == f"test-tax-{suf}"))
            if ent_ids:
                db.execute(delete(EntityCategory).where(EntityCategory.entity_id.in_(ent_ids)))
                db.execute(delete(Entity).where(Entity.id.in_(ent_ids)))
            db.execute(delete(Category).where(Category.id.in_(created)))
            db.commit()
