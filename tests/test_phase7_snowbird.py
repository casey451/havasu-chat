"""Phase 7 — snowbird-return homepage panel."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.chat.snowbird_query import (
    entity_reopened_after_seasonal_gap,
    get_snowbird_reopened_entities,
    is_snowbird_calendar_window,
    user_has_snowbird_activity_pattern,
)
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.models import Entity, User
from app.home.snowbird_panel import build_snowbird_panel_context
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seasonal_reopen_json() -> dict:
    return {
        "winter": {"hours": {"monday": [{"open": "09:00", "close": "17:00"}]}},
        "summer": {"hours": {}},
    }


def test_snowbird_window_october() -> None:
    assert is_snowbird_calendar_window(datetime(2026, 11, 1).date()) is True


def test_snowbird_window_july_off() -> None:
    assert is_snowbird_calendar_window(datetime(2026, 7, 1).date()) is False


def test_user_pattern_within_90_days() -> None:
    now = datetime(2026, 11, 1, 12, 0, tzinfo=LAKE_HAVASU_TZ)
    la = datetime(2026, 10, 15, 12, 0, tzinfo=LAKE_HAVASU_TZ)
    assert user_has_snowbird_activity_pattern(la, now=now) is True


def test_user_pattern_stale_outside_snowbird_window() -> None:
    now = datetime(2026, 11, 1, 12, 0, tzinfo=LAKE_HAVASU_TZ)
    la = datetime(2023, 7, 1, 12, 0, tzinfo=LAKE_HAVASU_TZ)
    assert user_has_snowbird_activity_pattern(la, now=now) is False


def test_reopened_entity_detection(db: Session) -> None:
    ent = Entity(
        id=str(uuid4()),
        entity_type="place",
        slug=f"p7-sb-{uuid4().hex[:8]}",
        name="Seasonal Pier",
        source="test",
        seasonal_hours=_seasonal_reopen_json(),
        is_active=True,
    )
    db.add(ent)
    db.commit()
    now = datetime(2026, 11, 15, tzinfo=LAKE_HAVASU_TZ)
    assert entity_reopened_after_seasonal_gap(ent, now=now.date()) is True
    rows = get_snowbird_reopened_entities(db, now=now)
    assert any(r.id == ent.id for r in rows)


def test_panel_none_for_anonymous(db: Session) -> None:
    now = datetime(2026, 11, 15, tzinfo=LAKE_HAVASU_TZ)
    assert build_snowbird_panel_context(db, current_user=None, now=now) is None


def test_panel_none_in_summer(db: Session) -> None:
    user = User(email=f"p7-{uuid4().hex}@example.com")
    db.add(user)
    db.flush()
    user.last_active_at = datetime.now(LAKE_HAVASU_TZ)
    db.commit()
    now = datetime(2026, 7, 15, tzinfo=LAKE_HAVASU_TZ)
    assert build_snowbird_panel_context(db, current_user=user, now=now) is None


def test_home_has_snowbird_anchor() -> None:
    text = Path("app/templates/home.html").read_text(encoding="utf-8")
    assert "<!-- snowbird-panel-include -->" in text


def test_home_has_search_region_separate() -> None:
    text = Path("app/templates/home.html").read_text(encoding="utf-8")
    snow = text.index("<!-- snowbird-panel-include -->")
    hero_end = text.index("</section>", text.index('class="hero"'))
    assert snow > hero_end
