"""Backfill of PENDING vision events is NEUTRALIZED by the review gate (2026-06-28).

The backfill script (``scripts/backfill_vision_auto_approve.py``) once promoted
clean pending Parks & Rec / senior-center vision rows to live, reusing the
production decision ``backfill_pending_vision_contribution``. The
sustainable-sourcing decision removed the three vision sources from the
auto-approve registry, so that shared decision now holds EVERY vision row as
``not registry-eligible`` -- the backfill promotes nothing. These tests lock that
invariant in: even the old promotion path can no longer publish a vision row;
``/admin`` review is the only route. (The vision *guards* -- weekday-mismatch,
should_hide -- still fire first, so their precedence is preserved.)
"""

from __future__ import annotations

import re
import uuid
from datetime import date, time

import pytest

from app.contrib.event_ingest import (
    backfill_pending_vision_contribution,
    vision_record_should_hold,
)
from app.contrib.event_record import EventRecord
from app.db import contribution_store as cs
from app.db.database import SessionLocal
from app.schemas.contribution import ContributionCreate

PARKS_VENUE = "Lake Havasu City Parks & Recreation"
_WD = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
VISION_SOURCES = ("parks_rec_calendar", "parks_rec_flyers", "senior_center_flyers")


def _pending(
    db,
    source: str,
    *,
    when: date,
    title: str | None = None,
    notes: str = "Drop-in play for tots. Source: LHC Parks & Rec monthly calendar.",
    start_time: time = time(10, 0),
):
    suf = uuid.uuid4().hex[:8]
    title = title or f"Tiny Tots Move & Groove {suf}"
    syn = f"https://www.lhcaz.gov/185/Parks-Recreation#cal|{when.isoformat()}|t-{suf}|10-00"
    return cs.create_contribution(
        db,
        ContributionCreate(
            entity_type="event",
            submission_name=title,
            submission_url="https://www.lhcaz.gov/185/Parks-Recreation",
            source_url=syn,
            submission_notes=notes,
            event_date=when,
            event_time_start=start_time,
            source=source,  # type: ignore[arg-type]
        ),
    )


# --------------------------------------------------------------------------- #
# Clean vision rows are now HELD (not registry-eligible) -- nothing publishes.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("source", VISION_SOURCES)
def test_clean_pending_vision_row_held_not_eligible(source: str) -> None:
    with SessionLocal() as db:
        c = _pending(db, source, when=date(2027, 7, 6))
        r = backfill_pending_vision_contribution(db, c, dry_run=False)
        assert r.action == "hold"
        assert r.reason == "not registry-eligible"
        assert r.event_id is None
        db.refresh(c)
        assert c.status == "pending"  # stays in the review queue
        assert c.created_event_id is None


def test_dry_run_holds_and_writes_nothing() -> None:
    with SessionLocal() as db:
        c = _pending(db, "parks_rec_flyers", when=date(2027, 7, 7))
        r = backfill_pending_vision_contribution(db, c, dry_run=True)
        assert r.action == "hold"
        assert r.reason == "not registry-eligible"
        db.refresh(c)
        assert c.status == "pending"  # dry-run wrote nothing


# --------------------------------------------------------------------------- #
# The per-row guards still fire FIRST (precedence preserved over the gate).
# --------------------------------------------------------------------------- #
def test_weekday_mismatch_row_held_with_guard_reason() -> None:
    """A weekday-mismatch row is held by its guard (before the registry gate)."""
    d = date(2027, 7, 9)
    a, b = _WD[(d.weekday() + 1) % 7], _WD[(d.weekday() + 2) % 7]
    with SessionLocal() as db:
        c = _pending(
            db,
            "parks_rec_calendar",
            when=d,
            notes=f"Meets {a}s and {b}s. Source: LHC Parks & Rec flyer.",
        )
        r = backfill_pending_vision_contribution(db, c, dry_run=False)
        assert r.action == "hold"
        assert r.reason == "weekday_mismatch"
        db.refresh(c)
        assert c.status == "pending"


def test_should_hide_gate_holds_via_reused_predicate() -> None:
    """should_hide isn't persisted on the contribution, so it's exercised at the
    gate level: a record the engine held must be blocked; a clean one must not."""
    held = EventRecord(
        source="parks_rec_calendar",
        title="Held Row",
        start_date=date(2027, 7, 10),
        start_time=time(9, 0),
        raw={"should_hide": True, "confidence": 0.4},
    )
    clean = EventRecord(
        source="parks_rec_calendar",
        title="Clean Row",
        start_date=date(2027, 7, 10),
        start_time=time(9, 0),
        raw={"should_hide": False, "confidence": 0.95},
    )
    assert vision_record_should_hold(held, source="parks_rec_calendar") is True
    assert vision_record_should_hold(clean, source="parks_rec_calendar") is False


# --------------------------------------------------------------------------- #
# Non-vision rows untouched; idempotent skip on non-pending.
# --------------------------------------------------------------------------- #
def test_non_vision_pending_untouched() -> None:
    with SessionLocal() as db:
        c = _pending(db, "allevents", when=date(2027, 7, 13))
        r = backfill_pending_vision_contribution(db, c, dry_run=False)
        assert r.action == "hold"
        assert r.reason == "not a vision event"
        db.refresh(c)
        assert c.status == "pending"
        assert c.created_event_id is None


def test_non_pending_row_is_idempotent_skip() -> None:
    with SessionLocal() as db:
        c = _pending(db, "senior_center_flyers", when=date(2027, 7, 14))
        c.status = "approved"  # simulate an already-resolved row
        db.add(c)
        db.commit()
        r = backfill_pending_vision_contribution(db, c, dry_run=False)
        assert r.action == "hold"
        assert "not pending" in r.reason


# --------------------------------------------------------------------------- #
# Script: selection query + dry-run CLI (promotes nothing).
# --------------------------------------------------------------------------- #
def test_select_pending_vision_excludes_non_vision() -> None:
    import scripts.backfill_vision_auto_approve as bcli

    with SessionLocal() as db:
        vis = _pending(db, "parks_rec_calendar", when=date(2027, 7, 15))
        non = _pending(db, "allevents", when=date(2027, 7, 15))
        selected = bcli._select_pending_vision(db, limit=None)
        ids = {c.id for c in selected}
        assert vis.id in ids
        assert non.id not in ids
        assert all(c.source != "allevents" for c in selected)


def test_script_dry_run_promotes_nothing(capsys) -> None:
    import scripts.backfill_vision_auto_approve as bcli

    with SessionLocal() as db:
        c = _pending(db, "parks_rec_calendar", when=date(2027, 7, 16))

    rc = bcli.main([])  # dry-run (no --apply)
    assert rc == 0
    out = capsys.readouterr().out
    assert "backfill vision pending -> live" in out
    # Nothing would auto-approve; the held breakdown names the registry gate.
    assert re.search(r"would_auto_approve\s+0", out)
    assert "not registry-eligible" in out
    assert "(dry run -- no database writes)" in out

    with SessionLocal() as db:
        fresh = cs.get_contribution(db, c.id)
        assert fresh is not None and fresh.status == "pending"  # nothing written
