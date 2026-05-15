"""Promote Phase 5.2 lake_recreation Providers from operator queue to
on-the-water when their Google ``primary_type`` is a known catch-all
(``service``, ``tour_agency``, ``tourist_attraction``, etc.) that the
narrower ``google_types_mapping.py`` table can't unambiguously route.

Surfaced by Phase 5.2 §1 Layer 1 load post-mortem: of 224 inserted rows
(``category='lake_recreation'``), only 4 landed at /category/on-the-water
(the marinas with ``primary_type='marina'``). 71 inserted rows landed
in the operator queue (``category_id=None``) because their primary type
wasn't in google_types_mapping. Examining the discovery labels they came
from (boat repair, boat tours, parasailing, fishing charters, fishing
guides, bait and tackle, etc.) — they're legitimately on-the-water,
just tagged generically by Google.

This script promotes them to on-the-water with operator-curated guard
rails: an EXCLUDE_PRIMARY_TYPES set keeps obvious false positives out.
The companion google_types_mapping.py extension (commit pair) catches
future loads with the unambiguous types (fishing_pier, ferry_service);
this script handles the catch-alls that need an operator decision.

Pattern matches the Phase 5.1 apply-script convention (--dry-run first,
idempotent, sets updated_at, self-verifies via post-run /category/<slug>
rendering count).

Usage:
    python outputs/apply_on_the_water_promote_unmapped.py --dry-run
    python outputs/apply_on_the_water_promote_unmapped.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

# Make repo importable when invoked as ``python outputs/...``
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, EntityCategory, Provider  # noqa: E402

# Cutoff for "this load" — only promote rows scraped on or after this
# date. Prevents the script from accidentally re-categorizing pre-5.2
# rows that may already have intentional category_id=None state.
SCRAPED_AT_CUTOFF = "2026-05-15"

# Google primary types that DEFINITELY shouldn't go to on-the-water
# even though their Provider was discovered via lake_recreation labels.
# Operator-curated; expand as the audit pass surfaces edge cases.
EXCLUDE_PRIMARY_TYPES: set[str] = {
    "real_estate_agency",   # one-off mis-discovery via "boat storage" probably
    "bridge",               # London Bridge is iconic but not a venue/business
    "transportation_service",   # could be airport shuttle, etc. — operator decides
}

# Optional: types known to be on-the-water that we want to log as
# "explicitly promoted" rather than "promoted via catch-all" (purely
# cosmetic — both result in the same DB write).
OBVIOUS_ON_THE_WATER_TYPES: set[str] = {
    "fishing_pier",
    "ferry_service",
    "tour_agency",
    "tourist_attraction",
    "tourist_information_center",
    "service",
    "point_of_interest",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; no DB writes.",
    )
    args = parser.parse_args()

    now_naive = datetime.now(UTC).replace(tzinfo=None)

    with SessionLocal() as session:
        target_id = session.scalar(
            select(Category.id).where(Category.slug == "on-the-water")
        )
        if target_id is None:
            print("ERROR: Category.slug='on-the-water' not found.", file=sys.stderr)
            return 2

        # Audit pass — show distribution of unmapped lake_recreation rows
        # from this load by primary_type.
        print("=" * 70)
        print(
            f"Audit — lake_recreation Providers loaded >= {SCRAPED_AT_CUTOFF} "
            f"with category_id=NULL"
        )
        print("=" * 70)
        candidates = session.scalars(
            select(Provider).where(
                Provider.category == "lake_recreation",
                Provider.category_id.is_(None),
                Provider.last_google_scraped_at >= datetime.fromisoformat(SCRAPED_AT_CUTOFF),
            )
        ).all()

        from collections import Counter
        by_type: Counter[str | None] = Counter()
        for p in candidates:
            by_type[p.google_primary_category] += 1

        print(f"  total candidates: {len(candidates)}")
        for ptype, n in sorted(by_type.items(), key=lambda kv: -kv[1]):
            decision = "EXCLUDE" if ptype in EXCLUDE_PRIMARY_TYPES else "PROMOTE"
            print(f"  primary_type={ptype or '<none>':<32} n={n:<4} -> {decision}")
        print()

        # Promote pass.
        provider_updates = 0
        entity_category_inserts = 0
        skipped_excluded = 0
        skipped_already_linked = 0

        for prov in candidates:
            if prov.google_primary_category in EXCLUDE_PRIMARY_TYPES:
                skipped_excluded += 1
                continue
            prov.category_id = target_id
            prov.updated_at = now_naive
            provider_updates += 1

            if not prov.entity_id:
                continue
            existing_link = session.scalars(
                select(EntityCategory).where(
                    EntityCategory.entity_id == prov.entity_id,
                    EntityCategory.category_id == target_id,
                )
            ).first()
            if existing_link is None:
                session.add(
                    EntityCategory(
                        entity_id=prov.entity_id,
                        category_id=target_id,
                        is_primary=True,
                        created_at=now_naive,
                    )
                )
                entity_category_inserts += 1
            else:
                skipped_already_linked += 1

        print("=" * 70)
        print("Promotion summary")
        print("=" * 70)
        print(f"  Provider.category_id set -> on-the-water : {provider_updates}")
        print(f"  EntityCategory inserts                   : {entity_category_inserts}")
        print(f"  Skipped (excluded primary_type)          : {skipped_excluded}")
        print(f"  Skipped (link already exists)            : {skipped_already_linked}")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify — re-run the route filter for /category/on-the-water.
        print()
        print("=" * 70)
        print("Self-verify — entities rendering at /category/on-the-water")
        print("=" * 70)
        count = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT e.id)
                FROM entities e
                JOIN entity_categories ec ON ec.entity_id = e.id
                JOIN categories c ON c.id = ec.category_id
                LEFT JOIN providers p ON p.entity_id = e.id
                WHERE e.is_active = 1
                  AND c.slug = 'on-the-water'
                  AND (
                    e.entity_type != 'commercial'
                    OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0)
                  )
                """
            )
        ).scalar_one()
        print(f"  /category/on-the-water: {count} entities rendering")
        print()
        print(
            "Phase 5.2 §6 acceptance gate item 1 (25+ entries) "
            f"{'CLEARED' if count >= 25 else 'NOT YET MET'}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
