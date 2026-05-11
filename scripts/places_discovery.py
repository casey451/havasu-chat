"""Google Places API (New) discovery sweep — Phase 3 of the LHC business pull.

Reads scripts/places_categories.json, runs Text Search per category against
the Places API (New), paginates via nextPageToken, dedupes by Place ID,
captures every raw response to JSONL for audit/replay, and writes a deduped
summary of unique places to a second JSONL.

Companion to relay/HAVA_BUSINESSES_EXECUTION_PLAN_2026-05-06.md.

Usage:
    python -m scripts.places_discovery --dry-run    # 5-category sample, ~$1
    python -m scripts.places_discovery              # full sweep, ~$5-9

The --dry-run sample is fixed (restaurants, coffee shops, hair salons,
auto repair, boat rentals) — a mix of high- and low-density verticals
designed to validate pagination, dedupe, and ZIP distribution before any
significant API spend.

Outputs land in scripts/output/places_pull/:
  - discovery_raw.jsonl     — every Places API response, with metadata
  - discovery_unique.jsonl  — deduped place summary (one row per Place ID)
  - discovery_summary.json  — counts, per-category breakdown, run timing

Environment:
    GOOGLE_PLACES_API_KEY — required.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.bootstrap_env import ensure_dotenv_loaded
from app.contrib.rate_limiter import GOOGLE_PLACES_LIMITER

ensure_dotenv_loaded()

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DEFAULT_CATEGORIES_PATH = Path(__file__).parent / "places_categories.json"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output" / "places_pull"
DRY_RUN_LABELS = {
    "restaurants",
    "coffee shops",
    "hair salons",
    "auto repair",
    "boat rentals",
}

# Field mask: discovery-tier fields only. Hours, website, phone, reviews,
# photos come in Phase 4 enrichment, so we don't pay Pro-tier per call here.
# `id` is essentials (free); the rest are basic-tier fields.
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.primaryType",
        "places.types",
        "nextPageToken",
    ]
)

# Pagination pause: Google's nextPageToken can take ~seconds to become valid.
# Not retry logic — do not fold into SourceLimiter (design memo 2026-05-13).
PAGINATION_SLEEP_S = 2.0
MAX_PAGES_PER_CATEGORY = 3
QUERY_SUFFIX = " in Lake Havasu City, AZ"
_RETRY_EXHAUSTED_STATUSES = frozenset({429, 500, 502, 503, 504})


def load_categories(path: Path, dry_run: bool) -> list[dict[str, str]]:
    data = json.loads(path.read_text())
    cats = data["categories"]
    if dry_run:
        cats = [c for c in cats if c["label"] in DRY_RUN_LABELS]
        missing = DRY_RUN_LABELS - {c["label"] for c in cats}
        if missing:
            raise SystemExit(
                f"Dry-run sample missing from categories file: {sorted(missing)}"
            )
    return cats


def request_text_search(
    api_key: str, query: str, page_token: str | None
) -> dict[str, Any]:
    """Single Text Search call. QPS + retries via ``GOOGLE_PLACES_LIMITER``."""
    body: dict[str, Any] = {"textQuery": query}
    if page_token:
        body["pageToken"] = page_token
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    with httpx.Client(timeout=30) as client:
        resp = GOOGLE_PLACES_LIMITER.call_with_retry(
            lambda: client.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=body)
        )
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code in _RETRY_EXHAUSTED_STATUSES:
        raise RuntimeError(
            f"Places API: retries exhausted for query={query!r} "
            f"(last status {resp.status_code})"
        )
    raise RuntimeError(
        f"Places API error {resp.status_code} on query={query!r}: "
        f"{resp.text[:500]}"
    )


def sweep(
    api_key: str,
    categories: list[dict[str, str]],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "discovery_raw.jsonl"
    unique_path = output_dir / "discovery_unique.jsonl"
    summary_path = output_dir / "discovery_summary.json"

    seen: dict[str, dict[str, Any]] = {}
    request_count = 0
    page_count_by_category: dict[str, int] = {}
    place_count_by_category: dict[str, int] = {}
    started_at = datetime.now(UTC).isoformat()

    with raw_path.open("w") as raw_f:
        for cat in categories:
            label = cat["label"]
            domain = cat.get("domain", "")
            query = label + QUERY_SUFFIX
            page_token: str | None = None
            pages = 0
            cat_unique_added = 0

            for page_idx in range(MAX_PAGES_PER_CATEGORY):
                payload = request_text_search(api_key, query, page_token)
                request_count += 1
                pages += 1

                # Audit log: every raw response with metadata.
                raw_f.write(
                    json.dumps(
                        {
                            "ts": datetime.now(UTC).isoformat(),
                            "category_label": label,
                            "category_domain": domain,
                            "query": query,
                            "page_index": page_idx,
                            "response": payload,
                        }
                    )
                    + "\n"
                )

                for place in payload.get("places", []) or []:
                    pid = place.get("id")
                    if not pid:
                        continue
                    if pid not in seen:
                        seen[pid] = {
                            **place,
                            "_first_seen_category": label,
                            "_first_seen_domain": domain,
                            "_seen_categories": [label],
                        }
                        cat_unique_added += 1
                    else:
                        cats_seen: list[str] = seen[pid]["_seen_categories"]
                        if label not in cats_seen:
                            cats_seen.append(label)

                page_token = payload.get("nextPageToken")
                if not page_token:
                    break
                time.sleep(PAGINATION_SLEEP_S)

            page_count_by_category[label] = pages
            place_count_by_category[label] = cat_unique_added
            print(
                f"  [{label:30s}] {cat_unique_added:4d} new unique  "
                f"({pages} page{'s' if pages != 1 else ''})",
                flush=True,
            )

    with unique_path.open("w") as unique_f:
        for place in seen.values():
            unique_f.write(json.dumps(place) + "\n")

    finished_at = datetime.now(UTC).isoformat()
    summary = {
        "started_at": started_at,
        "finished_at": finished_at,
        "request_count": request_count,
        "unique_place_count": len(seen),
        "categories_run": len(categories),
        "page_count_by_category": page_count_by_category,
        "unique_count_by_category": place_count_by_category,
        "raw_path": str(raw_path),
        "unique_path": str(unique_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run only on the 5-category dry-run sample (~$1 in API spend).",
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

    categories = load_categories(args.categories_file, args.dry_run)
    mode = "dry-run" if args.dry_run else "full"
    print(
        f"[discovery] mode={mode} categories={len(categories)} "
        f"output_dir={args.output_dir}",
        flush=True,
    )

    summary = sweep(api_key, categories, args.output_dir)

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
