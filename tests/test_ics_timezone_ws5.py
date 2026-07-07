"""WS5 / §14.2 item 3 — per-event ICS carries America/Phoenix TZID + nightly RRULE.

The 2026-07-06 audit (B5) found the Rainforest Rush camp ICS exported as a single
96-hour block with NO timezone:

    DTSTART:20260706T180000
    DTEND:20260710T180000        <- 4-day block, floating local time

Floating local time is interpreted in the *viewer's* zone, so an out-of-state
subscriber saw the wrong hour. The fix (app/api/routes/calendar_feed.py):
  * timed DTSTART/DTEND carry ``;TZID=America/Phoenix`` and the calendar embeds a
    VTIMEZONE (Arizona = MST year-round, no DST);
  * a recurring event's per-occurrence DTEND is SAME-DAY (``end_date`` is the
    series end, covered by the RRULE's UNTIL) instead of spanning the whole run.

The remaining half of B5 — the Rainforest Rush row is *stored* as a 4-day span
with no RRULE, so it still emits one block — is a data/ingest fix (re-store as a
nightly RRULE) that needs a gated backfill; it is documented as xfail here.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from dateutil.rrule import rrulestr

from app.api.routes.calendar_feed import build_single_event_ics
from app.db.models import Event


def _event(**kw) -> Event:
    base = dict(
        id="ev-ws5",
        title="Rainforest Rush Kids Camp 2026",
        normalized_title="rainforest rush kids camp 2026",
        location_name="Abundant Grace Church",
        description="Nightly camp",
        event_url="https://example.com/register",
        tags=[],
        status="live",
        source="test-ws5",
        date=date(2026, 7, 6),
        start_time=time(18, 0),
        end_time=time(20, 0),
        end_date=None,
        is_recurring=False,
        rrule=None,
    )
    base.update(kw)
    return Event(**base)


def _lines(ics: str) -> list[str]:
    return ics.split("\r\n")


def test_timed_event_carries_phoenix_tzid_and_vtimezone() -> None:
    ics = build_single_event_ics(_event())
    assert "BEGIN:VTIMEZONE" in ics
    assert "TZID:America/Phoenix" in ics
    assert "TZOFFSETTO:-0700" in ics  # MST, no DST
    assert "DTSTART;TZID=America/Phoenix:20260706T180000" in _lines(ics)
    assert "DTEND;TZID=America/Phoenix:20260706T200000" in _lines(ics)
    # Never the old floating form.
    assert "DTSTART:20260706T180000" not in ics


def test_nightly_rrule_event_is_per_day_not_a_multiday_block() -> None:
    ev = _event(
        end_date=date(2026, 7, 10),
        is_recurring=True,
        rrule="FREQ=DAILY;UNTIL=20260711T065959Z",
    )
    ics = build_single_event_ics(ev)
    lines = _lines(ics)
    # Per-occurrence DTEND is SAME DAY as DTSTART (20260706), NOT the 20260710 span.
    assert "DTSTART;TZID=America/Phoenix:20260706T180000" in lines
    assert "DTEND;TZID=America/Phoenix:20260706T200000" in lines
    assert "DTEND;TZID=America/Phoenix:20260710T200000" not in lines
    assert "RRULE:FREQ=DAILY;UNTIL=20260711T065959Z" in lines

    # The RRULE expands to exactly the 5 evenings Jul 6-10 (Google Calendar import).
    # A UTC UNTIL (…Z) requires a tz-aware DTSTART per RFC 5545 §3.3.10 — which is
    # exactly the Phoenix-local start the TZID encodes.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    start = datetime(2026, 7, 6, 18, 0, tzinfo=ZoneInfo("America/Phoenix"))
    occurrences = list(rrulestr("FREQ=DAILY;UNTIL=20260711T065959Z", dtstart=start))
    assert [d.date() for d in occurrences] == [date(2026, 7, d) for d in range(6, 11)]


def test_all_day_event_stays_value_date_without_tzid() -> None:
    ev = _event(start_time=time(0, 0), end_time=None)
    ics = build_single_event_ics(ev)
    assert "DTSTART;VALUE=DATE:20260706" in ics
    assert "DTSTART;TZID" not in ics  # all-day carries no time zone


def test_structural_validity_begin_end_balance() -> None:
    ics = build_single_event_ics(_event())
    for tag in ("VCALENDAR", "VTIMEZONE", "VEVENT"):
        assert ics.count(f"BEGIN:{tag}") == ics.count(f"END:{tag}") == 1
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.rstrip().endswith("END:VCALENDAR")
    assert ics.endswith("\r\n")


@pytest.mark.xfail(reason="B5 data half: the camp is stored as a 4-day span (no "
                          "RRULE); re-storing it as a nightly RRULE needs a gated "
                          "ingest fix + backfill (WS5 next step).", strict=True)
def test_span_stored_camp_should_become_nightly_rrule() -> None:
    # As currently STORED (date=Jul6, end_date=Jul10, no rrule) the builder can't
    # know it's nightly, so it still emits a multi-day DTEND. Documents the target.
    ev = _event(end_date=date(2026, 7, 10), is_recurring=False, rrule=None)
    ics = build_single_event_ics(ev)
    assert "RRULE:FREQ=DAILY" in ics
    assert "DTEND;TZID=America/Phoenix:20260710T200000" not in ics
