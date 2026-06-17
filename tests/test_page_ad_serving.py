"""Phase 6A — the top-of-category ``page_ad`` placement serving.

A sold ``page_ad`` for a category surfaces as the page's ``sponsored`` unit
(shaped like the legacy promoted dict, plus ``click_url`` + ``is_placement``);
nothing sold returns ``None`` so the caller falls back to the legacy sponsor and,
failing that, renders no slot. The unit is dormant by design — empty book today.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.db.monetization_models import Placement, PlacementStatus, PlacementType
from app.monetization import serving


def _mk_provider(db, name: str, suf: str) -> str:
    ent = Entity(entity_type="commercial", slug=f"pa-ent-{suf}", name=name, source="test-page-ad")
    db.add(ent)
    db.flush()
    prov = Provider(
        provider_name=name,
        category="eat_drink",
        slug=f"pa-prov-{suf}",
        is_active=True,
        draft=False,
        pending_review=False,
        source="test-page-ad",
        entity_id=ent.id,
        google_rating=4.5,
        google_review_count=22,
    )
    db.add(prov)
    db.commit()
    return prov.id


def _page_ad(provider_id: str, category_slug: str) -> Placement:
    return Placement(
        provider_id=provider_id,
        placement_type=PlacementType.page_ad.value,
        category_slug=category_slug,
        status=PlacementStatus.active.value,
        billing_type="monthly",
        price_cents=0,
    )


def test_page_ad_dormant_returns_none() -> None:
    """No placement sold for the category → None (the live state today)."""
    suf = uuid.uuid4().hex[:8]
    slug = f"pa-cat-{suf}"
    with SessionLocal() as db:
        assert serving.serve_category_page_ad(db, slug) is None


def test_page_ad_active_serves_labeled_placement() -> None:
    suf = uuid.uuid4().hex[:8]
    slug = f"pa-cat-{suf}"
    name = f"Page Ad Diner {suf}"
    with SessionLocal() as db:
        pid = _mk_provider(db, name, suf)
        db.add(_page_ad(pid, slug))
        db.commit()
        try:
            ad = serving.serve_category_page_ad(db, slug)
            assert ad is not None
            assert ad["is_placement"] is True
            assert ad["name"] == name
            assert ad["click_url"] == f"/provider/pa-prov-{suf}"
            # A different category has nothing sold → still dormant.
            assert serving.serve_category_page_ad(db, f"other-{suf}") is None
        finally:
            db.execute(delete(Placement).where(Placement.provider_id == pid))
            db.execute(delete(Provider).where(Provider.id == pid))
            db.commit()
