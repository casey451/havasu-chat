"""
CLI: prune stale aquatic events from the catalog.

The aquatic schedule scraper (``app.contrib.lhcaz_aquatic``) republishes
~25 days of class slots at a time. Old occurrences stay in ``events``
forever once their ``date`` is past — chat hides them via date filter,
but row count drifts up. This script is the periodic fix.

Scope: ONLY Event rows whose ``source_url`` points at the aquatic
schedule page. WebTrac registrations carry a different host and are
intentionally untouched.

Cutoff: ``today - 7 days`` (see ``AQUATIC_PRUNE_GRACE_DAYS``). The grace
window covers timezone slop, late-day chat queries, and a recovery cushion
if a prune runs early or against the wrong DB.

Usage
-----
  # Live prune:
  python scripts/parks_rec_prune.py

  # Dry run — count what would delete, write nothing:
  python scripts/parks_rec_prune.py --dry-run

  # Override the grace window (default 7 days):
  python scripts/parks_rec_prune.py --grace-days 14

Recommended cadence: alongside the scrape + load steps in your scheduler
(GitHub Actions, cron, etc.). Run AFTER ``parks_rec_load.py`` so a fresh
republish has a chance to re-import any rows the city extends backwards
through the window — though that should never happen in practice.

Exit code is non-zero if the prune surfaced any errors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.parks_rec_loader import (  # noqa: E402
    AQUATIC_PRUNE_GRACE_DAYS,
    prune_latest,
)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Prune stale aquatic-schedule Event rows from the catalog"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows that would delete without writing to the DB",
    )
    p.add_argument(
        "--grace-days",
        type=int,
        default=AQUATIC_PRUNE_GRACE_DAYS,
        metavar="N",
        help=f"Keep events whose date is within N days before today "
        f"(default: {AQUATIC_PRUNE_GRACE_DAYS})",
    )
    args = p.parse_args()

    stats = prune_latest(grace_days=args.grace_days, dry_run=bool(args.dry_run))

    label = "would delete" if stats.dry_run else "deleted"
    print(
        f"parks_rec_prune (dry_run={stats.dry_run}) "
        f"cutoff={stats.cutoff.isoformat()} grace_days={args.grace_days}"
    )
    print(
        f"  {stats.source}: matched={stats.matched} {label}={stats.matched if stats.dry_run else stats.deleted}"
    )

    if stats.errors:
        print(f"  errors ({len(stats.errors)}):")
        for e in stats.errors[:5]:
            print(f"    - {e}")
        if len(stats.errors) > 5:
            print(f"    ... and {len(stats.errors) - 5} more")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
