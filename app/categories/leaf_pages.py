"""Generalized taxonomy leaf pages (Workstream B.1).

Extends the dedicated-trade-page pattern (``app/categories/trades.py``) from the
ten curated ``home-property-services`` trades to EVERY department/leaf in the
live A.3 taxonomy.

Data contract (A.3, live on prod):
  * a **leaf** is a ``categories`` row with ``level = 1`` and ``parent_id`` →
    its department (``level = 0``);
  * a leaf's listings are the ACTIVE entities whose PRIMARY ``entity_categories``
    link is that leaf (``ec.category_id = {leaf.id} AND ec.is_primary AND
    Entity.is_active``).

Rendering: an entity with an active, non-draft **Provider** renders the rich
Provider card (rating / hours / photo). An entity with NO active Provider —
the place-type rows like trails, beaches, parks, libraries, utilities, plus a
handful of businesses still missing a Provider backfill — renders a **place
card** from the entity's own fields (name, district, the "New / few reviews
yet" state), non-linking (it has no ``/provider/{slug}`` detail page). Earlier
this listing INNER-joined Provider, so those ~154 entities never rendered and
their leaves under-counted toward the gate; including them lifts the
place-heavy and borderline leaves (Kayak & Paddle, Fishing Charters, Jet Ski &
Watersports, Dog Parks, Dance Studios, Utilities, Libraries, …).

Publish gate: a leaf "ships" — resolves, joins the sitemap, gets linked,
routes from chat — whenever it has at least :data:`LEAF_PAGE_MIN_PROVIDERS`
active renderable listing (Provider-backed OR place). As of 2026-06-11 every
seeded category/subcategory is its own indexable page, so a leaf 404s only
when it is genuinely empty (0 listings).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, joinedload, selectinload

from app.categories import cross_listing
from app.categories import queries as cat_queries
from app.db.models import Category, Entity, EntityCategory, Provider

#: Taxonomy-leaf publish gate (2026-06-11, Casey): every seeded category and
#: subcategory gets its own indexable page, so a leaf publishes (resolves,
#: joins the sitemap, gets linked, routes from chat) whenever it has at least
#: one renderable listing — it 404s only when genuinely empty. This supersedes
#: the prior >=3 "scaled-content" gate for taxonomy leaves; the curated trade
#: pages keep their own ``TRADE_PAGE_MIN_PROVIDERS`` threshold.
LEAF_PAGE_MIN_PROVIDERS = 1


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


def resolve_leaf_by_slug(db: Session, leaf_slug: str) -> Leaf | None:
    """Resolve a leaf by slug alone (department inferred from parent), or None.

    Used by chat routing (B.3), which has only the leaf slug. Mirrors
    :func:`resolve_leaf` minus the department-slug cross-check. Never raises.
    """
    ls = (leaf_slug or "").strip().lower()
    if not ls:
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
        if dept is None:
            return None
    except Exception:
        return None
    return _leaf_from_categories(leaf, dept)


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
            # Locality (2026-06-19, Casey): Lake Havasu-local only. Drop providers
            # classified out-of-area (Bullhead/Parker/Kingman/Laughlin/Needles…);
            # keep True and unknown/NULL (never assume an un-geocoded row is far).
            Provider.is_local.isnot(False),
        )
    )


def leaf_provider_rows(db: Session, leaf: Leaf) -> list[Provider]:
    """Active renderable Providers for ``leaf``, ranked by the dampened rating
    sort (institutions over thin 5.0/2-review outliers). Empty on any DB hiccup.
    """
    try:
        rows: list[Provider] = (
            _leaf_provider_query(db, leaf.id)
            .order_by(*cat_queries._dampened_rating_sort_key(db))
            .limit(cat_queries._MATERIALIZE_CAP)
            .all()
        )
    except Exception:
        return []
    return rows


def _leaf_entity_rows(db: Session, leaf_id: int) -> list[Entity]:
    """Active entities whose PRIMARY ``entity_categories`` link is ``leaf_id``,
    eager-loading location for the place card's area line."""
    return (
        db.query(Entity)
        .join(EntityCategory, EntityCategory.entity_id == Entity.id)
        .filter(
            EntityCategory.category_id == leaf_id,
            EntityCategory.is_primary.is_(True),
            Entity.is_active.is_(True),
        )
        .options(
            joinedload(Entity.location),
            selectinload(Entity.contact_points),
        )
        .limit(cat_queries._MATERIALIZE_CAP)
        .all()
    )


