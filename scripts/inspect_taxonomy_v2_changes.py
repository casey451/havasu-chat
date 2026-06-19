"""READ-ONLY inspector for the IA v2 (Phase 2) structural taxonomy changes.

Reports how many leaves and active listings each of the three structural moves
would touch in the CURRENT database (prod, in Casey's env). Writes NOTHING — only
SELECT/count. Run this BEFORE authoring or applying any migration, so the impact
is known and reviewable.

Moves:
  1. MERGE   outdoors-and-recreation + things-to-do-and-attractions -> things-to-do
  2. SPLIT   community-and-civic -> city-and-government + worship-and-nonprofits
  3. PROMOTE tattoo-and-piercing (leaf under beauty-and-personal-care) -> own dept

Usage:  python scripts/inspect_taxonomy_v2_changes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402

_CITY_LEAVES = {
    "government-and-mvd",
    "utilities",
    "post-office",
    "libraries",
    "community-centers",
}
_WORSHIP_LEAVES = {"places-of-worship", "nonprofits-and-charities"}


def _dept(db, slug):
    return (
        db.query(Category)
        .filter(Category.slug == slug, Category.level == 0)
        .one_or_none()
    )


def _leaves(db, dept):
    if dept is None:
        return []
    return (
        db.query(Category)
        .filter(Category.parent_id == dept.id, Category.level == 1)
        .all()
    )


def _active_listings(db, leaf_id):
    return (
        db.query(EntityCategory)
        .join(Entity, EntityCategory.entity_id == Entity.id)
        .filter(
            EntityCategory.category_id == leaf_id,
            EntityCategory.is_primary.is_(True),
            Entity.is_active.is_(True),
        )
        .count()
    )


def _report_dept(db, slug, *, only=None):
    dept = _dept(db, slug)
    if dept is None:
        print(f"  [MISSING] department slug not found: {slug}")
        return 0, 0
    leaves = _leaves(db, dept)
    n_leaves = 0
    total = 0
    for leaf in sorted(leaves, key=lambda c: c.slug):
        if only is not None and leaf.slug not in only:
            continue
        n = _active_listings(db, leaf.id)
        n_leaves += 1
        total += n
        print(f"    - {leaf.slug:38s} {n:4d} listings")
    print(f"  => {slug}: {n_leaves} leaves, {total} active listings")
    return n_leaves, total


def main():
    db = SessionLocal()
    try:
        print("=== IA v2 structural-change inspector (READ-ONLY, no writes) ===\n")

        print("1) MERGE -> things-to-do")
        l1, t1 = _report_dept(db, "outdoors-and-recreation")
        l2, t2 = _report_dept(db, "things-to-do-and-attractions")
        print(f"   TOTAL to re-parent: {l1 + l2} leaves, {t1 + t2} listings\n")

        print("2) SPLIT community-and-civic")
        print("   -> city-and-government:")
        _report_dept(db, "community-and-civic", only=_CITY_LEAVES)
        print("   -> worship-and-nonprofits:")
        _report_dept(db, "community-and-civic", only=_WORSHIP_LEAVES)
        print("   (all leaves, for reconciliation:)")
        _report_dept(db, "community-and-civic")
        print()

        print("3) PROMOTE tattoo-and-piercing")
        leaf = (
            db.query(Category)
            .filter(Category.slug == "tattoo-and-piercing", Category.level == 1)
            .one_or_none()
        )
        if leaf is None:
            print("    [MISSING] tattoo-and-piercing leaf not found")
        else:
            parent = (
                db.query(Category).filter(Category.id == leaf.parent_id).one_or_none()
            )
            pslug = parent.slug if parent else "?"
            print(
                f"    tattoo-and-piercing: {_active_listings(db, leaf.id)} listings "
                f"(current parent: {pslug})"
            )

        print("\n=== END (no writes performed) ===")
    finally:
        db.close()


if __name__ == "__main__":
    main()
