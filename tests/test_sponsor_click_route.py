"""v52 P0 — ``GET /sponsor/click`` attribution route.

Covers: 404 on missing/inactive/unapproved/out-of-window rows, 400 on bad slot,
302 + ``clicks`` increment on the happy path, ``/sponsor`` landing stub render.
The rate-limit decorator is not exercised here — ``conftest.py`` sets
``RATE_LIMIT_DISABLED=1`` for the whole suite, matching how the limiter is
already validated in ``test_auth_*`` paths.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
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
    cta_url: str = "https://example.com/landing",
    starts_at=None,
    ends_at=None,
) -> Sponsor:
    sp = Sponsor(
        name=name,
        slot=slot,
        status=status,
        active=active,
        cta_url=cta_url,
        starts_at=starts_at,
        ends_at=ends_at,
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
    # ``follow_redirects=False`` so we can assert the 302 + Location directly
    # instead of chasing the redirect onto an external URL the test client
    # would refuse.
    return TestClient(app, follow_redirects=False)


def _clicks(db: Session, sponsor_id: str) -> int:
    db.expire_all()
    return db.query(Sponsor).filter(Sponsor.id == sponsor_id).one().clicks


# 404 paths --------------------------------------------------------------------


def test_click_404_on_unknown_id(client: TestClient, db: Session) -> None:
    r = client.get("/sponsor/click", params={"id": "no-such-id", "slot": "marquee"})
    assert r.status_code == 404


def test_click_404_on_inactive_sponsor(client: TestClient, db: Session) -> None:
    sp = _add(db, name="killed", active=False)
    r = client.get("/sponsor/click", params={"id": sp.id, "slot": "marquee"})
    assert r.status_code == 404
    assert _clicks(db, sp.id) == 0


def test_click_404_on_unapproved_status(client: TestClient, db: Session) -> None:
    sp = _add(db, name="draft", status=SponsorStatus.DRAFT.value)
    r = client.get("/sponsor/click", params={"id": sp.id, "slot": "marquee"})
    assert r.status_code == 404
    assert _clicks(db, sp.id) == 0


def test_click_404_on_wrong_slot(client: TestClient, db: Session) -> None:
    """Row is live in marquee but request claims spotlight → 404, no increment."""
    sp = _add(db, name="marquee-live", slot=AdSlot.MARQUEE.value)
    r = client.get("/sponsor/click", params={"id": sp.id, "slot": "spotlight"})
    assert r.status_code == 404
    assert _clicks(db, sp.id) == 0


def test_click_outside_booking_window_404s(client: TestClient, db: Session) -> None:
    now = now_lake_havasu()
    future = (now + timedelta(days=1)).replace(tzinfo=LAKE_HAVASU_TZ)
    sp = _add(db, name="not-yet", starts_at=future)
    r = client.get("/sponsor/click", params={"id": sp.id, "slot": "marquee"})
    assert r.status_code == 404
    assert _clicks(db, sp.id) == 0


# 400 path ---------------------------------------------------------------------


def test_click_400_on_bad_slot(client: TestClient, db: Session) -> None:
    sp = _add(db, name="anything")
    r = client.get("/sponsor/click", params={"id": sp.id, "slot": "banner"})
    assert r.status_code == 400
    assert _clicks(db, sp.id) == 0


# Happy path -------------------------------------------------------------------


def test_click_302_redirects_to_cta_url_and_increments_clicks(
    client: TestClient, db: Session
) -> None:
    sp = _add(db, name="live", cta_url="https://acme.example/promo")

    r = client.get("/sponsor/click", params={"id": sp.id, "slot": "marquee"})

    assert r.status_code == 302
    assert r.headers["location"] == "https://acme.example/promo"
    assert _clicks(db, sp.id) == 1


def test_click_increments_repeatedly(client: TestClient, db: Session) -> None:
    sp = _add(db, name="hot")
    for _ in range(3):
        r = client.get("/sponsor/click", params={"id": sp.id, "slot": "marquee"})
        assert r.status_code == 302
    assert _clicks(db, sp.id) == 3


def test_click_works_for_all_four_tiers(client: TestClient, db: Session) -> None:
    sponsors = {
        slot: _add(db, name=f"{slot.value}-row", slot=slot.value)
        for slot in (
            AdSlot.MARQUEE,
            AdSlot.SPOTLIGHT,
            AdSlot.PROMOTED,
            AdSlot.SUPPORTER,
        )
    }
    for slot, sp in sponsors.items():
        r = client.get("/sponsor/click", params={"id": sp.id, "slot": slot.value})
        assert r.status_code == 302, slot
        assert _clicks(db, sp.id) == 1


# /sponsor landing -------------------------------------------------------------


def test_sponsor_landing_renders_200(client: TestClient) -> None:
    r = client.get("/sponsor")
    assert r.status_code == 200
    assert "Advertise on" in r.text
