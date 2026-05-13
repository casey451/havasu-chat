"""Phase 2A.3 — claim flow + viewer_is_owner integration."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_EVENT
from app.db.models import AuthSession, Claim, Entity, Provider, User
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


def test_claim_anonymous_redirects_to_login(client: TestClient) -> None:
    r = client.get("/claim/some-slug", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in (r.headers.get("location") or "")
    assert "next=" in (r.headers.get("location") or "")


def test_claim_signed_in_creates_pending_and_submitted_page(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"claim-ent-{suf}"
    email = f"claimant-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name=f"ClaimCo {suf}",
                source="test-claims",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        r = client.post(f"/claim/{slug}", follow_redirects=False)
        assert r.status_code == 200
        assert "received your claim" in r.text.lower() or "thanks" in r.text.lower()
        with SessionLocal() as db:
            u = db.query(User).filter(User.email == email).one()
            c = db.query(Claim).filter(Claim.user_id == u.id, Claim.entity_id == eid).one()
            assert c.status == "pending"
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_claim_duplicate_post_shows_status_not_second_row(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"claim-dup-{suf}"
    email = f"dup-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name=f"DupBiz {suf}",
                source="test-claims",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        r2 = client.post(f"/claim/{slug}")
        assert r2.status_code == 200
        assert "pending" in r2.text.lower() or "claim" in r2.text.lower()
        with SessionLocal() as db:
            n = db.query(Claim).filter(Claim.entity_id == eid).count()
            assert n == 1
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_claim_event_entity_not_claimable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"evt-{suf}"
    email = f"evu-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_EVENT,
                slug=slug,
                name=f"Gala {suf}",
                source="test-claims",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        r = client.get(f"/claim/{slug}", follow_redirects=False)
        assert r.status_code == 400
    finally:
        with SessionLocal() as db:
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_admin_claims_queue_lists_pending(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"adm-{suf}"
    email = f"admcl-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name=f"QueueCo {suf}",
                source="test-claims",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        c = client.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
        assert c.status_code == 303
        r = client.get("/admin/claims")
        assert r.status_code == 200
        assert email in r.text
        assert "QueueCo" in r.text or slug in r.text
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_admin_verify_promotes_end_user_to_merchant(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"vfy-{suf}"
    email = f"vfy-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name=f"VerifyCo {suf}",
                source="test-claims",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            claim_id = db.query(Claim).filter_by(entity_id=eid).one().id
        c = client.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
        assert c.status_code == 303
        r = client.post(
            f"/admin/claims/{claim_id}/verify",
            data={"verification_method": "email_confirmation"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        with SessionLocal() as db:
            u = db.query(User).filter(User.email == email).one()
            assert u.role == "merchant"
            cl = db.get(Claim, claim_id)
            assert cl is not None
            assert cl.status == "verified"
            assert cl.verification_method == "email_confirmation"
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                u.role = "end_user"
                db.add(u)
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_admin_reject_sets_reason(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"rej-{suf}"
    email = f"rej-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name=f"RejectCo {suf}",
                source="test-claims",
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            claim_id = db.query(Claim).filter_by(entity_id=eid).one().id
        client.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
        reason = "Could not verify ownership."
        r = client.post(
            f"/admin/claims/{claim_id}/reject",
            data={"rejection_reason": reason},
            follow_redirects=False,
        )
        assert r.status_code == 303
        with SessionLocal() as db:
            cl = db.get(Claim, claim_id)
            assert cl is not None
            assert cl.status == "rejected"
            assert cl.rejection_reason == reason
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()


def test_viewer_is_owner_true_after_verified_claim(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    eid = str(uuid4())
    slug = f"own-{suf}"
    prov_slug = f"own-prov-{suf}"
    email = f"owner-{suf}@example.com"
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name=f"OwnerBiz {suf}",
                source="test-claims",
            )
        )
        db.flush()
        db.add(
            Provider(
                provider_name=f"OwnerBiz {suf}",
                category="home_services",
                source="test-claims",
                slug=prov_slug,
                draft=False,
                is_active=True,
                verified=False,
                entity_id=eid,
            )
        )
        db.commit()
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/claim/{slug}")
        with SessionLocal() as db:
            claim_id = db.query(Claim).filter_by(entity_id=eid).one().id
        client.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
        client.post(
            f"/admin/claims/{claim_id}/verify",
            data={"verification_method": "in_person"},
            follow_redirects=False,
        )
        # claimant session still in client from magic link
        pr = client.get(f"/provider/{prov_slug}")
        assert pr.status_code == 200
        assert 'data-viewer-is-owner="1"' in pr.text
    finally:
        with SessionLocal() as db:
            db.query(Claim).filter_by(entity_id=eid).delete()
            db.query(Provider).filter_by(slug=prov_slug).delete()
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
            db.query(Entity).filter_by(id=eid).delete()
            db.commit()
