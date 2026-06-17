"""Phase 6C — the home Featured (Tier-2) + Promoted (Tier-3) slots draw from the
same homepage-rotating Placement pool as the marquee, with DISTINCT businesses
per load and a legacy fallback when the pool is empty.

Dormant by design: an empty pool yields ``[]`` / ``None`` so the home page falls
back to today's legacy sponsor behavior.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.db.monetization_models import Placement, PlacementStatus, PlacementType
from app.monetization import serving


def _mk_provider(db, name: str, suf: str) -> str:
    ent = Entity(entity_type="commercial", slug=f"hp-ent-{suf}", name=name, source="test-home-pool")
    db.add(ent)
    db.flush()
    prov = Provider(
        provider_name=name,
        category="eat_drink",
        slug=f"hp-prov-{suf}",
        is_active=True,
        draft=False,
        pending_review=False,
        source="test-home-pool",
        entity_id=ent.id,
        google_rating=4.4,
        google_review_count=18,
    )
    db.add(prov)
    db.commit()
    return prov.id


def _homepage(provider_id: str) -> Placement:
    return Placement(
        provider_id=provider_id,
        placement_type=PlacementType.homepage_rotating.value,
        status=PlacementStatus.active.value,
        billing_type="monthly",
        price_cents=0,
    )


def test_home_pool_dormant_returns_empty_and_none() -> None:
    with SessionLocal() as db:
        assert serving.serve_homepage_featured(db, exclude_ids=set()) == []
        assert serving.serve_homepage_promoted(db, exclude_ids=set()) is None


def test_home_pool_serves_distinct_featured_and_promoted() -> None:
    suf = uuid.uuid4().hex[:8]
    p1 = _mk_provider(SessionLocal(), f"Pool One {suf}", f"{suf}a")
    p2 = _mk_provider(SessionLocal(), f"Pool Two {suf}", f"{suf}b")
    with SessionLocal() as db:
        db.add(_homepage(p1))
        db.add(_homepage(p2))
        db.commit()
        try:
            featured = serving.serve_homepage_featured(db, exclude_ids=set(), limit=3)
            ids = {c["id"] for c in featured}
            assert ids == {p1, p2}
            assert all(c["is_placement"] and c["url"].startswith("/provider/") for c in featured)

            # Promoted draws from the same pool; excluding the featured ids drains
            # it (distinct per load), so nothing is left.
            assert serving.serve_homepage_promoted(db, exclude_ids=ids) is None
            # With nothing excluded, promoted serves one of the pool providers.
            promoted = serving.serve_homepage_promoted(db, exclude_ids=set())
            assert promoted is not None
            assert promoted["id"] in {p1, p2}
            assert promoted["is_placement"] is True
        finally:
            db.execute(delete(Placement).where(Placement.provider_id.in_([p1, p2])))
            db.execute(delete(Provider).where(Provider.id.in_([p1, p2])))
            db.commit()
