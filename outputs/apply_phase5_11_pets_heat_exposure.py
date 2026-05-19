"""Apply heat_exposure to all pets (cat-11) entities.

Closes Phase 5.11 acceptance gate item 5 ("heat_exposure non-NULL on
every entry"). Per kickoff 4: ``indoor`` is the default for most
cat-11 entries -- pet stores, dog groomers (grooming studios), dog
trainers (indoor classrooms), vet clinics are all
indoor-by-definition. Mobile groomers (Mandy's Mobile Pet Salon,
De-Tails Mobile Pet Grooming) are still treated as indoor since the
service venue is the customer's home or a mobile van interior, not
exposed outdoor surface.

The override surface for the 38-entry post-2-apply cat-11 pool
(within the kickoff 4 forecast of 2-5):

- **OUTDOOR_OVERRIDES (4 entries):** Pet boarding facilities and
  doggy daycares with outdoor exercise yards. LHC pet boarding venues
  typically have outdoor runs by primary identity. The 4 entries:
    - Pet Oasis Doggy Daycare and Spa -- daycare with outdoor yard
    - The Dog House Doggy Day Care -- daycare with outdoor yard
    - Picky Mickie's Overnight Pet Sitting -- overnight boarding,
      outdoor walks
    - Pooch Paradise, LLC -- name + 11r reviews suggest outdoor
      space (boarding/daycare hybrid)

- **WATER_ADJACENT_OVERRIDES (0 entries):** Pet services are not
  lake-adjacent by definition; no water_adjacent overrides expected
  for cat-11. (Differs from 5.10 lodging which had 1 water_adjacent
  for Lake Havasu State Park Campground.)

Mirrors ``apply_phase5_10_lodging_heat_exposure.py`` shape with
default ``indoor`` + OUTDOOR_OVERRIDES (no water_adjacent block).

Allowed values per Entity model CHECK constraint:
NULL, 'indoor', 'shaded', 'outdoor', 'water_adjacent'.

Usage:
    python outputs/apply_phase5_11_pets_heat_exposure.py --dry-run
    python outputs/apply_phase5_11_pets_heat_exposure.py
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

# Default for every cat-11 entity not overridden below. Pet services
# are venue-based indoor businesses (stores, grooming studios, vet
# clinics, training classrooms).
DEFAULT_HEAT_EXPOSURE = "indoor"

# Outdoor exceptions surfaced in Phase 5.11 2 audit. Keyed by
# Entity.name. The 4 entries are pet boarding facilities and doggy
# daycares with outdoor exercise yards.
OUTDOOR_OVERRIDES: dict[str, str] = {
    "Pet Oasis Doggy Daycare and Spa": "outdoor",
    "The Dog House Doggy Day Care": "outdoor",
    "Picky Mickie's Overnight Pet Sitting": "outdoor",
    "Pooch Paradise, LLC": "outdoor",
}

# No water_adjacent overrides for cat-11 -- pet services are not
# lake-adjacent by primary identity. (5.10 had 1 entry for Lake
# Havasu State Park Campground; 5.11 has none.)
WATER_ADJACENT_OVERRIDES: dict[str, str] = {}


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _resolve_entity_by_name(session, name: str):
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
        cat11 = session.scalars(
            select(Category).where(Category.slug == "pets")
        ).one_or_none()
        if cat11 is None:
            print("ERROR: Category.slug='pets' not found.")
            return 2

        entities = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == cat11.id,
                Entity.is_active == 1,
            )
        ).all()
        print(f"[apply] {len(entities)} cat-11 entities to process")

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
        before_mix: Counter = Counter()
        after_mix: Counter = Counter()
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

        # Self-verify: count NULL heat_exposure in cat-11.
        n_null = sum(1 for e in entities if e.heat_exposure is None)
        print(
            f"  cat-11 entities with NULL heat_exposure: {n_null} "
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
