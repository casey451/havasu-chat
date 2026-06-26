"""Lake Havasu golf scraper (Phase 4) — pure helper coverage.

Covers the curated in-geo-fence venue set, the EntityPayload mapping, the
hours-event specs (tags + window), the Toptracer open-days parse helper, and that
the generated hours titles route to Fitness & Sports → Golf. No DB/network here
(the loader's --dry-run against prod is the gated, operator-run step).
"""

from __future__ import annotations

from datetime import date

from app.contrib.lhc_golf import (
    DEFAULT_CATEGORY_SLUG,
    HOURS_WINDOW_DAYS,
    IN_TOWN_VENUES,
    OUT_OF_AREA_COURSES,
    SOURCE_NAME,
    facility_to_entity_payload,
    golf_facilities,
    golf_hours_event_specs,
    parse_toptracer_open_days,
)
from app.events.activity_taxonomy import classify_class_subgroup


def test_curated_venue_set_is_in_geo_fence() -> None:
    venues = golf_facilities()
    assert venues == list(IN_TOWN_VENUES)
    kinds = {v.venue_kind for v in venues}
    assert kinds == {"course", "range", "simulator"}
    names = {v.name for v in venues}
    # No out-of-area course leaks into the emitted set (Casey: no golf outside LHC).
    assert not (names & set(OUT_OF_AREA_COURSES))
    # The expected in-town anchors are present.
    assert "Lake Havasu Golf Club" in names
    assert "Iron Wolf Top Tracer Range" in names
    assert "Back Nine Golf" in names
    # Golf USA is left directory-only (not a curated sim venue).
    assert "Golf USA" not in names


def test_facility_payload_maps_to_golf_subcategory() -> None:
    v = next(v for v in IN_TOWN_VENUES if v.name == "Golf n' Brews")
    p = facility_to_entity_payload(v)
    assert p.entity_type == "place"
    assert p.category_slug == DEFAULT_CATEGORY_SLUG  # outdoors-parks-trails
    assert p.legacy_category == "golf"
    assert p.source == SOURCE_NAME
    assert "Hours:" in (p.description or "")


def test_hours_specs_carry_canonical_tags_and_window() -> None:
    today = date(2026, 7, 1)
    specs = golf_hours_event_specs(today=today, window_days=HOURS_WINDOW_DAYS)
    assert len(specs) == len(IN_TOWN_VENUES) * HOURS_WINDOW_DAYS
    for s in specs:
        assert s.all_day is True
        assert "activity:golf" in s.tags
        assert "facet:hours" in s.tags
        assert any(t.startswith("venue-kind:") for t in s.tags)
        assert s.source_anchor.startswith("golfhours|")
    # Simulators carry indoor:true; courses do not.
    sim = next(s for s in specs if "Back Nine Golf" in s.location_name)
    assert "indoor:true" in sim.tags and "venue-kind:simulator" in sim.tags
    course = next(s for s in specs if s.location_name == "Lake Havasu Golf Club")
    assert "venue-kind:course" in course.tags and "indoor:true" not in course.tags


def test_hours_titles_route_to_golf_subgroup() -> None:
    for s in golf_hours_event_specs(today=date(2026, 7, 1), window_days=1):
        assert classify_class_subgroup(s.title) == "Golf", s.title


def test_parse_toptracer_open_days() -> None:
    assert parse_toptracer_open_days("Our range is open 6 days/week!") == 6
    assert parse_toptracer_open_days("Open 6 days per week.") == 6
    assert parse_toptracer_open_days("open 7 days a week") == 7
    assert parse_toptracer_open_days("hours posted on the flyer") is None
    assert parse_toptracer_open_days("") is None
