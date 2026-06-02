"""Phase A4 — admin sponsor slot-inventory view + status-FSM action routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import AdSlot, Sponsor, SponsorStatus
from app.main import app


def _wipe(db: Session) -> None:
    db.query(Sponsor).delete()
    db.commit()


def _add(
    db: Session,
    *,
    slot: str = AdSlot.MARQUEE.value,
    status: str = SponsorStatus.APPROVED.value,
    active: bool = True,
    name: str = "Acme",
) -> Sponsor:
    sp = Sponsor(
        name=name, slot=slot, status=status, active=active, cta_url="https://example.com"
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return sp


@pytest.fixture
def db() -> Session:
    with SessionLocal() as session:
        _wipe(session)
        yield session
        _wipe(session)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def _login(c: TestClient) -> None:
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_inventory_requires_auth(client: TestClient, db: Session) -> None:
    client.cookies.clear()
    r = client.get("/admin/sponsors")
    assert r.status_code == 302
    assert r.headers.get("location", "").startswith("/admin/login")


def test_inventory_lists_sponsor_grouped_by_slot(client: TestClient, db: Session) -> None:
    _add(db, name="MarqueeCo", slot=AdSlot.MARQUEE.value)
    _add(db, name="SpotCo", slot=AdSlot.SPOTLIGHT.value)
    _login(client)
    r = client.get("/admin/sponsors")
    assert r.status_code == 200
    assert "MarqueeCo" in r.text
    assert "SpotCo" in r.text
    # All four slot headers render even when empty.
    for slot in ("marquee", "spotlight", "promoted", "supporter"):
        assert slot in r.text


def test_pause_flips_status_to_paused(client: TestClient, db: Session) -> None:
    sp = _add(db, name="ToPause")
    _login(client)
    r = client.post(f"/admin/sponsors/{sp.id}/pause", data={"reason": "abuse"})
    assert r.status_code == 303
    db.expire_all()
    row = db.query(Sponsor).filter(Sponsor.id == sp.id).one()
    assert row.status == SponsorStatus.PAUSED.value
    assert row.paused_reason == "abuse"
    assert row.paused_at is not None


def test_approve_flips_status_and_stamps_approved_at(client: TestClient, db: Session) -> None:
    sp = _add(db, name="ToApprove", status=SponsorStatus.REVIEW.value)
    _login(client)
    r = client.post(f"/admin/sponsors/{sp.id}/approve")
    assert r.status_code == 303
    db.expire_all()
    row = db.query(Sponsor).filter(Sponsor.id == sp.id).one()
    assert row.status == SponsorStatus.APPROVED.value
    assert row.approved_at is not None


def test_toggle_active_flips_kill_switch(client: TestClient, db: Session) -> None:
    sp = _add(db, name="Kill", active=True)
    _login(client)
    client.post(f"/admin/sponsors/{sp.id}/toggle-active")
    db.expire_all()
    assert db.query(Sponsor).filter(Sponsor.id == sp.id).one().active is False
    client.post(f"/admin/sponsors/{sp.id}/toggle-active")
    db.expire_all()
    assert db.query(Sponsor).filter(Sponsor.id == sp.id).one().active is True


def test_action_404_on_unknown_sponsor(client: TestClient, db: Session) -> None:
    _login(client)
    r = client.post("/admin/sponsors/no-such-id/pause", data={"reason": "x"})
    assert r.status_code == 404


def test_action_requires_auth(client: TestClient, db: Session) -> None:
    sp = _add(db, name="Guard")
    client.cookies.clear()
    r = client.post(f"/admin/sponsors/{sp.id}/pause", data={"reason": "x"})
    assert r.status_code == 302
    db.expire_all()
    assert db.query(Sponsor).filter(Sponsor.id == sp.id).one().status == SponsorStatus.APPROVED.value
