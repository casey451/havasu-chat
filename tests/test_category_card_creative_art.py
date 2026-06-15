"""Phase F (A2) — a sponsored category/leaf card can carry the placement's ad
creative: the creative's art skins the card thumbnail and its headline rides
along as a tagline. Dormant by default (no creative → today's organic card), and
honest (a creative the provider does not own is ignored).

Exercised through the deterministic single-provider leaf surface (leaf_listing)
plus a direct unit check of the serving helper's ownership gate.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete

from app.categories import leaf_pages
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Category, Entity, EntityCategory, Provider
from app.db.monetization_models import (
    AdCreative,
    Placement,
    PlacementStatus,
    PlacementType,
)
from app.monetization.serving import active_category_creatives

_CREATIVE_IMG = "https://cdn.example/creative-art.jpg"
_CREATIVE_HEADLINE = "Summer A/C tune-up — book today"


def _seed_leaf_with_paid_provider(db, suf: str):
    """A dept+leaf with one active provider primary-linked at the leaf, plus an
    active tier-1 category_rank placement on the leaf. Returns (leaf_obj, pid,
    ent_id, dept_id, leaf_id, placement)."""
    dept = Category(slug=f"a2-dept-{suf}", name=f"A2 Dept {suf}", sort_order=0, level=0)
    db.add(dept)
    db.flush()
    leaf = Category(
        slug=f"a2-leaf-{suf}", name=f"A2 Leaf {suf}", sort_order=0, level=1,
        parent_id=dept.id,
    )
    db.add(leaf)
    db.flush()
    name = f"A2 Paid HVAC {suf}"
    ent = Entity(entity_type="commercial", slug=f"a2-ent-{suf}", name=name, source="test-a2")
    db.add(ent)
    db.flush()
    prov = Provider(
        provider_name=name, category="home_services", slug=f"a2-prov-{suf}",
        is_active=True, draft=False, pending_review=False, source="test-a2",
        entity_id=ent.id, google_rating=4.7, google_review_count=33,
    )
    db.add(prov)
    db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
    db.commit()
    placement = Placement(
        provider_id=prov.id, placement_type=PlacementType.category_rank.value,
        category_slug=leaf.slug, rank_tier=1, status=PlacementStatus.active.value,
        billing_type="monthly", price_cents=0,
    )
    db.add(placement)
    db.commit()
    leaf_obj = leaf_pages.resolve_leaf(db, dept.slug, leaf.slug)
    return leaf_obj, prov.id, ent.id, dept.id, leaf.id, placement


def _cleanup(db, pid, ent_id, dept_id, leaf_id) -> None:
    db.execute(delete(Placement).where(Placement.provider_id == pid))
    db.execute(delete(AdCreative).where(AdCreative.provider_id == pid))
    db.execute(delete(EntityCategory).where(EntityCategory.entity_id == ent_id))
    db.execute(delete(Provider).where(Provider.id == pid))
    db.execute(delete(Entity).where(Entity.id == ent_id))
    db.execute(delete(Category).where(Category.id.in_([leaf_id, dept_id])))
    db.commit()


def test_sponsored_leaf_card_renders_attached_creative() -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime(2026, 1, 5, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    with SessionLocal() as db:
        leaf_obj, pid, ent_id, dept_id, leaf_id, placement = _seed_leaf_with_paid_provider(
            db, suf
        )
        assert leaf_obj is not None
        try:
            # Dormant first: a sponsored placement with NO creative leaves the
            # card on its own (here photoless) art and shows no tagline.
            cards, _, _ = leaf_pages.leaf_listing(db, leaf_obj, now=now)
            assert cards and cards[0]["is_sponsored"] is True
            assert cards[0]["ad_headline"] == ""

            # Attach a provider-owned creative to the placement → the art skins
            # the thumbnail and the headline becomes the card tagline.
            creative = AdCreative(
                provider_id=pid, headline=_CREATIVE_HEADLINE, image_url=_CREATIVE_IMG,
                active=True,
            )
            db.add(creative)
            db.commit()
            placement.creative_id = creative.id
            db.commit()

            cards2, _, _ = leaf_pages.leaf_listing(db, leaf_obj, now=now)
            assert cards2 and cards2[0]["is_sponsored"] is True
            assert cards2[0]["image_url"] == _CREATIVE_IMG
            assert cards2[0]["ad_headline"] == _CREATIVE_HEADLINE
        finally:
            _cleanup(db, pid, ent_id, dept_id, leaf_id)


def test_creative_owned_by_other_provider_is_ignored() -> None:
    """Honesty: a placement whose creative belongs to a different provider yields
    no creative for the holder (and the card stays organic)."""
    suf = uuid.uuid4().hex[:8]
    now = datetime(2026, 1, 5, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    with SessionLocal() as db:
        leaf_obj, pid, ent_id, dept_id, leaf_id, placement = _seed_leaf_with_paid_provider(
            db, suf
        )
        # A creative owned by an UNRELATED provider.
        other = Provider(
            provider_name=f"A2 Other {suf}", category="home_services",
            slug=f"a2-other-{suf}", is_active=True, draft=False, source="test-a2",
        )
        db.add(other)
        db.commit()
        foreign = AdCreative(
            provider_id=other.id, headline="Not yours", image_url=_CREATIVE_IMG, active=True,
        )
        db.add(foreign)
        db.commit()
        placement.creative_id = foreign.id
        db.commit()
        try:
            creatives = active_category_creatives(db, leaf_obj.slug)
            assert pid not in creatives  # foreign creative is not attributed

            cards, _, _ = leaf_pages.leaf_listing(db, leaf_obj, now=now)
            assert cards and cards[0]["is_sponsored"] is True
            assert cards[0]["ad_headline"] == ""
            assert cards[0]["image_url"] != _CREATIVE_IMG
        finally:
            db.execute(delete(AdCreative).where(AdCreative.provider_id == other.id))
            db.execute(delete(Provider).where(Provider.id == other.id))
            db.execute(delete(Entity).where(Entity.id == other.entity_id))
            _cleanup(db, pid, ent_id, dept_id, leaf_id)
