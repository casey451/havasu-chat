"""
CLI: dry-run Lake Havasu City Legistar meetings (council / P&Z / boards).

Build-only / inert: fetch + parse, prints the dry-run contract, writes nothing.

  python scripts/legistar_pull.py
  python scripts/legistar_pull.py --top 40
  python scripts/legistar_pull.py --apply        # guarded — refuses to write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import legistar  # noqa: E402
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--top", type=int, default=20, help="number of most-recent events to fetch")
    p.add_argument("--apply", action="store_true", help="(guarded) attempt live ingestion")
    args = p.parse_args(argv)

    if args.apply:
        apply_guard(legistar.SOURCE)

    meetings = legistar.fetch_events(top=args.top)
    print_dry_run_report(
        legistar.SOURCE,
        meetings,
        sample_fn=legistar.meeting_sample,
        notes=["Meetings modelled as events; would be routed through the event contribution flow."],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
