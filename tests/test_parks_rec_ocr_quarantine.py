"""parks_rec_ocr_quarantine: hold every live P&R OCR (#cal) event, leave WebTrac
and other sources alone; dry-run writes nothing; undo restores."""

from __future__ import annotations

import uuid
from datetime import date, time

from app.db.database import SessionLocal
from app.db.models import Event
from scripts.parks_rec_ocr_quarantine_2026_07_13 import _apply, _ocr_events, _undo

_CAL_URL = "https://www.lhcaz.gov/185/Parks-Recreation#cal|2026-07-20|line-dancing|10-00"
_WEBTRAC_URL = "https://register.lhcaz.gov/webtrac/web/iteminfo.html?Module=AR&FMID=88486410"


def _ev(url: str, *, status: str = "live", source: str = "parks_rec_calendar") -> Event:
    t = f"PR {uuid.uuid4().hex[:6]}"
    return Event(
        title=t, normalized_title=t.lower(), date=date(2026, 7, 20),
        start_time=time(10, 0), location_name="Lake Havasu City Parks & Recreation",
        location_normalized="lake havasu city parks & recreation", description="d",
        status=status, source=source, event_url=url,
    )


def test_selects_only_live_ocr_events() -> None:
    with SessionLocal() as db:
        vis = _ev(_CAL_URL)
        wt = _ev(_WEBTRAC_URL, source="webtrac")
        other = _ev("https://allevents.in/x", source="allevents")
        held = _ev(_CAL_URL, status="pending_review")
        for e in (vis, wt, other, held):
            db.add(e)
        db.commit()
        ids = {vis.id, wt.id, other.id, held.id}
        try:
            selected = {e.id for e in _ocr_events(db)}
            assert vis.id in selected            # live OCR row → selected
            assert wt.id not in selected         # WebTrac → left alone
            assert other.id not in selected      # other source → left alone
            assert held.id not in selected       # already held → skipped
        finally:
            for i in ids:
                row = db.get(Event, i)
                if row:
                    db.delete(row)
            db.commit()


def test_dry_run_writes_nothing_then_apply_and_undo(tmp_path) -> None:
    with SessionLocal() as db:
        vis = _ev(_CAL_URL)
        db.add(vis)
        db.commit()
        vid = vis.id
        undo = str(tmp_path / "undo.json")
        try:
            _apply(db, apply=False, undo_json=None)
            assert db.get(Event, vid).status == "live"  # dry-run: unchanged

            _apply(db, apply=True, undo_json=undo)
            assert db.get(Event, vid).status == "pending_review"

            _undo(db, undo_from=undo, apply=True)
            assert db.get(Event, vid).status == "live"  # restored
        finally:
            row = db.get(Event, vid)
            if row:
                db.delete(row)
                db.commit()
