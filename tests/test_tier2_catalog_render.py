"""Deterministic Tier 2 event catalog rendering (no LLM)."""

from __future__ import annotations

import pytest

from app.chat.tier2_catalog_render import render_tier2_events


def test_render_event_single_day_both_times_with_location() -> None:
    rows = [
        {
            "type": "event",
            "name": "Fair",
            "date": "2030-01-01",
            "start_time": "10:00",
            "end_time": "12:00",
            "location_name": "Rotary Park",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    expected = "Fair on January 1, 2030 from 10:00 AM to 12:00 PM at Rotary Park."
    assert render_tier2_events("q", rows) == expected


def test_render_event_single_day_start_time_only_with_location() -> None:
    rows = [
        {
            "type": "event",
            "name": "Fair",
            "date": "2030-01-01",
            "start_time": "08:00",
            "end_time": None,
            "location_name": "Rotary Park",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    expected = "Fair on January 1, 2030 at 8:00 AM at Rotary Park."
    assert render_tier2_events("q", rows) == expected


def test_render_event_single_day_no_times_with_location() -> None:
    rows = [
        {
            "type": "event",
            "name": "Fair",
            "date": "2030-01-01",
            "start_time": None,
            "end_time": None,
            "location_name": "Rotary Park",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    expected = "Fair on January 1, 2030 at Rotary Park."
    assert render_tier2_events("q", rows) == expected


def test_render_event_multiday_same_year_both_times_with_location() -> None:
    rows = [
        {
            "type": "event",
            "name": "Desert Bash",
            "date": "2026-05-02",
            "end_date": "2026-05-04",
            "start_time": "18:00",
            "end_time": "22:00",
            "location_name": "Site Six",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    expected = "Desert Bash runs May 2–4, 2026 from 6:00 PM to 10:00 PM at Site Six."
    assert render_tier2_events("q", rows) == expected


def test_render_event_multiday_same_year_start_time_only() -> None:
    rows = [
        {
            "type": "event",
            "name": "Desert Bash",
            "date": "2026-05-02",
            "end_date": "2026-05-04",
            "start_time": "18:00",
            "end_time": None,
            "location_name": "Site Six",
            "description": "Live music and food trucks.",
            "event_url": "https://example.com/bash",
            "tags": [],
        }
    ]
    expected = (
        "Desert Bash runs May 2–4, 2026 at 6:00 PM at Site Six. "
        "Live music and food trucks. [Desert Bash](https://example.com/bash)"
    )
    assert render_tier2_events("q", rows) == expected


def test_render_event_multiday_cross_year() -> None:
    rows = [
        {
            "type": "event",
            "name": "Holiday Fest",
            "date": "2025-12-31",
            "end_date": "2026-01-02",
            "start_time": "18:00",
            "end_time": "22:00",
            "location_name": "Downtown",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    expected = "Holiday Fest runs Dec 31, 2025–Jan 2, 2026 from 6:00 PM to 10:00 PM at Downtown."
    assert render_tier2_events("q", rows) == expected


def test_render_event_location_clause_omitted_when_empty() -> None:
    rows = [
        {
            "type": "event",
            "name": "Fair",
            "date": "2030-01-01",
            "start_time": "10:00",
            "end_time": "12:00",
            "location_name": "",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    expected = "Fair on January 1, 2030 from 10:00 AM to 12:00 PM."
    assert render_tier2_events("q", rows) == expected


def test_render_description_appends_period_when_missing_terminal_punctuation() -> None:
    rows = [
        {
            "type": "event",
            "name": "Test",
            "date": "2030-01-01",
            "start_time": "10:00",
            "end_time": "12:00",
            "location_name": "Park",
            "description": "Fresh donuts daily",
            "event_url": "",
            "tags": [],
        }
    ]
    out = render_tier2_events("q", rows)
    assert "Fresh donuts daily." in out


@pytest.mark.parametrize(
    "description,expected_fragment",
    [
        ("Ends with dot.", "Ends with dot."),
        ("Surprise!", "Surprise!"),
        ("Really?", "Really?"),
    ],
)
def test_render_description_preserves_terminal_punctuation(
    description: str, expected_fragment: str
) -> None:
    rows = [
        {
            "type": "event",
            "name": "Test",
            "date": "2030-01-01",
            "start_time": "10:00",
            "end_time": "12:00",
            "location_name": "Park",
            "description": description,
            "event_url": "",
            "tags": [],
        }
    ]
    out = render_tier2_events("q", rows)
    assert expected_fragment in out
    assert ".." not in out


def test_render_description_omitted_when_blank() -> None:
    rows = [
        {
            "type": "event",
            "name": "Test",
            "date": "2030-01-01",
            "start_time": "10:00",
            "end_time": "12:00",
            "location_name": "Park",
            "description": "   ",
            "event_url": "",
            "tags": [],
        }
    ]
    out = render_tier2_events("q", rows)
    assert out == "Test on January 1, 2030 from 10:00 AM to 12:00 PM at Park."


def test_render_event_url_markdown_link_appended() -> None:
    rows = [
        {
            "type": "event",
            "name": "River Day",
            "date": "2030-06-01",
            "start_time": "09:00",
            "end_time": "17:00",
            "location_name": "Waterfront",
            "description": "",
            "event_url": "https://riverscene.example/e/1",
            "tags": [],
        }
    ]
    out = render_tier2_events("q", rows)
    assert out.endswith("[River Day](https://riverscene.example/e/1)")


def test_render_noon_and_midnight_use_12h_clock() -> None:
    noon = [
        {
            "type": "event",
            "name": "Lunch",
            "date": "2030-01-01",
            "start_time": "12:00",
            "end_time": None,
            "location_name": "Cafe",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    assert "12:00 PM" in render_tier2_events("q", noon)
    midnight = [
        {
            "type": "event",
            "name": "Late",
            "date": "2030-01-01",
            "start_time": "00:00",
            "end_time": "01:00",
            "location_name": "Hall",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    out = render_tier2_events("q", midnight)
    assert "12:00 AM" in out
    assert "1:00 AM" in out


def test_render_event_url_omitted_when_empty() -> None:
    rows = [
        {
            "type": "event",
            "name": "No Link",
            "date": "2030-06-01",
            "start_time": "09:00",
            "end_time": None,
            "location_name": "X",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    out = render_tier2_events("q", rows)
    assert "[" not in out
    assert "](" not in out


def test_render_single_event_has_no_header_line() -> None:
    rows = [
        {
            "type": "event",
            "name": "Fair",
            "date": "2030-01-01",
            "start_time": "10:00",
            "end_time": "12:00",
            "location_name": "Rotary Park",
            "description": "",
            "event_url": "",
            "tags": [],
        }
    ]
    out = render_tier2_events("q", rows)
    first = out.split("\n")[0]
    assert not first.endswith("events:")
    assert not first.endswith("event:")
    assert first.startswith("Fair on")


def test_render_multiple_events_header_and_numbered_prefixes() -> None:
    rows = [
        {
            "type": "event",
            "name": "Alpha",
            "date": "2030-01-01",
            "start_time": "10:00",
            "end_time": "11:00",
            "location_name": "A",
            "description": "",
            "event_url": "",
            "tags": [],
        },
        {
            "type": "event",
            "name": "Beta",
            "date": "2030-01-02",
            "start_time": "14:00",
            "end_time": "15:00",
            "location_name": "B",
            "description": "",
            "event_url": "",
            "tags": [],
        },
    ]
    out = render_tier2_events("q", rows)
    assert out.startswith("2 events:\n\n1. ")
    assert "\n2. " in out
    assert out.index("Alpha") < out.index("Beta")


def test_render_preserves_sql_row_order() -> None:
    rows = [
        {
            "type": "event",
            "name": "Starts Today",
            "date": "2026-05-08",
            "start_time": "10:00",
            "end_time": "11:00",
            "location_name": "X",
            "description": "",
            "event_url": "",
            "tags": [],
        },
        {
            "type": "event",
            "name": "Overlap Only",
            "date": "2026-05-06",
            "end_date": "2026-05-10",
            "start_time": "06:00",
            "end_time": None,
            "location_name": "Lake",
            "description": "",
            "event_url": "",
            "tags": [],
        },
    ]
    out = render_tier2_events("q", rows)
    assert out.index("Starts Today") < out.index("Overlap Only")
