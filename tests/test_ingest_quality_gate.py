"""Ingest quality gate (2026-07-13): an auto-approve-source row whose resolved
"Where" is a bare street address is HELD pending for review, not published live.

"Bad info can't go live" (Casey): the auto-approve sources (chamber /
go_lake_havasu / river_scene / legistar / lhusd) publish straight to the live
calendar, so a row that would render address-as-venue must land PENDING instead.
Real named venues from the same sources still auto-approve unchanged, so the gate
does not flood the review queue. Reuses the lint battery's ``generic_venue_reason``
so ingest and the nightly audit agree on what a bad venue is.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from app.contrib.event_ingest import _quality_hold, ingest_event_records
from app.contrib.event_record import EventRecord

_ADDRESS_VENUE = "2144 McCulloch Blvd N Lake Havasu City, AZ 86403"
_NAMED_VENUE = "London Bridge Beach"


def _rec(source: str, *, venue: str) -> EventRecord:
    suf = uuid.uuid4().hex[:8]
    d = date(2027, 8, 1)
    return EventRecord(
        source=source,
        title=f"Structured Feed Event {suf}",
        start_date=d,
        start_time=time(18, 0),
        venue_name=venue,
        url=f"https://www.golakehavasu.com/events/evt-{suf}/",
        description="A real event from a structured, re-pullable feed.",
        raw=None,
    )


def test_quality_hold_flags_bare_address() -> None:
    assert _quality_hold(_rec("go_lake_havasu", venue=_ADDRESS_VENUE), source="go_lake_havasu") is not None
    assert _quality_hold(_rec("go_lake_havasu", venue=_NAMED_VENUE), source="go_lake_havasu") is None


def test_quality_hold_exempts_address_venue_feeds() -> None:
    # Schools (lhusd) and civic buildings (legistar) legitimately sit at an
    # address — the address hold must not fire for them (would flood the queue).
    assert _quality_hold(_rec("lhusd", venue=_ADDRESS_VENUE), source="lhusd") is None
    assert _quality_hold(_rec("legistar", venue=_ADDRESS_VENUE), source="legistar") is None


def test_auto_approve_source_address_venue_is_held_pending() -> None:
    rec = _rec("go_lake_havasu", venue=_ADDRESS_VENUE)
    counts = ingest_event_records([rec], source="go_lake_havasu", dry_run=False)
    assert counts.auto_approved == 0
    assert counts.held_low_quality == 1
    assert counts.inserted_pending == 1
    assert counts.errors == 0


def test_auto_approve_source_named_venue_still_publishes() -> None:
    # Regression guard: the gate must not block a clean, named-venue row.
    rec = _rec("go_lake_havasu", venue=_NAMED_VENUE)
    counts = ingest_event_records([rec], source="go_lake_havasu", dry_run=False)
    assert counts.auto_approved == 1
    assert counts.held_low_quality == 0
    assert counts.inserted_pending == 0


def test_dry_run_previews_address_venue_as_held() -> None:
    rec = _rec("river_scene", venue=_ADDRESS_VENUE)
    counts = ingest_event_records([rec], source="river_scene", dry_run=True)
    assert counts.auto_approved == 0
    assert counts.held_low_quality == 1
    assert counts.inserted_pending == 1


def test_address_expected_source_still_publishes() -> None:
    # lhusd (school calendar) events sit at a street address — must still publish.
    rec = _rec("lhusd", venue=_ADDRESS_VENUE)
    counts = ingest_event_records([rec], source="lhusd", dry_run=False)
    assert counts.auto_approved == 1
    assert counts.held_low_quality == 0


def test_aggregator_unaffected_by_quality_gate() -> None:
    # allevents already lands pending; the quality counter must not fire for it
    # (it never would have auto-approved, so it isn't "held" by the gate).
    rec = _rec("allevents", venue=_ADDRESS_VENUE)
    counts = ingest_event_records([rec], source="allevents", dry_run=False)
    assert counts.auto_approved == 0
    assert counts.held_low_quality == 0
    assert counts.inserted_pending == 1
