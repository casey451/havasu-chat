"""Unit tests for app.chat.conditions_answer (Phase 6, P1-4).

Covers the value-seeking conditions detector and the formatter (against stub
payloads — no DB / cache needed).
"""

from __future__ import annotations

import pytest

from app.chat.conditions_answer import _format, detect_conditions_dimension


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("What is the water temperature today?", "water_temp"),
        ("What are water temperature and visibility like right now?", "water_temp"),
        ("Is it too windy to kayak this afternoon?", "wind"),
        ("How windy is it right now?", "wind"),
        ("What's the air quality today?", "aqi"),
        ("is it smoky out", "aqi"),
        ("what's the lake level right now", "lake_level"),
        ("Are there any current weather or safety advisories before going?", "alerts"),
        ("Is there a heat advisory or weather reason not to hike today?", "alerts"),
        ("how hot is it right now", "air_temp"),
        ("what's the weather like in Lake Havasu", "general"),
    ],
)
def test_detect_value_seeking_dimensions(query: str, expected: str) -> None:
    assert detect_conditions_dimension(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        # place questions with a weather modifier are NOT conditions lookups
        "Is there a dog-friendly place to cool off in hot weather?",
        "What is the smart weather backup for wind or extreme heat?",
        "What can I do outdoors before it gets dangerously hot?",
        "Where can I kayak with a shuttle?",
        "Which beach has shade and easy parking?",
    ],
)
def test_detect_place_with_modifier_returns_none(query: str) -> None:
    assert detect_conditions_dimension(query) is None


def test_format_water_temp_present() -> None:
    out = _format("water_temp", {"water_temp_f": 62.4}, "water temp today")
    assert "62" in out
    assert "water" in out.lower()


def test_format_water_temp_missing_is_graceful() -> None:
    out = _format("water_temp", {}, "water temp today")
    assert "don't have" in out.lower()
    assert "62" not in out


def test_format_wind_strong_with_paddle_note() -> None:
    out = _format(
        "wind",
        {"wind_speed_mph": 18, "wind_direction_cardinal": "SW"},
        "too windy to kayak?",
    )
    assert "18 mph" in out
    assert "SW" in out
    assert "caution" in out.lower()


def test_format_aqi_banding() -> None:
    good = _format("aqi", {"current_aqi": 35, "current_aqi_parameter": "PM2.5"}, "air quality")
    assert "35" in good and "good" in good.lower()
    bad = _format("aqi", {"current_aqi": 165}, "air quality")
    assert "unhealthy" in bad.lower()


def test_format_alerts_none_and_present() -> None:
    none = _format("alerts", {"active_nws_alerts": []}, "any advisories")
    assert "no active" in none.lower()
    present = _format(
        "alerts", {"active_nws_alerts": [{"event": "Excessive Heat Warning"}]}, "any advisories"
    )
    assert "Excessive Heat Warning" in present


def test_format_air_temp_with_heat_index_and_extreme_note() -> None:
    out = _format("air_temp", {"current_temp_f": 104, "heat_index_f": 110}, "how hot is it")
    assert "104" in out
    assert "110" in out  # heat index surfaced when notably higher
    assert "water" in out.lower()  # extreme-heat nudge


def test_format_lake_level() -> None:
    out = _format("lake_level", {"lake_gauge_ft": 448.2}, "lake level")
    assert "448" in out
