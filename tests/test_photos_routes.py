"""Phase 2B.1 — photo upload + delete + hero + reorder HTTP API."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.auth.session import COOKIE_NAME, SESSION_LIFETIME_SECONDS, sign_session_cookie
from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_EVENT
from app.db.models import AuthSession, Claim, Entity, Photo, User
from app.main import app


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), (40, 50, 60)).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _mock_r2_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_upload(key: str, content: bytes, content_type: str) -> str:
        return f"https://pub-test.r2.dev/{key}"

    monkeypatch.setattr("app.photos.processor.upload_bytes", fake_upload)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


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


def _verify_claim(client: TestClient, claim_id: str) -> None:
    client.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    client.post(
        f"/admin/claims/{claim_id}/verify",
        data={"verification_method": "email_confirmation"},
        follow_redirects=False,
    )


def test_upload_anon_401(client: TestClient) -> None:
    r = client.post(
        f"/api/entities/{uuid.uuid4()}/photos",
        files={"file": ("a.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert r.status_code == 401


def test_upload_no_verified_claim_403(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    slug = f"ph403-{suf}"
    email = f"nvc-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="N",
                source="t",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        r = client.post(
            f"/api/entities/{eid}/photos",
            files={"file": ("a.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert r.status_code == 403
        assert r.json().get("detail") == "claim_not_verified"
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_upload_verified_claim_201(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    slug = f"ph201-{suf}"
    email = f"vc-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="V",
                source="t",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            cid = db.query(Claim).filter_by(entity_id=eid).one().id
        _verify_claim(client, cid)
        r = client.post(
            f"/api/entities/{eid}/photos",
            files={"file": ("a.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "uploading"
        pid = body["photo_id"]
        with SessionLocal() as db:
            row = db.get(Photo, pid)
            assert row is not None
            assert row.status == "live"
    finally:
        with SessionLocal() as db:
            db.query(Photo).filter(Photo.entity_id == eid).delete()
            db.query(Claim).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_upload_admin_bypass_without_claim(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    email = f"admup-{suf}@example.com"
    now_a = datetime.now(timezone.utc)
    uid = ""
    sid = ""
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=f"admup-{suf}",
                name="A",
                source="t",
            )
        )
        u = User(email=email, role="admin")
        db.add(u)
        db.flush()
        sid_row = AuthSession(
            user_id=u.id,
            expires_at=now_a + timedelta(seconds=SESSION_LIFETIME_SECONDS),
        )
        db.add(sid_row)
        db.flush()
        uid = u.id
        sid = sid_row.id
        db.commit()
    try:
        client.cookies.clear()
        client.cookies.set(COOKIE_NAME, sign_session_cookie(sid), path="/")
        r = client.post(
            f"/api/entities/{eid}/photos",
            files={"file": ("a.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert r.status_code == 201
    finally:
        with SessionLocal() as db:
            db.query(Photo).filter(Photo.entity_id == eid).delete()
            db.query(AuthSession).filter_by(user_id=uid).delete()
            db.query(User).filter_by(id=uid).delete()
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_upload_gif_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    slug = f"gif-{suf}"
    email = f"gif-{suf}@example.com"
    gif = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff"
        b"\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00"
        b"\x01\x00\x01\x00\x00\x02\x02\x04\x01\x00;"
    )
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="G",
                source="t",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            cid = db.query(Claim).filter_by(entity_id=eid).one().id
        _verify_claim(client, cid)
        r = client.post(
            f"/api/entities/{eid}/photos",
            files={"file": ("x.gif", gif, "image/gif")},
        )
        assert r.status_code == 400
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_upload_too_large_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    slug = f"big-{suf}"
    email = f"big-{suf}@example.com"
    huge = b"\xff" * (11 * 1024 * 1024)
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="B",
                source="t",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            cid = db.query(Claim).filter_by(entity_id=eid).one().id
        _verify_claim(client, cid)
        r = client.post(
            f"/api/entities/{eid}/photos",
            files={"file": ("h.jpg", huge, "image/jpeg")},
        )
        assert r.status_code == 413
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_upload_event_entity_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    email = f"ev-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_EVENT,
                slug=f"evt-{suf}",
                name="E",
                source="t",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        r = client.post(
            f"/api/entities/{eid}/photos",
            files={"file": ("a.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert r.status_code == 400
    finally:
        with SessionLocal() as db:
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_upload_entity_not_found_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = f"nf-{uuid.uuid4().hex[:8]}@example.com"
    _login_email(client, monkeypatch, email)
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == email).one()
        u.role = "admin"
        db.commit()
    try:
        r = client.post(
            f"/api/entities/{uuid.uuid4()}/photos",
            files={"file": ("a.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert r.status_code == 404
    finally:
        with SessionLocal() as db:
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.commit()


def test_upload_entity_cap_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    slug = f"cap-{suf}"
    email = f"cap-{suf}@example.com"
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="C",
                source="t",
            )
        )
        db.flush()
        u = User(email=email)
        db.add(u)
        db.commit()
        db.refresh(u)
        old = now - timedelta(days=3)
        for i in range(100):
            c_at = old if i < 81 else now
            db.add(
                Photo(
                    entity_id=eid,
                    uploaded_by_user_id=u.id,
                    mime_type="image/jpeg",
                    storage_key=f"k{i}/",
                    status="live",
                    display_order=i,
                    created_at=c_at,
                    updated_at=c_at,
                )
            )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            cid = db.query(Claim).filter_by(entity_id=eid).one().id
        _verify_claim(client, cid)
        r = client.post(
            f"/api/entities/{eid}/photos",
            files={"file": ("a.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert r.status_code == 429
        assert r.json().get("detail") == "entity_photo_cap_exceeded"
    finally:
        with SessionLocal() as db:
            db.query(Photo).filter(Photo.entity_id == eid).delete()
            db.query(Claim).filter_by(entity_id=eid).delete()
            u2 = db.query(User).filter(User.email == email).first()
            if u2:
                db.query(AuthSession).filter_by(user_id=u2.id).delete()
                db.delete(u2)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_upload_daily_cap_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    slug = f"dcap-{suf}"
    email = f"dcap-{suf}@example.com"
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        e = Entity(
            id=eid,
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=slug,
            name="D",
            source="t",
            created_at=now,
            updated_at=now,
        )
        u = User(email=email)
        db.add(e)
        db.add(u)
        db.commit()
        db.refresh(u)
        for i in range(20):
            db.add(
                Photo(
                    entity_id=eid,
                    uploaded_by_user_id=u.id,
                    mime_type="image/jpeg",
                    storage_key=f"d{i}/",
                    status="flagged",
                    display_order=i,
                    created_at=now,
                    updated_at=now,
                )
            )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            cid = db.query(Claim).filter_by(entity_id=eid).one().id
        _verify_claim(client, cid)
        r = client.post(
            f"/api/entities/{eid}/photos",
            files={"file": ("a.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert r.status_code == 429
        assert r.json().get("detail") == "uploader_daily_cap_exceeded"
    finally:
        with SessionLocal() as db:
            db.query(Photo).filter(Photo.entity_id == eid).delete()
            db.query(Claim).filter_by(entity_id=eid).delete()
            u2 = db.query(User).filter(User.email == email).first()
            if u2:
                db.query(AuthSession).filter_by(user_id=u2.id).delete()
                db.delete(u2)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_delete_by_uploader_soft_deletes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    slug = f"del-{suf}"
    email = f"del-{suf}@example.com"
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="X",
                source="t",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            cid = db.query(Claim).filter_by(entity_id=eid).one().id
            u = db.query(User).filter(User.email == email).one()
            pid = str(uuid.uuid4())
            db.add(
                Photo(
                    id=pid,
                    entity_id=eid,
                    uploaded_by_user_id=u.id,
                    mime_type="image/jpeg",
                    storage_key="k/",
                    status="live",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()
        _verify_claim(client, cid)
        r = client.delete(f"/api/photos/{pid}")
        assert r.status_code == 200
        with SessionLocal() as db:
            row = db.get(Photo, pid)
            assert row is not None
            assert row.status == "deleted"
    finally:
        with SessionLocal() as db:
            db.query(Photo).filter(Photo.entity_id == eid).delete()
            db.query(Claim).filter_by(entity_id=eid).delete()
            u2 = db.query(User).filter(User.email == email).first()
            if u2:
                db.query(AuthSession).filter_by(user_id=u2.id).delete()
                db.delete(u2)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_delete_forbidden_for_stranger(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    slug = f"str-{suf}"
    owner_email = f"own-{suf}@example.com"
    other_email = f"oth-{suf}@example.com"
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="X",
                source="t",
                created_at=now,
                updated_at=now,
            )
        )
        uo = User(email=owner_email)
        db.add(uo)
        db.commit()
        db.refresh(uo)
        pid = str(uuid.uuid4())
        db.add(
            Photo(
                id=pid,
                entity_id=eid,
                uploaded_by_user_id=uo.id,
                mime_type="image/jpeg",
                storage_key="k/",
                status="live",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, owner_email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            cid = db.query(Claim).filter_by(entity_id=eid).one().id
        _verify_claim(client, cid)
        _login_email(client, monkeypatch, other_email)
        r = client.delete(f"/api/photos/{pid}")
        assert r.status_code == 403
    finally:
        with SessionLocal() as db:
            db.query(Photo).filter(Photo.entity_id == eid).delete()
            db.query(Claim).filter_by(entity_id=eid).delete()
            for em in (owner_email, other_email):
                u = db.query(User).filter(User.email == em).first()
                if u:
                    db.query(AuthSession).filter_by(user_id=u.id).delete()
                    db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_set_hero_clears_siblings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = str(uuid.uuid4())
    slug = f"hero-{suf}"
    email = f"hero-{suf}@example.com"
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="H",
                source="t",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            cid = db.query(Claim).filter_by(entity_id=eid).one().id
            u = db.query(User).filter(User.email == email).one()
            p1 = str(uuid.uuid4())
            p2 = str(uuid.uuid4())
            db.add(
                Photo(
                    id=p1,
                    entity_id=eid,
                    uploaded_by_user_id=u.id,
                    mime_type="image/jpeg",
                    storage_key="k1/",
                    status="live",
                    is_hero=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                Photo(
                    id=p2,
                    entity_id=eid,
                    uploaded_by_user_id=u.id,
                    mime_type="image/jpeg",
                    storage_key="k2/",
                    status="live",
                    is_hero=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()
        _verify_claim(client, cid)
        r = client.post(f"/api/photos/{p2}/set-hero")
        assert r.status_code == 200
        with SessionLocal() as db:
            r1 = db.get(Photo, p1)
            r2 = db.get(Photo, p2)
            assert r1 is not None and r2 is not None
            assert r1.is_hero is False
            assert r2.is_hero is True
    finally:
        with SessionLocal() as db:
            db.query(Photo).filter(Photo.entity_id == eid).delete()
            db.query(Claim).filter_by(entity_id=eid).delete()
            u2 = db.query(User).filter(User.email == email).first()
            if u2:
                db.query(AuthSession).filter_by(user_id=u2.id).delete()
                db.delete(u2)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()
