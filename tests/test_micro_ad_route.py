"""Phase A4 — GET /api/micro_ad loading-overlay micro-ad payload.

Covers: null payload when unsold, live sponsor surfaced, slot selection +
fallback, click_url points at the existing /sponsor/click attribution route,
and the deliberate no-impression-bump policy (a load-screen render must not
inflate the paid /home CTR denominator).
"""

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
    weight: int = 0,
) -> Sponsor:
    sp = Sponsor(
        name=name,
        slot=slot,
        status=status,
        active=active,
        cta_url="https://example.com",
        weight=weight,
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


def test_micro_ad_null_when_unsold(client: TestClient, db: Session) -> None:
    r = client.get("/api/micro_ad")
    assert r.status_code == 200
    assert r.json() == {"micro_ad": None}


def test_micro_ad_surfaces_live_marquee(client: TestClient, db: Session) -> None:
    sp = _add(db, name="Marquee Co", slot=AdSlot.MARQUEE.value)
    r = client.get("/api/micro_ad")
    assert r.status_code == 200
    ad = r.json()["micro_ad"]
    assert ad is not None
    assert ad["name"] == "Marquee Co"
    assert ad["slot"] == "marquee"
    assert ad["click_url"] == f"/sponsor/click?id={sp.id}&slot=marquee"


def test_micro_ad_ignores_draft_and_inactive(client: TestClient, db: Session) -> None:
    _add(db, name="draft", status=SponsorStatus.DRAFT.value)
    _add(db, name="off", active=False)
    assert client.get("/api/micro_ad").json() == {"micro_ad": None}


def test_micro_ad_slot_param_selects_slot(client: TestClient, db: Session) -> None:
    _add(db, name="spot", slot=AdSlot.SPOTLIGHT.value)
    # default slot (marquee) is unsold -> null
    assert client.get("/api/micro_ad").json()["micro_ad"] is None
    ad = client.get("/api/micro_ad", params={"slot": "spotlight"}).json()["micro_ad"]
    assert ad is not None and ad["slot"] == "spotlight"


def test_micro_ad_bad_slot_falls_back_to_default(client: TestClient, db: Session) -> None:
    _add(db, name="Marquee Co", slot=AdSlot.MARQUEE.value)
    ad = client.get("/api/micro_ad", params={"slot": "not-a-slot"}).json()["micro_ad"]
    assert ad is not None and ad["slot"] == "marquee"


def test_micro_ad_picks_highest_weight(client: TestClient, db: Session) -> None:
    _add(db, name="light", weight=1)
    _add(db, name="heavy", weight=9)
    ad = client.get("/api/micro_ad").json()["micro_ad"]
    assert ad["name"] == "heavy"


def test_micro_ad_does_not_increment_impressions(client: TestClient, db: Session) -> None:
    """Deliberate: load-screen render must not bump the paid impression counter."""
    sp = _add(db, name="no-bump")
    client.get("/api/micro_ad")
    client.get("/api/micro_ad")
    db.expire_all()
    assert db.query(Sponsor).filter(Sponsor.id == sp.id).one().impressions == 0


def test_micro_ad_partial_renders_link(client: TestClient, db: Session) -> None:
    sp = _add(db, name="Partial Co")
    r = client.get("/api/micro_ad/partial")
    assert r.status_code == 200
    assert "Partial Co" in r.text
    assert f"/sponsor/click?id={sp.id}" in r.text


def test_micro_ad_partial_empty_when_unsold(client: TestClient, db: Session) -> None:
    r = client.get("/api/micro_ad/partial")
    assert r.status_code == 200
    assert "ll-micro-ad" not in r.text
