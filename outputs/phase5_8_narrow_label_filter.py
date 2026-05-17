"""Phase 5.8 §1 discovery — Narrow-scope wrapper around GooglePlacesClient.

Phase 5.8's kickoff §1 commits to a **Narrow scope**: only 7 of the 10
labels in the `events` slug's domain bundle are in-scope for the Layer
1 Google scrape. The other 3 are deferred to 5.7's lane:

  - **3 cat-7 outdoors-parks-trails labels** (parks, golf courses, mini
    golf) — already absorbed by Phase 5.7's Narrow scope. Re-scraping
    them in 5.8 would either (a) double-categorize the existing cat-7
    entities via the ambig path, or (b) fight the 5.7 catch-all
    ``(None, "entertainment_attractions") -> "outdoors-parks-trails"``.
    Deferred.

The standard ``python -m scripts.places_discovery --category events``
dispatch would pull all 10 labels per
``DISCOVERY_CATEGORY_TO_DOMAINS["events"] =
frozenset({"entertainment_attractions"})``. This wrapper short-
circuits to just the 7 in-scope labels by pre-filtering the categories
list before calling ``GooglePlacesClient.sweep_discovery``.

**One-shot script.** After Phase 5.8 ships, this file can be
git-removed in the close-out commit OR kept as an audit-trail artifact
under ``outputs/`` (same shape as 5.7's
``outputs/phase5_7_narrow_label_filter.py``).

Discovery is the ONLY pipeline step that needs the narrow filter:

  - **Discovery** (this script) writes ``discovery_unique.jsonl`` with
    only rows from the 7 in-scope labels.
  - **Enrichment** (``python -m scripts.places_enrichment --limit 200``)
    reads ``discovery_unique.jsonl`` row-by-row — no per-category
    filter; only sees the 7-label rows because discovery already
    filtered.
  - **Load** (``python -m scripts.places_load --category events``)
    reads the enrichment output and routes via ``_resolve_category_id``
    — the ``events`` slug accepts ``entertainment_attractions`` domain;
    the 7 new ``_PRIMARY_TYPE_MAP`` entries shipped at ``0b426e1`` beat
    the 5.7 catch-all per the resolver order, so the 7 event
    primary_types land in cat-2 while wildlife_refuge /
    tourist_attraction remain routed to cat-7.

Usage (mirrors ``python -m scripts.places_discovery`` flag shape):

    python outputs/phase5_8_narrow_label_filter.py --dry-run
        # 1-label dry-run (event venues only), very cheap (~$0.10-0.20)
    python outputs/phase5_8_narrow_label_filter.py
        # full 7-label sweep (~$0.50-1.20)

Then continue with the standard chain:

    python -m scripts.places_enrichment --limit 200
    python -m scripts.places_load --category events --dry-run
    python -m scripts.places_load --category events

Environment:
    ``GOOGLE_PLACES_API_KEY`` — required (same as places_discovery).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow ``python outputs/phase5_8_narrow_label_filter.py`` to import from
# the repo root, in addition to the standard ``python -m`` invocation.
# Running a .py file via ``python <path>`` only adds the file's directory
# to sys.path, not the repo root; ``app.*`` imports would fail without
# this. (5.7 boot session caught this at first dry-run smoke; mirror it
# correctly first time.)
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

# Phase 5.8 Narrow scope — the 7 in-scope labels per kickoff §1.
# All 7 are domain=entertainment_attractions in
# scripts/places_categories.json (lines 184-193). The 3 deferred labels
# (mini golf, golf courses, parks) live in the same domain but are
# already absorbed by 5.7.
NARROW_LABELS: frozenset[str] = frozenset(
    {
        "event venues",
        "live music venues",
        "art galleries",
        "museums",
        "movie theaters",
        "bowling alleys",
        "arcades",
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
        help="Run only the dry-run sample (1 label — event venues — very "
        "cheap, ~$0.10-0.20). Without --dry-run: full 7-label sweep "
        "(~$0.50-1.20).",
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

    # Step 1: load the full 10-label bundle the standard
    # ``--category events`` dispatch would see.
    try:
        all_cats = load_categories_for_discovery(
            args.categories_file,
            dry_run=False,  # we do our own narrow filter; don't intersect with the legacy 5-label dry-run set
            category_slug="events",
        )
    except SystemExit as e:
        code = e.code
        if isinstance(code, int):
            return code
        return 1

    # Step 2: narrow to the 7 in-scope labels per kickoff §1.
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

    # Step 3: if --dry-run, further reduce to a single label (event
    # venues) to keep dispatch cheap. Otherwise sweep all 7.
    if args.dry_run:
        narrow_cats = [c for c in narrow_cats if c.get("label") == "event venues"]

    mode = "dry-run (event venues only)" if args.dry_run else "full (7 labels)"
    label_list = ", ".join(c["label"] for c in narrow_cats)
    print(
        f"[phase5_8-narrow-discovery] mode={mode} category=events "
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
