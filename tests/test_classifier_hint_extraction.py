"""Phase 6.4 — hint extraction wired through ``route`` (mock ``extract_hints``)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.chat.hint_extractor import ExtractedHints
from app.chat.unified_router import route
from app.core.session import clear_session_state, get_session
from app.db.database import SessionLocal


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_route_updates_age_from_mocked_extractor(db: Session) -> None:
    clear_session_state("hint-a")
    with patch(
        "app.chat.unified_router.extract_hints",
        return_value=ExtractedHints(age=6, location=None),
    ):
        with patch("app.chat.unified_router.try_tier1", return_value=None):
            with patch(
                "app.chat.unified_router.try_tier2_with_usage",
                return_value=("ok", 1, 1, 0),
            ):
                route("my 6-year-old likes BMX", "hint-a", db)
    assert get_session("hint-a")["onboarding_hints"]["age"] == 6


def test_route_updates_location_only(db: Session) -> None:
    clear_session_state("hint-b")
    with patch(
        "app.chat.unified_router.extract_hints",
        return_value=ExtractedHints(age=None, location="near the island"),
    ):
        with patch("app.chat.unified_router.try_tier1", return_value=None):
            with patch(
                "app.chat.unified_router.try_tier2_with_usage",
                return_value=("ok", 1, 1, 0),
            ):
                route("near the island stuff", "hint-b", db)
    assert get_session("hint-b")["onboarding_hints"]["location"] == "near the island"


def test_route_extractor_none_leaves_session(db: Session) -> None:
    clear_session_state("hint-c")
    get_session("hint-c")["onboarding_hints"]["age"] = 9
    with patch("app.chat.unified_router.extract_hints", return_value=None):
        with patch("app.chat.unified_router.try_tier1", return_value=None):
            with patch(
                "app.chat.unified_router.try_tier2_with_usage",
                return_value=("ok", 1, 1, 0),
            ):
                route("what's open right now", "hint-c", db)
    assert get_session("hint-c")["onboarding_hints"]["age"] == 9


def test_route_extractor_empty_hints_noop(db: Session) -> None:
    clear_session_state("hint-d")
    with patch("app.chat.unified_router.extract_hints", return_value=ExtractedHints(age=None, location=None)):
        with patch("app.chat.unified_router.try_tier1", return_value=None):
            with patch(
                "app.chat.unified_router.try_tier2_with_usage",
                return_value=("ok", 1, 1, 0),
            ):
                route("my kid wants fun", "hint-d", db)
    h = get_session("hint-d")["onboarding_hints"]
    assert h.get("age") is None
