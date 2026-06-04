"""
CLI: dry-run LHUSD (school district) feeds via Apptegy Thrillshare.

Build-only / inert: fetch + parse, prints the dry-run contract, writes nothing.

  python scripts/lhusd_pull.py                  # calendar events (iCal, noise-filtered)
  python scripts/lhusd_pull.py --feed news      # live-feed announcements (JSON)
  python scripts/lhusd_pull.py --apply          # guarded — refuses to write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import lhusd  # noqa: E402
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--feed", choices=["events", "news"], default="events")
    p.add_argument("--apply", action="store_true", help="(guarded) attempt live ingestion")
    args = p.parse_args(argv)

    if args.apply:
        apply_guard(lhusd.SOURCE)

    if args.feed == "news":
        items = lhusd.fetch_live_feeds()
        print_dry_run_report(
            f"{lhusd.SOURCE}:news",
            items,
            sample_fn=lhusd.news_sample,
            notes=["NEEDS_PROD_VERIFY: live_feeds JSON field names parsed defensively."],
        )
    else:
        events = lhusd.fetch_events()
        print_dry_run_report(
            f"{lhusd.SOURCE}:events",
            events,
            sample_fn=lhusd.event_sample,
            notes=[f"Academic spans >= {lhusd.ACADEMIC_SPAN_MIN_DAYS}d filtered out as noise."],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
