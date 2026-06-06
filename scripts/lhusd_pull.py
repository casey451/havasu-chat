"""
CLI: LHUSD (school district) feeds via Apptegy Thrillshare.

Dry-run (default): fetch + parse, print the dry-run contract, write nothing.
``--apply`` (events feed only): map upcoming calendar events to EventRecords and
route them through the shared ingestion path (app.contrib.event_ingest ->
reconcile -> contribution -> approve). lhusd is a high-trust official source in
the auto-approve registry, so complete upcoming events go LIVE. The NEWS feed
has no surface yet and is dry-run only.

  python scripts/lhusd_pull.py                  # calendar events (iCal, noise-filtered)
  python scripts/lhusd_pull.py --feed news      # live-feed announcements (JSON, dry-run only)
  python scripts/lhusd_pull.py --apply          # ingests upcoming calendar events (auto-approve)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import lhusd  # noqa: E402
from app.contrib.scrape_dryrun import print_dry_run_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--feed", choices=["events", "news"], default="events")
    p.add_argument("--apply", action="store_true", help="ingest upcoming events (auto-approve)")
    args = p.parse_args(argv)

    if args.feed == "news":
        items = lhusd.fetch_live_feeds()
        # News has no surface yet (on hold) — dry-run only, never ingests.
        print_dry_run_report(
            f"{lhusd.SOURCE}:news",
            items,
            sample_fn=lhusd.news_sample,
            notes=[
                "NEEDS_PROD_VERIFY: live_feeds JSON field names parsed defensively.",
                "News surface on hold: --apply does not ingest the news feed.",
            ],
        )
        return 0

    events = lhusd.fetch_events()

    if args.apply:
        from app.contrib.event_ingest import ingest_event_records, print_ingest_report

        records = lhusd.to_event_records(events)
        counts = ingest_event_records(records, source=lhusd.SOURCE, dry_run=False)
        print_ingest_report(f"{lhusd.SOURCE}:events", counts, dry_run=False)
        # Surface record-level failures to the cron (don't hide broken runs).
        return 0 if counts.errors == 0 else 1

    print_dry_run_report(
        f"{lhusd.SOURCE}:events",
        events,
        sample_fn=lhusd.event_sample,
        notes=[
            f"Academic spans >= {lhusd.ACADEMIC_SPAN_MIN_DAYS}d filtered out as noise.",
            "--apply ingests upcoming calendar events (auto-approve).",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
