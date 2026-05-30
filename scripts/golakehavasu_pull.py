"""
CLI: pull golakehavasu.com (Visit Lake Havasu / CVB) events into the
contributions queue, via the shared event reconciler.

  python scripts/golakehavasu_pull.py
  python scripts/golakehavasu_pull.py --start-date 2026-06-01
  python scripts/golakehavasu_pull.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.golakehavasu_pull import run_pull


def main() -> int:
    p = argparse.ArgumentParser(
        description="Ingest golakehavasu.com events into the contribution queue"
    )
    p.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="YYYY-MM-DD (default: today)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write to the database",
    )
    args = p.parse_args()
    start_date = date.fromisoformat(args.start_date) if args.start_date else date.today()
    return run_pull(start_date, dry_run=bool(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
