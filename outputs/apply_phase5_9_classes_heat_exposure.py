"""Apply heat_exposure to all classes-sports-recreation (cat-12) entities.

Closes Phase 5.9 acceptance gate item 5 ("heat_exposure non-NULL on
every entry"). Per kickoff §4: ``indoor`` is the default for most
cat-12 entries — daycare, preschools, schools, tutoring, music
lessons, driving schools are all indoor-by-definition. 5.9 mirrors
5.6/5.8's ``indoor`` default and populates ``OUTDOOR_OVERRIDES`` for
the 2 cat-12-native outdoor venues (a public swimming pool + public
tennis courts).

The 2 outdoor overrides in the 31-entry post-§2-apply cat-12 pool
(under the kickoff §4 forecast of 5-10 since most cat-12 entries are
schools/daycare):
- Lake Havasu City Aquatic Center (city outdoor pool + pickleball =
  outdoor by primary identity; Slice E NEW create)
- Stormy Wade Courts (public outdoor tennis courts; Slice B FLIP-in)

Mirrors ``apply_phase5_8_events_heat_exposure.py`` shape exactly with
default ``indoor`` + smaller ``OUTDOOR_OVERRIDES`` set.

Allowed values per Entity model CHECK constraint:
NULL, 'indoor', 'shaded', 'outdoor', 'water_adjacent'.

Usage:
    python outputs/apply_phase5_9_classes_heat_exposure.py --dry-run
    python outputs/apply_phase5_9_classes_heat_exposure.py
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

# Default for every cat-12 entity not overridden below. 5.9 mirrors
# 5.6/5.8's 'indoor' default — cat-12 entries are largely indoor
# classroom / daycare / studio facilities.
DEFAULT_HEAT_EXPOSURE = "indoor"

# Outdoor exceptions surfaced in Phase 5.9 §2 audit. Keyed by
# Entity.name. Operator extends as needed if future loads surface more
# outdoor venues (e.g., a new outdoor pickleball court complex).
OUTDOOR_OVERRIDES: dict[str, str] = {
    # Lake Havasu City Aquatic Center — municipal outdoor pool (the
    # primary identity) plus 4 outdoor pickleball courts + seasonal
    # outdoor classes. Slice E NEW create from 5.9 §2 audit (595r).
    "Lake Havasu City Aquatic Center": "outdoor",
    # Stormy Wade Courts — public outdoor tennis courts at 2675 Palo
    # Verde Blvd S. Lighted; open past 10pm. Slice B FLIP-in from 5.9
    # §2 audit (re-routed from cat-5 to cat-12 per the new tennis_court
    # direct mapping shipped at 0af5f73).
    "Stormy Wade Courts": "outdoor",
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
        cat12 = session.scalars(
            select(Category).where(Category.slug == "classes-sports-recreation")
        ).one_or_none()
        if cat12 is None:
            print("ERROR: Category.slug='classes-sports-recreation' not found.")
            return 2

        entities = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == cat12.id,
                Entity.is_active == 1,
            )
        ).all()
        print(f"[apply] {len(entities)} cat-12 entities to process")

        # First pass: validate that every OUTDOOR_OVERRIDE name resolves.
        unresolved = []
        for name in OUTDOOR_OVERRIDES:
            ent = _resolve_entity_by_name(session, name)
            if ent is None:
                unresolved.append(name)
        if unresolved:
            print(
                "  [WARNING] OUTDOOR_OVERRIDES has unresolved names "
                f"(skipped): {unresolved!r}"
            )

        # Second pass: apply default + overrides.
        applied = 0
        unchanged = 0
        before_mix: Counter[str | None] = Counter()
        after_mix: Counter[str | None] = Counter()
        for ent in entities:
            before_mix[ent.heat_exposure] += 1
            target = OUTDOOR_OVERRIDES.get(ent.name, DEFAULT_HEAT_EXPOSURE)
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

        # Self-verify: count NULL heat_exposure in cat-12.
        n_null = sum(1 for e in entities if e.heat_exposure is None)
        print(
            f"  cat-12 entities with NULL heat_exposure: {n_null} "
            f"(gate-5 target: 0)"
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
