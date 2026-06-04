"""
CLI: dry-run the City of LHC CivicPlus RSS feeds (News Flash + Alert Center).

Build-only / inert: fetches + parses and prints the dry-run contract. Writes
nothing and is wired into no orchestrator. --apply is intentionally guarded.

  python scripts/lhc_civicplus_pull.py                 # newsflash (default)
  python scripts/lhc_civicplus_pull.py --feed alerts   # alert center (usually 0 items)
  python scripts/lhc_civicplus_pull.py --apply         # guarded — refuses to write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import lhc_alerts, lhc_newsflash  # noqa: E402
from app.contrib.civicplus_rss import feed_sample  # noqa: E402
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--feed", choices=["newsflash", "alerts"], default="newsflash")
    p.add_argument("--apply", action="store_true", help="(guarded) attempt live ingestion")
    args = p.parse_args(argv)

    if args.feed == "alerts":
        name, fetch = lhc_alerts.SOURCE, lhc_alerts.fetch_alerts
        notes = ["Alert Center is usually empty (0 items) — that is the healthy steady state."]
    else:
        name, fetch = lhc_newsflash.SOURCE, lhc_newsflash.fetch_newsflash
        notes = ["News store is TBD (proposed in PR) — all items count as would-insert."]

    if args.apply:
        apply_guard(name)

    items = fetch()
    print_dry_run_report(name, items, sample_fn=feed_sample, notes=notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
