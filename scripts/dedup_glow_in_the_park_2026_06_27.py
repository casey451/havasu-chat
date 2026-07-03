"""Dedup the Altitude "Glow in the Park" double-listing on 2026-06-27.

Live prod audit (docs/ASKHAVA_DATA_FIXES_2026-06-27.md §3): on Sat 2026-06-27 the
Altitude Trampoline Park "Glow in the Park" night appears twice —

  * ``Glow in the Park``           18:00-21:00, source_url carries the funzone
    ``#funspecial`` marker, and exists ONLY on 2026-06-27 (a one-off collision
    from the 7-day funzone rolling window — same shape as the bowling/cosmic
    dedup, scripts/dedup_bowling_cosmic_2026_06_26.py).
  * ``Glow in the Park - All Ages`` 19:00-21:00, the RECURRING series (17 rows
    2026-06-13 -> 2026-08-05, Wed + Sat), carrying every future date.

Web check (2026-06-27): Altitude runs ONE Saturday Glow Night (~6-9pm), not two
sessions — so the two 2026-06-27 rows are the same event double-ingested, not a
6pm + 7pm pair. We KEEP the recurring "- All Ages" series (it covers all future
dates) and DELETE the one-off plain row, mirroring the cosmic-bowling dedup.

(Heads-up for Casey: the one-off's 18:00 start actually matches the marketed
6-9pm better than the series' 19:00 Saturday rows. We follow the audit doc and
keep the series; correcting the series' Saturday start time is out of scope here.)

Read-only by default. ``--apply`` is a prod-data op: dry-run -> counts -> Casey
approves -> apply (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func  # noqa: E402

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

ONE_OFF_TITLE_NORM = "glow in the park"  # exact: excludes "... - all ages"
SERIES_NEEDLE = "glow in the park"  # the series shares this prefix
COLLISION_DATE = date(2026, 6, 27)
FUNZONE_MARKER = "#funspecial"


def _target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Perform the delete (default: dry run).")
    args = ap.parse_args(argv)

    print(f"DB target: {_target()}\n")
    db = SessionLocal()
    try:
        # The one-off: EXACT normalized title "glow in the park" (the series is
        # "glow in the park - all ages", so the exact match excludes it).
        delete = (
            db.query(Event)
            .filter(func.lower(func.trim(Event.normalized_title)) == ONE_OFF_TITLE_NORM)
            .order_by(Event.date)
            .all()
        )
        # The recurring series we are protecting.
        series = (
            db.query(Event)
            .filter(Event.normalized_title.like(f"%{SERIES_NEEDLE}%"))
            .filter(func.lower(func.trim(Event.normalized_title)) != ONE_OFF_TITLE_NORM)
            .order_by(Event.date)
            .all()
        )

        print(f"KEEP series '... - All Ages' ({len(series)} rows):")
        for r in series[:4]:
            print(f"  id={r.id[:8]} {r.date} {r.start_time}-{r.end_time} {r.title!r}")
        print("  ...")

        print(f"\nDELETE one-off ({len(delete)} rows):")
        for r in delete:
            print(f"  id={r.id[:8]} {r.date} {r.start_time}-{r.end_time} {r.title!r} "
                  f"src_url={(r.source_url or '')[:60]!r}")

        # Safety rails.
        if not series:
            print("\nABORT: no '- All Ages' series found — refusing to only delete.")
            return 2
        if len(delete) != 1:
            print(f"\nABORT: expected exactly 1 one-off row, found {len(delete)} — refusing.")
            return 2
        row = delete[0]
        if row.date != COLLISION_DATE:
            print(f"\nABORT: one-off date {row.date} != expected {COLLISION_DATE} — refusing.")
            return 2
        if FUNZONE_MARKER not in (row.source_url or ""):
            print(f"\nABORT: one-off source_url lacks the {FUNZONE_MARKER!r} marker — refusing.")
            return 2
        if not any(s.date == COLLISION_DATE for s in series):
            print(f"\nABORT: series has no row on {COLLISION_DATE} — deleting would drop coverage.")
            return 2

        if not args.apply:
            print(f"\nDRY RUN - would delete {len(delete)} row. Re-run with --apply.")
            return 0

        db.delete(row)
        db.commit()
        print(f"\nAPPLIED - deleted the one-off 'Glow in the Park' row on {COLLISION_DATE}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
