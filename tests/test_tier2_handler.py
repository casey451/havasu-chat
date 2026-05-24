"""Tests for ``app.chat.tier2_handler`` orchestrator."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from app.chat.tier2_handler import (
    TIER2_CONFIDENCE_THRESHOLD,
    _normalize_tier2_filters_from_query,
    answer_with_tier2,
    try_tier2_with_usage,
)
from app.chat.tier2_schema import Tier2Filters


def test_happy_path_returns_formatter_string() -> None:
    f = Tier2Filters(parser_confidence=0.9, entity_name="X", fallback_to_tier3=False)
    q = "tell me about X happy path isolate"
    with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 10, 5)):
        with patch(
            "app.chat.tier2_handler.tier2_db_query.query",
            return_value=[{"type": "provider", "id": "1", "name": "X"}],
        ):
            with patch(
                "app.chat.tier2_handler.tier2_formatter.format",
                return_value=("Final answer.", 8, 3),
            ):
                assert answer_with_tier2(q) == "Final answer."


def test_try_tier2_with_usage_happy_path_token_sums() -> None:
    f = Tier2Filters(parser_confidence=0.9, entity_name="X", fallback_to_tier3=False)
    q = "tell me about X token sums isolate"
    with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 10, 5)):
        with patch(
            "app.chat.tier2_handler.tier2_db_query.query",
            return_value=[{"type": "provider", "id": "1", "name": "X"}],
        ):
            with patch(
                "app.chat.tier2_handler.tier2_formatter.format",
                return_value=("Final answer.", 8, 3),
            ):
                text, total, tin, tout = try_tier2_with_usage(q)
    assert text == "Final answer."
    assert tin == 18 and tout == 8 and total == 26


def test_parser_none_returns_none() -> None:
    with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(None, None, None)):
        assert answer_with_tier2("q") is None


def test_parser_fallback_flag_returns_none() -> None:
    f = Tier2Filters(parser_confidence=0.2, fallback_to_tier3=True)
    with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 1, 1)):
        assert answer_with_tier2("vague") is None


def test_low_confidence_returns_none() -> None:
    f = Tier2Filters(parser_confidence=TIER2_CONFIDENCE_THRESHOLD - 0.01, category="x")
    with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 1, 1)):
        assert answer_with_tier2("q") is None


def test_no_db_rows_returns_none() -> None:
    f = Tier2Filters(parser_confidence=0.95, category="nonexistent_xyz_12345")
    with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 1, 1)):
        with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=[]):
            assert answer_with_tier2("anything") is None


def test_formatter_none_returns_none() -> None:
    f = Tier2Filters(parser_confidence=0.95, entity_name="Something")
    with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 1, 1)):
        with patch(
            "app.chat.tier2_handler.tier2_db_query.query",
            return_value=[{"type": "provider", "id": "1", "name": "Something"}],
        ):
            with patch(
                "app.chat.tier2_handler.tier2_formatter.format",
                return_value=(None, 9, 2),
            ):
                assert answer_with_tier2("q") is None


def test_threshold_constant_documented() -> None:
    assert TIER2_CONFIDENCE_THRESHOLD == 0.7


def test_normalize_filters_uses_explicit_month_day(monkeypatch) -> None:
    class _FixedNow:
        def date(self) -> date:
            return date(2026, 5, 7)

    monkeypatch.setattr("app.chat.tier2_handler.now_lake_havasu", lambda: _FixedNow())
    f = Tier2Filters(
        parser_confidence=0.9,
        date_exact=date(2026, 5, 15),
    )
    out = _normalize_tier2_filters_from_query("what's happening on Friday May 8", f)
    assert out.date_exact == date(2026, 5, 8)
    assert out.time_window is None
    assert out.day_of_week is None


def test_normalize_filters_uses_weekend_token() -> None:
    f = Tier2Filters(
        parser_confidence=0.9,
        date_start=date(2026, 5, 9),
        date_end=date(2026, 5, 10),
    )
    out = _normalize_tier2_filters_from_query("is there dodgeball this weekend?", f)
    assert out.time_window == "this_weekend"
    assert out.date_start is None
    assert out.date_end is None


def test_normalize_filters_maps_art_class_query_to_arts() -> None:
    f = Tier2Filters(parser_confidence=0.9, category="classes", time_window="this_month")
    out = _normalize_tier2_filters_from_query("any art classes this week?", f)
    assert out.category == "arts"
    assert out.time_window == "this_week"


# ---------------------------------------------------------------------------
# Phase 7.7 — honest empty listing on open_now zero-rows (q03 UX fix)
# ---------------------------------------------------------------------------


def test_open_now_empty_listing_helper_pluralizes() -> None:
    """The helper must pluralize one-word and two-word categories naturally."""
    from app.chat.tier2_handler import _open_now_empty_listing

    assert "restaurants" in _open_now_empty_listing("restaurant")
    assert "coffee shops" in _open_now_empty_listing("coffee shop")
    assert "pharmacies" in _open_now_empty_listing("pharmacy")
    assert "Lake Havasu catalog" in _open_now_empty_listing("restaurant")
    assert "/contribute" in _open_now_empty_listing("restaurant")
    assert "golakehavasu.com" in _open_now_empty_listing("restaurant")


def test_shortcut_open_now_zero_rows_returns_honest_empty_listing() -> None:
    """q03 shortcut path: shortcut fires, DB returns zero rows, handler emits template (no LLM)."""
    with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=[]):
        text, total, tin, tout = try_tier2_with_usage("what restaurants are open now")
    assert text is not None
    assert "restaurants" in text
    assert "current hours data" in text
    assert total == 0  # zero LLM tokens — shortcut path
    assert tin == 0
    assert tout == 0


def test_parser_path_open_now_zero_rows_returns_honest_empty_listing() -> None:
    """Parser-built filters with the q03 shape also fire the template (carries parser tokens)."""
    f = Tier2Filters(
        parser_confidence=0.9,
        category="restaurant",
        open_now=True,
        fallback_to_tier3=False,
    )
    # Bypass the shortcut by submitting a query the shortcut won't match
    # (so the parser path is reached).
    with patch(
        "app.chat.tier2_handler.tier2_business_shortcut.try_business_listing_shortcut",
        return_value=None,
    ):
        with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 12, 5)):
            with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=[]):
                text, total, tin, tout = try_tier2_with_usage(
                    "anywhere good for dinner that's open right now"
                )
    assert text is not None
    assert "restaurants" in text
    # Parser tokens carried through honestly:
    assert tin == 12
    assert tout == 5
    assert total == 17


def test_parser_path_open_now_no_category_still_cascades() -> None:
    """LLM parser sets open_now=True with category=None (recommendation shape): NO template fires."""
    f = Tier2Filters(
        parser_confidence=0.9,
        category=None,
        open_now=True,
        fallback_to_tier3=False,
    )
    with patch(
        "app.chat.tier2_handler.tier2_business_shortcut.try_business_listing_shortcut",
        return_value=None,
    ):
        with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 12, 5)):
            with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=[]):
                text, _, _, _ = try_tier2_with_usage("anywhere open right now")
    assert text is None  # cascades to tier-3 as before


def test_shortcut_open_now_with_rows_still_renders_listing() -> None:
    """Sanity: when rows DO survive the open_now filter, the existing listing render wins."""
    rows = [{"type": "provider", "name": "Open Diner", "address": "1 Main", "phone": "555-1"}]
    with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=rows):
        text, total, _, _ = try_tier2_with_usage("what restaurants are open now")
    assert text is not None
    assert "Open Diner" in text
    assert "current hours data" not in text  # template did NOT fire
    assert total == 0  # shortcut path is zero-token


def test_non_open_now_zero_rows_still_returns_none() -> None:
    """Non-open_now zero-rows path is unchanged (no template, falls through)."""
    f = Tier2Filters(
        parser_confidence=0.9,
        category="nonexistent_xyz",
        open_now=False,
        fallback_to_tier3=False,
    )
    with patch(
        "app.chat.tier2_handler.tier2_business_shortcut.try_business_listing_shortcut",
        return_value=None,
    ):
        with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 1, 1)):
            with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=[]):
                text, total, _, _ = try_tier2_with_usage("find me a nonexistent_xyz")
    assert text is None  # original behavior preserved
    assert total is None


# ---------------------------------------------------------------------------
# Lane B-2 — parser + formatter cache integration (token savings)
# ---------------------------------------------------------------------------


def test_try_tier2_parser_cache_hit_fires_parse_once(monkeypatch) -> None:
    """Second identical turn serves parser from cache (zero extra parse tokens)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    class _FixedNow:
        def strftime(self, fmt: str) -> str:
            return datetime(2026, 5, 24, 12, 0, tzinfo=ZoneInfo("America/Phoenix")).strftime(fmt)

    monkeypatch.setattr("app.chat.tier2_handler.now_lake_havasu", lambda: _FixedNow())
    monkeypatch.setattr("app.chat.tier2_cache.now_lake_havasu", lambda: _FixedNow(), raising=False)

    f = Tier2Filters(
        parser_confidence=0.9,
        entity_name="B2CacheEntity",
        fallback_to_tier3=False,
    )
    rows = [{"type": "provider", "id": "b2-1", "name": "B2CacheEntity"}]
    parse_calls: list[str] = []

    def counting_parse(q: str):
        parse_calls.append(q)
        return (f, 10, 5)

    query = "b2 lane parser cache integration sentinel v2"
    with patch(
        "app.chat.tier2_handler.tier2_business_shortcut.try_business_listing_shortcut",
        return_value=None,
    ):
        with patch("app.chat.tier2_handler.tier2_parser.parse", side_effect=counting_parse):
            with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=rows):
                with patch(
                    "app.chat.tier2_handler.tier2_formatter.format",
                    return_value=("Cached path answer.", 8, 3),
                ):
                    try_tier2_with_usage(query)
                    text2, total2, tin2, tout2 = try_tier2_with_usage(query)
    assert len(parse_calls) == 1
    assert text2 == "Cached path answer."
    assert total2 == 0 and tin2 == 0 and tout2 == 0


