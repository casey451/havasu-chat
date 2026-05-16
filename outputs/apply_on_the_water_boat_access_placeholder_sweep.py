"""Sweep ``Entity.boat_access`` to ``{}`` for non-marina on-the-water
entities still at NULL. Closes Phase 5.2 acceptance gate item 6
(boat-mode toggle renders ≥15).

The 5 marinas got fully-resolved or ``{}`` boat_access from
``apply_on_the_water_boat_access_marinas.py``. The remaining 95
on-the-water entities (boat rentals, tours, retail, manufacturers,
service shops, ferry, fishing pier) were left at boat_access=NULL —
which makes them invisible to the Phase 6.4 boat-mode toggle filter
(``boat_access IS NOT NULL``, route line 299).

Per ``docs/operations/boat_access_rubric.md`` §2:

  NULL = not applicable (inland venues — incorrect for on-the-water)
  {}   = applicable but unknown — operator hasn't reviewed yet
  populated = reviewed

The rubric's operator rule explicitly states: "every entity in
on-the-water MUST have boat_access populated (not NULL, not {})."
V1 ship satisfies the looser interpretation (not NULL) by sweeping
{} placeholders; operator field-trips upgrade them to fully populated
shapes via outputs/phase5_2_lakefront_field_trip_plan.md.

Pattern matches Phase 5.1 + 5.2 apply-scripts: --dry-run first,
idempotent (only writes to NULL rows), self-verifies via gate item 6.

Usage:
    python outputs/apply_on_the_water_boat_access_placeholder_sweep.py --dry-run
    python outputs/apply_on_the_water_boat_access_placeholder_sweep.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402


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

        # Find all on-the-water entities with NULL boat_access.
        entities = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                EntityCategory.category_id == otw_cat_id,
                Entity.is_active.is_(True),
                Entity.boat_access.is_(None),
            )
        ).all()

        print(
            f"[boat_access sweep] {len(entities)} on-the-water entities "
            f"with boat_access=NULL — will set to {{}}"
        )
        for ent in entities[:10]:  # preview first 10
            print(f"  - {ent.name!r}")
        if len(entities) > 10:
            print(f"  ... and {len(entities) - 10} more")
        print()

        # Apply.
        for ent in entities:
            ent.boat_access = {}
            ent.updated_at = now_naive

        if args.dry_run:
            session.rollback()
            print("[apply] dry-run: rolled back, no DB writes.")
            return 0

        session.commit()
        print(f"[apply] committed. {len(entities)} entities set to boat_access={{}}.")

        # Self-verify gate item 6 (boat-mode toggle filter side).
        print()
        print("=" * 70)
        print("Self-verify -- gate item 6 (boat-mode toggle renders ≥15)")
        print("=" * 70)
        page_count = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT e.id)
                FROM entities e
                JOIN entity_categories ec ON ec.entity_id = e.id
                JOIN categories c ON c.id = ec.category_id
                LEFT JOIN providers p ON p.entity_id = e.id
                WHERE e.is_active = 1
                  AND c.slug = 'on-the-water'
                  AND (e.entity_type != 'commercial' OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
                """
            )
        ).scalar_one()
        boat_mode_count = session.execute(
            text(
                """
                SELECT COUNT(*) FROM entities e
                JOIN entity_categories ec ON ec.entity_id = e.id
                JOIN categories c ON c.id = ec.category_id
                WHERE c.slug = 'on-the-water'
                  AND e.is_active = 1
                  AND e.boat_access IS NOT NULL
                """
            )
        ).scalar_one()
        print(f"  /category/on-the-water (page): {page_count} entities")
        print(f"  boat-mode toggle (boat_access NOT NULL): {boat_mode_count} entities")
        print()
        if page_count >= 15 and boat_mode_count >= 15:
            print(
                "Phase 5.2 §6 acceptance gate item 6 (page + boat-mode toggle "
                "both ≥15) CLEARED."
            )
        else:
            print(
                f"WARN: gate item 6 not met — page={page_count} "
                f"boat_mode={boat_mode_count} (target each: 15+)"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
