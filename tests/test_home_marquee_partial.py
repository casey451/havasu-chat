"""GET /home — Marquee partial (legacy template, Phase 2B)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import AdSlot, Sponsor, SponsorStatus
from app.main import app


@pytest.fixture(autouse=True)
def legacy_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Marquee partial lives on home.html, not home_c."""
    monkeypatch.setenv("HOME_REDESIGN", "0")
    monkeypatch.delenv("HAVA_DEMO_MODE", raising=False)


def _wipe(db: Session) -> None:
    db.query(Sponsor).delete()
    db.commit()


def test_home_marquee_unsold_when_no_sponsors() -> None:
    with SessionLocal() as db:
        _wipe(db)
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert "marquee-unsold" in r.text
    assert "Become the marquee sponsor" in r.text


def test_home_marquee_renders_sold_card() -> None:
    with SessionLocal() as db:
        _wipe(db)
        db.add(
            Sponsor(
                name="Desert Auto",
                slot=AdSlot.MARQUEE.value,
                status=SponsorStatus.APPROVED.value,
                active=True,
                headline="Best brakes in town",
                pitch="Same-day service",
                cta_url="https://example.com/desert",
            )
        )
        db.commit()
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert "marquee-card" in r.text
    assert "Best brakes in town" in r.text
    assert "marquee-unsold" not in r.text
