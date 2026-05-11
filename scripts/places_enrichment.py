"""Google Places API (New) enrichment runner — Phase 4 of the LHC business pull.

Reads scripts/output/places_pull/discovery_unique.jsonl, calls Place Details
on each Place ID with the Pro + Enterprise + Atmosphere field mask, captures
raw responses to JSONL for audit, and writes a flattened enriched JSONL ready
for Phase 5 filter + load.

Resume-safe: on restart, scans enrichment_enriched.jsonl for already-processed
Place IDs and skips them. Append-mode writes. Network blips don't lose progress.

Companion to relay/HAVA_BUSINESSES_EXECUTION_PLAN_2026-05-06.md.

Usage:
    python -m scripts.places_enrichment              # full enrichment
    python -m scripts.places_enrichment --limit 10   # smoke-test on 10

Outputs land in scripts/output/places_pull/:
  - enrichment_raw.jsonl       — every Place Details response with metadata
  - enrichment_enriched.jsonl  — one flattened row per Place ID, ready for load
  - enrichment_summary.json    — counts, errors, run timing

Cost: ~$0.040 per call at Enterprise+Atmosphere SKU (includes reviews/photos).
For 2,525 places: ~$100. See §6 of the handoff brief.

Environment:
    GOOGLE_PLACES_API_KEY — required.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.bootstrap_env import ensure_dotenv_loaded
from app.contrib.rate_limiter import SourceLimiter

ensure_dotenv_loaded()

PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
DEFAULT_INPUT_PATH = (
    Path(__file__).parent / "output" / "places_pull" / "discovery_unique.jsonl"
)
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output" / "places_pull"

# Field mask per §6 of the handoff brief. NOTE: Place Details v1 returns a
# single Place object (not a list), so paths do NOT have a "places." prefix.
# The presence of `reviews` + `photos` puts us on the Enterprise+Atmosphere
# SKU (~$40/1k). Brief §6 explicitly accepts this tier for top 5 reviews.
FIELD_MASK = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "addressComponents",
        "nationalPhoneNumber",
        "websiteUri",
        "regularOpeningHours",
        "primaryType",
        "types",
        "location",
        "rating",
        "userRatingCount",
        "reviews",
        "photos",
    ]
)

# Enrichment uses 6.5 QPS (operator-tuned) — distinct from lookup path's 4 QPS.
_ENRICHMENT_LIMITER = SourceLimiter("google_places_enrichment", qps=6.5)
_RETRY_EXHAUSTED_STATUSES = frozenset({429, 500, 502, 503, 504})
PROGRESS_EVERY = 50


def load_unique_places(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_processed_ids(enriched_path: Path) -> set[str]:
    """Resume support — every place_id already written to enriched_path is skipped."""
    if not enriched_path.exists():
        return set()
    ids: set[str] = set()
    for line in enriched_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            pid = row.get("place_id")
            if pid:
                ids.add(pid)
        except json.JSONDecodeError:
            # Tolerate a partial last line from a crashed previous run.
            continue
    return ids


def request_place_details(api_key: str, place_id: str) -> dict[str, Any]:
    """Single Place Details call. QPS + retries via ``_ENRICHMENT_LIMITER``."""
    url = PLACE_DETAILS_URL.format(place_id=place_id)
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    with httpx.Client(timeout=30) as client:
        resp = _ENRICHMENT_LIMITER.call_with_retry(lambda: client.get(url, headers=headers))
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 404:
        return {"_error_status": 404, "_place_id": place_id}
    if resp.status_code in _RETRY_EXHAUSTED_STATUSES:
        raise RuntimeError(
            f"Places API: retries exhausted for place_id={place_id!r} "
            f"(last status {resp.status_code})"
        )
    raise RuntimeError(
        f"Places API error {resp.status_code} on place_id={place_id!r}: "
        f"{resp.text[:500]}"
    )


def extract_zip(addr_components: list[dict[str, Any]] | None) -> str | None:
    """Pull the postal code out of addressComponents."""
    if not addr_components:
        return None
    for comp in addr_components:
        types = comp.get("types", []) or []
        if "postal_code" in types:
            return comp.get("longText") or comp.get("shortText")
    return None


def flatten_review(review: dict[str, Any]) -> dict[str, Any]:
    """Pull the fields we care about from a review object into a flat dict."""
    text_field = review.get("text")
    if isinstance(text_field, dict):
        text = text_field.get("text")
    else:
        text = text_field
    author = review.get("authorAttribution") or {}
    return {
        "author": author.get("displayName"),
        "rating": review.get("rating"),
        "text": text,
        "publish_time": review.get("publishTime"),
    }


def build_enriched_row(
    place_id: str,
    payload: dict[str, Any],
    discovery_meta: dict[str, Any],
) -> dict[str, Any]:
    location = payload.get("location") or {}
    return {
        "place_id": place_id,
        "display_name": (payload.get("displayName") or {}).get("text"),
        "formatted_address": payload.get("formattedAddress"),
        "zip": extract_zip(payload.get("addressComponents")),
        "phone": payload.get("nationalPhoneNumber"),
        "website": payload.get("websiteUri"),
        "primary_type": payload.get("primaryType"),
        "types": payload.get("types") or [],
        "lat": location.get("latitude"),
        "lng": location.get("longitude"),
        "rating": payload.get("rating"),
        "review_count": payload.get("userRatingCount"),
        "review_snippets": [
            flatten_review(r) for r in (payload.get("reviews") or [])
        ],
        "photo_refs": [p.get("name") for p in (payload.get("photos") or [])],
        "regular_opening_hours": payload.get("regularOpeningHours"),
        "address_components": payload.get("addressComponents"),
        "_seen_categories": discovery_meta.get("_seen_categories", []),
        "_first_seen_category": discovery_meta.get("_first_seen_category"),
        "_first_seen_domain": discovery_meta.get("_first_seen_domain"),
    }


def enrich(
    api_key: str,
    places: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "enrichment_raw.jsonl"
    enriched_path = output_dir / "enrichment_enriched.jsonl"
    summary_path = output_dir / "enrichment_summary.json"

    already_done = load_processed_ids(enriched_path)
    if already_done:
        print(
            f"[enrichment] resume: {len(already_done)} place(s) already enriched, "
            "skipping those",
            flush=True,
        )

    started_at = datetime.now(UTC).isoformat()
    success = 0
    skipped = 0
    errors_404 = 0
    other_errors = 0

    # Append-mode writes for resume safety.
    with raw_path.open("a") as raw_f, enriched_path.open("a") as enriched_f:
        for idx, place in enumerate(places, start=1):
            pid = place.get("id")
            if not pid:
                continue
            if pid in already_done:
                skipped += 1
                continue

            try:
                payload = request_place_details(api_key, pid)
            except Exception as exc:
                other_errors += 1
                raw_f.write(
                    json.dumps(
                        {
                            "ts": datetime.now(UTC).isoformat(),
                            "place_id": pid,
                            "_error": str(exc),
                        }
                    )
                    + "\n"
                )
                raw_f.flush()
                if idx % PROGRESS_EVERY == 0:
                    print(
                        f"  [{idx:4d}/{len(places)}] success={success} "
                        f"errors={other_errors + errors_404} skipped={skipped}",
                        flush=True,
                    )
                continue

            if payload.get("_error_status") == 404:
                errors_404 += 1
                raw_f.write(
                    json.dumps(
                        {
                            "ts": datetime.now(UTC).isoformat(),
                            "place_id": pid,
                            "_error_status": 404,
                        }
                    )
                    + "\n"
                )
                raw_f.flush()
                continue

            success += 1
            raw_f.write(
                json.dumps(
                    {
                        "ts": datetime.now(UTC).isoformat(),
                        "place_id": pid,
                        "response": payload,
                    }
                )
                + "\n"
            )
            raw_f.flush()

            row = build_enriched_row(pid, payload, place)
            enriched_f.write(json.dumps(row) + "\n")
            enriched_f.flush()

            if idx % PROGRESS_EVERY == 0:
                print(
                    f"  [{idx:4d}/{len(places)}] success={success} "
                    f"errors={other_errors + errors_404} skipped={skipped}",
                    flush=True,
                )

    finished_at = datetime.now(UTC).isoformat()
    summary = {
        "started_at": started_at,
        "finished_at": finished_at,
        "input_count": len(places),
        "success_count": success,
        "skipped_count": skipped,
        "errors_404": errors_404,
        "other_errors": other_errors,
        "raw_path": str(raw_path),
        "enriched_path": str(enriched_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    summary["summary_path"] = str(summary_path)
    return summary


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

    places = load_unique_places(args.input)
    if args.limit is not None:
        places = places[: args.limit]
    print(
        f"[enrichment] enriching up to {len(places)} place(s) "
        f"output_dir={args.output_dir}",
        flush=True,
    )

    summary = enrich(api_key, places, args.output_dir)

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
