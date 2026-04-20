"""Gap template responses include /contribute (Phase 5.4)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.chat.unified_router import route
from app.db.database import SessionLocal


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_date_lookup_gap_includes_contribute(db: Session) -> None:
    with patch("app.chat.unified_router.answer_with_tier3") as m3:
        r = route("When is the zzznonexistentevent999abc?", "sess-gap-date", db)
    m3.assert_not_called()
    assert r.sub_intent == "DATE_LOOKUP"
    assert "/contribute" in r.response


def test_location_lookup_gap_includes_contribute(db: Session) -> None:
    with patch("app.chat.unified_router.answer_with_tier3") as m3:
        r = route("Where is Totally Fictional Venue XYZ?", "sess-gap-loc", db)
    m3.assert_not_called()
    assert r.sub_intent == "LOCATION_LOOKUP"
    assert "/contribute" in r.response


def test_hours_lookup_gap_includes_contribute(db: Session) -> None:
    with patch("app.chat.unified_router.answer_with_tier3") as m3:
        r = route("What are the hours for zzznonexistent999xyz?", "sess-gap-hrs", db)
    m3.assert_not_called()
    assert r.sub_intent == "HOURS_LOOKUP"
    assert "/contribute" in r.response
