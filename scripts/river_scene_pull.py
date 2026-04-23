"""
CLI: pull RiverScene events (sitemap discovery + event HTML pages) into the contributions queue.

  python scripts/river_scene_pull.py
  python scripts/river_scene_pull.py --start-date 2026-05-01
  python scripts/river_scene_pull.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.river_scene_pull import run_pull


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest RiverScene events into the contribution queue")
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
    if args.start_date:
        start_date = date.fromisoformat(args.start_date)
    else:
        start_date = date.today()
    return run_pull(start_date, dry_run=bool(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
