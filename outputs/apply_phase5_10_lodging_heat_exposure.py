"""Apply heat_exposure to all lodging-vacation-rentals (cat-10) entities.

Closes Phase 5.10 acceptance gate item 5 ("heat_exposure non-NULL on
every entry"). Per kickoff 4: ``indoor`` is the default for most
cat-10 entries -- hotels, motels, vacation rentals (cottage/lodging),
B&Bs, guest_house, camping_cabin, mobile_home_park, service-typed
vacation rentals are all indoor-by-definition.

The override surface for the 73-entry post-2-apply cat-10 pool
(under the kickoff 4 forecast of 3-8 since the kickoff anticipated
named waterfront resorts that didn't materialize):

- **OUTDOOR_OVERRIDES (19 entries):** All rv_park-primary (14) +
  inland desert campgrounds (5: Craggy Wash BLM, Craggy Wash
  Campground, Crazy Horse Campgrounds, Lone Tree BLM, Windsor
  Campgrounds). RV parks and campgrounds are outdoor camping spaces
  by primary identity.

- **WATER_ADJACENT_OVERRIDES (1 entry):** Lake Havasu State Park
  Campground -- the LITERAL waterfront campground inside Lake Havasu
  State Park. Mirrors the 5.2 on-the-water lock per kickoff 4
  ("Mirror the 5.2 on-the-water heat_exposure pattern for the
  water_adjacent shape"). Other lake-named cat-10 entries (Sam's
  Beachcomber RV Resort, Anchor Lake House, Campbell Cove RV Resort,
  Islander Resort, Havasu Falls RV Resort) are uncertain without
  coordinate verification -- documented in 2 audit 9 V1.5 carry.

Mirrors ``apply_phase5_9_classes_heat_exposure.py`` shape with
default ``indoor`` + dual OUTDOOR_OVERRIDES / WATER_ADJACENT_OVERRIDES
dicts.

Allowed values per Entity model CHECK constraint:
NULL, 'indoor', 'shaded', 'outdoor', 'water_adjacent'.

Usage:
    python outputs/apply_phase5_10_lodging_heat_exposure.py --dry-run
    python outputs/apply_phase5_10_lodging_heat_exposure.py
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

# Default for every cat-10 entity not overridden below. 5.10 mirrors
# 5.6/5.8/5.9's 'indoor' default -- the bulk of cat-10 entries are
# hotels/motels/vacation rentals which are indoor-by-definition.
DEFAULT_HEAT_EXPOSURE = "indoor"

# Outdoor exceptions surfaced in Phase 5.10 2 audit. Keyed by
# Entity.name. Operator extends as needed if future loads surface more
# outdoor venues. The 19 entries are:
#   - 14 rv_park-primary entries (outdoor camping sites)
#   - 5 inland desert campgrounds (outdoor; uncertain water proximity)
OUTDOOR_OVERRIDES: dict[str, str] = {
    # RV parks (14) -- all are outdoor camping spaces
    "Anchor Lake House": "outdoor",
    "Artesa Resort": "outdoor",
    "Campbell Cove RV Resort": "outdoor",
    "D-J's RV Park": "outdoor",
    "Desert Hills RV Park": "outdoor",
    "Havasu Falls RV Resort": "outdoor",
    "Havasu RV Resort": "outdoor",
    "Havasu View RV Space": "outdoor",
    "Islander Resort": "outdoor",
    "Lake Havasu Resort": "outdoor",
    "Prospectors RV Resort": "outdoor",
    "Riverbound Custom Storage & RV Park": "outdoor",
    "Sam's Beachcomber RV Resort": "outdoor",
    "The Gravel Pit": "outdoor",
    # Campgrounds (5) -- inland desert campgrounds (no lake adjacency)
    "Craggy Wash BLM Land Camping": "outdoor",
    "Craggy Wash Campground": "outdoor",
    "Crazy Horse Campgrounds": "outdoor",
    "Lone Tree BLM Campground, Lake Havasu, AZ": "outdoor",
    "Windsor Campgrounds": "outdoor",
}

# Water-adjacent exceptions surfaced in Phase 5.10 2 audit. Keyed by
# Entity.name. Only entries where lake access is the PRIMARY
# environmental factor (mirroring the 5.2 cat-3 on-the-water default).
# V1 conservative: 1 entry. V1.5 may extend after coordinate
# verification of Sam's Beachcomber / Anchor Lake House / Campbell
# Cove / Islander / Havasu Falls per 2 audit 9 carry.
WATER_ADJACENT_OVERRIDES: dict[str, str] = {
    # Lake Havasu State Park Campground -- IS at Lake Havasu State
    # Park (the state park is on the lake; the campground is within
    # the park). Lake access is the primary draw for campers.
    "Lake Havasu State Park Campground": "water_adjacent",
}


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _resolve_entity_by_name(session, name: str) -> Entity | None:
    rows = session.scalars(
        select(Entity).where(Entity.name == name, Entity.is_active == 1)
    ).all()
    if not rows:
        return None
    if len(rows) > 1:
        raise RuntimeError(
            f"name-resolution collision: {len(rows)} active entities match "
            f"Entity.name={name!r}; expected exactly 1."
        )
    return rows[0]


def _override_for(name: str) -> str:
    """Resolve a single heat_exposure target for `name`. Priority:
    WATER_ADJACENT_OVERRIDES > OUTDOOR_OVERRIDES > DEFAULT."""
    if name in WATER_ADJACENT_OVERRIDES:
        return WATER_ADJACENT_OVERRIDES[name]
    if name in OUTDOOR_OVERRIDES:
        return OUTDOOR_OVERRIDES[name]
    return DEFAULT_HEAT_EXPOSURE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; roll back; no DB writes.",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        cat10 = session.scalars(
            select(Category).where(Category.slug == "lodging-vacation-rentals")
        ).one_or_none()
        if cat10 is None:
            print("ERROR: Category.slug='lodging-vacation-rentals' not found.")
            return 2

        entities = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == cat10.id,
                Entity.is_active == 1,
            )
        ).all()
        print(f"[apply] {len(entities)} cat-10 entities to process")

        # First pass: validate that every override name resolves.
        unresolved_outdoor = [
            n for n in OUTDOOR_OVERRIDES
            if _resolve_entity_by_name(session, n) is None
        ]
        unresolved_water = [
            n for n in WATER_ADJACENT_OVERRIDES
            if _resolve_entity_by_name(session, n) is None
        ]
        if unresolved_outdoor:
            print(
                "  [WARNING] OUTDOOR_OVERRIDES has unresolved names "
                f"(skipped): {unresolved_outdoor!r}"
            )
        if unresolved_water:
            print(
                "  [WARNING] WATER_ADJACENT_OVERRIDES has unresolved names "
                f"(skipped): {unresolved_water!r}"
            )

        # Second pass: apply default + overrides.
        applied = 0
        unchanged = 0
        before_mix: Counter[str | None] = Counter()
        after_mix: Counter[str | None] = Counter()
        for ent in entities:
            before_mix[ent.heat_exposure] += 1
            target = _override_for(ent.name)
            if ent.heat_exposure == target:
                unchanged += 1
                after_mix[target] += 1
                continue
            ent.heat_exposure = target
            ent.updated_at = _utc_now_naive()
            applied += 1
            after_mix[target] += 1

        print(f"\n  before mix: {dict(before_mix)}")
        print(f"  after mix:  {dict(after_mix)}")
        print(f"\n=== Summary ===\n  applied: {applied}\n  unchanged: {unchanged}")

        # Self-verify: count NULL heat_exposure in cat-10.
        n_null = sum(1 for e in entities if e.heat_exposure is None)
        print(
            f"  cat-10 entities with NULL heat_exposure: {n_null} "
            "(gate-5 target: 0)"
        )

        if args.dry_run:
            print("\n[dry-run] rolling back; no DB writes.")
            session.rollback()
        else:
            session.commit()
            print("\n[apply] committed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
