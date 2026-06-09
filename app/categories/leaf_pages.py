"""Generalized taxonomy leaf pages (Workstream B.1).

Extends the dedicated-trade-page pattern (``app/categories/trades.py``) from the
ten curated ``home-property-services`` trades to EVERY department/leaf in the
live A.3 taxonomy.

Data contract (A.3, live on prod):
  * a **leaf** is a ``categories`` row with ``level = 1`` and ``parent_id`` →
    its department (``level = 0``);
  * a leaf's listings are Providers whose Entity carries a PRIMARY
    ``entity_categories`` link at that leaf::

        Provider JOIN Entity          ON Provider.entity_id = Entity.id
                 JOIN EntityCategory  ON ec.entity_id       = Entity.id
        WHERE ec.category_id = {leaf.id} AND ec.is_primary
          AND Entity.is_active AND Provider.is_active AND NOT Provider.draft

The card renderer (``cat_queries._provider_card``) needs Provider data
(rating / hours / photo), so the listing INNER-joins Provider — an entity with a
primary leaf but no active Provider simply has no renderable card, and the page
count reflects exactly what renders (same honesty contract as the trade pages,
where ``count == len(providers)``).

Thin-page gate (shared with trades): a leaf "ships" — resolves, joins the
sitemap, gets linked — only at/above :data:`LEAF_PAGE_MIN_PROVIDERS` active
renderable listings. Below that the page 404s, mirroring the Google
scaled-content rule already applied to trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.categories import queries as cat_queries
from app.categories.trades import TRADE_PAGE_MIN_PROVIDERS
from app.db.models import Category, Entity, EntityCategory, Provider

#: Shared thin-page gate — one rule for trades and every taxonomy leaf.
LEAF_PAGE_MIN_PROVIDERS = TRADE_PAGE_MIN_PROVIDERS


@dataclass(frozen=True)
class Leaf:
    """A resolved taxonomy leaf + its department (slugs/labels for rendering)."""

    id: int
    slug: str
    name: str
    department_slug: str
    department_name: str


def resolve_leaf(db: Session, department_slug: str, leaf_slug: str) -> Leaf | None:
    """Resolve ``(department, leaf)`` slugs to a :class:`Leaf`, or ``None``.

    The leaf must be a ``level = 1`` category whose ``parent_id`` points at a
    ``level = 0`` department whose slug matches ``department_slug``. Slugs are
    lower-cased/stripped. Any mismatch (unknown leaf, wrong/missing parent,
    department slug that doesn't match the leaf's actual parent) returns
    ``None`` so the caller 404s. Never raises.
    """
    ds = (department_slug or "").strip().lower()
    ls = (leaf_slug or "").strip().lower()
    if not ds or not ls:
        return None
    try:
        leaf = (
            db.query(Category)
            .filter(Category.slug == ls, Category.level == 1)
            .one_or_none()
        )
        if leaf is None or leaf.parent_id is None:
            return None
        dept = (
            db.query(Category)
            .filter(Category.id == leaf.parent_id, Category.level == 0)
            .one_or_none()
        )
        if dept is None or dept.slug != ds:
            return None
    except Exception:
        return None
    return Leaf(
        id=leaf.id,
        slug=leaf.slug,
        name=leaf.name,
        department_slug=dept.slug,
        department_name=dept.name,
    )


def _leaf_provider_query(db: Session, leaf_id: int):
    """Base query: active renderable Providers whose entity's PRIMARY leaf is
    ``leaf_id``."""
    return (
        db.query(Provider)
        .join(Entity, Provider.entity_id == Entity.id)
        .join(EntityCategory, EntityCategory.entity_id == Entity.id)
        .filter(
            EntityCategory.category_id == leaf_id,
            EntityCategory.is_primary.is_(True),
            Entity.is_active.is_(True),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        )
    )


def leaf_provider_rows(db: Session, leaf: Leaf) -> list[Provider]:
    """Active renderable Providers for ``leaf``, ranked by the dampened rating
    sort (institutions over thin 5.0/2-review outliers). Empty on any DB hiccup.
    """
    try:
        rows: list[Provider] = (
            _leaf_provider_query(db, leaf.id)
            .order_by(*cat_queries._dampened_rating_sort_key())
            .limit(cat_queries._MATERIALIZE_CAP)
            .all()
        )
    except Exception:
        return []
    return rows


def leaf_listing(
    db: Session, leaf: Leaf, *, now: datetime
) -> tuple[list[dict[str, Any]], int, list[Provider]]:
    """``(cards, total, providers)`` for a leaf page.

    Cards use the SAME builder as the category/trade pages, so a leaf renders
    identical listing cards. ``providers`` rides along for the ItemList JSON-LD.
    """
    providers = leaf_provider_rows(db, leaf)
    cards = [cat_queries._provider_card(db, p, now=now) for p in providers]
    return cards, len(providers), providers


def leaf_provider_count(db: Session, leaf: Leaf) -> int:
    """Active renderable Provider count for ``leaf`` (the thin-page gate input)."""
    try:
        return int(_leaf_provider_query(db, leaf.id).count())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Department landings + sitemap enumeration (B.2)
# ---------------------------------------------------------------------------


def _leaf_from_categories(leaf: Category, dept: Category) -> Leaf:
    return Leaf(
        id=leaf.id,
        slug=leaf.slug,
        name=leaf.name,
        department_slug=dept.slug,
        department_name=dept.name,
    )


def _gate_counts(db: Session, *, dept_id: int | None = None) -> dict[int, int]:
    """``{leaf category_id: renderable provider count}`` for leaves at/above the
    gate. One grouped query. Optionally scoped to a single department."""
    from sqlalchemy import func

    q = (
        db.query(EntityCategory.category_id, func.count(Provider.id))
        .select_from(EntityCategory)
        .join(Entity, EntityCategory.entity_id == Entity.id)
        .join(Provider, Provider.entity_id == Entity.id)
        .join(Category, Category.id == EntityCategory.category_id)
        .filter(
            EntityCategory.is_primary.is_(True),
            Entity.is_active.is_(True),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
            Category.level == 1,
        )
    )
    if dept_id is not None:
        q = q.filter(Category.parent_id == dept_id)
    rows = (
        q.group_by(EntityCategory.category_id)
        .having(func.count(Provider.id) >= LEAF_PAGE_MIN_PROVIDERS)
        .all()
    )
    return {cid: int(n) for cid, n in rows}


def qualifying_leaves(db: Session) -> list[tuple[Leaf, int]]:
    """Every taxonomy leaf clearing the gate, with its renderable count, sorted
    by count desc then name. Used by the sitemap so sub-gate leaves stay out."""
    try:
        counts = _gate_counts(db)
        if not counts:
            return []
        cats = (
            db.query(Category)
            .filter(Category.id.in_(list(counts)), Category.level == 1)
            .all()
        )
        dept_ids = {c.parent_id for c in cats if c.parent_id is not None}
        depts = {
            d.id: d
            for d in db.query(Category).filter(Category.id.in_(dept_ids)).all()
        }
    except Exception:
        return []
    out: list[tuple[Leaf, int]] = []
    for c in cats:
        dept = depts.get(c.parent_id) if c.parent_id is not None else None
        if dept is None:
            continue
        out.append((_leaf_from_categories(c, dept), counts[c.id]))
    out.sort(key=lambda t: (-t[1], t[0].name.lower()))
    return out


def resolve_department(db: Session, dept_slug: str) -> Category | None:
    """A ``level = 0`` department category with the given slug that actually has
    child leaves, or ``None``. (A flat legacy slug with no children is not a
    taxonomy department and stays the existing flat route's concern.)"""
    ds = (dept_slug or "").strip().lower()
    if not ds:
        return None
    try:
        dept = (
            db.query(Category)
            .filter(Category.slug == ds, Category.level == 0)
            .one_or_none()
        )
        if dept is None:
            return None
        has_children = (
            db.query(Category.id)
            .filter(Category.parent_id == dept.id, Category.level == 1)
            .first()
            is not None
        )
        return dept if has_children else None
    except Exception:
        return None


def department_leaves(db: Session, dept: Category) -> list[tuple[Leaf, int]]:
    """Gate-clearing child leaves of ``dept`` with counts, sorted by count desc."""
    try:
        counts = _gate_counts(db, dept_id=dept.id)
        if not counts:
            return []
        cats = (
            db.query(Category)
            .filter(Category.id.in_(list(counts)), Category.level == 1)
            .all()
        )
    except Exception:
        return []
    out = [(_leaf_from_categories(c, dept), counts[c.id]) for c in cats]
    out.sort(key=lambda t: (-t[1], t[0].name.lower()))
    return out