def _place_website(entity: Entity) -> str:
    """First website-shaped contact point for a Provider-less place entity.

    A civic place (the Aquatic Center, a library) has no ``/provider/{slug}``
    detail page but often has an official page (city Parks & Rec, etc.). When a
    ``contact_points`` row carries a web URL, the place card links out to it
    instead of rendering inert. Empty string when there is none."""
    for cp in getattr(entity, "contact_points", None) or []:
        if (getattr(cp, "kind", "") or "").strip().lower() in {"website", "web", "url"}:
            val = (getattr(cp, "value", "") or "").strip()
            if val:
                return val
    return ""


def _place_card(entity: Entity) -> dict[str, Any]:
    """A listing card for a Provider-less place entity, built from its own
    fields. ``slug`` is None (no ``/provider/{slug}`` detail page); when the
    entity has an official website (``contact_points``), ``website`` is set and
    the card links OUT to it — otherwise it renders non-linking. Same
    "New / few reviews yet" state as a Provider with no Google rating."""
    loc = getattr(entity, "location", None)
    area = ""
    if loc is not None:
        area = (loc.district or loc.city or "").strip()
    return {
        "slug": None,
        "website": _place_website(entity),
        "name": entity.name,
        "image_url": None,
        "neighborhood": area,
        "status": "unknown",
        "status_text": "",
        "rating": None,
        "review_count": None,
        "has_reviews": False,
        "area": area,
        "distance_hint": "",
        "subcategory": "",
        "cuisine": "",
        "is_open": None,
        # Place entities are never paid placements (no Provider to sell against).
        "is_sponsored": False,
    }


def leaf_listing(
    db: Session, leaf: Leaf, *, now: datetime
) -> tuple[list[dict[str, Any]], int, list[Provider]]:
    """``(cards, total, providers)`` for a leaf page.

    Provider-backed entities render first (the existing dampened-rating ranking);
    Provider-less place entities follow as place cards, alphabetically. ``total``
    is the full renderable count (the gate input). ``providers`` carries only the
    Provider-backed rows for the ItemList JSON-LD (place cards aren't linkable).
    """
    providers = leaf_provider_rows(db, leaf)
    provider_eids = {p.entity_id for p in providers}
    try:
        place_entities = [
            e for e in _leaf_entity_rows(db, leaf.id) if e.id not in provider_eids
        ]
    except Exception:
        place_entities = []
    place_entities.sort(key=lambda e: (e.name or "").lower())

    # Phase F §7.2 honesty gate: pin active paid sticky-tier placements to the
    # top of this niche and label them Sponsored. No-op (organic order, no
    # badges) until a placement is sold for this leaf — zero effect on the live
    # site today.
    from app.monetization.serving import (
        active_category_creatives,
        active_category_tiers,
        apply_category_order,
    )

    tiers = active_category_tiers(db, leaf.slug)
    sponsored_ids = set(tiers.values())
    try:
        creatives = active_category_creatives(db, leaf.slug) if tiers else {}
    except Exception:
        creatives = {}
    if tiers:
        by_id = {p.id: p for p in providers}
        new_order = apply_category_order([p.id for p in providers], tiers)
        providers = [by_id[pid] for pid in new_order if pid in by_id]

    cards = [
        cat_queries._provider_card(
            db, p, now=now, sponsored_provider_ids=sponsored_ids, creatives=creatives
        )
        for p in providers
    ]
    cards += [_place_card(e) for e in place_entities]

    # Curated hybrid cross-listings (e.g. "The Spot" on the arcade leaf as well
    # as its primary restaurants leaf). Additive to the page, de-duplicated
    # against what's already shown; empty unless explicitly curated.
    shown_eids = provider_eids | {e.id for e in place_entities}
    extra_cards, extra_providers = _cross_listed_cards(
        db, leaf, now=now, exclude_entity_ids=shown_eids
    )
    cards += extra_cards
    providers = providers + extra_providers

    total = len(cards)
    return cards, total, providers


