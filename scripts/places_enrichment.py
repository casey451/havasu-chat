"""Google Places API (New) enrichment runner — Phase 4 of the LHC business pull.

Thin entry point around :class:`app.contrib.google_places_scraper.GooglePlacesClient`.
Core logic lives in ``app/contrib/google_places_scraper.py``.

Reads ``scripts/output/places_pull/discovery_unique.jsonl``, calls Place Details
on each Place ID with the Pro + Enterprise + Atmosphere field mask, captures
raw responses to JSONL for audit, and writes a flattened enriched JSONL ready
for Phase 5 filter + load.

Resume-safe: on restart, scans ``enrichment_enriched.jsonl`` for already-processed
Place IDs and skips them. Append-mode writes. Network blips don't lose progress.

Companion to relay/HAVA_BUSINESSES_EXECUTION_PLAN_2026-05-06.md.

Usage:
    python -m scripts.places_enrichment              # full enrichment
    python -m scripts.places_enrichment --limit 10   # smoke-test on 10

Outputs land in ``scripts/output/places_pull/``:

  - ``enrichment_raw.jsonl`` — every Place Details response with metadata
  - ``enrichment_enriched.jsonl`` — one flattened row per Place ID, ready for load
  - ``enrichment_summary.json`` — counts, errors, run timing

Cost: ~$0.040 per call at Enterprise+Atmosphere SKU (includes reviews/photos).
For 2,525 places: ~$100. See §6 of the handoff brief.

Environment:
    ``GOOGLE_PLACES_API_KEY`` — required.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.bootstrap_env import ensure_dotenv_loaded
from app.contrib.google_places_scraper import GooglePlacesClient

ensure_dotenv_loaded()

DEFAULT_INPUT_PATH = (
    Path(__file__).parent / "output" / "places_pull" / "discovery_unique.jsonl"
)
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output" / "places_pull"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on places to enrich (handy for smoke tests).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print(
            "ERROR: GOOGLE_PLACES_API_KEY not set in environment.",
            file=sys.stderr,
        )
        return 1

    n_places = sum(
        1 for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    if args.limit is not None:
        n_places = min(n_places, args.limit)
    print(
        f"[enrichment] enriching up to {n_places} place(s) "
        f"output_dir={args.output_dir}",
        flush=True,
    )

    client = GooglePlacesClient()
    summary = client.run_enrichment(
        input_path=args.input,
        output_dir=args.output_dir,
        limit=args.limit,
        api_key=api_key,
    )

    print("\n--- enrichment summary ---")
    print(f"input:           {summary['input_count']}")
    print(f"success:         {summary['success_count']}")
    print(f"skipped (resume):{summary['skipped_count']}")
    print(f"404 errors:      {summary['errors_404']}")
    print(f"other errors:    {summary['other_errors']}")
    print(f"raw:             {summary['raw_path']}")
    print(f"enriched:        {summary['enriched_path']}")
    print(f"summary:         {summary['summary_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
