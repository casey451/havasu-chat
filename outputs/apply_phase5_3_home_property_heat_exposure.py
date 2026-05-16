"""Apply heat_exposure to all home-property-services entities.

Closes Phase 5.3 acceptance gate item 5 ("heat_exposure set on every
entry"). Per kickoff §4: ``indoor`` is the default for essentially every
home-property-services entity — the BUSINESS venue is typically an
office or service yard, indoor. Exceptions for outdoor service yards
are rare and operator-curated (currently zero exceptions surfaced;
extend ``OUTDOOR_OVERRIDES`` if operator surfaces specific ones).

Mirrors ``apply_on_the_water_heat_exposure.py`` shape: id-keyed dict,
--dry-run-first, idempotent, sets updated_at, self-verifies via
distribution query.

Allowed values per Entity model CHECK constraint:
NULL, 'indoor', 'shaded', 'outdoor', 'water_adjacent'.

Usage:
    python outputs/apply_phase5_3_home_property_heat_exposure.py --dry-run
    python outputs/apply_phase5_3_home_property_heat_exposure.py
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

# Default for every home-property-services entity not overridden below.
DEFAULT_HEAT_EXPOSURE = "indoor"

# Outdoor exceptions (currently empty). Extend if the operator surfaces
# specific outdoor-yard businesses (rare — most service businesses operate
# from an indoor office even when their work goes outdoors).
# Keyed by 8-char entity_id prefix (matches the audit inventory).
OUTDOOR_OVERRIDES: dict[str, str] = {
    # No exceptions surfaced in Phase 5.3 §1 + audit. Operator extends as needed.
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
        cat_id = session.scalar(
            select(Category.id).where(Category.slug == "home-property-services")
        )
        if cat_id is None:
            print(
                "ERROR: Category.slug='home-property-services' not found.",
                file=sys.stderr,
            )
            return 2

        entities = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == cat_id,
                Entity.is_active.is_(True),
            )
        ).all()
        print(
            f"[heat_exposure] {len(entities)} home-property-services entities discovered"
        )

        # Build OUTDOOR override mapping by full entity_id once.
        outdoor_entity_ids: dict[str, str] = {}
        for prefix, name in OUTDOOR_OVERRIDES.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(
                    f"  WARN: OUTDOOR_OVERRIDES prefix={prefix!r} ({name!r}) not found"
                )
                continue
            outdoor_entity_ids[ent.id] = name

        applied_default = 0
        applied_outdoor = 0
        already_correct = 0
        for ent in entities:
            target = "outdoor" if ent.id in outdoor_entity_ids else DEFAULT_HEAT_EXPOSURE
            if ent.heat_exposure == target:
                already_correct += 1
                continue
            ent.heat_exposure = target
            ent.updated_at = now_naive
            if target == "outdoor":
                applied_outdoor += 1
            else:
                applied_default += 1

        print()
        print("=" * 70)
        print("Apply summary")
        print("=" * 70)
        print(f"  set to indoor (default)     : {applied_default}")
        print(f"  set to outdoor (override)   : {applied_outdoor}")
        print(f"  already correct (no change) : {already_correct}")
        print(f"  total entities              : {len(entities)}")
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
        print("Self-verify — heat_exposure distribution across home-property-services")
        print("=" * 70)
        dist: Counter[str | None] = Counter()
        for ent in session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == cat_id,
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
                "Phase 5.3 §6 acceptance gate item 5 (heat_exposure set on every "
                "entry) CLEARED."
            )
        else:
            print(
                f"WARN: {null_count} entities still have heat_exposure=NULL"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
