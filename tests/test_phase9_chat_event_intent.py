"""Phase 9a — tier-2 event intent detection."""

from __future__ import annotations

from app.chat.tier2_handler import detect_event_intent


def test_detect_tonight() -> None:
    assert detect_event_intent("what's happening tonight") == {"when": "tonight"}


def test_detect_this_weekend() -> None:
    assert detect_event_intent("events this weekend") == {"when": "this_weekend"}


def test_detect_non_event_none() -> None:
    assert detect_event_intent("best plumber near me") is None
