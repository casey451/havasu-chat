"""Google Places API (New) discovery sweep — Phase 3 of the LHC business pull.

Thin entry point around :class:`app.contrib.google_places_scraper.GooglePlacesClient`.
Core logic lives in ``app/contrib/google_places_scraper.py`` for reuse by Phase 4
layered-scrape orchestration + future Railway cron jobs.

Reads ``scripts/places_categories.json``, runs Text Search per category against
the Places API (New), paginates via ``nextPageToken``, dedupes by Place ID,
captures every raw response to JSONL for audit/replay, and writes a deduped
summary of unique places to a second JSONL.

Companion to relay/HAVA_BUSINESSES_EXECUTION_PLAN_2026-05-06.md.

Usage:
    python -m scripts.places_discovery --dry-run
        # 5-category sample, ~$1 (unchanged default)
    python -m scripts.places_discovery --category eat-drink --dry-run
        # dry-run labels intersecting ``eat-drink`` domains only
    python -m scripts.places_discovery --category eat-drink
        # full vertical for one Tier-1 slug (Railway cron shape)
    python -m scripts.places_discovery
        # full sweep, ~$5-9

The ``--dry-run`` sample (when ``--category`` is omitted) is fixed
(restaurants, coffee shops, hair salons, auto repair, boat rentals).

Outputs land in ``scripts/output/places_pull/``:

  - ``discovery_raw.jsonl`` — every Places API response, with metadata
  - ``discovery_unique.jsonl`` — deduped place summary (one row per Place ID)
  - ``discovery_summary.json`` — counts, per-category breakdown, run timing

Environment:
    ``GOOGLE_PLACES_API_KEY`` — required.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.bootstrap_env import ensure_dotenv_loaded
from app.contrib.google_places_scraper import (
    GooglePlacesClient,
    load_categories_for_discovery,
)

ensure_dotenv_loaded()

DEFAULT_CATEGORIES_PATH = Path(__file__).parent / "places_categories.json"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output" / "places_pull"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run only on the dry-run sample (~$1). Without --category: the "
        "legacy 5-category mix. With --category: those labels intersecting the slug.",
    )
    parser.add_argument(
        "--category",
        default=None,
        metavar="SLUG",
        help="Tier-1 taxonomy slug (e.g. eat-drink). Filters ``places_categories.json`` "
        "rows by domain. Omit for all categories (or the legacy 5-label dry-run).",
    )
    parser.add_argument(
        "--categories-file",
        type=Path,
        default=DEFAULT_CATEGORIES_PATH,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print(
            "ERROR: GOOGLE_PLACES_API_KEY not set in environment.",
            file=sys.stderr,
        )
        return 1

    try:
        categories = load_categories_for_discovery(
            args.categories_file,
            dry_run=args.dry_run,
            category_slug=args.category,
        )
    except SystemExit as e:
        code = e.code
        if isinstance(code, int):
            return code
        return 1

    mode = "dry-run" if args.dry_run else "full"
    cat_note = args.category or "all"
    print(
        f"[discovery] mode={mode} category={cat_note} categories={len(categories)} "
        f"output_dir={args.output_dir}",
        flush=True,
    )

    client = GooglePlacesClient()
    summary = client.sweep_discovery(api_key, categories, args.output_dir)

    print("\n--- discovery summary ---")
    print(f"requests:        {summary['request_count']}")
    print(f"unique places:   {summary['unique_place_count']}")
    print(f"categories run:  {summary['categories_run']}")
    print(f"raw log:         {summary['raw_path']}")
    print(f"unique places:   {summary['unique_path']}")
    print(f"summary json:    {summary['summary_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
