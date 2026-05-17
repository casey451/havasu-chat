"""Apply heat_exposure to all outdoors-parks-trails entities.

Closes Phase 5.7 acceptance gate item 5 ("heat_exposure set on every
entry"). Per kickoff §4: ``outdoor`` is the default for nearly all
parks-and-trails — parks, state parks, golf courses, mini golf,
dog parks, hiking trails, wildlife refuges are all outdoor-by-
definition. **5.7 flips the default to `outdoor`** (vs 5.6's `indoor`
default for retail) and populates ``INDOOR_OVERRIDES`` instead of
``OUTDOOR_OVERRIDES``.

The only obvious indoor candidate in the 27-entry post-§2-apply cat-7
pool is Altitude Trampoline Park (DRAFT'd in §2 but still gets
heat_exposure per the 5.6 close-out gate-5 precedent — gate-5 reads
"on every entry" regardless of draft state).

Mirrors ``apply_phase5_6_shopping_heat_exposure.py`` shape exactly:
name-keyed override dict (the §2 apply-script's idiom — single
affected entry has a unique name; no prefix-indirection needed),
--dry-run-first, idempotent, sets updated_at, self-verifies via
distribution query.

Allowed values per Entity model CHECK constraint:
NULL, 'indoor', 'shaded', 'outdoor', 'water_adjacent'.

Usage:
    python outputs/apply_phase5_7_parks_heat_exposure.py --dry-run
    python outputs/apply_phase5_7_parks_heat_exposure.py
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

# Default for every outdoors-parks-trails entity not overridden below.
# Flipped from 5.6's 'indoor' default — parks/golf/trails are
# outdoor-by-definition.
DEFAULT_HEAT_EXPOSURE = "outdoor"

# Indoor exceptions surfaced in Phase 5.7 §2 audit. Keyed by Entity.name
# (matches the §2 apply-script idiom — 1 affected entry has a unique
# name; name-based lookup with collision assert). Operator extends as
# needed if more indoor venues surface (e.g., if a future re-load adds
# an indoor mini golf facility).
INDOOR_OVERRIDES: dict[str, str] = {
    # Indoor amusement_park — kickoff §1 explicitly deferred indoor
    # entertainment; DRAFT'd in §2 apply-script but still needs
    # heat_exposure set (gate-5 covers every entry regardless of draft).
    "Altitude Trampoline Park": (
        "indoor trampoline facility; kickoff §1 indoor-entertainment "
        "defer; §2 apply DRAFT'd in cat-7"
    ),
}


def _resolve_entity_by_name(session, name: str) -> Entity | None:
    """Resolve Entity.name exact-match. Asserts at most one active row;
    returns None if zero rows. Raises RuntimeError if multiple rows
    match (defensive against future name collisions). Mirrors the §2
    apply-script's helper."""
    rows = session.scalars(
        select(Entity).where(Entity.name == name, Entity.is_active == 1)
    ).all()
    if not rows:
        return None
    if len(rows) > 1:
        raise RuntimeError(
            f"name-resolution collision: {len(rows)} active entities "
            f"match Entity.name={name!r}; expected exactly 1. Update "
            f"this apply-script to disambiguate before re-running."
        )
    return rows[0]


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
            select(Category.id).where(Category.slug == "outdoors-parks-trails")
        )
        if cat_id is None:
            print(
                "ERROR: Category.slug='outdoors-parks-trails' not found.",
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
            f"[heat_exposure] {len(entities)} outdoors-parks-trails entities discovered"
        )

        # Build INDOOR override mapping by full entity_id once.
        indoor_entity_ids: dict[str, str] = {}
        for name in INDOOR_OVERRIDES:
            ent = _resolve_entity_by_name(session, name)
            if ent is None:
                print(
                    f"  WARN: INDOOR_OVERRIDES name={name!r} not found"
                )
                continue
            indoor_entity_ids[ent.id] = name

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
        print(f"  set to outdoor (default)    : {applied_default}")
        print(f"  set to indoor (override)    : {applied_indoor}")
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
        print("Self-verify — heat_exposure distribution across outdoors-parks-trails")
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
                "Phase 5.7 acceptance gate item 5 (heat_exposure set on every "
                "entry) CLEARED."
            )
        else:
            print(
                f"WARN: {null_count} entities still have heat_exposure=NULL"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
