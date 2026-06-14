"""Phase F §8 — merchant placement purchase logic (creative attachment)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.db.monetization_models import AdCreative, Placement, PlacementType
from app.portal import placements as placement_logic


def _new_provider(db, suf: str) -> Provider:
    p = Provider(
        provider_name=f"Merchant {suf}",
        category="home_services",
        draft=False,
        is_active=True,
        pending_review=False,
        source="test-portal",
    )
    db.add(p)
    db.commit()
    return p


def test_create_pending_placement_attaches_own_creative_only() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        prov = _new_provider(db, suf)
        other = _new_provider(db, f"o{suf}")
        mine = placement_logic.create_creative(
            db,
            provider_id=prov.id,
            headline="Sunset cruises",
            body=None,
            cta_label=None,
            cta_url=None,
            image_url=None,
            image_url_mobile=None,
        )
        foreign = placement_logic.create_creative(
            db,
            provider_id=other.id,
            headline="Not mine",
            body=None,
            cta_label=None,
            cta_url=None,
            image_url=None,
            image_url_mobile=None,
        )
        try:
            # Own creative is attached.
            p1 = placement_logic.create_pending_placement(
                db,
                provider_id=prov.id,
                placement_type=PlacementType.homepage_rotating.value,
                category_slug=None,
                rank_tier=None,
                billing_type="monthly",
                creative_id=mine.id,
            )
            assert p1.creative_id == mine.id
            assert p1.status == "pending"

            # A creative owned by a different provider is ignored (not trusted).
            p2 = placement_logic.create_pending_placement(
                db,
                provider_id=prov.id,
                placement_type=PlacementType.homepage_rotating.value,
                category_slug=None,
                rank_tier=None,
                billing_type="monthly",
                creative_id=foreign.id,
            )
            assert p2.creative_id is None
        finally:
            for pid in (prov.id, other.id):
                db.execute(delete(Placement).where(Placement.provider_id == pid))
                db.execute(delete(AdCreative).where(AdCreative.provider_id == pid))
            db.execute(delete(Provider).where(Provider.id.in_([prov.id, other.id])))
            db.execute(
                delete(Entity).where(Entity.id.in_([prov.entity_id, other.entity_id]))
            )
            db.commit()
