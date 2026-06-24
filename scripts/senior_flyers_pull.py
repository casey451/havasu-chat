"""CLI: Senior Center flyer vision scraper -- dry-run only (build-only).

Reads the Lake Havasu Senior Center Current Events flyer images (and the two
monthly calendar grids) into ``senior``-tagged events via a vision model, and
prints the dry-run contract. Performs NO database writes, does NOT touch the live
senior loader, and is wired into no orchestrator. ``--apply`` is guarded.

This is the build-only path to retiring the hand-maintained
``app.events.senior_center.CURATED_SPECIAL_EVENTS`` table -- review the dry-run
output before deciding whether it supersedes the manual table.

  .venv\\Scripts\\python.exe scripts/senior_flyers_pull.py
  .venv\\Scripts\\python.exe scripts/senior_flyers_pull.py --max-flyers 6

Needs OPENAI_API_KEY for a live vision call (0 fetched without it -- not a bug).
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
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402
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
        *([f"fetch errors: {len(result.errors)}"] if result.errors else []),
        "Decorative (non-event) images drop out via the provenance/date guards.",
        "Does NOT touch the live senior loader; review before retiring CURATED_SPECIAL_EVENTS.",
    ]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-flyers", type=int, default=None, help="cap flyer vision calls")
    p.add_argument("--apply", action="store_true", help="guarded: build-only, refuses to write")
    args = p.parse_args(argv)

    if args.apply:
        apply_guard(SOURCE)

    result = pull_senior_flyers(max_flyers=args.max_flyers)
    print_dry_run_report(
        SOURCE,
        result.records,
        sample_fn=event_sample,
        notes=_notes(result, result.records),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
