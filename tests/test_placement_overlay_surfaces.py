"""Phase F §7.2 — integration: a single active ``category_rank`` tier-1 placement
pins the paid provider to the top AND labels it ``Sponsored`` on every organic
overlay surface at once:

  * the dept/category grid (:func:`app.categories.queries.category_listing`),
  * a taxonomy leaf page (:func:`app.categories.leaf_pages.leaf_listing`), and
  * a curated trade page (:func:`app.categories.trades.trade_listing`).

This is the surface-level twin of the view-model honesty-gate unit test in
``tests/test_phase6_hava_card.py`` (``test_paid_placement_sets_is_sponsored_
honesty_gate``): there we proved the card view-model honours an injected paid
set; here we prove each listing surface actually *derives* that set from a live
``Placement`` row, pins the holder, and labels it — and that pulling the
placements drops both the pin and the badge (the gate is placement-driven, not a
property of the provider).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete

from app.categories import leaf_pages
from app.categories.queries import category_listing
from app.categories.trades import TRADES, trade_listing
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Category, Entity, EntityCategory, Provider
from app.db.monetization_models import Placement, PlacementStatus, PlacementType


def _active_tier1(provider_id: str, category_slug: str) -> Placement:
    """An active category_rank tier-1 placement for ``provider_id`` keyed to
    ``category_slug`` (the surface key: a route slug, a leaf slug, or a trade
    slug)."""
    return Placement(
        provider_id=provider_id,
        placement_type=PlacementType.category_rank.value,
        category_slug=category_slug,
        rank_tier=1,
        status=PlacementStatus.active.value,
        billing_type="monthly",
        price_cents=0,
    )


def test_active_placement_pins_and_labels_on_all_overlay_surfaces() -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime(2026, 1, 5, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    dept_slug = f"ovl-dept-{suf}"
    leaf_slug = f"ovl-leaf-{suf}"
    name = f"Overlay Paid Plumber {suf}"

    with SessionLocal() as db:
        # A throwaway department + leaf for the leaf-page surface.
        dept = Category(slug=dept_slug, name=f"Overlay Dept {suf}", sort_order=0, level=0)
        db.add(dept)
        db.flush()
        leaf = Category(
            slug=leaf_slug, name=f"Overlay Leaf {suf}", sort_order=0, level=1,
            parent_id=dept.id,
        )
        db.add(leaf)
        db.flush()

        # One provider that simultaneously: (a) routes to home-property-services
        # via its legacy category, (b) matches the "plumbers" trade via its
        # Google primary type, and (c) is primary-linked to our throwaway leaf.
        ent = Entity(
            entity_type="commercial", slug=f"ovl-ent-{suf}", name=name,
            source="test-overlay",
        )
        db.add(ent)
        db.flush()
        prov = Provider(
            provider_name=name,
            category="home_services",
            google_primary_category="plumber",
            slug=f"ovl-prov-{suf}",
            is_active=True,
            draft=False,
            pending_review=False,
            source="test-overlay",
            entity_id=ent.id,
            google_rating=4.6,
            google_review_count=40,
        )
        db.add(prov)
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
        db.commit()
        pid = prov.id

        # One active tier-1 placement per surface key.
        db.add(_active_tier1(pid, "home-property-services"))
        db.add(_active_tier1(pid, leaf_slug))
        db.add(_active_tier1(pid, "plumbers"))
        db.commit()

        leaf_obj = leaf_pages.resolve_leaf(db, dept_slug, leaf_slug)
        assert leaf_obj is not None

        try:
            # 1) dept/category grid — pinned to position 1 and labeled.
            cards, _total = category_listing(db, "home-property-services", now=now)
            assert cards, "category grid returned no cards"
            assert cards[0]["name"] == name
            assert cards[0]["is_sponsored"] is True

            # 2) taxonomy leaf page — pinned + labeled.
            leaf_cards, _, _ = leaf_pages.leaf_listing(db, leaf_obj, now=now)
            assert leaf_cards
            assert leaf_cards[0]["name"] == name
            assert leaf_cards[0]["is_sponsored"] is True

            # 3) curated trade page — pinned + labeled.
            trade_cards, _, _ = trade_listing(db, TRADES["plumbers"], now=now)
            assert trade_cards
            assert trade_cards[0]["name"] == name
            assert trade_cards[0]["is_sponsored"] is True

            # Honesty gate: remove the placements and the same provider is no
            # longer pinned/labeled on the (deterministic, single-provider) leaf
            # surface — proving the badge is placement-driven, not intrinsic.
            db.execute(delete(Placement).where(Placement.provider_id == pid))
            db.commit()
            leaf_cards2, _, _ = leaf_pages.leaf_listing(db, leaf_obj, now=now)
            assert leaf_cards2
            assert leaf_cards2[0]["name"] == name
            assert leaf_cards2[0]["is_sponsored"] is False
        finally:
            db.execute(delete(Placement).where(Placement.provider_id == pid))
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id == ent.id))
            db.execute(delete(Provider).where(Provider.id == pid))
            db.execute(delete(Entity).where(Entity.id == ent.id))
            db.execute(delete(Category).where(Category.id.in_([leaf.id, dept.id])))
            db.commit()
