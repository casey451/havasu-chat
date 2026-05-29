"""Tests for ``build_single_business_card`` (BUILD.md step 7.5 spotlight)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.chat.component_builders import build_single_business_card
from app.chat.intent_classifier import IntentResult


def _intent() -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent="OPEN_ENDED",
        confidence=0.9,
        entity="Spot Pros",
        raw_query="tell me about spot pros",
        normalized_query="tell me about spot pros",
    )


def test_build_single_business_card_emits_spotlight(monkeypatch) -> None:
    fixed = datetime(2026, 5, 28, 12, 0, tzinfo=ZoneInfo("America/Phoenix"))
    monkeypatch.setattr("app.chat.component_builders.now_lake_havasu", lambda: fixed)
    row = {
        "type": "provider",
        "name": "Spot Pros",
        "slug": "spot-pros",
        "tier": "spotlight",
        "sponsored_until": fixed + timedelta(days=7),
        "google_rating": 4.5,
    }
    payload = build_single_business_card(_intent(), row)
    assert payload["spotlight"] is True
