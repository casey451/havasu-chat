"""P2.HOME.1 — /home Local pros row uses ``DISCLOSURE_WORD`` for paid badges."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.chat.disclosure_render import DISCLOSURE_WORD
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Provider
from app.main import app


@pytest.fixture(autouse=True)
def legacy_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disclosure badges render on legacy home.html, not home_c."""
    monkeypatch.setenv("HOME_REDESIGN", "0")
    monkeypatch.delenv("HAVA_DEMO_MODE", raising=False)


def _seed_spotlight_provider(db: Session) -> None:
    db.query(Provider).filter(Provider.tier == "spotlight").delete()
    now = now_lake_havasu()
    db.add(
        Provider(
            provider_name="Paid Pro Test",
            category="retail",
            tier="spotlight",
            sponsored_until=now + timedelta(days=30),
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-disclosure",
        )
    )
    db.commit()


def test_home_spotlight_row_uses_disclosure_word_not_spotlight_label() -> None:
    """Spotlight cards must show the canonical disclosure word (see disclosure_render)."""
    with SessionLocal() as db:
        _seed_spotlight_provider(db)
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    html_out = r.text
    assert DISCLOSURE_WORD in html_out
    assert "Spotlight" not in html_out
