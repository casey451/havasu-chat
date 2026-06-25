"""One-time backfill: auto-approve already-PENDING CLEAN vision events (2026-06-25).

#514 auto-publishes CLEAN vision rows on FUTURE ingest; this backfill applies the
SAME gate to rows that already landed pending. These exercise the reusable decision
``backfill_pending_vision_contribution`` (and the script's selection query) against
the test DB.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, time

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
# Clean rows approve through the canonical path.
# --------------------------------------------------------------------------- #
def test_clean_pending_calendar_row_approves() -> None:
    with SessionLocal() as db:
        c = _pending(db, "parks_rec_calendar", when=date(2027, 7, 6))
        r = backfill_pending_vision_contribution(db, c, dry_run=False)
        assert r.action == "approve"
        assert r.reason == "approved"
        assert r.event_id is not None
        db.refresh(c)
        assert c.status == "approved"
        assert c.created_event_id == r.event_id


def test_dry_run_would_approve_writes_nothing() -> None:
    with SessionLocal() as db:
        c = _pending(db, "parks_rec_flyers", when=date(2027, 7, 7))
        r = backfill_pending_vision_contribution(db, c, dry_run=True)
        assert r.action == "approve"
        assert r.reason == "would_auto_approve"
        assert r.event_id is None
        db.refresh(c)
        assert c.status == "pending"  # dry-run wrote nothing


# --------------------------------------------------------------------------- #
# Flagged rows stay pending.
# --------------------------------------------------------------------------- #
def test_weekday_mismatch_row_held() -> None:
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


def test_reconcile_duplicate_against_live_event_held() -> None:
    """A pending row that now matches a live event is held (never double-booked)."""
    d = date(2027, 7, 12)
    title = f"Family Movie Night {uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        first = _pending(db, "parks_rec_calendar", when=d, title=title)
        r1 = backfill_pending_vision_contribution(db, first, dry_run=False)
        assert r1.action == "approve"  # creates the live event

        # A second pending row for the same title/date/venue/time now duplicates it.
        dup = _pending(db, "parks_rec_calendar", when=d, title=title)
        r2 = backfill_pending_vision_contribution(db, dup, dry_run=False)
        assert r2.action == "hold"
        assert r2.reason.startswith("reconcile:")
        db.refresh(dup)
        assert dup.status == "pending"


# --------------------------------------------------------------------------- #
# Non-vision rows untouched; idempotent re-run.
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


def test_rerun_after_apply_approves_nothing() -> None:
    with SessionLocal() as db:
        c = _pending(db, "senior_center_flyers", when=date(2027, 7, 14))
        r1 = backfill_pending_vision_contribution(db, c, dry_run=False)
        assert r1.action == "approve"
        db.refresh(c)
        # Re-running sees an already-approved (non-pending) row -> no-op hold.
        r2 = backfill_pending_vision_contribution(db, c, dry_run=False)
        assert r2.action == "hold"
        assert "not pending" in r2.reason


# --------------------------------------------------------------------------- #
# Script: selection query + dry-run CLI.
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


def test_script_dry_run_reports_and_writes_nothing(capsys) -> None:
    import scripts.backfill_vision_auto_approve as bcli

    with SessionLocal() as db:
        c = _pending(db, "parks_rec_calendar", when=date(2027, 7, 16))

    rc = bcli.main([])  # dry-run (no --apply)
    assert rc == 0
    out = capsys.readouterr().out
    assert "backfill vision pending -> live" in out
    assert re.search(r"would_auto_approve\s+[1-9]", out)
    assert "(dry run -- no database writes)" in out

    with SessionLocal() as db:
        fresh = cs.get_contribution(db, c.id)
        assert fresh is not None and fresh.status == "pending"  # nothing written
