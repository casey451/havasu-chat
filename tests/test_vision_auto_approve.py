"""Vision/flyer sources are review-gated: every row lands PENDING (2026-06-28).

Sustainable-sourcing decision (Casey): the events catalog only auto-publishes
data from STRUCTURED, re-pullable feeds (city CivicPlus iCal/RSS, go_lake_havasu
JSON-LD, chamber, legistar, lhusd). The Parks & Rec calendar/flyer and
senior-center flyer VISION scrapers used to auto-publish their "clean" rows
(2026-06-24), but flyer OCR has no re-pullable ground truth -- it produced
cross-contaminated craft/fishing descriptions and an unverifiable date. So the
three vision sources were removed from ``_DEFAULT_AUTO_APPROVE_EVENT_SOURCES``:
they keep ingesting (nothing lost) but now queue for human review, like the
``allevents`` aggregator.

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
# Vision rows now land PENDING for review -- even the clean ones.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("source", VISION_SOURCES)
def test_clean_vision_row_lands_pending(source: str) -> None:
    """The behavior flip: a guard-passing vision row no longer auto-publishes."""
    counts = ingest_event_records([_clean_rec(source)], source=source, dry_run=False)
    assert counts.auto_approved == 0
    assert counts.inserted_pending == 1
    assert counts.errors == 0


# --------------------------------------------------------------------------- #
# Flagged / held rows also stay PENDING (the per-row guards are now redundant
# with the review gate, but must never flip a held row to auto-approved).
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
    """A listed-weekday-vs-body contradiction still holds the row pending."""
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
# Non-vision sources are unaffected by the registry change.
# --------------------------------------------------------------------------- #
def test_non_vision_aggregator_still_pending() -> None:
    """allevents is not in the registry -> pending (unchanged)."""
    rec = _clean_rec("allevents")
    counts = ingest_event_records([rec], source="allevents", dry_run=False)
    assert counts.auto_approved == 0
    assert counts.inserted_pending == 1


def test_non_vision_civic_still_auto_approves() -> None:
    """legistar is a structured auto-approve source -> live (unchanged).

    Guards the regression risk that the registry edit could block a structured
    source by accident."""
    rec = _clean_rec("legistar")
    rec.raw = None  # civic records carry no vision raw payload
    counts = ingest_event_records([rec], source="legistar", dry_run=False)
    assert counts.auto_approved == 1
    assert counts.inserted_pending == 0


# --------------------------------------------------------------------------- #
# Dry-run honestly previews the new --apply decision (pending).
# --------------------------------------------------------------------------- #
def test_dry_run_previews_clean_vision_row_as_pending() -> None:
    counts = ingest_event_records(
        [_clean_rec("parks_rec_calendar")], source="parks_rec_calendar", dry_run=True
    )
    assert counts.auto_approved == 0
    assert counts.inserted_pending == 1


def test_dry_run_previews_held_row_as_pending() -> None:
    counts = ingest_event_records(
        [_clean_rec("parks_rec_calendar", should_hide=True, confidence=0.40)],
        source="parks_rec_calendar",
        dry_run=True,
    )
    assert counts.auto_approved == 0
    assert counts.inserted_pending == 1
