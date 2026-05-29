"""Tests for single_card / single_business_card builders and tier2 wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.chat.component_builders import (
    build_single_business_card,
    build_single_card,
    fallback_single_card_voice,
    is_single_business_card_query,
    is_single_card_query,
)
from app.chat.intent_classifier import IntentResult
from app.chat.tier2_schema import Tier2Filters
from app.chat.tier2_single_card import try_build_single_card
from app.chat.unified_router import route
from app.db.database import SessionLocal


def _intent(
    *,
    entity: str | None = "Bridgewater 5K",
    sub_intent: str | None = "OPEN_ENDED",
) -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent=sub_intent,
        confidence=0.9,
        entity=entity,
        raw_query="tell me about something",
        normalized_query="tell me about something",
    )


def _event_row(**overrides: object) -> dict:
    row = {
        "type": "event",
        "name": "Bridgewater 5K",
        "date": "2026-05-31",
        "start_time": "08:00",
        "end_time": "10:00",
        "location_name": "Rotary Park",
        "description": "Annual waterfront 5K along the Bridgewater Channel.",
        "event_url": "https://example.com/5k",
        "tags": ["fitness"],
    }
    row.update(overrides)
    return row


def _provider_row(**overrides: object) -> dict:
    row = {
        "type": "provider",
        "name": "Channel Brewing",
        "slug": "channel-brewing",
        "category": "restaurant",
        "google_primary_category": "restaurant",
        "google_place_id": "places/abc123",
        "address": "123 Main St\nLake Havasu City AZ",
        "phone": "9284531400",
        "website": "https://example.com/channel",
        "hours": "Mon–Sun 11 AM – 9 PM",
        "hours_structured": {
            "monday": [{"open": "11:00", "close": "21:00"}],
        },
        "description": "Local brewery with a patio on the channel.",
        "google_rating": 4.6,
        "google_review_count": 212,
    }
    row.update(overrides)
    return row


def test_is_single_card_matches_event_lookup() -> None:
    intent = _intent(entity="Bridgewater 5K", sub_intent=None)
    rows = [_event_row()]
    assert is_single_card_query(intent, rows) is True


def test_is_single_card_rejects_tier1_subintent() -> None:
    intent = _intent(sub_intent="PHONE_LOOKUP")
    rows = [_event_row()]
    assert is_single_card_query(intent, rows) is False


def test_is_single_card_rejects_missing_entity() -> None:
    intent = _intent(entity=None)
    rows = [_event_row()]
    assert is_single_card_query(intent, rows) is False


def test_is_single_card_rejects_multiple_rows() -> None:
    intent = _intent(entity="Bridgewater 5K")
    rows = [_event_row(), _event_row(name="Bridgewater 5K Fun Run"), _event_row()]
    assert is_single_card_query(intent, rows) is False


def test_is_single_business_card_matches_provider_lookup() -> None:
    intent = _intent(entity="Channel Brewing")
    rows = [_provider_row()]
    assert is_single_business_card_query(intent, rows) is True


def test_is_single_business_card_rejects_event_row() -> None:
    intent = _intent(entity="Bridgewater 5K")
    rows = [_event_row()]
    assert is_single_business_card_query(intent, rows) is False


def test_build_single_card_event_basics() -> None:
    data = build_single_card(_intent(), _event_row())
    assert data["title"] == "Bridgewater 5K"
    assert data["summary"]
    keys = [f["key"] for f in data["facts"]]
    assert "When" in keys
    assert "Where" in keys
    where = next(f for f in data["facts"] if f["key"] == "Where")
    assert where.get("val_url", "").startswith("https://www.google.com/maps")
    labels = [a["label"] for a in data["actions"]]
    assert "Directions" in labels


def test_build_single_card_skips_missing_facts() -> None:
    row = _event_row(end_time=None, cost=None)
    row.pop("end_time", None)
    data = build_single_card(_intent(), row)
    keys = [f["key"] for f in data["facts"]]
    assert keys == ["When", "Where"]
    assert "Cost" not in keys


def test_build_single_business_card_basics() -> None:
    data = build_single_business_card(_intent(entity="Channel Brewing"), _provider_row())
    assert data["title"] == "Channel Brewing"
    assert data["status"] in ("open", "closed", "unknown")
    keys = [f["key"] for f in data["facts"]]
    assert "Hours" in keys
    assert "Address" in keys
    assert "Rating" in keys
    labels = [a["label"] for a in data["actions"]]
    assert "Call" in labels
    assert "Website" in labels
    assert "Directions" in labels


def test_build_single_business_card_with_review_snippet() -> None:
    row = _provider_row(
        google_review_snippets=[
            {"text": "Great patio and friendly staff.", "attribution": "Alex R."},
        ]
    )
    data = build_single_business_card(_intent(entity="Channel Brewing"), row)
    review = next(f for f in data["facts"] if f["key"] == "Recent review")
    assert "Alex R." in review["val"]
    assert "Great patio" in review["val"]


def test_build_single_business_card_no_hours() -> None:
    row = _provider_row(hours="", hours_structured=None)
    data = build_single_business_card(_intent(entity="Channel Brewing"), row)
    assert data["status"] == "unknown"
    assert data["status_text"] == "Hours on profile"


def test_fallback_voice_event_pattern() -> None:
    voice = fallback_single_card_voice(_event_row(), is_business=False)
    assert "?" not in voice
    assert voice.endswith(".")
    assert "Bridgewater 5K" in voice


def test_fallback_voice_business_pattern() -> None:
    voice = fallback_single_card_voice(_provider_row(), is_business=True)
    assert "?" not in voice
    assert voice.endswith(".")
    assert "Channel Brewing" in voice


def test_try_build_single_card_returns_none_for_non_lookup() -> None:
    f = Tier2Filters(time_window="this_week", parser_confidence=0.9)
    rows = [_event_row(date=f"2026-05-{d:02d}") for d in range(28, 33)]
    intent = _intent(entity="Bridgewater 5K")
    assert try_build_single_card("what's on this week", intent, f, rows) is None


def test_try_build_single_card_llm_fallback_on_exception() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    intent = _intent(entity="Bridgewater 5K")
    rows = [_event_row()]
    with patch(
        "app.chat.voice_principles.call_anthropic_messages",
        side_effect=RuntimeError("llm down"),
    ):
        result = try_build_single_card("tell me about the bridgewater 5k", intent, f, rows)
    assert result is not None
    comp_type, voice, data, v_in, v_out = result
    assert comp_type == "single_card"
    assert v_in == 0 and v_out == 0
    assert "?" not in voice
    assert data["title"] == "Bridgewater 5K"


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _disable_llm_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_LLM_ROUTER", "false")


def test_gap_path_emits_none(db: Session) -> None:
    r = route("tell me about Foobar Bistro", "sess-single-card-gap", db)
    assert r.tier_used == "gap_template"
    assert r.component_type == "none"
