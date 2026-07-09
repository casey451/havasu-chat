"""Lake Havasu funzone scraper (Phase 5) — pure helper coverage.

Covers the curated venue set, the EntityPayload mapping, the hours-event specs
(facet:hours + window), and the themed special-session specs (facet:special,
dated on the matching weekday). No DB/network here (the loader's --dry-run
against prod is the gated, operator-run step).
"""

from __future__ import annotations

from datetime import date

from app.contrib.lhc_funzone import (
    DEFAULT_CATEGORY_SLUG,
    HOURS_WINDOW_DAYS,
    IN_TOWN_VENUES,
    SOURCE_NAME,
    SPECIAL_SESSIONS,
    facility_to_entity_payload,
    funzone_facilities,
    funzone_hours_event_specs,
    funzone_special_event_specs,
)
from app.events.activity_taxonomy import classify_events_subgroup


def test_curated_venue_set() -> None:
    venues = funzone_facilities()
    assert venues == list(IN_TOWN_VENUES)
    slugs = {v.activity_slug for v in venues}
    assert slugs == {"bowling", "billiards", "trampoline"}
    names = {v.name for v in venues}
    assert "Havasu Lanes & Keglers Pub" in names
    assert "Altitude Trampoline Park" in names
    assert "Mr. Lucky's Billiards & Pub" in names


def test_facility_payload_maps_to_funzone_subcategory() -> None:
    v = next(v for v in IN_TOWN_VENUES if v.name == "Altitude Trampoline Park")
    p = facility_to_entity_payload(v)
    assert p.entity_type == "place"
    assert p.category_slug == DEFAULT_CATEGORY_SLUG  # things-to-do-and-attractions
    assert p.legacy_category == "family-fun-and-arcades"
    assert p.source == SOURCE_NAME
    assert "Hours:" in (p.description or "")


def test_hours_specs_carry_activity_and_facet_hours() -> None:
    today = date(2026, 7, 1)
    specs = funzone_hours_event_specs(today=today, window_days=HOURS_WINDOW_DAYS)
    assert len(specs) == len(IN_TOWN_VENUES) * HOURS_WINDOW_DAYS
    for s in specs:
        assert s.all_day is True
        assert any(t.startswith("activity:") for t in s.tags)
        assert "facet:hours" in s.tags
        assert "facet:special" not in s.tags  # hours are NOT special sessions
        assert s.source_anchor.startswith("funhours|")
    # Bowling/trampoline carry family (Kids & Family overlay); billiards/pub do not.
    bowl = next(s for s in specs if "Havasu Lanes" in s.location_name)
    assert "activity:bowling" in bowl.tags and "family" in bowl.tags
    pool = next(s for s in specs if "Mr. Lucky" in s.location_name)
    assert "activity:billiards" in pool.tags and "family" not in pool.tags


def test_special_sessions_are_dated_and_facet_special() -> None:
    # Window covering a full week from a Monday (2026-06-29 is a Monday).
    specs = funzone_special_event_specs(today=date(2026, 6, 29), window_days=7)
    assert specs, "expected at least one special session in a full week"
    for s in specs:
        assert s.all_day is False
        assert "facet:special" in s.tags
        assert "facet:hours" not in s.tags
        assert s.start_time  # timed destination event
        assert s.source_anchor.startswith("funspecial|")
    titles = {s.title for s in specs}
    assert "Glow in the Park" in titles
    # Glow in the Park (Sat) lands only on a Saturday.
    sat = next(s for s in specs if s.title == "Glow in the Park")
    assert sat.date.weekday() == 5


def test_special_titles_route_to_their_venue_type() -> None:
    # Casey 2026-06-26: no Special Sessions silo — a themed session nests under its
    # venue type (Glow in the Park → Trampoline). The Havasu Lanes Cosmic Bowling
    # sessions were removed from this loader on 2026-06-26 (the dated "Cosmic
    # Bowling" series owns that listing now), so Glow in the Park is the lone
    # special session here.
    by_title = {
        s.title: classify_events_subgroup(s.title, s.tags)
        for s in funzone_special_event_specs(today=date(2026, 6, 29), window_days=7)
    }
    assert by_title.get("Glow in the Park") == "Trampoline"


def test_hours_titles_route_to_their_venue_type() -> None:
    expected = {
        "bowling": "Bowling", "billiards": "Billiards",
        "trampoline": "Trampoline", "family-fun": "Arcade & Family Fun",
    }
    for s in funzone_hours_event_specs(today=date(2026, 7, 1), window_days=1):
        slug = next(t.split(":", 1)[1] for t in s.tags if t.startswith("activity:"))
        assert classify_events_subgroup(s.title, s.tags) == expected[slug]


def test_special_sessions_count_matches_weekdays_in_window() -> None:
    # Over exactly 7 days from a Monday: Saturday glow ×1 = 1 special (the lone
    # remaining session after the Cosmic Bowling sessions were removed 2026-06-26).
    specs = funzone_special_event_specs(today=date(2026, 6, 29), window_days=7)
    assert len(specs) == len(SPECIAL_SESSIONS)
