"""Apply the Phase 5.2 on-the-water data-quality audit decisions.

Mirrors the 5.1 apply-script pattern (apply_eat_drink_cleanup.py,
apply_provider_category_id_backfill.py, apply_on_the_water_promote_unmapped.py):
id-keyed dict, --dry-run first, idempotent, sets updated_at, self-verifies
via /category/<slug> rendering count for the affected slugs.

Source of truth for the decisions:
``outputs/phase5_2_on_the_water_data_quality_audit.md``

Usage:
    python outputs/apply_phase5_2_on_the_water_audit.py --dry-run
    python outputs/apply_phase5_2_on_the_water_audit.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, text  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Provider  # noqa: E402

# Audit decisions keyed by entity_id (first 8 chars of UUID, as printed in
# the audit inventory). Matched against full entity_id with LIKE 'prefix%'
# at runtime — safe because UUID prefixes are practically unique within
# 73+41+35 = 149 rows. Operator can flip any 'KEEP' default to a re-route
# action by adding an entry here.

# Slice A — 73 entities currently at /category/on-the-water — RE-ROUTE OUT
REROUTE_OUT_FROM_OTW: dict[str, str] = {
    # entity_id_prefix : target_slug
    "76280ea0": "auto-rv-fuel",            # 3-T's RV Products, Inc
    "6f453929": "lodging-vacation-rentals", # JR RV Rentals
}

# Slice B + C — RE-ROUTE INTO on-the-water
REROUTE_IN_TO_OTW: list[str] = [
    # Slice B: auto-rv-fuel (2)
    "e15c7638",  # Marine One Motorsports
    "aa47b572",  # Connolly Marine Performance

    # Slice C: shopping-essentials boat manufacturers (10)
    "ca6b3ea1",  # Cheetah Power Boats
    "5cc611eb",  # Advantage Boats
    "e7f95f35",  # Domn8er Power Boats
    "8af3d328",  # Hallett Boats
    "351532b5",  # HTM Performance Boats
    "cd69eba9",  # Interceptor Boats Lake Havasu
    "daf7b64e",  # Nordic Boats
    "e132f4fc",  # Maxed Out Marine
    "34f69bdc",  # R & D Marine
    "516d455c",  # IMAGE MARINE

    # Marine retail / parts (6)
    "1fdedd6d",  # West Marine
    "4abf5327",  # Marina Store
    "e34bd1a2",  # Total Marine Pros and Powersports
    "537f371d",  # Alco Marine Sales & Services
    "ea22e86f",  # Germaine Marine
    "eff14e6f",  # Shimmer Boat Service

    # Watersports rentals / services (5)
    "f68da5e2",  # All Seasons Water Sports
    "99028be4",  # Nautical Watersports
    "cce85063",  # Pro Watercraft
    "9118ee9d",  # Wet Monkey Powersport Rentals
    "ef949e05",  # Wolf Watersports

    # Fishing (3)
    "8fb10bfa",  # Bass Tackle Master
    "ca465d30",  # Mc Coy Fishing Line Inc
    "c13c022f",  # Project 72 Custom Baits

    # Marine services (3)
    "ad258025",  # Fallon Marine LLC
    "2d7ab66d",  # Prestige Marine
    "9ae51449",  # Xtreme Speed And Marine
]


def _resolve_entity_by_prefix(session, prefix: str) -> Entity | None:
    """Find entity whose id starts with the 8-char prefix used in audit doc."""
    return session.scalars(
        select(Entity).where(Entity.id.like(f"{prefix}%"))
    ).first()


def _route_entity_to_slug(
    session, entity_id: str, target_slug: str, slug_to_id: dict[str, int]
) -> None:
    """Atomically replace all EntityCategory rows for the entity with a
    single (entity_id, target_id, is_primary=True) row, and set the
    matching Provider.category_id."""
    target_id = slug_to_id[target_slug]
    session.execute(
        delete(EntityCategory).where(EntityCategory.entity_id == entity_id)
    )
    session.add(
        EntityCategory(
            entity_id=entity_id,
            category_id=target_id,
            is_primary=True,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    prov = session.scalars(
        select(Provider).where(Provider.entity_id == entity_id)
    ).first()
    if prov is not None:
        prov.category_id = target_id
        prov.updated_at = datetime.now(UTC).replace(tzinfo=None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; roll back; no DB writes.",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        slug_to_id: dict[str, int] = {
            c.slug: c.id for c in session.scalars(select(Category)).all()
        }
        for needed in ("on-the-water", "auto-rv-fuel", "lodging-vacation-rentals"):
            if needed not in slug_to_id:
                print(f"ERROR: Category.slug={needed!r} not found.", file=sys.stderr)
                return 2

        print("=" * 70)
        print("RE-ROUTE OUT of /category/on-the-water")
        print("=" * 70)
        out_done = 0
        out_missing = 0
        for prefix, target_slug in REROUTE_OUT_FROM_OTW.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  MISSING entity_id prefix={prefix!r} (target={target_slug})")
                out_missing += 1
                continue
            _route_entity_to_slug(session, ent.id, target_slug, slug_to_id)
            print(f"  {ent.name!r}  ->  {target_slug}")
            out_done += 1
        print(f"  total: {out_done} re-routed, {out_missing} missing")
        print()

        print("=" * 70)
        print("RE-ROUTE INTO /category/on-the-water")
        print("=" * 70)
        in_done = 0
        in_missing = 0
        for prefix in REROUTE_IN_TO_OTW:
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  MISSING entity_id prefix={prefix!r}")
                in_missing += 1
                continue
            _route_entity_to_slug(session, ent.id, "on-the-water", slug_to_id)
            print(f"  {ent.name!r}  ->  on-the-water")
            in_done += 1
        print(f"  total: {in_done} re-routed, {in_missing} missing")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify
        print()
        print("=" * 70)
        print("Self-verify — /category/<slug> rendering counts (post-apply)")
        print("=" * 70)
        for slug in (
            "on-the-water",
            "auto-rv-fuel",
            "shopping-essentials",
            "lodging-vacation-rentals",
        ):
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
            marker = " <-- target" if slug == "on-the-water" else ""
            print(f"  /category/{slug:<28} {count}{marker}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
