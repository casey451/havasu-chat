"""Tests for card_row component builders and tier2_card_row integration."""

from __future__ import annotations

from unittest.mock import patch

from app.chat.component_builders import (
    build_card_row,
    fallback_card_row_voice,
    is_card_row_query,
)
from app.chat.tier2_schema import Tier2Filters
from app.chat.tier2_card_row import try_build_card_row


def _event(
    day: str,
    *,
    name: str = "Event",
    start_time: str = "18:00",
    description: str = "A fun evening.",
    tags: list[str] | None = None,
    event_url: str = "https://example.com/event",
) -> dict:
    return {
        "type": "event",
        "date": day,
        "name": name,
        "start_time": start_time,
        "description": description,
        "tags": tags or ["food"],
        "event_url": event_url,
        "location_name": "Waterfront",
    }


def _provider(
    *,
    name: str = "Sunset Grill",
    slug: str = "sunset-grill",
    address: str = "123 Main St\nLake Havasu City AZ",
    thumb_url: str | None = "https://example.com/thumb.jpg",
    description: str = "Upscale waterfront dining.",
) -> dict:
    return {
        "type": "provider",
        "name": name,
        "slug": slug,
        "address": address,
        "thumb_url": thumb_url,
        "description": description,
        "google_primary_category": "restaurant",
    }


def test_is_card_row_query_matches_date_night() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [_event("2026-05-30") for _ in range(3)]
    assert is_card_row_query("where's good for date night", f, rows) is True


def test_is_card_row_query_matches_best_spots_for() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [_event("2026-05-30"), _event("2026-05-31"), _provider()]
    assert is_card_row_query("best spots for sunset drinks", f, rows) is True


def test_is_card_row_query_rejects_no_intent_match() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [_event("2026-05-30") for _ in range(3)]
    assert is_card_row_query("tell me about Channel Brewing", f, rows) is False


def test_is_card_row_query_rejects_single_day_filter() -> None:
    f = Tier2Filters(time_window="today", parser_confidence=0.9)
    rows = [_event("2026-05-30") for _ in range(3)]
    assert is_card_row_query("any good spots for Friday", f, rows) is False


def test_is_card_row_query_rejects_week_window() -> None:
    f = Tier2Filters(time_window="this_week", parser_confidence=0.9)
    rows = [_event("2026-05-30") for _ in range(3)]
    assert is_card_row_query("anything good this week", f, rows) is False


def test_is_card_row_query_rejects_too_few_rows() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [_event("2026-05-30")]
    assert is_card_row_query("good spots for date night", f, rows) is False


def test_is_card_row_query_rejects_too_many_rows() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [_event("2026-05-30") for _ in range(8)]
    assert is_card_row_query("recommend a spot", f, rows) is False


def test_is_card_row_query_rejects_provider_listing() -> None:
    f = Tier2Filters(category="plumber", parser_confidence=0.9)
    rows = [_provider(name=f"P{i}", slug=f"p{i}") for i in range(4)]
    assert is_card_row_query("any good plumbers", f, rows) is False


def test_build_card_row_caps_at_three_items() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [_event("2026-05-30", name=f"E{i}") for i in range(5)]
    data = build_card_row(f, rows)
    assert len(data["items"]) == 3


def test_build_card_row_ranks_image_url_first() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [
        _event("2026-05-28", name="A"),
        _event("2026-05-29", name="B"),
        _provider(name="Photo Spot", slug="photo-spot"),
        _event("2026-05-30", name="D"),
    ]
    data = build_card_row(f, rows)
    assert data["items"][0]["title"] == "Photo Spot"
    assert data["items"][0]["image_url"] == "https://example.com/thumb.jpg"


def test_build_card_row_event_row_shape() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [_event("2026-05-30", name="Jazz Night")]
    data = build_card_row(f, rows)
    item = data["items"][0]
    assert item["title"] == "Jazz Night"
    assert "meta" in item
    assert item["url"] == "https://example.com/event"
    assert "category" in item
    assert "category_warm" in item
    assert item["image_url"] is None


def test_build_card_row_provider_row_shape() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [_provider()]
    data = build_card_row(f, rows)
    item = data["items"][0]
    assert item["image_url"] == "https://example.com/thumb.jpg"
    assert item["meta"] == "123 Main St"
    assert item["url"] == "/provider/sunset-grill"


def test_fallback_voice_three_items_pattern() -> None:
    rows = [_event("2026-05-30") for _ in range(3)]
    voice = fallback_card_row_voice(rows, "good spots for date night")
    assert "?" not in voice
    assert voice.endswith(".")
    assert "three" in voice.lower()


def test_try_build_card_row_returns_none_for_non_match() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [_event("2026-05-30") for _ in range(3)]
    assert try_build_card_row("tell me about X", f, rows) is None


def test_try_build_card_row_llm_fallback_on_exception() -> None:
    f = Tier2Filters(parser_confidence=0.9)
    rows = [_event("2026-05-30") for _ in range(3)]
    with patch(
        "app.chat.tier2_card_row.call_anthropic_messages",
        side_effect=RuntimeError("llm down"),
    ):
        result = try_build_card_row("where's good for date night", f, rows)
    assert result is not None
    voice, data, v_in, v_out = result
    assert v_in == 0 and v_out == 0
    assert "?" not in voice
    assert len(data["items"]) == 3
