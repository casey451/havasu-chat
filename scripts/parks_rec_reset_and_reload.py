"""
One-off: delete every parks-rec contribution / event / program and
reload from the latest snapshots.

Use this after changing the loader's tagging or category logic so the
new metadata gets applied to existing rows. The regular
``parks_rec_load.py`` is idempotent and short-circuits on duplicate
``source_url``, so it cannot retag rows that already exist — this
script is the explicit reset path.

Usage
-----
  python scripts/parks_rec_reset_and_reload.py            # really delete + reload
  python scripts/parks_rec_reset_and_reload.py --dry-run  # show what would delete

Selection criteria for deletion (no other rows are touched):
  - Events with ``source_url`` matching a parks-rec hostname
  - Programs with ``contact_url`` matching the WebTrac iteminfo host
  - Contributions with ``submission_category_hint`` in
    {parks_rec_webtrac, parks_rec_aquatic}

Run ``scripts/run_scrapes.py`` first if you want fresh snapshot data;
otherwise this script reuses the most recent snapshot on disk.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import or_  # noqa: E402

from app.contrib.parks_rec_loader import load_latest_snapshots  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution, Event, Program  # noqa: E402

PARKS_REC_HINTS = ("parks_rec_webtrac", "parks_rec_aquatic")


def _purge(db, *, dry_run: bool) -> tuple[int, int, int]:
    e_filter = or_(
        Event.source_url.like("%register.lhcaz.gov%"),
        Event.source_url.like("%lhcaz.gov/parks-recreation%"),
    )
    p_filter = Program.contact_url.like("%register.lhcaz.gov%")
    c_filter = Contribution.submission_category_hint.in_(PARKS_REC_HINTS)

    e_count = db.query(Event).filter(e_filter).count()
    p_count = db.query(Program).filter(p_filter).count()
    c_count = db.query(Contribution).filter(c_filter).count()

    if dry_run:
        return e_count, p_count, c_count

    db.query(Event).filter(e_filter).delete(synchronize_session=False)
    db.query(Program).filter(p_filter).delete(synchronize_session=False)
    db.query(Contribution).filter(c_filter).delete(synchronize_session=False)
    db.commit()
    return e_count, p_count, c_count


def main() -> int:
    p = argparse.ArgumentParser(description="Reset parks-rec catalog rows and reload from snapshots")
    p.add_argument("--dry-run", action="store_true", help="Count rows without deleting or reloading")
    args = p.parse_args()

    with SessionLocal() as db:
        e, prog, c = _purge(db, dry_run=bool(args.dry_run))

    if args.dry_run:
        print(f"would delete: {e} events, {prog} programs, {c} contributions")
        print("(skipping reload because --dry-run)")
        return 0

    print(f"deleted: {e} events, {prog} programs, {c} contributions")
    print("reloading from latest snapshots...")
    results = load_latest_snapshots(dry_run=False)
    for r in results:
        print(
            f"  {r.source}: imported_event={r.imported_event} "
            f"imported_program={r.imported_program} "
            f"skipped_not_public={r.skipped_not_public} "
            f"skipped_duplicate={r.skipped_duplicate} "
            f"errors={len(r.errors)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
