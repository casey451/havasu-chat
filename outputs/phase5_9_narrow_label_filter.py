"""Phase 5.9 §1 discovery — Narrow-scope wrapper around GooglePlacesClient.

Phase 5.9's kickoff §1 commits to a **Narrow scope**: only 9 of the 16
labels in the `classes-sports-recreation` slug's two-domain bundle are
in-scope for the Layer 1 Google scrape. The 7 deferred labels are all
HWC-absorbed fitness_sports labels:

  - **7 HWC-absorbed fitness_sports labels** (gyms, yoga studios,
    pilates studios, crossfit gyms, martial arts, jiu-jitsu, dance
    studios) — already absorbed by Phase 5.4's HWC scrape via the
    ``(None, "fitness_sports") -> "health-wellness-care"`` catch-all at
    ``scripts/places_load._DISCOVERY_DOMAIN_FALLBACK:260``. Re-scraping
    them in 5.9 would either (a) double-categorize existing HWC
    entities via the ambig path, or (b) fight the 5.4 catch-all. The
    9 in-scope direct ``_PRIMARY_TYPE_MAP`` entries shipped at
    ``0af5f73`` beat the 5.4 catch-all for the 4 cat-12-native fitness
    types (personal_trainer + swimming_pool + tennis_court +
    pickleball_court) — but leaving the 7 HWC-absorbed labels OUT of
    discovery prevents pulling new gym/yoga/pilates entities that
    would still route correctly (via the 5.4 catch-all to HWC) but
    would create cross-cat noise in the §2 audit.

The standard ``python -m scripts.places_discovery --category
classes-sports-recreation`` dispatch would pull all 16 labels per
``DISCOVERY_CATEGORY_TO_DOMAINS["classes-sports-recreation"] =
frozenset({"childcare_education", "fitness_sports"})``. This wrapper
short-circuits to just the 9 in-scope labels by pre-filtering the
categories list before calling ``GooglePlacesClient.sweep_discovery``.
Unlike 5.8 (single-domain bundle for ``events``), 5.9 spans TWO
domains — but the narrow filter is label-based, so the filter logic is
identical to 5.8's.

**One-shot script.** After Phase 5.9 ships, this file can be
git-removed in the close-out commit OR kept as an audit-trail artifact
under ``outputs/`` (same shape as 5.7/5.8's narrow-label filters).

Discovery is the ONLY pipeline step that needs the narrow filter:

  - **Discovery** (this script) writes ``discovery_unique.jsonl`` with
    only rows from the 9 in-scope labels (5 childcare_education + 4
    cat-12-native fitness_sports).
  - **Enrichment** (``python -m scripts.places_enrichment --limit 200``)
    reads ``discovery_unique.jsonl`` row-by-row — no per-category
    filter; only sees the 9-label rows because discovery already
    filtered.
  - **Load** (``python -m scripts.places_load --category
    classes-sports-recreation``) reads the enrichment output and
    routes via ``_resolve_category_id`` — the
    ``classes-sports-recreation`` slug accepts both
    ``childcare_education`` AND ``fitness_sports`` domains; the 9
    direct ``_PRIMARY_TYPE_MAP`` entries shipped at ``0af5f73`` beat
    the 5.4 ``(None, "fitness_sports") -> "health-wellness-care"``
    catch-all per the resolver order, so the 4 cat-12-native fitness
    types land in cat-12 (instead of cat-5); the new ``(None,
    "childcare_education") -> "classes-sports-recreation"`` catch-all
    (also at ``0af5f73``) covers any unmapped childcare_education
    primary_types.

Usage (mirrors ``python -m scripts.places_discovery`` flag shape):

    python outputs/phase5_9_narrow_label_filter.py --dry-run
        # 1-label dry-run (daycare only), very cheap (~$0.05-0.15)
    python outputs/phase5_9_narrow_label_filter.py
        # full 9-label sweep (~$0.50-1.20)

Then continue with the standard chain:

    python -m scripts.places_enrichment --limit 200
    python -m scripts.places_load --category classes-sports-recreation --dry-run
    python -m scripts.places_load --category classes-sports-recreation

Environment:
    ``GOOGLE_PLACES_API_KEY`` — required (same as places_discovery).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow ``python outputs/phase5_9_narrow_label_filter.py`` to import
# from the repo root, in addition to the standard ``python -m``
# invocation. Running a .py file via ``python <path>`` only adds the
# file's directory to sys.path, not the repo root; ``app.*`` imports
# would fail without this. (5.7 boot session caught this at first
# dry-run smoke; mirror it correctly first time.)
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

# Phase 5.9 Narrow scope — the 9 in-scope labels per kickoff §1.
# 5 are domain=childcare_education (places_categories.json lines
# 200-204); 4 are domain=fitness_sports (lines 136 + 143-145). The 7
# deferred fitness_sports labels (gyms, yoga studios, pilates studios,
# crossfit gyms, martial arts, jiu-jitsu, dance studios) are already
# absorbed by 5.4's HWC scrape via the
# ``(None, "fitness_sports") -> "health-wellness-care"`` catch-all.
NARROW_LABELS: frozenset[str] = frozenset(
    {
        # childcare_education (5)
        "daycare",
        "preschools",
        "tutoring",
        "music lessons",
        "driving schools",
        # fitness_sports — cat-12 native (4)
        "personal trainers",
        "swimming pools",
        "tennis courts",
        "pickleball",
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
        help="Run only the dry-run sample (1 label — daycare — very "
        "cheap, ~$0.05-0.15). Without --dry-run: full 9-label sweep "
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

    # Step 1: load the full 16-label bundle the standard
    # ``--category classes-sports-recreation`` dispatch would see (both
    # childcare_education + fitness_sports domains).
    try:
        all_cats = load_categories_for_discovery(
            args.categories_file,
            dry_run=False,  # we do our own narrow filter; don't intersect with the legacy 5-label dry-run set
            category_slug="classes-sports-recreation",
        )
    except SystemExit as e:
        code = e.code
        if isinstance(code, int):
            return code
        return 1

    # Step 2: narrow to the 9 in-scope labels per kickoff §1.
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

    # Step 3: if --dry-run, further reduce to a single label (daycare)
    # to keep dispatch cheap. Otherwise sweep all 9. Daycare picked
    # over personal trainers / tutoring as the dry-run label because
    # AZDHS-licensed childcare facilities have abundant Google
    # presence + reviews — the densest signal for a cheap smoke test.
    if args.dry_run:
        narrow_cats = [c for c in narrow_cats if c.get("label") == "daycare"]

    mode = "dry-run (daycare only)" if args.dry_run else "full (9 labels)"
    label_list = ", ".join(c["label"] for c in narrow_cats)
    print(
        f"[phase5_9-narrow-discovery] mode={mode} "
        f"category=classes-sports-recreation "
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