def _cross_listed_cards(
    db: Session, leaf: Leaf, *, now: datetime, exclude_entity_ids: set[str]
) -> tuple[list[dict[str, Any]], list[Provider]]:
    """Cards for entities curated to also appear on ``leaf`` (hybrid venues).

    Returns ``([], [])`` immediately when the leaf has no curated cross-listings
    (the common case — zero added DB cost). A cross-listed entity with an active
    Provider renders the rich Provider card; otherwise a place card."""
    slugs = cross_listing.cross_listed_slugs_for_leaf(leaf.slug)
    if not slugs:
        return [], []
    try:
        entities = (
            db.query(Entity)
            .filter(Entity.slug.in_(slugs), Entity.is_active.is_(True))
            .options(
                joinedload(Entity.location),
                selectinload(Entity.contact_points),
            )
            .all()
        )
    except Exception:
        return [], []
    cards: list[dict[str, Any]] = []
    providers: list[Provider] = []
    for e in entities:
        if e.id in exclude_entity_ids:
            continue
        prov = (
            db.query(Provider)
            .filter(
                Provider.entity_id == e.id,
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .first()
        )
        if prov is not None:
            cards.append(cat_queries._provider_card(db, prov, now=now))
            providers.append(prov)
        else:
            cards.append(_place_card(e))
    return cards, providers


def leaf_renderable_count(db: Session, leaf: Leaf) -> int:
    """Active renderable listing count for ``leaf`` — every active entity whose
    primary is this leaf (Provider-backed OR place). The thin-page gate input."""
    try:
        return (
            db.query(EntityCategory)
            .join(Entity, EntityCategory.entity_id == Entity.id)
            # Locality: keep places (no Provider row → NULL → kept) and local /
            # unknown providers; drop explicit out-of-area providers so the gate
            # count matches what leaf_listing renders.
            .outerjoin(Provider, Provider.entity_id == Entity.id)
            .filter(
                EntityCategory.category_id == leaf.id,
                EntityCategory.is_primary.is_(True),
                Entity.is_active.is_(True),
                Provider.is_local.isnot(False),
            )
            .count()
        )
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
    """``{leaf category_id: renderable count}`` for leaves at/above the gate.

    Counts every ACTIVE entity whose primary is the leaf (Provider-backed OR
    place) — matching what ``leaf_listing`` renders — so the sitemap and
    department landings agree with the page's own gate. One grouped query.
    """
    from sqlalchemy import func

    q = (
        db.query(EntityCategory.category_id, func.count(EntityCategory.entity_id))
        .select_from(EntityCategory)
        .join(Entity, EntityCategory.entity_id == Entity.id)
        .join(Category, Category.id == EntityCategory.category_id)
        # Locality: outerjoin so places (no Provider) stay; drop out-of-area
        # providers so department/sitemap counts match the rendered pages.
        .outerjoin(Provider, Provider.entity_id == Entity.id)
        .filter(
            EntityCategory.is_primary.is_(True),
            Entity.is_active.is_(True),
            Category.level == 1,
            Provider.is_local.isnot(False),
        )
    )
    if dept_id is not None:
        q = q.filter(Category.parent_id == dept_id)
    rows = (
        q.group_by(EntityCategory.category_id)
        .having(func.count(EntityCategory.entity_id) >= LEAF_PAGE_MIN_PROVIDERS)
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


def all_departments(db: Session) -> list[tuple[Category, int, int]]:
    """Every ``level = 0`` department owning >=1 gate-clearing leaf, as
    ``(department, gate-clearing leaf count, renderable listing total)``,
    ordered by taxonomy ``sort_order`` then name.

    The listing total sums the department's gate-clearing leaves' renderable
    counts — the same number the department landing's giant counter shows — so
    nav counts and landing counts always agree. Because a listing keys on the
    PRIMARY ``entity_categories`` link, a business counts under exactly one
    leaf and therefore exactly one department (no cross-department double
    counting, unlike the retired flat ``CATEGORY_FILTERS`` buckets). Empty on
    any DB hiccup.
    """
    try:
        counts = _gate_counts(db)
        if not counts:
            return []
        leaf_parents = (
            db.query(Category.parent_id, Category.id)
            .filter(Category.id.in_(list(counts)), Category.level == 1)
            .all()
        )
        by_dept: dict[int, tuple[int, int]] = {}
        for parent_id, leaf_id in leaf_parents:
            if parent_id is None:
                continue
            leaf_n, total = by_dept.get(parent_id, (0, 0))
            by_dept[parent_id] = (leaf_n + 1, total + counts[leaf_id])
        if not by_dept:
            return []
        depts = (
            db.query(Category)
            .filter(Category.id.in_(list(by_dept)), Category.level == 0)
            .order_by(Category.sort_order, Category.name)
            .all()
        )
    except Exception:
        return []
    rows = [(d, by_dept[d.id][0], by_dept[d.id][1]) for d in depts]
    # Phase E §3.1: kids/family-first ordering when TAXONOMY_REORG_ENABLED is on
    # (dormant otherwise — returns rows in taxonomy sort_order unchanged).
    from app.categories.taxonomy_overlay import reorder_departments

    return reorder_departments(rows, slug_of=lambda row: (row[0].slug or "").lower())


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
