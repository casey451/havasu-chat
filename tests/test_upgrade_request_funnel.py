"""Phase A4 — claim-your-listing upgrade funnel.

Merchant side: a verified owner submits a featured-listing request (NO billing).
Admin side: review queue + approve (optionally spinning out a DRAFT Sponsor) +
decline. Auth follows the magic-link pattern used by tests/test_claims.py.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import (
    AuthSession,
    Claim,
    Entity,
    Sponsor,
    UpgradeRequest,
    UpgradeRequestStatus,
    User,
)
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def _login_email(client: TestClient, monkeypatch: pytest.MonkeyPatch, email: str) -> None:
    toks: list[str] = []

    def _fake(email_: str, tok: str, *, next_path: str | None = None) -> None:
        toks.append(tok)

    monkeypatch.setattr("app.auth.email_sender.send_magic_link", _fake)
    client.post("/api/auth/request-link", data={"email": email})
    client.get(f"/auth/callback?token={toks[0]}", follow_redirects=False)


def _seed_entity_with_owner(slug: str, email: str, *, verified: bool) -> tuple[str, str]:
    """Create an Entity + a (verified|pending) Claim for a fresh user. Returns ids."""
    eid = str(uuid4())
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="UpgradeCo",
                source="test-upgrade",
            )
        )
        user = User(id=str(uuid4()), email=email, role="merchant")
        db.add(user)
        db.flush()
        db.add(
            Claim(
                user_id=user.id,
                entity_id=eid,
                status="verified" if verified else "pending",
            )
        )
        db.commit()
        return eid, user.id


def _cleanup(eid: str, email: str) -> None:
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == email).first()
        if u:
            db.query(UpgradeRequest).filter_by(user_id=u.id).delete()
            db.query(Claim).filter_by(user_id=u.id).delete()
            db.query(AuthSession).filter_by(user_id=u.id).delete()
        db.query(UpgradeRequest).filter_by(entity_id=eid).delete()
        db.query(Sponsor).filter(Sponsor.name == "UpgradeCo").delete()
        db.query(Entity).filter_by(id=eid).delete()
        if u:
            db.delete(u)
        db.commit()


def _admin_login(c: TestClient) -> None:
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code in (302, 303)


# ── merchant capture ──────────────────────────────────────────────────────


def test_upgrade_get_anonymous_redirects_to_login(client: TestClient) -> None:
    r = client.get("/merchant/upgrade/whatever", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in (r.headers.get("location") or "")


def test_verified_owner_can_submit_upgrade_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    slug, email = f"up-{suf}", f"owner-{suf}@example.com"
    eid, _ = _seed_entity_with_owner(slug, email, verified=True)
    try:
        _login_email(client, monkeypatch, email)
        r = client.post(
            f"/merchant/upgrade/{slug}",
            data={"requested_slot": "spotlight", "message": "summer promo"},
        )
        assert r.status_code == 200
        with SessionLocal() as db:
            req = db.query(UpgradeRequest).filter_by(entity_id=eid).one()
            assert req.status == UpgradeRequestStatus.PENDING.value
            assert req.requested_slot == "spotlight"
            assert req.message == "summer promo"
    finally:
        _cleanup(eid, email)


def test_non_owner_forbidden(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid4().hex[:8]
    slug, owner_email = f"up-{suf}", f"owner-{suf}@example.com"
    eid, _ = _seed_entity_with_owner(slug, owner_email, verified=True)
    other_email = f"intruder-{suf}@example.com"
    try:
        _login_email(client, monkeypatch, other_email)
        r = client.post(f"/merchant/upgrade/{slug}", data={"requested_slot": "spotlight"})
        assert r.status_code == 403
    finally:
        _cleanup(eid, owner_email)
        with SessionLocal() as db:
            u = db.query(User).filter(User.email == other_email).first()
            if u:
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
                db.commit()


def test_pending_claim_not_enough(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid4().hex[:8]
    slug, email = f"up-{suf}", f"owner-{suf}@example.com"
    eid, _ = _seed_entity_with_owner(slug, email, verified=False)
    try:
        _login_email(client, monkeypatch, email)
        r = client.post(f"/merchant/upgrade/{slug}", data={"requested_slot": "spotlight"})
        assert r.status_code == 403
    finally:
        _cleanup(eid, email)


def test_duplicate_pending_not_stacked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    slug, email = f"up-{suf}", f"owner-{suf}@example.com"
    eid, _ = _seed_entity_with_owner(slug, email, verified=True)
    try:
        _login_email(client, monkeypatch, email)
        client.post(f"/merchant/upgrade/{slug}", data={"requested_slot": "spotlight"})
        client.post(f"/merchant/upgrade/{slug}", data={"requested_slot": "marquee"})
        with SessionLocal() as db:
            assert db.query(UpgradeRequest).filter_by(entity_id=eid).count() == 1
    finally:
        _cleanup(eid, email)


def test_invalid_slot_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid4().hex[:8]
    slug, email = f"up-{suf}", f"owner-{suf}@example.com"
    eid, _ = _seed_entity_with_owner(slug, email, verified=True)
    try:
        _login_email(client, monkeypatch, email)
        r = client.post(f"/merchant/upgrade/{slug}", data={"requested_slot": "banner"})
        assert r.status_code == 400
    finally:
        _cleanup(eid, email)


# ── admin review ──────────────────────────────────────────────────────────


def _seed_pending_request(eid: str, user_id: str, slot: str = "spotlight") -> str:
    with SessionLocal() as db:
        req = UpgradeRequest(
            user_id=user_id,
            entity_id=eid,
            requested_slot=slot,
            status=UpgradeRequestStatus.PENDING.value,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req.id


def test_admin_queue_requires_auth(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/admin/upgrade-requests")
    assert r.status_code == 302


def test_admin_approve_creates_draft_sponsor(client: TestClient) -> None:
    suf = uuid4().hex[:8]
    slug, email = f"up-{suf}", f"owner-{suf}@example.com"
    eid, uid = _seed_entity_with_owner(slug, email, verified=True)
    rid = _seed_pending_request(eid, uid)
    try:
        _admin_login(client)
        r = client.post(
            f"/admin/upgrade-requests/{rid}/approve",
            data={"create_sponsor": "1", "admin_note": "ok"},
        )
        assert r.status_code == 303
        with SessionLocal() as db:
            req = db.query(UpgradeRequest).filter_by(id=rid).one()
            assert req.status == UpgradeRequestStatus.APPROVED.value
            assert req.created_sponsor_id is not None
            sp = db.query(Sponsor).filter_by(id=req.created_sponsor_id).one()
            # Created as DRAFT + inactive — never auto-live, no billing.
            assert sp.status == "draft"
            assert sp.active is False
            assert sp.slot == "spotlight"
    finally:
        _cleanup(eid, email)


def test_admin_approve_without_sponsor(client: TestClient) -> None:
    suf = uuid4().hex[:8]
    slug, email = f"up-{suf}", f"owner-{suf}@example.com"
    eid, uid = _seed_entity_with_owner(slug, email, verified=True)
    rid = _seed_pending_request(eid, uid)
    try:
        _admin_login(client)
        client.post(f"/admin/upgrade-requests/{rid}/approve", data={})
        with SessionLocal() as db:
            req = db.query(UpgradeRequest).filter_by(id=rid).one()
            assert req.status == UpgradeRequestStatus.APPROVED.value
            assert req.created_sponsor_id is None
    finally:
        _cleanup(eid, email)


def test_admin_decline(client: TestClient) -> None:
    suf = uuid4().hex[:8]
    slug, email = f"up-{suf}", f"owner-{suf}@example.com"
    eid, uid = _seed_entity_with_owner(slug, email, verified=True)
    rid = _seed_pending_request(eid, uid)
    try:
        _admin_login(client)
        r = client.post(
            f"/admin/upgrade-requests/{rid}/decline", data={"admin_note": "not now"}
        )
        assert r.status_code == 303
        with SessionLocal() as db:
            req = db.query(UpgradeRequest).filter_by(id=rid).one()
            assert req.status == UpgradeRequestStatus.DECLINED.value
            assert req.admin_note == "not now"
    finally:
        _cleanup(eid, email)


def test_admin_action_404_on_unknown(client: TestClient) -> None:
    _admin_login(client)
    r = client.post("/admin/upgrade-requests/no-such/approve", data={})
    assert r.status_code == 404
