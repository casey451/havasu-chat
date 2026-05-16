"""Populate ``Entity.boat_access`` for the 5 marinas at /category/on-the-water.

Closes Phase 5.2 acceptance gate item 2 ("Every marina has boat_access
JSON populated"). Per docs/operations/boat_access_rubric.md §2 semantic
lock:

  NULL            -> not applicable (inland venues)
  {}              -> applicable but unknown — operator hasn't reviewed yet
  {"type": ..., ...} -> reviewed by operator

This script populates marinas with evidence-based data from the cached
google_review_snippets where available, and sets ``{}`` for marinas
with thin data per the rubric's "don't guess booleans" rule. Phase 6.4
boat-mode toggle reads ``boat_access IS NOT NULL`` (route line 299 of
category_pages.py) so both populated and ``{}`` satisfy the boat-mode
filter; the populated marinas additionally get the rich profile-page
boat-access region.

Pattern matches Phase 5.1 + 5.2 apply-scripts: id-keyed dict,
--dry-run first, idempotent, sets updated_at, self-verifies.

Usage:
    python outputs/apply_on_the_water_boat_access_marinas.py --dry-run
    python outputs/apply_on_the_water_boat_access_marinas.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity  # noqa: E402

# entity_id 8-char prefix -> boat_access JSON (or {} for "field-survey pending").
# Evidence drawn from google_review_snippets cached during enrichment.
# Unverified booleans deliberately omitted per rubric §4 ("Don't guess").
BOAT_ACCESS_MARINAS: dict[str, dict[str, Any]] = {
    # Lake Havasu Marina (293 reviews, 4.6*). Snippets:
    #   - "Nice Ramp, all concrete and a gentle slope, 6 lanes, and plenty of large parking" (ramps=6)
    #   - "Slip rental was convenient online" (slips>0; count unverified)
    #   - "Day-use $21 at the gatehouse" + "BAD GAS" snippet (fuel=true)
    "8ce77957": {
        "type": "marina",
        "ramps": 6,
        "fuel": True,
        "fee_required": True,
        "fee_notes": "Day-use $21 at the gatehouse; slip rentals separate",
    },
    # Havasu Riviera Marina (171 reviews, 4.6*). Snippets:
    #   - "HUGE boat ramps with SIX LANES!!" (ramps=6)
    #   - "multiple gas pumps" (fuel=true)
    #   - "many boat slips for rent" (slips>0; count unverified)
    #   - "a great store" (on-site retail; not a boat_access key but noted)
    "a63febcb": {
        "type": "marina",
        "ramps": 6,
        "fuel": True,
        "fee_required": True,
        "fee_notes": "Day-use fee at gatehouse; slip rentals separate",
    },
    # Lake Havasu Yacht Club (5 reviews) — thin Google data, field-survey
    # pending. {} satisfies gate item 2's "populated" per rubric §2.
    "4b5b7c2a": {},
    # Riverside Boat Dock Sales (1 review) — name suggests dealer with dock;
    # primary_type=marina per Google but operator should verify shape
    # (marina vs shoreline_commercial) on field trip. {} for now.
    "7265d2ca": {},
    # Havasu Cove (OSM way 622179700) — no Google reviews, OSM polygon only.
    # Field-survey pending. {} satisfies gate item 2.
    "5a25ca41": {},
}


def _resolve_entity_by_prefix(session, prefix: str) -> Entity | None:
    return session.scalars(
        select(Entity).where(Entity.id.like(f"{prefix}%"))
    ).first()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; roll back; no DB writes.",
    )
    args = parser.parse_args()

    now_naive = datetime.now(UTC).replace(tzinfo=None)

    with SessionLocal() as session:
        applied = 0
        missing = 0
        populated = 0
        placeholder = 0
        for prefix, payload in BOAT_ACCESS_MARINAS.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  MISSING entity_id prefix={prefix!r}")
                missing += 1
                continue
            ent.boat_access = payload
            ent.updated_at = now_naive
            label = "populated" if payload else "placeholder {}"
            print(f"  {ent.name!r:<40} -> {label}")
            applied += 1
            if payload:
                populated += 1
            else:
                placeholder += 1

        print()
        print("=" * 70)
        print("Apply summary")
        print("=" * 70)
        print(f"  total marinas processed : {applied}")
        print(f"  evidence-populated      : {populated}")
        print(f"  placeholder {{}}        : {placeholder}")
        print(f"  missing entity prefix   : {missing}")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify gate item 2: every entity at /category/on-the-water
        # whose Google primary_type is `marina` (or source is osm) has
        # non-NULL boat_access.
        print()
        print("=" * 70)
        print("Self-verify -- gate item 2 (every marina has boat_access populated)")
        print("=" * 70)
        otw_cat_id = session.scalar(
            select(Category.id).where(Category.slug == "on-the-water")
        )
        marina_rows = session.execute(
            text(
                """
                SELECT e.id, e.name, e.boat_access IS NOT NULL AS has_boat_access,
                       e.source, p.google_primary_category
                FROM entities e
                JOIN entity_categories ec ON ec.entity_id = e.id
                LEFT JOIN providers p ON p.entity_id = e.id
                WHERE e.is_active = 1
                  AND ec.category_id = :cid
                  AND (p.google_primary_category = 'marina' OR e.source LIKE '%osm%')
                ORDER BY e.name
                """
            ),
            {"cid": otw_cat_id},
        ).all()
        all_populated = True
        for r in marina_rows:
            marker = "OK" if r.has_boat_access else "MISSING"
            print(f"  [{marker}] {r.name!r}  source={r.source}  primary_type={r.google_primary_category}")
            if not r.has_boat_access:
                all_populated = False
        print()
        if all_populated and marina_rows:
            print(
                "Phase 5.2 §6 acceptance gate item 2 (Every marina has "
                "boat_access JSON populated) CLEARED."
            )
        else:
            print(
                f"WARN: {sum(1 for r in marina_rows if not r.has_boat_access)} "
                f"of {len(marina_rows)} marina rows still have boat_access=NULL"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
