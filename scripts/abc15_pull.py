"""
CLI: dry-run ABC15 Lake Havasu section RSS.

Build-only / inert: fetch + parse, prints the dry-run contract, writes nothing.

  python scripts/abc15_pull.py
  python scripts/abc15_pull.py --apply       # guarded — refuses to write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import abc15_havasu  # noqa: E402
from app.contrib.civicplus_rss import feed_sample  # noqa: E402
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="(guarded) attempt live ingestion")
    args = p.parse_args(argv)

    if args.apply:
        apply_guard(abc15_havasu.SOURCE)

    items = abc15_havasu.fetch_articles()
    print_dry_run_report(
        abc15_havasu.SOURCE,
        items,
        sample_fn=feed_sample,
        notes=["Sporadic feed; an empty result is normal."],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
