"""CLI: Senior Center flyer vision scraper (dry-run default; --apply ingests).

Reads the Lake Havasu Senior Center Current Events flyer images (and the two
monthly calendar grids) into ``senior``-tagged events via a vision model.

Dry-run (default) prints the contract and writes nothing. ``--apply`` ingests via
``ingest_event_records``; senior_center_flyers is NOT in the auto-approve
registry, so rows land PENDING for admin review, and this does NOT touch the live
senior loader. It is the path to retiring the hand-maintained
``app.events.senior_center.CURATED_SPECIAL_EVENTS`` table -- review the pending
rows before deciding whether it supersedes the manual table.

  .venv\\Scripts\\python.exe scripts/senior_flyers_pull.py
  .venv\\Scripts\\python.exe scripts/senior_flyers_pull.py --apply   # lands pending

Needs OPENAI_API_KEY for the vision call (0 fetched without it -- graceful no-op).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.contrib.event_record import EventRecord, event_sample  # noqa: E402
from app.contrib.scrape_dryrun import print_dry_run_report  # noqa: E402
from app.contrib.senior_center_vision import (  # noqa: E402
    SOURCE,
    SeniorFlyerPullResult,
    pull_senior_flyers,
)


def _confidence_histogram(records: list[EventRecord]) -> str:
    buckets: Counter[str] = Counter()
    for rec in records:
        try:
            cf = float((rec.raw or {}).get("confidence"))
        except (TypeError, ValueError):
            cf = 0.0
        if cf >= 0.9:
            buckets["0.90-1.00"] += 1
        elif cf >= 0.75:
            buckets["0.75-0.89"] += 1
        elif cf >= 0.5:
            buckets["0.50-0.74"] += 1
        else:
            buckets["0.00-0.49"] += 1
    if not records:
        return "confidence: (no records)"
    order = ["0.90-1.00", "0.75-0.89", "0.50-0.74", "0.00-0.49"]
    return "confidence: " + ", ".join(f"{k}={buckets.get(k, 0)}" for k in order)


def _notes(result: SeniorFlyerPullResult, records: list[EventRecord]) -> list[str]:
    held = sum(1 for r in records if (r.raw or {}).get("should_hide"))
    return [
        f"images considered={result.images_considered} extracted={result.images_extracted}",
        f"would-hold-hidden (confidence<0.75 -> draft+pending_review): {held}",
        _confidence_histogram(records),
        (
            f"guards dropped: out_of_month={result.dropped_out_of_month} "
            f"no_provenance={result.dropped_no_provenance} "
            f"bad_title={result.dropped_bad_title} bad_date={result.dropped_bad_date}"
        ),
        f"skipped non-image (HTML/PDF/empty/oversize): {result.skipped_non_image}",
        *([f"fetch errors: {len(result.errors)}"] if result.errors else []),
        "Decorative (non-event) images drop out via the provenance/date guards.",
        "Does NOT touch the live senior loader; review before retiring CURATED_SPECIAL_EVENTS.",
    ]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-flyers", type=int, default=None, help="cap flyer vision calls")
    p.add_argument(
        "--apply",
        action="store_true",
        help="ingest the rows (they land PENDING in the review queue, never live)",
    )
    args = p.parse_args(argv)

    result = pull_senior_flyers(max_flyers=args.max_flyers)
    records = result.records

    # Always show the fetched samples + confidence/guard notes.
    print_dry_run_report(SOURCE, records, sample_fn=event_sample, notes=_notes(result, records))

    # Run the shared event funnel for authoritative counts + schema validation: it
    # constructs a ContributionCreate per record, so a bad `source` surfaces in the
    # DRY-RUN too. senior_center_flyers isn't auto-approve (rows land PENDING) and
    # this does NOT touch the live senior loader.
    from app.contrib.event_ingest import ingest_event_records, print_ingest_report

    counts = ingest_event_records(records, source=SOURCE, dry_run=not args.apply)
    print_ingest_report(SOURCE, counts, dry_run=not args.apply)
    return 0 if counts.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
