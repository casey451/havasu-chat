"""Sponsor impressions must equal renders (audit 2026-07-01, finding #1).

The v4 (HOME_REDESIGN) templates render only the marquee + promoted slots —
there is no Featured/Spotlight surface. ``active_spotlights`` and
``serve_homepage_featured`` each count an impression per call, so calling them
on the v4 path inflated ``Sponsor.impressions`` (billing-relevant) for a slot
users never saw. The fetches now live in the legacy branch only.
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


def _add_spotlight(db: Session) -> Sponsor:
    sp = Sponsor(
        name="Spotlight Acme",
        slot=AdSlot.SPOTLIGHT.value,
        status=SponsorStatus.APPROVED.value,
        active=True,
        cta_url="https://example.com",
        weight=0,
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return sp


def _impressions(db: Session, sponsor_id: str) -> int:
    row = db.get(Sponsor, sponsor_id)
    db.refresh(row)
    return row.impressions


@pytest.fixture
def db() -> Session:
    with SessionLocal() as session:
        _wipe(session)
        yield session
        _wipe(session)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_home_does_not_count_spotlight_impressions(db: Session, client: TestClient) -> None:
    # The v4 home (the only home since the 2026-07-02 flag collapse) renders no
    # Featured/Spotlight slot -> no impression may be counted on a page view.
    sp = _add_spotlight(db)
    resp = client.get("/home")
    assert resp.status_code == 200
    assert _impressions(db, sp.id) == 0
