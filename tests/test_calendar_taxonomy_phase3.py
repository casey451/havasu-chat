"""Calendar taxonomy rebuild — Phase 3 (2026-06-25): Golf in the taxonomy.

Golf is a first-class Fitness & Sports subgroup (course tee-times, Toptracer
range, indoor simulators, lessons, tournaments). "disc golf" stays a field sport
(Sports & Racing), never ball-golf — guarded by title even though it contains
the word "golf".
"""

from __future__ import annotations

from datetime import date

from app.contrib.event_ingest import _tags
from app.contrib.event_record import EventRecord
from app.events.activity_taxonomy import (
    SUBGROUP_ORDER,
    SUBGROUP_SLUGS,
    activity_bucket,
    activity_slug,
    classify_activity,
    classify_class_subgroup,
)
from app.home.events_views import _occurrence_group_keys


def test_golf_titles_classify_to_golf() -> None:
    for title in (
        "Toptracer Range",
        "Top Tracer — Family Night Golf",
        "Indoor Golf Simulator",
        "Driving Range Open",
        "Tee Time Special",
        "Golf Lessons & Clinics",
    ):
        assert classify_class_subgroup(title) == "Golf", title
        assert activity_slug(title) == "golf", title


def test_golf_in_taxonomy_structures() -> None:
    assert "Golf" in SUBGROUP_ORDER
    assert SUBGROUP_SLUGS["Golf"] == "golf"
    assert activity_bucket("golf") == "classes"


def test_disc_golf_stays_a_field_sport() -> None:
    # The negative guard: "disc golf" contains "golf" but must NOT be ball-golf.
    assert classify_class_subgroup("Disc Golf League") == "Sports & Racing"
    assert classify_class_subgroup("Disc Golf Doubles at the Golf Club") == "Sports & Racing"
    assert classify_activity("Disc Golf League") == "sports-racing"
    # Plain ball golf is unaffected.
    assert classify_activity("Golf Scramble") == "golf"


def test_golf_routes_to_fitness_bucket() -> None:
    # A golf occurrence stays in Fitness & Sports (classes bucket); a disc-golf
    # one also routes to classes (as a field sport), never out to learn/events.
    assert _occurrence_group_keys(
        "classes", title="Toptracer Family Night Golf", venue="Iron Wolf",
        activity=None, tags=None, is_family=False, is_senior=False,
    ) == ["classes"]
    assert _occurrence_group_keys(
        "classes", title="Disc Golf League", venue=None, activity=None,
        tags=None, is_family=False, is_senior=False,
    ) == ["classes"]


def test_ingest_stamps_activity_golf() -> None:
    rec = EventRecord(
        source="test", title="Toptracer Range — Family Night Golf",
        start_date=date(2026, 7, 1), venue_name="Iron Wolf Golf & Country Club",
        url="https://example.com/g", description="Range night.", tags=[],
    )
    tags = _tags(rec)
    assert "activity:golf" in tags
    # disc golf must NOT get activity:golf.
    disc = EventRecord(
        source="test", title="Disc Golf League Night", start_date=date(2026, 7, 1),
        venue_name="Lake Havasu Golf Club", url="https://example.com/d",
        description="Field sport.", tags=[],
    )
    dtags = _tags(disc)
    assert "activity:sports-racing" in dtags
    assert "activity:golf" not in dtags
