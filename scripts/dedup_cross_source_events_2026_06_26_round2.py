"""Round 2: the 3 cross-source event dups held out of round 1 (--apply writes).

The round-1 script (dedup_cross_source_events_2026_06_26.py) deleted 8
unambiguous twins and deliberately held three pairs for an operator decision.
Casey 2026-06-26 ("do what you think is best") cleared them:

  * Lake Havasu Farmers Market (2026-06-20) — only ONE of the market's 36 weekly
    rows was double-loaded; delete the river_scene 00:00 twin, keep the
    go_lake 08:00 row.
  * Crosscutt @ Flying X (2026-09-05) — keep the ``allevents`` row because it
    carries the real 8 PM start, delete the timeless river_scene twin. (This
    inverts source priority on purpose: data quality wins.)
  * Sunrise Kayak (2026-06-16) — keep the canonical "Sunrise Kayaking"
    (go_lake/parks_rec), delete the redundant admin "Sunrise Kayak June 16".

Same explicit-id + keeper-guard contract as round 1.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

# (delete_id, keep_id, label)
PAIRS: tuple[tuple[str, str, str], ...] = (
    ("bf799320", "1e4cd9d7", "Lake Havasu Farmers Market (2026-06-20)"),
    ("f263ace7", "f29f9cd9", "Crosscutt @ Flying X — keep timed allevents (2026-09-05)"),
    ("1235c236", "b6ed39d2", "Sunrise Kayak — keep canonical 'Sunrise Kayaking' (2026-06-16)"),
)


def _one(db, prefix: str) -> Event | None:
    return db.query(Event).filter(Event.id.like(prefix + "%")).one_or_none()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Perform the deletes (default: dry run).")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        to_delete: list[Event] = []
        ok = True
        for del_id, keep_id, label in PAIRS:
            d = _one(db, del_id)
            k = _one(db, keep_id)
            if d is None:
                print(f"  SKIP  {label}: delete row {del_id} not found (already gone?)")
                continue
            if k is None:
                print(f"  ABORT {label}: KEEPER {keep_id} missing — refusing to delete its twin.")
                ok = False
                continue
            if d.date != k.date:
                print(f"  ABORT {label}: date mismatch keep={k.date} del={d.date} — refusing.")
                ok = False
                continue
            print(f"  DEL  {label}")
            print(f"        keep[{k.source}] {k.id[:8]} {k.start_time} {k.title[:50]!r} @ {k.location_name[:28]!r}")
            print(f"        del [{d.source}] {d.id[:8]} {d.start_time} {d.title[:50]!r} @ {d.location_name[:28]!r}")
            to_delete.append(d)

        if not ok:
            print("\nABORTED — fix the keeper/date issues above before applying.")
            return 2

        if not args.apply:
            print(f"\nDRY RUN — would delete {len(to_delete)} duplicate rows. Re-run with --apply.")
            return 0

        for d in to_delete:
            db.delete(d)
        db.commit()
        print(f"\nAPPLIED — deleted {len(to_delete)} cross-source duplicate rows.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
