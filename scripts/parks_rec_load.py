"""
CLI: load the latest parks-and-rec snapshot into the catalog.

Reads the newest snapshot per source from ``data/scrapes/<source>/`` and
routes each record through the existing contribution → auto-approval
flow (Event for single-day sections, Program for recurring ones).

Usage
-----
  # Full live load:
  python scripts/parks_rec_load.py

  # Dry run — count what would be imported, write nothing:
  python scripts/parks_rec_load.py --dry-run

Run ``scripts/run_scrapes.py`` first to refresh the snapshots; this
script does not fetch.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.parks_rec_loader import load_latest_snapshots  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Load the latest parks-and-rec snapshot into the catalog")
    p.add_argument("--dry-run", action="store_true", help="Count imports without writing to the DB")
    args = p.parse_args()

    results = load_latest_snapshots(dry_run=bool(args.dry_run))

    any_failures = False
    print(f"parks_rec_load (dry_run={bool(args.dry_run)})")
    for s in results:
        print(
            f"  {s.source}: considered={s.considered} "
            f"imported_event={s.imported_event} imported_program={s.imported_program} "
            f"skipped_not_public={s.skipped_not_public} "
            f"skipped_duplicate={s.skipped_duplicate} "
            f"skipped_invalid={s.skipped_invalid} "
            f"auto_approval_failed={s.auto_approval_failed}"
        )
        if s.errors:
            any_failures = True
            print(f"    errors ({len(s.errors)}):")
            for e in s.errors[:5]:
                print(f"      - {e}")
            if len(s.errors) > 5:
                print(f"      ... and {len(s.errors) - 5} more")
    return 1 if any_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
