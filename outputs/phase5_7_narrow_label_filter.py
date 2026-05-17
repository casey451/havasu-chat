"""Phase 5.7 §1 discovery — Narrow-scope wrapper around GooglePlacesClient.

Phase 5.7's kickoff §1 commits to a **Narrow scope**: only 3 of the 21
labels in the `outdoors-parks-trails` slug's domain bundle are
in-scope for the Layer 1 Google scrape. The other 18 are deferred:

  - **11 `fitness_sports` labels** (gyms, yoga, pilates, crossfit,
    martial arts, jiu-jitsu, dance studios, swimming pools, tennis
    courts, pickleball, personal trainers) — deferred to V1.5 to avoid
    collision with the existing
    `(None, "fitness_sports") -> "health-wellness-care"` fallback in
    `scripts/places_load._DISCOVERY_DOMAIN_FALLBACK`. Phase 5.4 already
    absorbed gyms/yoga/pilates into HWC.

  - **7 indoor entertainment_attractions labels** (movie theaters,
    bowling alleys, arcades, museums, art galleries, live music
    venues, event venues) — semantic mismatch with "outdoors, parks &
    trails"; deferred to a future "indoor entertainment" or
    "civic-resources" phase.

The standard `python -m scripts.places_discovery --category
outdoors-parks-trails` dispatch would pull all 21 labels per
`DISCOVERY_CATEGORY_TO_DOMAINS["outdoors-parks-trails"] =
frozenset({"fitness_sports", "entertainment_attractions"})`. This
wrapper short-circuits to just the 3 in-scope labels by pre-filtering
the categories list before calling `GooglePlacesClient.sweep_discovery`.

**One-shot script.** After Phase 5.7 ships, this file can be
git-removed in the close-out commit OR kept as an audit-trail artifact
under `outputs/` (same shape as 5.2's `apply_on_the_water_*.py` etc.).

Discovery is the ONLY pipeline step that needs the narrow filter:

  - **Discovery** (this script) writes `discovery_unique.jsonl` with
    only rows from the 3 in-scope labels.
  - **Enrichment** (`python -m scripts.places_enrichment --limit 200`)
    reads `discovery_unique.jsonl` row-by-row — no per-category
    filter; only sees the 3-label rows because discovery already
    filtered.
  - **Load** (`python -m scripts.places_load --category
    outdoors-parks-trails`) reads the enrichment output and routes
    via `_resolve_category_id` — the `outdoors-parks-trails` slug
    accepts both `entertainment_attractions` AND `fitness_sports`
    domains, but only entertainment_attractions rows exist in the
    enrichment cache (because discovery filtered them out), so no
    spillover.

Usage (mirrors `python -m scripts.places_discovery` flag shape):

    python outputs/phase5_7_narrow_label_filter.py --dry-run
        # 3-label dry-run, very cheap (~$0.20)
    python outputs/phase5_7_narrow_label_filter.py
        # full 3-label sweep (~$0.30-0.70)

Then continue with the standard chain:

    python -m scripts.places_enrichment --limit 200
    python -m scripts.places_load --category outdoors-parks-trails --dry-run
    python -m scripts.places_load --category outdoors-parks-trails

Environment:
    ``GOOGLE_PLACES_API_KEY`` — required (same as places_discovery).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow ``python outputs/phase5_7_narrow_label_filter.py`` to import from
# the repo root, in addition to the standard ``python -m`` invocation.
# Running a .py file via ``python <path>`` only adds the file's directory
# to sys.path, not the repo root; `app.*` imports would fail without
# this. (5.7 boot session caught this at first dry-run smoke.)
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402
from app.contrib.google_places_scraper import (  # noqa: E402
    GooglePlacesClient,
    load_categories_for_discovery,
)

ensure_dotenv_loaded()

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATEGORIES_PATH = REPO_ROOT / "scripts" / "places_categories.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "places_pull"

# Phase 5.7 Narrow scope — the 3 in-scope labels per kickoff §1.
# All 3 are domain=entertainment_attractions in
# scripts/places_categories.json.
NARROW_LABELS: frozenset[str] = frozenset(
    {
        "parks",
        "golf courses",
        "mini golf",
    }
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run only the dry-run sample (very cheap, ~$0.20). Without "
        "--dry-run: full 3-label sweep (~$0.30-0.70).",
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

    # Step 1: load the full 21-label bundle the standard
    # --category outdoors-parks-trails dispatch would see.
    try:
        all_cats = load_categories_for_discovery(
            args.categories_file,
            dry_run=False,  # we do our own narrow filter; don't intersect with the legacy 5-label dry-run set
            category_slug="outdoors-parks-trails",
        )
    except SystemExit as e:
        code = e.code
        if isinstance(code, int):
            return code
        return 1

    # Step 2: narrow to the 3 in-scope labels per kickoff §1.
    narrow_cats = [c for c in all_cats if c.get("label", "") in NARROW_LABELS]

    if len(narrow_cats) != len(NARROW_LABELS):
        present = {c.get("label", "") for c in narrow_cats}
        missing = NARROW_LABELS - present
        print(
            f"ERROR: Expected {len(NARROW_LABELS)} in-scope labels but "
            f"only found {len(narrow_cats)} in places_categories.json. "
            f"Missing: {sorted(missing)}. Verify the file is HEAD-clean "
            "(recurring corruption pattern — see kickoff §0 item 6).",
            file=sys.stderr,
        )
        return 2

    # Step 3: if --dry-run, further reduce to a single label (parks)
    # to keep dispatch cheap. Otherwise sweep all 3.
    if args.dry_run:
        narrow_cats = [c for c in narrow_cats if c.get("label") == "parks"]

    mode = "dry-run (parks only)" if args.dry_run else "full (3 labels)"
    label_list = ", ".join(c["label"] for c in narrow_cats)
    print(
        f"[phase5_7-narrow-discovery] mode={mode} category=outdoors-parks-trails "
        f"categories={len(narrow_cats)} [{label_list}] "
        f"output_dir={args.output_dir}",
        flush=True,
    )

    # Step 4: dispatch identical to scripts/places_discovery.main()
    # from line 115 onward.
    client = GooglePlacesClient()
    summary = client.sweep_discovery(api_key, narrow_cats, args.output_dir)

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
