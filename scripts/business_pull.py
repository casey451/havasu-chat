"""
CLI: dry-run the source-expansion business/community sources.

Build-only / inert: fetch + parse, prints a dry-run summary, writes nothing.

  python scripts/business_pull.py --source food_inspections
  python scripts/business_pull.py --source chamber        # enrichment signal
  python scripts/business_pull.py --source downtown        # enrichment signal
  python scripts/business_pull.py --source reddit          # NEEDS_PROD_VERIFY (egress)
  python scripts/business_pull.py --source zillow          # market-context CSVs
  python scripts/business_pull.py --source p2c             # probe JSON backend, then stop
  python scripts/business_pull.py --source chamber --apply # guarded — refuses to write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import (  # noqa: E402
    chamber_directory,
    downtown_lhc,
    food_inspections,
    p2c_bulletin,
    reddit_havasu,
    zillow_research,
)
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402


def _run_p2c() -> None:
    result, entries = p2c_bulletin.probe_json_backend()
    print("=== p2c_bulletin — DRY RUN / PROBE (no writes) ===")
    print(f"backend_present: {result.backend_present}")
    print(f"status_code:     {result.status_code}")
    print(f"note:            {result.note}")
    if result.backend_present:
        print_dry_run_report(p2c_bulletin.SOURCE, entries, sample_fn=p2c_bulletin.entry_sample)
    else:
        print("Per the build prompt: backend not confirmed -> document findings and stop. "
              "Do not reverse-engineer further. NEEDS_PROD_VERIFY.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--source",
        choices=["food_inspections", "chamber", "downtown", "reddit", "zillow", "p2c"],
        required=True,
    )
    p.add_argument("--apply", action="store_true", help="(guarded) attempt live ingestion")
    args = p.parse_args(argv)

    if args.apply:
        apply_guard(f"business:{args.source}")

    if args.source == "food_inspections":
        records = food_inspections.fetch_latest()
        print_dry_run_report(
            food_inspections.SOURCE, records, sample_fn=food_inspections.inspection_sample,
            notes=["Lake Havasu region only; match to providers by name+address at ingest."],
        )
    elif args.source == "chamber":
        members = chamber_directory.fetch_members()
        print_dry_run_report(
            chamber_directory.SOURCE, members, sample_fn=chamber_directory.member_sample,
            notes=["ENRICHMENT signal (chamber_member=true) on existing providers, not a creator."],
        )
    elif args.source == "downtown":
        members = downtown_lhc.fetch_members()
        print_dry_run_report(
            downtown_lhc.SOURCE, members, sample_fn=downtown_lhc.member_sample,
            notes=["ENRICHMENT signal (downtown_member=true); events skipped (golakehavasu dupe)."],
        )
    elif args.source == "reddit":
        posts = reddit_havasu.fetch_new()
        print_dry_run_report(
            reddit_havasu.SOURCE, posts, sample_fn=reddit_havasu.post_sample,
            notes=["Permalink+snippet only; mentions piped to mention_scanner. NEEDS_PROD_VERIFY egress."],
        )
    elif args.source == "zillow":
        stats = zillow_research.fetch_all()
        print_dry_run_report(
            zillow_research.SOURCE, stats, sample_fn=zillow_research.stat_sample,
            notes=["Research CSVs only (no listing scraping); market-context cache payload."],
        )
    elif args.source == "p2c":
        _run_p2c()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
