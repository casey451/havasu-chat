"""Backfill ``Provider.category_id`` + ``EntityCategory`` for Phase 5.1
rows that were loaded before scripts/places_load.py set ``category_id``.

Surfaced by the Phase 5.2 §0 pre-flight diagnostic (``outputs/
diagnose_category_id_gap.py``) — at HEAD, 287 of 287 ``food_drink``
Providers had ``category_id IS NULL`` and 0 had ``EntityCategory``
linkage to the ``eat-drink`` slug, meaning ``/category/eat-drink``
rendered 0 entities (Phase 5.1 gate item 5 retroactively false).

This script reverses that for the unambiguous legacy → Tier-1 mappings
below. Ambiguous legacy strings (``fitness_sports``,
``entertainment_attractions``, ``childcare_education``) are flagged but
NOT backfilled — they need an operator decision since the legacy domain
maps to multiple Tier-1 slugs.

Pattern matches the Phase 5.1 apply-script convention
(``apply_eat_drink_cleanup.py``, ``apply_heat_exposure.py``,
``apply_crowd_notes_top17.py``): ``--dry-run`` first, idempotent (skips
rows already linked), sets ``updated_at`` explicitly, self-verifies via
post-run distribution query.

Usage:
    python outputs/apply_provider_category_id_backfill.py --dry-run
    python outputs/apply_provider_category_id_backfill.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

# Make repo importable when invoked as ``python outputs/...``
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, EntityCategory, Provider  # noqa: E402

# Legacy ``Provider.category`` string -> Tier-1 ``Category.slug``.
# Mirrors ``app/contrib/google_places_scraper.DISCOVERY_CATEGORY_TO_DOMAINS``
# inverted, restricted to the unambiguous direction (one legacy domain ->
# exactly one Tier-1 slug). Multi-target legacy values stay unmapped here
# and surface in the AMBIGUOUS bucket for operator review.
LEGACY_TO_SLUG: dict[str, str] = {
    "food_drink": "eat-drink",
    "lake_recreation": "on-the-water",
    "home_services": "home-property-services",
    "health_medical": "health-wellness-care",
    "auto": "auto-rv-fuel",
    "retail": "shopping-essentials",
    "lodging": "lodging-vacation-rentals",
    "pets": "pets",
    "religion_community": "public-civic-resources",
}

# Multi-target legacy domains — unambiguously map to *no* single Tier-1
# slug. Listed here so the script can surface counts during the audit
# pass without silently skipping them.
AMBIGUOUS_LEGACY: set[str] = {
    "fitness_sports",                # health-wellness-care | outdoors-parks-trails | classes-sports-recreation
    "entertainment_attractions",     # events | outdoors-parks-trails
    "childcare_education",           # classes-sports-recreation | (others)
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
        # Pre-fetch slug -> Category.id once.
        slug_to_id: dict[str, int] = {
            c.slug: c.id for c in session.scalars(select(Category)).all()
        }
        for legacy, slug in LEGACY_TO_SLUG.items():
            if slug not in slug_to_id:
                print(
                    f"ERROR: Category.slug={slug!r} (mapped from "
                    f"legacy {legacy!r}) not present in categories table.",
                    file=sys.stderr,
                )
                return 2

        # Audit pass — read counts before changing anything.
        print("=" * 70)
        print("Audit — providers grouped by legacy category, category_id state")
        print("=" * 70)
        rows = session.execute(
            select(
                Provider.category,
                Provider.category_id.is_not(None).label("has_cat_id"),
            )
        ).all()
        from collections import Counter

        legacy_state: Counter[tuple[str | None, bool]] = Counter()
        for r in rows:
            legacy_state[(r.category, r.has_cat_id)] += 1
        for (legacy, has_id), n in sorted(legacy_state.items()):
            tag = "OK" if has_id else "NULL"
            mapped = LEGACY_TO_SLUG.get(legacy or "", None)
            note = f" -> {mapped}" if mapped else (
                "  (AMBIGUOUS)" if legacy in AMBIGUOUS_LEGACY else "  (no Tier-1 mapping)"
            )
            print(f"  {legacy!r:>30} category_id={tag:<4} n={n:<5}{note}")
        print()

        # Backfill pass — for each unambiguous legacy mapping, find rows
        # where category_id IS NULL, set it, and ensure EntityCategory
        # exists.
        provider_updates = 0
        entity_category_inserts = 0
        skipped_already_linked = 0

        for legacy, target_slug in LEGACY_TO_SLUG.items():
            target_id = slug_to_id[target_slug]
            providers = session.scalars(
                select(Provider).where(
                    Provider.category == legacy,
                    Provider.category_id.is_(None),
                )
            ).all()
            if not providers:
                continue
            print(
                f"  legacy={legacy!r} -> slug={target_slug!r} (id={target_id}): "
                f"{len(providers)} provider(s) to backfill"
            )
            for prov in providers:
                # Set Provider.category_id (and stamp updated_at).
                prov.category_id = target_id
                prov.updated_at = now_naive
                provider_updates += 1

                # Ensure EntityCategory linkage idempotently.
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

        print()
        print("=" * 70)
        print("Backfill summary")
        print("=" * 70)
        print(f"  Provider.category_id updates : {provider_updates}")
        print(f"  EntityCategory inserts       : {entity_category_inserts}")
        print(f"  Skipped (link already exists): {skipped_already_linked}")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify — re-run the route's filter to confirm rendering count.
        # Mirrors app/api/routes/category_pages.py:_select_entities_for_category
        # via raw SQL so the diagnostic matches the route 1:1.
        print()
        print("=" * 70)
        print("Self-verify — entities rendering per /category/<slug>")
        print("=" * 70)
        from sqlalchemy import text

        for slug in ("eat-drink", "on-the-water"):
            count = session.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT e.id)
                    FROM entities e
                    JOIN entity_categories ec ON ec.entity_id = e.id
                    JOIN categories c ON c.id = ec.category_id
                    LEFT JOIN providers p ON p.entity_id = e.id
                    WHERE e.is_active = 1
                      AND c.slug = :slug
                      AND (
                        e.entity_type != 'commercial'
                        OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0)
                      )
                    """
                ),
                {"slug": slug},
            ).scalar_one()
            print(f"  /category/{slug}: {count} entities rendering")

    return 0


if __name__ == "__main__":
    sys.exit(main())
