"""Quarantine ALL live Parks & Rec vision-OCR calendar events (2026-07-13).

Casey: the P&R monthly-calendar OCR is unreliable — live events carry garbled
titles ("Kids & Clay Kids - Pickleball"), wrong times (OCR "Back to School" at
10:00/15:00 vs WebTrac's real 17:15), and scattered series. Pull the ENTIRE OCR
source off the public calendar now (reversible), pending a reliable rebuild
(WebTrac for the registerable programs it covers; a fixed extractor for the free
drop-in activities WebTrac doesn't carry).

Unlike ``parks_rec_quarantine_2026_07_08.py`` (which held only the lint-flagged
subset), this holds EVERY live OCR row — identified by the synthetic
``…/185/Parks-Recreation#cal|…`` anchor that only the vision calendar scraper
produces. WebTrac events (``register.lhcaz.gov/webtrac``) are NOT matched, so the
verified-correct registration data stays live.

Rows move ``status="live" -> "pending_review"`` (out of the public calendar/ICS,
into the /admin queue). Idempotent (already-held rows are skipped) and fully
reversible via the undo snapshot.

PROD DB WRITE — dry-run default; ``--apply`` writes. The repo .env DATABASE_URL is
Railway's internal host, so the live run happens in CI (a gated apply workflow).

    python scripts/parks_rec_ocr_quarantine_2026_07_13.py                      # DRY RUN
    python scripts/parks_rec_ocr_quarantine_2026_07_13.py --apply --undo-json undo.json
    python scripts/parks_rec_ocr_quarantine_2026_07_13.py --undo-from undo.json --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import or_, select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_HELD_STATUS = "pending_review"
_LIVE = "live"
# The synthetic anchor ONLY the P&R vision calendar scraper emits. WebTrac rows
# (register.lhcaz.gov/webtrac/…) never carry it, so they are untouched.
_CAL = "%/185/Parks-Recreation#cal|%"


def _ocr_events(db):
    stmt = (
        select(Event)
        .where(
            Event.status == _LIVE,
            or_(Event.event_url.like(_CAL), Event.source_url.like(_CAL)),
        )
        .order_by(Event.date, Event.id)
    )
    return list(db.scalars(stmt).all())


def _apply(db, *, apply: bool, undo_json: str | None) -> int:
    events = _ocr_events(db)
    by_venue: Counter = Counter()
    snapshot: list[dict] = []
    for ev in events:
        by_venue[ev.location_name] += 1
        snapshot.append({
            "id": ev.id, "old_status": ev.status,
            "date": ev.date.isoformat() if ev.date else "",
            "title": ev.title,
        })
        if apply:
            ev.status = _HELD_STATUS
    if apply:
        db.commit()

    print(f"live P&R OCR events (#cal anchor): {len(events)}")
    verb = "QUARANTINED" if apply else "would quarantine"
    print(f"{verb} (status {_LIVE} -> {_HELD_STATUS}): {len(events)}")
    print("  by venue:")
    for venue, n in sorted(by_venue.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        print(f"    {n:>3}  {venue!r}")
    print("\n  sample (first 25) leaving the public calendar:")
    for s in snapshot[:25]:
        print(f"    {s['date']} {s['title'][:48]!r}")

    if apply:
        if undo_json:
            Path(undo_json).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            print(f"\nAPPLIED. undo snapshot -> {undo_json} ({len(snapshot)} rows)")
        else:
            print(f"\nAPPLIED {len(snapshot)} rows.")
    else:
        print("\nDRY RUN — no DB writes. Re-run with --apply (prod-data gate).")
    return len(events)


def _undo(db, *, undo_from: str, apply: bool) -> int:
    rows = json.loads(Path(undo_from).read_text(encoding="utf-8"))
    print(f"restoring {len(rows)} row(s) from {undo_from}:")
    n = 0
    for s in rows:
        ev = db.get(Event, s["id"])
        if ev is None:
            print(f"  MISSING {s['id']} — skip")
            continue
        if apply:
            ev.status = s["old_status"]
        n += 1
    if apply:
        db.commit()
        print(f"APPLIED: restored {n} row(s).")
    else:
        print("DRY RUN: no writes.")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Quarantine ALL live P&R OCR calendar events (gated).")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--undo-json", help="on apply, write an undo snapshot to this path")
    p.add_argument("--undo-from", help="restore status from a prior undo snapshot")
    args = p.parse_args(argv)
    with SessionLocal() as db:
        if args.undo_from:
            _undo(db, undo_from=args.undo_from, apply=args.apply)
        else:
            _apply(db, apply=args.apply, undo_json=args.undo_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