def test_try_tier2_formatter_cache_hit_fires_format_once(monkeypatch) -> None:
    """Second identical turn serves formatter from cache (zero extra format tokens)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    class _FixedNow:
        def strftime(self, fmt: str) -> str:
            return datetime(2026, 5, 24, 12, 0, tzinfo=ZoneInfo("America/Phoenix")).strftime(fmt)

    monkeypatch.setattr("app.chat.tier2_handler.now_lake_havasu", lambda: _FixedNow())

    f = Tier2Filters(
        parser_confidence=0.9,
        entity_name="B2FmtEntity",
        fallback_to_tier3=False,
    )
    rows = [{"type": "provider", "id": "b2-fmt-1", "name": "B2FmtEntity"}]
    format_calls: list[str] = []

    def counting_format(q: str, r):
        format_calls.append(q)
        return ("Formatter once.", 8, 3)

    query = "b2 lane formatter cache integration sentinel v2"
    with patch(
        "app.chat.tier2_handler.tier2_business_shortcut.try_business_listing_shortcut",
        return_value=None,
    ):
        with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 0, 0)):
            with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=rows):
                with patch(
                    "app.chat.tier2_handler.tier2_formatter.format",
                    side_effect=counting_format,
                ):
                    try_tier2_with_usage(query)
                    text2, total2, tin2, tout2 = try_tier2_with_usage(query)
    assert len(format_calls) == 1
    assert text2 == "Formatter once."
    assert tin2 == 0 and tout2 == 0 and total2 == 0
