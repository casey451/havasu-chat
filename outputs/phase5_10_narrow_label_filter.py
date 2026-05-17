"""Phase 5.10 1 discovery -- Narrow-scope wrapper around GooglePlacesClient.

Phase 5.10's kickoff 1 commits to a **Narrow scope**: only 5 of the labels
in the `lodging-vacation-rentals` slug's two-domain bundle are in-scope
for the Layer 1 Google scrape. All `lake_recreation`-domain labels are
deferred to V1.5:

  - **Marina / boat-shape lake_recreation labels** (marinas, boat rentals,
    fishing charters, boat dealers, boat repair, etc.) -- already absorbed
    by Phase 5.2's on-the-water scrape via the
    ``(None, "lake_recreation") -> "on-the-water"`` catch-all at
    ``scripts/places_load._DISCOVERY_DOMAIN_FALLBACK:216``.
  - **RV / campground lake_recreation labels** (RV parks, RV rentals, RV
    dealers, RV repair, campgrounds) -- RV parks already in cat-10 via
    the pre-Phase-5 ``rv_park`` direct mapping in ``_PRIMARY_TYPE_MAP``;
    campgrounds + RV dealers/rentals can be re-evaluated per-label in
    V1.5. The 5.10 0 spot-check empirically confirms 14 RV parks +
    6 campgrounds + 2 mobile home parks + 1 camping cabin + 1 service
    (JR RV Rentals) already in cat-10 (24 of the 31 pre-existing
    entries) -- they got there via the ``rv_park`` direct map or the
    ``lodging`` direct map's secondary-types[] first-match behavior.

The standard ``python -m scripts.places_discovery --category
lodging-vacation-rentals`` dispatch would pull both domains per
``DISCOVERY_CATEGORY_TO_DOMAINS["lodging-vacation-rentals"] =
frozenset({"lodging", "lake_recreation"})``. This wrapper short-circuits
to just the 5 in-scope lodging-domain labels by pre-filtering the
categories list before calling ``GooglePlacesClient.sweep_discovery``.
Mirrors 5.9's narrow-label-filter shape exactly (same Path A.2 pattern --
standalone outputs/ wrapper, no production code touched).

**One-shot script.** After Phase 5.10 ships, this file can be git-removed
in the close-out commit OR kept as an audit-trail artifact under
``outputs/`` (same shape as 5.7/5.8/5.9's narrow-label filters).

Discovery is the ONLY pipeline step that needs the narrow filter:

  - **Discovery** (this script) writes ``discovery_unique.jsonl`` with
    only rows from the 5 in-scope lodging labels.
  - **Enrichment** (``python -m scripts.places_enrichment --limit 200``)
    reads ``discovery_unique.jsonl`` row-by-row -- no per-category filter;
    only sees the 5-label rows because discovery already filtered.
  - **Load** (``python -m scripts.places_load --category
    lodging-vacation-rentals``) reads the enrichment output and routes
    via ``_resolve_category_id`` -- the ``lodging-vacation-rentals``
    slug accepts both ``lodging`` AND ``lake_recreation`` domains; the
    pre-existing ``"lodging": ("lodging-vacation-rentals", "commercial")``
    direct mapping in ``_PRIMARY_TYPE_MAP`` catches most lodging-shape
    rows (per 5.10 0 spot-check evidence: 4 distinct non-mapped primary
    types are landing in cat-10 today via the secondary-types[]
    first-match behavior). Conditional sustainability commit deferred
    to 1 load output per kickoff 1 forecast (95% no-commit, 5% Option A).

Usage (mirrors ``python -m scripts.places_discovery`` flag shape):

    python outputs/phase5_10_narrow_label_filter.py --dry-run
        # 1-label dry-run (hotels only), very cheap (~$0.05-0.15)
    python outputs/phase5_10_narrow_label_filter.py
        # full 5-label sweep (~$0.30-0.60)

Then continue with the standard chain:

    python -m scripts.places_enrichment --limit 200
    python -m scripts.places_load --category lodging-vacation-rentals --dry-run
    python -m scripts.places_load --category lodging-vacation-rentals

Environment:
    ``GOOGLE_PLACES_API_KEY`` -- required (same as places_discovery).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow ``python outputs/phase5_10_narrow_label_filter.py`` to import
# from the repo root, in addition to the standard ``python -m``
# invocation. Running a .py file via ``python <path>`` only adds the
# file's directory to sys.path, not the repo root; ``app.*`` imports
# would fail without this. (5.7 boot session caught this at first
# dry-run smoke; mirror it correctly first time per 5.8/5.9 discipline.)
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

# Phase 5.10 Narrow scope -- the 5 in-scope labels per kickoff 1.
# All 5 are domain=lodging (places_categories.json lines 178-182). All
# lake_recreation-domain labels (24 in the json, all in the
# lodging-vacation-rentals bundle per DISCOVERY_CATEGORY_TO_DOMAINS)
# are deferred to V1.5: marina/boat shape absorbed by 5.2 on-the-water;
# RV parks already in cat-10 via pre-Phase-5 ``rv_park`` direct map;
# campgrounds + RV dealers/rentals re-evaluable per-label in V1.5.
NARROW_LABELS: frozenset[str] = frozenset(
    {
        # lodging (5)
        "hotels",
        "motels",
        "resorts",
        "vacation rentals",
        "bed and breakfast",
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
        help="Run only the dry-run sample (1 label -- hotels -- very "
        "cheap, ~$0.05-0.15). Without --dry-run: full 5-label sweep "
        "(~$0.30-0.60).",
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

    # Step 1: load the full two-domain bundle the standard
    # ``--category lodging-vacation-rentals`` dispatch would see (both
    # lodging + lake_recreation domains).
    try:
        all_cats = load_categories_for_discovery(
            args.categories_file,
            dry_run=False,  # we do our own narrow filter; don't intersect with the legacy 5-label dry-run set
            category_slug="lodging-vacation-rentals",
        )
    except SystemExit as e:
        code = e.code
        if isinstance(code, int):
            return code
        return 1

    # Step 2: narrow to the 5 in-scope labels per kickoff 1.
    narrow_cats = [c for c in all_cats if c.get("label", "") in NARROW_LABELS]

    if len(narrow_cats) != len(NARROW_LABELS):
        present = {c.get("label", "") for c in narrow_cats}
        missing = NARROW_LABELS - present
        print(
            f"ERROR: Expected {len(NARROW_LABELS)} in-scope labels but "
            f"only found {len(narrow_cats)} in places_categories.json. "
            f"Missing: {sorted(missing)}. Verify the file is HEAD-clean "
            "(recurring corruption pattern -- see kickoff 0 item 6).",
            file=sys.stderr,
        )
        return 2

    # Step 3: if --dry-run, further reduce to a single label (hotels)
    # to keep dispatch cheap. Otherwise sweep all 5. Hotels picked over
    # resorts / motels / vacation rentals / B&B as the dry-run label
    # because LHC hotel density is the highest of the 5 (tourism focus
    # + chain presence), and hotel reviews tend to be abundant -- the
    # densest signal for a cheap smoke test.
    if args.dry_run:
        narrow_cats = [c for c in narrow_cats if c.get("label") == "hotels"]

    mode = "dry-run (hotels only)" if args.dry_run else "full (5 labels)"
    label_list = ", ".join(c["label"] for c in narrow_cats)
    print(
        f"[phase5_10-narrow-discovery] mode={mode} "
        f"category=lodging-vacation-rentals "
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
