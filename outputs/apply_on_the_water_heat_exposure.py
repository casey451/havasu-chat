"""Apply heat_exposure to all 100 on-the-water entities.

Closes Phase 5.2 acceptance gate item 5 ("heat_exposure set on every
entry"). Per the kickoff context + heat_exposure_priority_30_list.md
§3 lock, ``water_adjacent`` is the defining attribute for on-the-water
venues -- it's the default. Exceptions (INDOOR_OVERRIDES) are venues
where the customer experience happens inside a building: marine retail
stores, boat manufacturers, fishing supply shops. Mobile detailers and
service garages default to water_adjacent (their work is on boats /
at the lake) unless the operator flips them.

Pattern matches the 5.1 apply_heat_exposure.py: id-keyed dict,
--dry-run-first, idempotent, sets updated_at, self-verifies via
distribution query.

Allowed values per Entity model CHECK constraint:
NULL, 'indoor', 'shaded', 'outdoor', 'water_adjacent'.

Usage:
    python outputs/apply_on_the_water_heat_exposure.py --dry-run
    python outputs/apply_on_the_water_heat_exposure.py
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402

# Default for every on-the-water entity not overridden below.
DEFAULT_HEAT_EXPOSURE = "water_adjacent"

# Venues that should be ``indoor`` — customer experience happens inside
# a building rather than at the lake. Keyed by 8-char entity_id prefix
# (matches the audit inventory). Names included as comments for review.
INDOOR_OVERRIDES: dict[str, str] = {
    # Marine retail / showrooms (mostly inland strip-mall locations)
    "1fdedd6d": "West Marine",
    "516d455c": "IMAGE MARINE",
    "4abf5327": "Marina Store",
    "e34bd1a2": "Total Marine Pros and Powersports",
    "537f371d": "Alco Marine Sales & Services",
    "ea22e86f": "Germaine Marine",

    # Boat manufacturers (production facilities -- industrial parks)
    "ca6b3ea1": "Cheetah Power Boats",
    "8af3d328": "Hallett Boats",
    "e7f95f35": "Domn8er Power Boats",
    "351532b5": "HTM Performance Boats",
    "daf7b64e": "Nordic Boats",
    "cd69eba9": "Interceptor Boats Lake Havasu",
    "5cc611eb": "Advantage Boats",

    # Boat repair / service garages (no fixed lakeside location)
    "e132f4fc": "Maxed Out Marine",
    "34f69bdc": "R & D Marine",
    "eff14e6f": "Shimmer Boat Service",
    "2d7ab66d": "Prestige Marine",
    "ad258025": "Fallon Marine LLC",
    "9ae51449": "Xtreme Speed And Marine",

    # Fishing supply (tackle shops -- indoor retail)
    "8fb10bfa": "Bass Tackle Master",
    "ca465d30": "Mc Coy Fishing Line Inc",
    "c13c022f": "Project 72 Custom Baits",
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
        otw_cat_id = session.scalar(
            select(Category.id).where(Category.slug == "on-the-water")
        )
        if otw_cat_id is None:
            print("ERROR: Category.slug='on-the-water' not found.", file=sys.stderr)
            return 2

        # Resolve all on-the-water entities (post-audit count = 100).
        entities = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == otw_cat_id,
                Entity.is_active.is_(True),
            )
        ).all()
        print(f"[heat_exposure] {len(entities)} on-the-water entities discovered")

        # Build INDOOR override mapping by full entity_id once.
        indoor_entity_ids: dict[str, str] = {}
        for prefix, name in INDOOR_OVERRIDES.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  WARN: INDOOR_OVERRIDES prefix={prefix!r} ({name!r}) not found")
                continue
            indoor_entity_ids[ent.id] = name

        # Apply.
        applied_default = 0
        applied_indoor = 0
        already_correct = 0
        for ent in entities:
            target = "indoor" if ent.id in indoor_entity_ids else DEFAULT_HEAT_EXPOSURE
            if ent.heat_exposure == target:
                already_correct += 1
                continue
            ent.heat_exposure = target
            ent.updated_at = now_naive
            if target == "indoor":
                applied_indoor += 1
            else:
                applied_default += 1

        print()
        print("=" * 70)
        print("Apply summary")
        print("=" * 70)
        print(f"  set to water_adjacent (default) : {applied_default}")
        print(f"  set to indoor (override)        : {applied_indoor}")
        print(f"  already correct (no change)     : {already_correct}")
        print(f"  total entities                  : {len(entities)}")
        print()

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print("[apply] committed.")

        # Self-verify distribution.
        print()
        print("=" * 70)
        print("Self-verify -- heat_exposure distribution across on-the-water entities")
        print("=" * 70)
        dist: Counter[str | None] = Counter()
        for ent in session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == otw_cat_id,
                Entity.is_active.is_(True),
            )
        ).all():
            dist[ent.heat_exposure] += 1
        for k, n in sorted(dist.items(), key=lambda kv: -kv[1]):
            print(f"  {str(k):<20} {n}")
        null_count = dist.get(None, 0)
        print()
        if null_count == 0:
            print(
                "Phase 5.2 §6 acceptance gate item 5 (heat_exposure set on every "
                "entry) CLEARED."
            )
        else:
            print(
                f"WARN: {null_count} entities still have heat_exposure=NULL"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
