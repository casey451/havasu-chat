"""Minimum-info bar for calendar events/classes (2026-06-23).

Encodes the decision: the genuinely-empty floor (title/date/real venue/link) is
blocked at ingest; a description-less but otherwise-real event is NOT dropped —
its description is backfilled from the source page instead. So
``REQUIRE_DESCRIPTION`` is False for blocking.
"""

from __future__ import annotations

from datetime import date, time

from app.contrib import event_min_info as mi
from app.contrib.event_min_info import (
    class_meets_min_info,
    class_missing_info,
    event_meets_min_info,
    event_missing_info,
)

_FULL = dict(
    title="Summer Concert",
    start_date=date(2026, 7, 1),
    location_name="The Nautical",
    source_url="https://example.com/e/1",
    description="An evening of live music on the lawn.",
)


def test_description_is_not_required_for_blocking():
    # The decision: a real event missing only a description still PASSES the bar
    # (it gets enriched, not dropped).
    assert mi.REQUIRE_DESCRIPTION is False
    no_desc = {**_FULL, "description": ""}
    assert event_missing_info(**no_desc) == []
    assert event_meets_min_info(**no_desc) is True


def test_full_event_passes():
    assert event_missing_info(**_FULL) == []


def test_genuinely_empty_event_is_below_bar():
    # No real venue AND no link = no information → blocked.
    bare = {**_FULL, "location_name": "", "source_url": None, "description": ""}
    missing = event_missing_info(**bare)
    assert "venue" in missing and "link" in missing
    assert event_meets_min_info(**bare) is False


def test_title_as_venue_flagged():
    tav = {**_FULL, "location_name": "Summer Concert"}
    assert "venue(title-as-venue)" in event_missing_info(**tav)


def test_all_day_event_with_zero_time_passes():
    # All-day markets/festivals carry venue+link+desc; a 00:00/None time is fine
    # (the bar never required a specific time for events).
    market = {**_FULL, "title": "Lake Havasu Farmers Market", "description": "Weekly market."}
    assert event_missing_info(**market) == []


def test_short_or_missing_title_below_bar():
    assert "title" in event_missing_info(**{**_FULL, "title": "x"})
    assert "title" in event_missing_info(**{**_FULL, "title": ""})
    assert "date" in event_missing_info(**{**_FULL, "start_date": None})


# --- classes: title + venue + days + time -------------------------------------


def test_class_full_passes():
    assert class_meets_min_info(
        title="Yoga", venue="Amalaya", days=["monday"], start_time=time(9, 0)
    ) is True


def test_class_missing_each_field():
    assert class_missing_info(title="", venue="V", days=["mon"], start_time=time(9, 0)) == ["title"]
    assert class_missing_info(title="Yoga", venue="", days=["mon"], start_time=time(9, 0)) == ["venue"]
    assert class_missing_info(title="Yoga", venue="V", days=[], start_time=time(9, 0)) == ["days"]
    assert class_missing_info(title="Yoga", venue="V", days=["mon"], start_time=None) == ["time"]


# --- ingest guard integration: resolved fields drive the skip ------------------


def test_ingest_guard_uses_resolved_fields():
    """The ingest loop checks the RESOLVED venue/link/description, so a genuinely
    empty record is below the bar while a description-less real one passes."""
    from app.contrib.event_ingest import _description, _http_url_or_none, _location_name
    from app.contrib.event_record import EventRecord

    real = EventRecord(
        source="river_scene_import",
        title="Lake Havasu Farmers Market",
        start_date=date(2026, 7, 1),
        start_time=None,
        end_date=date(2026, 7, 1),
        end_time=None,
        venue_name="Main Street Plaza",
        venue_address=None,
        url="https://riverscenemagazine.com/events/lake-havasu-farmers-market-115",
        description="",  # the legacy gap — backfilled later, NOT a reason to drop
    )
    assert event_missing_info(
        title=real.title,
        start_date=real.start_date,
        location_name=_location_name(real),
        source_url=_http_url_or_none(real.url),
        description=_description(real),
    ) == []

    empty = EventRecord(
        source="x", title="Mystery", start_date=date(2026, 7, 1), start_time=None,
        end_date=None, end_time=None, venue_name="Mystery", venue_address=None,
        url=None, description="",
    )
    missing = event_missing_info(
        title=empty.title,
        start_date=empty.start_date,
        location_name=_location_name(empty),
        source_url=_http_url_or_none(empty.url),
        description=_description(empty),
    )
    # No link, and the venue resolved to the city fallback (title-as-venue dropped)
    # — a no-information row that the guard blocks.
    assert "link" in missing
