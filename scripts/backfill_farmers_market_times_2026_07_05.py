"""3D Op 2 — backfill Lake Havasu Farmers Market times to 08:00–12:00.

The market runs every **Saturday 8 AM – 12 PM**, but the River Scene ingest
dropped the time on most rows (the old parser couldn't read the "8 AM – 12 PM"
range, fixed forward in PR #710), leaving them TBD / bare-00:00. This sets the
known Saturday schedule on the live FM rows.

Scope guard: ONLY live rows whose ``normalized_title`` is exactly
``lake havasu farmers market`` AND whose date is a **Saturday** (the market day)
are touched — a non-Saturday row would be a different instance and is skipped
(logged). Rows already reading 08:00–12:00 are left alone.

DRY-RUN by default (no writes); ``--apply`` writes and emits an undo CSV.

    .venv\\Scripts\\python.exe scripts\\backfill_farmers_market_times_2026_07_05.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\backfill_farmers_market_times_2026_07_05.py --apply    # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import time

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Event

_NORM = "lake havasu farmers market"
_START = time(8, 0)
_END = time(12, 0)
_SATURDAY = 5
_UNDO_CSV = "backfill_farmers_market_times_undo_2026-07-05.csv"


def _needs_backfill(e: Event) -> bool:
    return e.start_time != _START or e.end_time != _END


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Farmers Market times.")
    parser.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(Event)
                .where(Event.normalized_title == _NORM)
                .where(Event.status == "live")
            ).all()
        )
        targets: list[Event] = []
        skipped_nonsat = 0
        for e in rows:
            if e.date.weekday() != _SATURDAY:
                skipped_nonsat += 1
                print(f"  SKIP non-Saturday {e.date} id={str(e.id)[:8]}")
                continue
            if _needs_backfill(e):
                targets.append(e)

        print(
            f"live FM rows={len(rows)}  non-Saturday skipped={skipped_nonsat}  "
            f"would set 08:00-12:00 on={len(targets)}"
        )
        for e in targets[:5]:
            print(f"    {str(e.id)[:8]} {e.date} {e.start_time}-{e.end_time} -> 08:00-12:00")

        if not args.apply:
            print("\nDRY RUN — no DB writes. Re-run with --apply to write (prod-data gate).")
            return 0

        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "old_start_time", "old_end_time"])
            for e in targets:
                w.writerow([e.id, e.start_time, e.end_time])

        for e in targets:
            e.start_time = _START
            e.end_time = _END
        db.commit()
        print(f"APPLIED: set 08:00-12:00 on {len(targets)} rows. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
