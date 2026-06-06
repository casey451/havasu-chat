"""
CLI: Lake Havasu City Legistar meetings (council / P&Z / boards).

Dry-run (default): fetch + parse, print the dry-run contract, write nothing.
``--apply``: map upcoming meetings to EventRecords and route them through the
shared ingestion path (app.contrib.event_ingest.ingest_event_records ->
reconcile -> contribution -> approve). legistar is a high-trust civic source in
the auto-approve registry, so complete upcoming meetings go LIVE; ambiguous
same-date/venue matches land pending. Past meetings are dropped.

  python scripts/legistar_pull.py
  python scripts/legistar_pull.py --top 40
  python scripts/legistar_pull.py --apply        # ingests upcoming meetings (auto-approve)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib import legistar  # noqa: E402
from app.contrib.scrape_dryrun import print_dry_run_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--top", type=int, default=20, help="number of most-recent events to fetch")
    p.add_argument("--apply", action="store_true", help="ingest upcoming meetings (auto-approve)")
    args = p.parse_args(argv)

    meetings = legistar.fetch_events(top=args.top)

    if args.apply:
        from app.contrib.event_ingest import ingest_event_records, print_ingest_report

        records = legistar.to_event_records(meetings)
        counts = ingest_event_records(records, source=legistar.SOURCE, dry_run=False)
        print_ingest_report(legistar.SOURCE, counts, dry_run=False)
        # Surface record-level failures to the cron (don't hide broken runs).
        return 0 if counts.errors == 0 else 1

    print_dry_run_report(
        legistar.SOURCE,
        meetings,
        sample_fn=legistar.meeting_sample,
        notes=["Meetings modelled as events; --apply ingests upcoming ones (auto-approve)."],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
