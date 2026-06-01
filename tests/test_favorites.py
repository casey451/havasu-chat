"""Phase 2A.3 — favorites API + account page + tier2 card HTML."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.chat import tier2_catalog_render
from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PROGRAM
from app.db.models import AuthSession, Entity, Provider, User, UserFavorite
from app.main import app


def _capture_send(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    toks: list[str] = []

    def _fake(email: str, tok: str, *, next_path: str | None = None) -> None:
        toks.append(tok)

    # Phase 4.1: magic-link send is invoked by the Outbox handler in
    # app.core.background, which lazy-imports from app.auth.email_sender.
    monkeypatch.setattr("app.auth.email_sender.send_magic_link", _fake)
    return toks


def _login_email(client: TestClient, monkeypatch: pytest.MonkeyPatch, email: str) -> None:
    toks = _capture_send(monkeypatch)
    client.post("/api/auth/request-link", data={"email": email})
    client.get(f"/auth/callback?token={toks[0]}", follow_redirects=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_favorites_toggle_anonymous_401(client: TestClient) -> None:
    r = client.post("/api/favorites/toggle", json={"entity_id": str(uuid4())})
    assert r.status_code == 401


def test_favorites_toggle_add_and_remove(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    email = f"fav-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=f"fav-slug-{suf}",
                name=f"FavCo {suf}",
                source="test-fav",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        r1 = client.post("/api/favorites/toggle", json={"entity_id": eid})
        assert r1.status_code == 200
        assert r1.json() == {"action": "added", "favorite_count": 1}
        r2 = client.post("/api/favorites/toggle", json={"entity_id": eid})
        assert r2.status_code == 200
        assert r2.json() == {"action": "removed", "favorite_count": 0}
    finally:
        with SessionLocal() as db:
            db.query(UserFavorite).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_favorites_toggle_missing_entity_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = f"nf-{uuid4().hex[:8]}@example.com"
    _login_email(client, monkeypatch, email)
    r = client.post("/api/favorites/toggle", json={"entity_id": str(uuid4())})
    assert r.status_code == 404
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == email).first()
        if u:
            db.query(AuthSession).filter_by(user_id=u.id).delete()
            db.delete(u)
            db.commit()


def test_favorites_toggle_program_not_favoritable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    email = f"pg-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_PROGRAM,
                slug=f"prog-{suf}",
                name=f"Prog {suf}",
                source="test-fav",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        r = client.post("/api/favorites/toggle", json={"entity_id": eid})
        assert r.status_code == 400
    finally:
        with SessionLocal() as db:
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_favorites_api_list_json(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    email = f"lst-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=f"lst-slug-{suf}",
                name=f"ListCo {suf}",
                source="test-fav",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post("/api/favorites/toggle", json={"entity_id": eid})
        r = client.get("/api/favorites")
        assert r.status_code == 200
        data = r.json()
        assert "favorites" in data
        assert any(f.get("entity_id") == eid for f in data["favorites"])
    finally:
        with SessionLocal() as db:
            db.query(UserFavorite).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_account_favorites_renders(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    email = f"af-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=f"af-slug-{suf}",
                name=f"AcctFav {suf}",
                source="test-fav",
            )
        )
        db.flush()
        db.add(
            Provider(
                provider_name=f"AcctFav {suf}",
                category="home_services",
                source="test-fav",
                slug=f"af-prov-{suf}",
                draft=False,
                is_active=True,
                verified=False,
                entity_id=eid,
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post("/api/favorites/toggle", json={"entity_id": eid})
        r = client.get("/account/favorites")
        assert r.status_code == 200
        assert "Saved listings" in r.text
        assert f"AcctFav {suf}" in r.text
    finally:
        with SessionLocal() as db:
            db.query(UserFavorite).filter_by(entity_id=eid).delete()
            db.query(Provider).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_provider_profile_heart_hidden_when_anonymous(client: TestClient) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"heart-{suf}"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=f"heart-ent-{suf}",
                name=f"HeartBiz {suf}",
                source="test-fav",
            )
        )
        db.flush()
        db.add(
            Provider(
                provider_name=f"HeartBiz {suf}",
                category="home_services",
                source="test-fav",
                slug=slug,
                draft=False,
                is_active=True,
                verified=False,
                entity_id=eid,
            )
        )
        db.commit()
    try:
        r = client.get(f"/provider/{slug}")
        assert r.status_code == 200
        assert 'data-current-user=""' in r.text
        assert f'data-favorite-entity-id="{eid}"' in r.text
    finally:
        with SessionLocal() as db:
            db.query(Provider).filter_by(slug=slug).delete()
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_tier2_provider_cards_html_includes_favorite_heart() -> None:
    html = tier2_catalog_render.render_tier2_provider_cards_html(
        [
            {
                "entity_id": "e1",
                "slug": "biz-slug",
                "name": "Biz Name",
            }
        ]
    )
    assert "tier2-catalog-card" in html
    assert "favorite-heart" in html
    assert 'data-entity-id="e1"' in html
