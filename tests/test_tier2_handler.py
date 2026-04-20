"""Tests for ``app.chat.tier2_handler`` orchestrator."""

from __future__ import annotations

from unittest.mock import patch

from app.chat.tier2_handler import TIER2_CONFIDENCE_THRESHOLD, answer_with_tier2, try_tier2_with_usage
from app.chat.tier2_schema import Tier2Filters


def test_happy_path_returns_formatter_string() -> None:
    f = Tier2Filters(parser_confidence=0.9, entity_name="X", fallback_to_tier3=False)
    with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 10, 5)):
        with patch(
            "app.chat.tier2_handler.tier2_db_query.query",
            return_value=[{"type": "provider", "id": "1", "name": "X"}],
        ):
            with patch(
                "app.chat.tier2_handler.tier2_formatter.format",
                return_value=("Final answer.", 8, 3),
            ):
                assert answer_with_tier2("tell me about X") == "Final answer."


def test_try_tier2_with_usage_happy_path_token_sums() -> None:
    f = Tier2Filters(parser_confidence=0.9, entity_name="X", fallback_to_tier3=False)
    with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 10, 5)):
        with patch(
            "app.chat.tier2_handler.tier2_db_query.query",
            return_value=[{"type": "provider", "id": "1", "name": "X"}],
        ):
            with patch(
                "app.chat.tier2_handler.tier2_formatter.format",
                return_value=("Final answer.", 8, 3),
            ):
                text, total, tin, tout = try_tier2_with_usage("tell me about X")
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
