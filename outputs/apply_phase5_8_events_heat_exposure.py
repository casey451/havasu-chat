"""Apply heat_exposure to all events (cat-2) entities.

Closes Phase 5.8 acceptance gate item 5 ("heat_exposure set on every
entry"). Per kickoff §4: ``indoor`` is the default for most events —
movie theaters, bowling alleys, arcades, art galleries, museums,
indoor convention/conference venues are all indoor-by-definition.
**5.8 keeps the 5.6 default of `indoor`** (vs 5.7's `outdoor` default
for parks) and populates ``OUTDOOR_OVERRIDES`` for festival /
outdoor-venue entries.

The 3 outdoor overrides in the 20-entry post-§2-apply cat-2 pool
(forecast per kickoff §4 was 2-5):
- Buses By The Bridge (annual bus-and-cars festival = outdoor)
- Desert Storm Headquarters (annual boat poker run venue = outdoor)
- WORCS Racing (World Off-Road Championship Series — off-road
  racetrack venue = outdoor)

Mirrors ``apply_phase5_7_parks_heat_exposure.py`` shape with the
default flipped back to ``indoor`` and ``OUTDOOR_OVERRIDES`` (vs
5.7's ``INDOOR_OVERRIDES``).

Allowed values per Entity model CHECK constraint:
NULL, 'indoor', 'shaded', 'outdoor', 'water_adjacent'.

Usage:
    python outputs/apply_phase5_8_events_heat_exposure.py --dry-run
    python outputs/apply_phase5_8_events_heat_exposure.py
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

# Default for every events entity not overridden below. 5.8 mirrors 5.6's
# 'indoor' default — events are largely indoor (theaters, bowling,
# arcades, galleries, museums, indoor convention venues).
DEFAULT_HEAT_EXPOSURE = "indoor"

# Outdoor exceptions surfaced in Phase 5.8 §2 audit + carry. Keyed by
# Entity.name. Operator extends as needed if more outdoor venues surface
# (e.g., future re-load adds an open-air amphitheater).
OUTDOOR_OVERRIDES: dict[str, str] = {
    # Buses By The Bridge — annual bus-and-cars festival held outdoors
    # along Lake Havasu's bridge area. 5.7 §2 FLIP carry-over.
    "Buses By The Bridge": "outdoor",
    # Desert Storm Headquarters — annual outdoor boat poker run venue.
    # 5.7 §2 FLIP carry-over.
    "Desert Storm Headquarters": "outdoor",
    # WORCS Racing — World Off-Road Championship Series. Off-road
    # racetrack venue per the race_course primary_type. 5.8 §2 Slice A
    # FLIP — outdoor by definition.
    "WORCS Racing": "outdoor",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; roll back; no DB writes.",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        cat2 = session.scalars(
            select(Category).where(Category.slug == "events")
        ).one()

        # Pull all active cat-2 entities.
        entities = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == cat2.id,
                Entity.is_active == 1,
            )
        ).all()
        print(f"[heat] {len(entities)} active cat-2 entities loaded")

        changes: list[tuple[str, str | None, str]] = []
        for ent in entities:
            target = OUTDOOR_OVERRIDES.get(ent.name, DEFAULT_HEAT_EXPOSURE)
            if ent.heat_exposure != target:
                changes.append((ent.name, ent.heat_exposure, target))
                ent.heat_exposure = target
                ent.updated_at = _utc_now_naive()

        print(f"\n=== Changes: {len(changes)} ===")
        for name, old, new in changes:
            old_disp = old if old else "(NULL)"
            print(f"  {name!r:55s}  {old_disp!r:18s} -> {new!r}")

        # Verify OUTDOOR_OVERRIDES all matched a real entity.
        names_in_db = {e.name for e in entities}
        for override_name in OUTDOOR_OVERRIDES:
            if override_name not in names_in_db:
                print(
                    f"\n[WARNING] OUTDOOR_OVERRIDES name {override_name!r} "
                    "did not match any active cat-2 entity."
                )

        # Distribution check post-apply.
        dist = Counter()
        for ent in entities:
            dist[ent.heat_exposure or "(NULL)"] += 1
        print("\n=== Distribution ===")
        for val, cnt in sorted(dist.items()):
            print(f"  {val:20s}  {cnt}")

        # Gate-5 check: zero NULL.
        nulls = sum(1 for ent in entities if ent.heat_exposure is None)
        print(f"\n  NULL heat_exposure: {nulls} (gate-5 target: 0)")

        if args.dry_run:
            print("\n[dry-run] rolling back; no DB writes.")
            session.rollback()
        else:
            session.commit()
            print("\n[apply] committed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
