"""Apply the Phase 5.3 home-property-services data-quality audit decisions.

Mirrors apply_phase5_2_on_the_water_audit.py:
id-prefix-keyed dicts, --dry-run first, idempotent, sets updated_at,
self-verifies via /category/<slug> rendering count for the affected slugs.

Source of truth for the decisions:
``outputs/phase5_3_home_property_pre_load_audit.md``

Usage:
    python outputs/apply_phase5_3_home_property_audit.py --dry-run
    python outputs/apply_phase5_3_home_property_audit.py

Net effect (per audit doc §6):
    /category/home-property-services : 245  -> 230  (-16 out, +1 Stanley Steemer)
    /category/on-the-water           : 100  -> 119  (+16 misroutes/storage, +3 Slice B NULL)
    /category/shopping-essentials    : (-1 Stanley Steemer)
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
# at runtime — UUID prefixes are practically unique within the slice sizes.
# Cross-list policy: NO cross-list for V1 (follows 5.2 close-out §3.2). Each
# entity gets exactly one EntityCategory row after this apply.

# Slice A — 16 RE-ROUTE OUT of home-property-services → on-the-water
# (3 sustainability-fallback misroutes + 13 boat-named storage facilities)
REROUTE_OUT_FROM_HPS: dict[str, str] = {
    # 3 high-confidence misroutes (sustainability fallback caught powersports
    # businesses by their service/supplier primary_type):
    "54e3c237": "on-the-water",  # Sandbar Powersports (313 reviews)
    "23244621": "on-the-water",  # Horizon MotorSports (53)
    "4d88c09e": "on-the-water",  # Campbell Cove Complex (19)

    # 13 boat-named storage facilities (cross-list policy → primary on-the-water):
    "79e88dce": "on-the-water",  # Island Storage & Marine (53)
    "7e994b21": "on-the-water",  # Dave's Boat & RV Storage (42)
    "31163faf": "on-the-water",  # Havasu Boat Storage (35)
    "3954a1bd": "on-the-water",  # Boat Storage of Lake Havasu (21)
    "8947770e": "on-the-water",  # Depot Storage Boat and RV (17)
    "2fabfe90": "on-the-water",  # Lakeside Boat & RV Storage (11)
    "1ffd4559": "on-the-water",  # Havasu Boat & RV Storage (10)
    "0b5ffd7c": "on-the-water",  # Countryshire Boat & RV Storage (7)
    "eeec35a8": "on-the-water",  # Havasu Boat & Storage (4)
    "2e91b06e": "on-the-water",  # Advantage Boats & RV Storage (3)
    "5e600363": "on-the-water",  # Prestige Boat and RV Storage (1)
    "3da2460d": "on-the-water",  # Absolute Boat & RV Storage (-)
    "f7cab489": "on-the-water",  # Riviera View Boat & RV Storage (-)
}

# Slice B — 3 NULL-category_id residuals → on-the-water + EntityCategory insert
# (carry-forward from 5.2; primary_type was unusual so 5.2's fallback table missed them)
REROUTE_IN_TO_OTW_FROM_NULL: list[str] = [
    "e4a788d8",  # Havasu Watercraft Rental (real_estate_agency primary)
    "13b0ba9e",  # Butters Boat valet & Concierge services (transportation_service)
    "51a41647",  # London Bridge (bridge primary)
]

# Slice D — 1 RE-ROUTE INTO home-property-services from shopping-essentials
# (carpet cleaning is home_services, not retail)
REROUTE_IN_TO_HPS_FROM_SHOPPING: list[str] = [
    "fee7df69",  # Stanley Steemer (10 reviews — verified via post-load audit)
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
        needed_slugs = (
            "on-the-water",
            "home-property-services",
            "shopping-essentials",
        )
        for needed in needed_slugs:
            if needed not in slug_to_id:
                print(f"ERROR: Category.slug={needed!r} not found.", file=sys.stderr)
                return 2

        print("=" * 70)
        print("Slice A — RE-ROUTE OUT of /category/home-property-services")
        print("=" * 70)
        out_done = 0
        out_missing = 0
        for prefix, target_slug in REROUTE_OUT_FROM_HPS.items():
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
        print("Slice B — RE-ROUTE INTO /category/on-the-water from NULL category_id")
        print("=" * 70)
        slice_b_done = 0
        slice_b_missing = 0
        for prefix in REROUTE_IN_TO_OTW_FROM_NULL:
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  MISSING entity_id prefix={prefix!r}")
                slice_b_missing += 1
                continue
            _route_entity_to_slug(session, ent.id, "on-the-water", slug_to_id)
            print(f"  {ent.name!r}  ->  on-the-water")
            slice_b_done += 1
        print(f"  total: {slice_b_done} re-routed, {slice_b_missing} missing")
        print()

        print("=" * 70)
        print("Slice D — RE-ROUTE INTO /category/home-property-services from shopping")
        print("=" * 70)
        slice_d_done = 0
        slice_d_missing = 0
        for prefix in REROUTE_IN_TO_HPS_FROM_SHOPPING:
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  MISSING entity_id prefix={prefix!r}")
                slice_d_missing += 1
                continue
            _route_entity_to_slug(session, ent.id, "home-property-services", slug_to_id)
            print(f"  {ent.name!r}  ->  home-property-services")
            slice_d_done += 1
        print(f"  total: {slice_d_done} re-routed, {slice_d_missing} missing")
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
            "home-property-services",
            "on-the-water",
            "shopping-essentials",
            "eat-drink",
        ):
            count = session.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT e.id)
                    FROM entities e
                    JOIN entity_categories ec ON ec.entity_id = e.id
                    JOIN categories c ON c.id = ec.category_id
                    WHERE c.slug = :slug AND e.is_active = 1
                    """
                ),
                {"slug": slug},
            ).scalar()
            print(f"  /category/{slug:30s} : {count}")

        # Sanity check residual NULL category_id (should be 0 after Slice B)
        print()
        n_null = session.execute(
            text("SELECT COUNT(*) FROM providers WHERE category_id IS NULL")
        ).scalar()
        print(f"  providers w/ category_id IS NULL : {n_null}  (expected 0 if Slice B clean)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
