"""Delete 8 cross-source duplicate events (READ-ONLY by default; --apply writes).

A same-date / similar-title sweep over live events surfaced pairs where the same
real-world event was ingested twice from different feeds. The duplicate twin is
always the messier row (address-as-venue, a 00:00 "no time" placeholder, or
smart-quote-mangled title) from a lower-priority feed; the keeper is the clean
``go_lake_havasu`` row (and wins on EVENT_SOURCE_PRIORITY).

Only the 8 UNAMBIGUOUS pairs are listed here. Three more candidates were held
out for an operator decision (Sunrise Kayak — unclear which row is canonical;
Crosscutt @ Flying X — the priority keeper has no start time while the dup
carries the real 8pm; and "4th of July Mini Bakers" vs "Mini Bakers & Parents",
which are DIFFERENT sessions at different times, i.e. not a duplicate at all).

Each entry is (delete_id, keep_id, label). We refuse to delete unless the keeper
still exists and both rows actually share the event date — a guard against a
stale id silently nuking a singleton.
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
    ("755aea62", "f3eb58db", "GraceArts SpongeBob Musical (2026-06-05)"),
    ("e03615c0", "2db52fb1", "Battle for the Buoy Waterball (2026-06-06)"),
    ("cef4755f", "7f7b674a", "Lady Lee's Monday Night Dance Party (2026-06-08)"),
    ("918cf3e0", "9f5bdec3", "Back to the 80's Bowling Night (2026-07-18)"),
    ("de90bd41", "9d9e3c48", "Kiwanis Krazy Bowling Tournament (2026-07-18)"),
    ("70b0c29c", "dd72255f", "Taste of Havasu (2026-10-22)"),
    ("31458c92", "7298d75f", "Havasu Christmas Craft & Gift Show (2026-11-14)"),
    ("8e0961ce", "25cc416e", "Rockabilly Reunion (2027-01-29)"),
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
