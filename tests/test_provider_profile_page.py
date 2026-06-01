"""Phase 1C regression — provider profile HTML stays stable with ENTITY-linked reads."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.session import COOKIE_NAME, SESSION_LIFETIME_SECONDS, sign_session_cookie
from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import AuthSession, Claim, ContactPoint, Entity, Hours, Location, Provider, User
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


def _session_cookie(user_id: str) -> str:
    now_a = datetime.now(timezone.utc)
    with SessionLocal() as db:
        row = AuthSession(
            user_id=user_id,
            expires_at=now_a + timedelta(seconds=SESSION_LIFETIME_SECONDS),
        )
        db.add(row)
        db.commit()
        return sign_session_cookie(row.id)


def test_profile_anonymous_viewer_is_owner_false() -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"anon-vm-{suf}"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=f"anon-vm-e-{suf}",
                name=f"AnonVM {suf}",
                source="test-vm",
            )
        )
        db.flush()
        db.add(
            Provider(
                provider_name=f"AnonVM {suf}",
                category="home_services",
                source="test-vm",
                slug=slug,
                draft=False,
                is_active=True,
                verified=False,
                entity_id=eid,
            )
        )
        db.commit()
    try:
        with TestClient(app) as client:
            r = client.get(f"/provider/{slug}")
        assert r.status_code == 200
        assert 'data-viewer-is-owner="0"' in r.text
    finally:
        with SessionLocal() as db:
            db.query(Provider).filter_by(slug=slug).delete()
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_profile_verified_claim_viewer_is_owner_true() -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"ver-vm-{suf}"
    email = f"vervm-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=f"ver-vm-e-{suf}",
                name=f"VerVM {suf}",
                source="test-vm",
            )
        )
        db.flush()
        db.add(
            Provider(
                provider_name=f"VerVM {suf}",
                category="home_services",
                source="test-vm",
                slug=slug,
                draft=False,
                is_active=True,
                verified=False,
                entity_id=eid,
            )
        )
        u = User(email=email, role="end_user")
        db.add(u)
        db.flush()
        db.add(
            Claim(
                user_id=u.id,
                entity_id=eid,
                status="verified",
                verification_method="email_confirmation",
            )
        )
        db.commit()
        uid = u.id
    try:
        ck = _session_cookie(uid)
        with TestClient(app) as client:
            client.cookies.set(COOKIE_NAME, ck, path="/")
            r = client.get(f"/provider/{slug}")
        assert r.status_code == 200
        assert 'data-viewer-is-owner="1"' in r.text
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            db.query(Provider).filter_by(slug=slug).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_profile_pending_claim_viewer_is_owner_false() -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"pend-vm-{suf}"
    email = f"pendvm-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=f"pend-vm-e-{suf}",
                name=f"PendVM {suf}",
                source="test-vm",
            )
        )
        db.flush()
        db.add(
            Provider(
                provider_name=f"PendVM {suf}",
                category="home_services",
                source="test-vm",
                slug=slug,
                draft=False,
                is_active=True,
                verified=False,
                entity_id=eid,
            )
        )
        u = User(email=email, role="end_user")
        db.add(u)
        db.flush()
        db.add(Claim(user_id=u.id, entity_id=eid, status="pending"))
        db.commit()
        uid = u.id
    try:
        ck = _session_cookie(uid)
        with TestClient(app) as client:
            client.cookies.set(COOKIE_NAME, ck, path="/")
            r = client.get(f"/provider/{slug}")
        assert r.status_code == 200
        assert 'data-viewer-is-owner="0"' in r.text
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            db.query(Provider).filter_by(slug=slug).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_profile_admin_user_viewer_is_owner_true_without_claim() -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"adm-vm-{suf}"
    email = f"admvm-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=f"adm-vm-e-{suf}",
                name=f"AdmVM {suf}",
                source="test-vm",
            )
        )
        db.flush()
        db.add(
            Provider(
                provider_name=f"AdmVM {suf}",
                category="home_services",
                source="test-vm",
                slug=slug,
                draft=False,
                is_active=True,
                verified=False,
                entity_id=eid,
            )
        )
        u = User(email=email, role="admin")
        db.add(u)
        db.commit()
        uid = u.id
    try:
        ck = _session_cookie(uid)
        with TestClient(app) as client:
            client.cookies.set(COOKIE_NAME, ck, path="/")
            r = client.get(f"/provider/{slug}")
        assert r.status_code == 200
        assert 'data-viewer-is-owner="1"' in r.text
    finally:
        with SessionLocal() as db:
            db.query(Provider).filter_by(slug=slug).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()
