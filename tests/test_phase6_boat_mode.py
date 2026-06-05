"""Phase 6.4 — boat-access mode persistence and filtering."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth.session import COOKIE_NAME, SESSION_LIFETIME_SECONDS, sign_session_cookie
from app.db.database import SessionLocal
from app.db.models import AuthSession, Category, Entity, Provider, User
from app.groups.themed_groups import get_categories_for_group, get_group_for_category
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_themed_group_mapping_helpers() -> None:
    assert get_categories_for_group("eat-drink-group") == ["eat-drink"]
    assert get_categories_for_group("health-fitness-group") == [
        "health-wellness-care",
        "classes-sports-recreation",
    ]
    assert get_group_for_category("auto-rv-fuel") == "home-auto-group"
    assert get_group_for_category("unknown-slug") is None


def test_new_user_preferred_mode_defaults_default() -> None:
    email = f"boat-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        user = User(email=email, role="end_user")
        db.add(user)
        db.commit()
        uid = user.id
        assert user.preferred_mode == "default"
    with SessionLocal() as db:
        db.execute(delete(User).where(User.id == uid))
        db.commit()


def _authed_client(user_id: str) -> TestClient:
    from datetime import timedelta

    with SessionLocal() as db:
        sess = AuthSession(
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=SESSION_LIFETIME_SECONDS),
        )
        db.add(sess)
        db.commit()
        sid = sess.id
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, sign_session_cookie(sid), path="/")
    return client


def test_boat_mode_preference_api_persists(client: TestClient) -> None:
    email = f"boat-api-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        user = User(email=email, role="end_user")
        db.add(user)
        db.commit()
        uid = user.id

    try:
        authed = _authed_client(uid)
        r = authed.post(
            "/api/users/me/boat_mode_preference",
            json={"enabled": True},
        )
        assert r.status_code == 200
        assert r.json()["boat_mode_preference"] is True
        with SessionLocal() as db:
            row = db.get(User, uid)
            assert row is not None
            assert row.preferred_mode == "boat"
        r2 = authed.get("/api/users/me/boat_mode_preference")
        assert r2.status_code == 200
        assert r2.json()["boat_mode_preference"] is True
    finally:
        with SessionLocal() as db:
            db.execute(delete(AuthSession).where(AuthSession.user_id == uid))
            db.execute(delete(User).where(User.id == uid))
            db.commit()


def test_category_page_boat_query_filters(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        cat = db.scalars(select(Category).where(Category.slug == "on-the-water")).first()
        assert cat is not None
        boat = Provider(
            provider_name=f"Boat Filter Yes {suf}",
            category="marina",
            category_id=cat.id,
            google_primary_category="marina",
            draft=False,
            is_active=True,
            source="test-phase64-boat",
        )
        land = Provider(
            provider_name=f"Boat Filter No {suf}",
            category="marina",
            category_id=cat.id,
            google_primary_category="marina",
            draft=False,
            is_active=True,
            source="test-phase64-boat",
        )
        db.add_all([boat, land])
        db.commit()
        e_boat, e_land = boat.entity_id, land.entity_id
        ent_b = db.get(Entity, e_boat)
        ent_l = db.get(Entity, e_land)
        assert ent_b is not None and ent_l is not None
        ent_b.boat_access = {"type": "marina"}
        db.commit()

    try:
        # P1.1: the singular filter surface 301s to the plural page now.
        r = client.get("/category/on-the-water?boat=1", follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["location"] == "/categories/on-the-water?boat=1"
    finally:
        with SessionLocal() as db:
            for eid in (e_boat, e_land):
                db.execute(delete(Provider).where(Provider.entity_id == eid))
                db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()


def test_profile_boat_access_region_markup(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Boat Profile {suf}",
            slug=f"boat-prof-{suf}",
            category="marina",
            google_primary_category="marina",
            draft=False,
            is_active=True,
            source="test-phase64-boat",
        )
        db.add(p)
        db.commit()
        ent = db.get(Entity, p.entity_id)
        assert ent is not None
        ent.boat_access = {"type": "marina", "fuel": True, "transient_dock": True}
        db.commit()
        slug = p.slug
        eid = p.entity_id

    try:
        r = client.get(f"/provider/{slug}")
        assert r.status_code == 200
        assert f"Boat Profile {suf}" in r.text
        assert "/static/styles/sandstone.css" in r.text
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.slug == slug))
            db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()


def test_boat_mode_api_requires_login(client: TestClient) -> None:
    r = client.post("/api/users/me/boat_mode_preference", json={"enabled": True})
    assert r.status_code == 401
