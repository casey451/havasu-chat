"""WP-9 — canonical primary category (the 12). Invariant + validation tests.

Covers the audit's structural-keystone requirements:
* Every live subtype resolves to exactly ONE of the 12 primaries (totality).
* The primary mapping never yields a slug outside the canonical 12.
* Surface label-set parity: Home / Explore / Map all derive from the same 12.
* A card's rendered subtype is a member of its page bucket's chip set (C-1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete

from app.api.routes.category_pages import TIER_1_CATEGORY_SLUGS
from app.categories.queries import (
    CategoryFacets,
    _route_primary_categories,
    _route_subcategory_slugs,
    category_listing,
)
from app.categories.subcategories import (
    _SUBCATEGORIES,
    PRIMARY_CATEGORY_SLUGS,
    SUBCATEGORY_TO_PRIMARY,
    derive_primary_category,
    primary_for_subcategory,
)
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.home.queries import CATEGORY_LABELS

# The canonical 12, as Home declares them.
_CANONICAL_12 = set(CATEGORY_LABELS.keys())

_NOW = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)


# --- invariant: totality + single primary -----------------------------------


def test_canonical_set_is_exactly_the_twelve() -> None:
    assert set(PRIMARY_CATEGORY_SLUGS) == _CANONICAL_12
    assert len(PRIMARY_CATEGORY_SLUGS) == 12


def test_every_live_subtype_maps_to_exactly_one_primary() -> None:
    """Totality: every subcategory slug in the taxonomy resolves to one of the 12."""
    live_slugs = {s.slug for s in _SUBCATEGORIES}
    for slug in live_slugs:
        primary = primary_for_subcategory(slug)
        assert primary is not None, f"subcategory {slug!r} maps to no primary"
        assert primary in _CANONICAL_12, f"{slug!r} -> {primary!r} not in the 12"


def test_primary_mapping_codomain_is_within_the_twelve() -> None:
    for sub, primary in SUBCATEGORY_TO_PRIMARY.items():
        assert primary in _CANONICAL_12, f"{sub!r} -> {primary!r} escapes the 12"


def test_no_subtype_maps_to_two_primaries() -> None:
    """The mapping is a function — each subtype has a single (deterministic) primary."""
    # SUBCATEGORY_TO_PRIMARY is a dict, so this is structurally guaranteed, but
    # assert the derive path agrees with the table for every subtype.
    for slug in {s.slug for s in _SUBCATEGORIES}:
        from_table = SUBCATEGORY_TO_PRIMARY[slug]
        from_derive = derive_primary_category(category=None, subcategory=slug)
        assert from_derive == from_table


# --- derivation precedence ---------------------------------------------------


def test_derive_prefers_subcategory_over_legacy() -> None:
    # subcategory wins even when the legacy category would fold elsewhere.
    assert (
        derive_primary_category(category="retail", subcategory="health-medical")
        == "health-wellness-care"
    )


def test_derive_falls_back_to_legacy_when_no_subcategory() -> None:
    assert derive_primary_category(category="retail", subcategory=None) == "shopping-essentials"
    assert derive_primary_category(category="lodging", subcategory=None) == "lodging-vacation-rentals"


def test_derive_from_google_type_when_only_category_given() -> None:
    # No stored subcategory: derive one from the Google type, then fold to primary.
    assert (
        derive_primary_category(category="x", google_primary_category="plumber")
        == "home-property-services"
    )
    assert (
        derive_primary_category(category="x", google_primary_category="dentist")
        == "health-wellness-care"
    )


def test_derive_returns_none_for_unknown() -> None:
    assert derive_primary_category(category="totally-unknown-bucket", subcategory=None) is None
    assert derive_primary_category(category=None, subcategory=None) is None


# --- surface label-set parity (no drift) -------------------------------------


def test_home_explore_map_share_one_canonical_source() -> None:
    """Home's CATEGORY_LABELS, the Map's TIER_1 set, and the primary codomain are
    the same 12 — no surface invents its own top-level category list."""
    assert set(TIER_1_CATEGORY_SLUGS) == _CANONICAL_12
    assert set(SUBCATEGORY_TO_PRIMARY.values()) <= _CANONICAL_12
    # Every canonical primary is reachable from at least one subtype (no orphan
    # bucket that nothing folds into).
    reachable = set(SUBCATEGORY_TO_PRIMARY.values())
    assert reachable == _CANONICAL_12


def test_route_primary_categories_resolve_within_the_twelve() -> None:
    """Each Explore route resolves to primaries drawn only from the 12."""
    for route in ("eat-drink", "health-wellness-care", "services", "shopping-essentials"):
        primaries = _route_primary_categories(route)
        assert primaries, f"route {route!r} resolved no primary"
        assert primaries <= _CANONICAL_12


# --- C-1: a card's subtype belongs to its page bucket's chip set -------------


def test_card_subtype_is_member_of_page_bucket_chip_set() -> None:
    """Every subtype that a route lists/chips (``_route_subcategory_slugs`` — the
    exact set used by ``route_provider_filter`` and ``subcategory_chips_for_route``)
    must fold to one of the route's own canonical primaries. So a card rendered on
    a page can never carry a subtype whose primary is foreign to that page (C-1)."""
    routes = (
        "eat-drink",
        "on-the-water",
        "services",
        "shopping-essentials",
        "classes-sports-recreation",
        "health-wellness-care",
        "home-property-services",
        "auto-rv-fuel",
        "public-civic-resources",
        "pets",
        "professional",
        "beauty-care",
        "attractions",
    )
    for route in routes:
        listed = _route_subcategory_slugs(route)
        if not listed:
            continue
        route_primaries = _route_primary_categories(route)
        for sub in listed:
            primary = primary_for_subcategory(sub)
            assert primary in route_primaries, (
                f"route {route!r} lists subtype {sub!r} whose primary {primary!r} "
                f"is not among the route's primaries {route_primaries}"
            )


# --- DB: primary_category is the strongest Explore signal -------------------


def test_primary_category_overrides_wrong_subcategory_and_legacy() -> None:
    """A row whose primary_category says Health routes to Health even when both its
    subcategory and legacy category point at Shopping — primary is authoritative."""
    suf = uuid.uuid4().hex[:8]
    name = f"Primary Wins Clinic {suf}"
    with SessionLocal() as db:
        p = Provider(
            provider_name=name,
            category="retail",  # legacy -> shopping
            subcategory="specialty",  # subcat -> shopping
            primary_category="health-wellness-care",  # canonical -> health (wins)
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-primary",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
    try:
        with SessionLocal() as db:
            health, _ = category_listing(db, "health-wellness-care", now=_NOW, facets=CategoryFacets())
            shopping, _ = category_listing(db, "shopping-essentials", now=_NOW, facets=CategoryFacets())
        health_names = {c["name"] for c in health}
        shopping_names = {c["name"] for c in shopping}
        assert name in health_names, "primary_category should route the card to Health"
        assert name not in shopping_names, "primary_category must override the Shopping signals"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()


def test_null_primary_falls_back_to_subcategory_then_legacy() -> None:
    """With primary NULL, the existing subcategory signal still routes the card."""
    suf = uuid.uuid4().hex[:8]
    name = f"Fallback Hospital {suf}"
    with SessionLocal() as db:
        p = Provider(
            provider_name=name,
            category="retail",
            subcategory="health-medical",
            primary_category=None,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-primary",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
    try:
        with SessionLocal() as db:
            health, _ = category_listing(db, "health-wellness-care", now=_NOW, facets=CategoryFacets())
            shopping, _ = category_listing(db, "shopping-essentials", now=_NOW, facets=CategoryFacets())
        assert name in {c["name"] for c in health}
        assert name not in {c["name"] for c in shopping}
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()
