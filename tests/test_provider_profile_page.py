"""Phase 1C regression — provider profile HTML stays stable with ENTITY-linked reads."""

from __future__ import annotations

from datetime import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import ContactPoint, Entity, Hours, Location, Provider
from app.main import app


def test_profile_renders_entity_location_hours_and_contact_over_legacy_columns() -> None:
    """Representative ENTITY-backed provider: page shows extension location/hours/phone."""
    suf = uuid4().hex[:8]
    slug_part = uuid4().hex[:12]
    eid = str(uuid4())
    street = f"500 ENTITY ROW TEST {suf}"
    phone_entity = "(928) 555-1234"

    with SessionLocal() as db:
        ent = Entity(
            id=eid,
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"prof-ent-{slug_part}",
            name=f"Profile Pivot Plumbing {suf}",
            source="test-profile-page",
        )
        db.add(ent)
        db.flush()
        db.add(
            Location(
                entity_id=eid,
                address=f"{street}, Lake Havasu City, AZ 86403",
                city="Lake Havasu City",
                state="AZ",
                zip="86403",
            )
        )
        db.add(
            Hours(
                entity_id=eid,
                day_of_week=1,
                opens_at=time(8, 0),
                closes_at=time(17, 0),
            )
        )
        db.add(
            ContactPoint(
                entity_id=eid,
                kind="phone",
                value=phone_entity,
                display_order=0,
                is_primary=True,
            )
        )
        p = Provider(
            provider_name=f"Profile Pivot Plumbing {suf}",
            category="home_services",
            source="test-profile-page",
            slug=f"pivot-prof-{slug_part}",
            draft=False,
            is_active=True,
            verified=True,
            address="999 WRONG LEGACY ST",
            phone="(928) 555-0001",
            hours_structured=None,
            description="We fix pipes.",
            entity_id=eid,
        )
        db.add(p)
        db.commit()
        slug = p.slug

    try:
        with TestClient(app) as client:
            r = client.get(f"/provider/{slug}")
        assert r.status_code == 200
        body = r.text
        assert street.split()[0] in body
        assert "999 WRONG LEGACY ST" not in body
        assert "555-1234" in body.replace(" ", "") or "5551234" in body.replace(" ", "")
        assert "Tuesday" in body
        assert "08:00" in body or "8:00" in body
    finally:
        with SessionLocal() as db:
            cp = db.query(ContactPoint).filter_by(entity_id=eid).all()
            for row in cp:
                db.delete(row)
            db.query(Hours).filter_by(entity_id=eid).delete()
            db.query(Location).filter_by(entity_id=eid).delete()
            pr = db.query(Provider).filter_by(slug=slug).first()
            if pr:
                db.delete(pr)
            en = db.get(Entity, eid)
            if en:
                db.delete(en)
            db.commit()
