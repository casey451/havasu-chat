"""iCal datetime normalization — UTC ``Z`` and ``TZID=…`` values become naive
Lake Havasu wall time (the convention every scraper consumer relies on).

Fixed in the 2026-06-10 cleanup pass: previously the ``tzid`` parameter was
parsed but ignored and ``Z``-suffixed UTC values were returned as naive UTC
wall time — a +7h error for genuinely-UTC feeds. Both live feeds (Trumba,
CivicEngage) emit ``TZID=America/Phoenix``, for which conversion is the
identity, so those feeds are unaffected.
"""

from __future__ import annotations

from datetime import datetime

from app.events.scrapers.ical_parse import _parse_ical_datetime, parse_ical_events


def test_z_suffix_converts_utc_to_local_wall_time() -> None:
    # 19:00 UTC == 12:00 America/Phoenix (UTC-7, no DST).
    dt = _parse_ical_datetime("20260610T190000Z")
    assert dt == datetime(2026, 6, 10, 12, 0, 0)
    assert dt.tzinfo is None


def test_tzid_phoenix_is_identity() -> None:
    # The live Trumba/CivicEngage feeds' TZID — must not shift.
    dt = _parse_ical_datetime("20260615T100000", tzid="America/Phoenix")
    assert dt == datetime(2026, 6, 15, 10, 0, 0)
    assert dt.tzinfo is None


def test_tzid_other_zone_converts_to_local() -> None:
    # 10:00 New York (EDT, UTC-4 in June) == 07:00 Phoenix.
    dt = _parse_ical_datetime("20260615T100000", tzid="America/New_York")
    assert dt == datetime(2026, 6, 15, 7, 0, 0)
    assert dt.tzinfo is None


def test_unknown_tzid_falls_back_to_assume_local() -> None:
    dt = _parse_ical_datetime("20260615T100000", tzid="Not/A_Zone")
    assert dt == datetime(2026, 6, 15, 10, 0, 0)
    assert dt.tzinfo is None


def test_floating_time_and_date_only_unchanged() -> None:
    assert _parse_ical_datetime("20260609T180000") == datetime(2026, 6, 9, 18, 0, 0)
    assert _parse_ical_datetime("20260601") == datetime(2026, 6, 1, 0, 0, 0)


def test_vevent_dtstart_tzid_applied_end_to_end() -> None:
    text = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\n"
        "SUMMARY:UTC Stamped Event\r\n"
        "UID:utc-1\r\n"
        "DTSTART:20260610T190000Z\r\n"
        "DTEND:20260610T200000Z\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "SUMMARY:Phoenix Event\r\n"
        "UID:phx-1\r\n"
        "DTSTART;TZID=America/Phoenix:20260615T100000\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    events = {e.uid: e for e in parse_ical_events(text)}
    assert events["utc-1"].start == datetime(2026, 6, 10, 12, 0, 0)
    assert events["utc-1"].end == datetime(2026, 6, 10, 13, 0, 0)
    assert events["phx-1"].start == datetime(2026, 6, 15, 10, 0, 0)
