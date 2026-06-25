"""Vision sources auto-publish CLEAN rows; flagged ones stay PENDING (2026-06-24).

Casey's decision: the Parks & Rec calendar/flyer + senior-center flyer vision
scrapers should auto-populate the live calendar — but ONLY the guard-passing rows.
A row the vision engine held (confidence below the §6 threshold or a self-check
demotion, stamped on ``EventRecord.raw['should_hide']``) or whose listed weekday
contradicts its body must land pending for /admin review. Ambiguous reconciles and
cross-source duplicates are already held upstream.

These exercise ``ingest_event_records`` against the test DB (it opens its own
``SessionLocal``); no live HTTP/LLM. Titles/dates are uuid-unique so rows don't
collide across tests in a shared DB.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from app.contrib.event_ingest import ingest_event_records
from app.contrib.event_record import EventRecord

DEFAULT_VENUE = "Lake Havasu City Parks & Recreation"
_WD_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _clean_rec(
    source: str,
    *,
    should_hide: bool = False,
    confidence: float = 0.95,
    description: str = "Drop-in play for tots. Source: LHC Parks & Rec monthly calendar.",
    when: date | None = None,
    venue: str = DEFAULT_VENUE,
) -> EventRecord:
    """A vision EventRecord shaped like the adapters' ``row_to_event_record`` output."""
    suf = uuid.uuid4().hex[:8]
    title = f"Tiny Tots Move & Groove {suf}"
    d = when or date(2027, 7, 8)
    return EventRecord(
        source=source,
        title=title,
        start_date=d,
        start_time=time(10, 0),
        venue_name=venue,
        url=f"https://www.lhcaz.gov/185/Parks-Recreation#cal|{d.isoformat()}|tiny-{suf}|10-00",
        description=description,
        raw={"should_hide": should_hide, "confidence": confidence, "kind": "calendar"},
    )


VISION_SOURCES = ("parks_rec_calendar", "parks_rec_flyers", "senior_center_flyers")


# --------------------------------------------------------------------------- #
# Clean rows auto-approve (one per vision source).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("source", VISION_SOURCES)
def test_clean_vision_row_auto_approves(source: str) -> None:
    counts = ingest_event_records([_clean_rec(source)], source=source, dry_run=False)
    assert counts.auto_approved == 1
    assert counts.inserted_pending == 0
    assert counts.errors == 0


# --------------------------------------------------------------------------- #
# Held / flagged rows stay PENDING.
# --------------------------------------------------------------------------- #
def test_low_confidence_row_held_pending() -> None:
    """A row the engine flagged should_hide (confidence < threshold) is NOT live."""
    counts = ingest_event_records(
        [_clean_rec("parks_rec_calendar", should_hide=True, confidence=0.40)],
        source="parks_rec_calendar",
        dry_run=False,
    )
    assert counts.auto_approved == 0
    assert counts.inserted_pending == 1


def test_self_check_demoted_row_held_pending() -> None:
    """should_hide is also set by the self-check demotion path (confidence high)."""
    counts = ingest_event_records(
        [_clean_rec("senior_center_flyers", should_hide=True, confidence=0.91)],
        source="senior_center_flyers",
        dry_run=False,
    )
    assert counts.auto_approved == 0
    assert counts.inserted_pending == 1


def test_weekday_mismatch_row_held_pending() -> None:
    """A listed-weekday-vs-body contradiction holds the row pending (flagged)."""
    d = date(2027, 7, 9)
    a, b = _WD_NAMES[(d.weekday() + 1) % 7], _WD_NAMES[(d.weekday() + 2) % 7]
    rec = _clean_rec(
        "parks_rec_flyers",
        description=f"Meets {a}s and {b}s at the rec center. Source: LHC Parks & Rec flyer.",
        when=d,
    )
    counts = ingest_event_records([rec], source="parks_rec_flyers", dry_run=False)
    assert counts.flagged_weekday_mismatch == 1
    assert counts.auto_approved == 0
    assert counts.inserted_pending == 1


# --------------------------------------------------------------------------- #
# Non-vision sources are NOT gated by the vision guards (no behavior change).
# --------------------------------------------------------------------------- #
def test_non_vision_aggregator_still_pending() -> None:
    """allevents is not in the registry -> pending, regardless of the vision gate."""
    rec = _clean_rec("allevents")
    counts = ingest_event_records([rec], source="allevents", dry_run=False)
    assert counts.auto_approved == 0
    assert counts.inserted_pending == 1


def test_non_vision_civic_still_auto_approves() -> None:
    """legistar is a civic auto-approve source and carries no should_hide -> live.

    Guards the regression risk that the new gate could block a non-vision source."""
    rec = _clean_rec("legistar")
    rec.raw = None  # civic records carry no vision raw payload
    counts = ingest_event_records([rec], source="legistar", dry_run=False)
    assert counts.auto_approved == 1
    assert counts.inserted_pending == 0


# --------------------------------------------------------------------------- #
# Dry-run honestly previews the --apply decision.
# --------------------------------------------------------------------------- #
def test_dry_run_previews_clean_row_as_auto_approved() -> None:
    counts = ingest_event_records(
        [_clean_rec("parks_rec_calendar")], source="parks_rec_calendar", dry_run=True
    )
    assert counts.auto_approved == 1
    assert counts.inserted_pending == 0


def test_dry_run_previews_held_row_as_pending() -> None:
    counts = ingest_event_records(
        [_clean_rec("parks_rec_calendar", should_hide=True, confidence=0.40)],
        source="parks_rec_calendar",
        dry_run=True,
    )
    assert counts.auto_approved == 0
    assert counts.inserted_pending == 1
