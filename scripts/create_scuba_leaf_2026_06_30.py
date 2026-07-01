"""Create the Scuba & Dive leaf and re-home Scuba Training & Technology.

Search audit 2A: "Scuba Training & Technology -> Scuba (out of Jet Ski &
Watersports)". No scuba leaf existed, so this creates
``scuba-and-dive`` (level-1, under the On the Water department) and repoints the
business's PRIMARY entity_categories link onto it. The routing terms + seed entry
that make "scuba" reach the page ship in the companion code PR.

Dry-run default; --apply --confirm gated. Idempotent (no-ops if the leaf already
exists / the row is already re-homed). Reversible via the printed snapshot.

Usage:
    .venv\\Scripts\\python.exe scripts/create_scuba_leaf_2026_06_30.py
    .venv\\Scripts\\python.exe scripts/create_scuba_leaf_2026_06_30.py --apply --confirm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402

_LEAF_SLUG = "scuba-and-dive"
_LEAF_NAME = "Scuba & Dive"
_DEPT_SLUG = "on-the-water"
_SCUBA_EID = "c415c33d-29fb-4125-b2c6-e56d2a7e427a"
_SCUBA_GUARD = "scuba training"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create scuba leaf + re-home (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 72)
    print(f"CREATE SCUBA LEAF + RE-HOME — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 72)
    print(f"DB target: …@{redacted}\n")

    with SessionLocal() as db:
        dept = db.query(Category).filter(Category.slug == _DEPT_SLUG, Category.level == 0).first()
        if dept is None:
            print(f"ABORT: department {_DEPT_SLUG!r} not found at level 0")
            return 1
        leaf = db.query(Category).filter(Category.slug == _LEAF_SLUG).first()
        if leaf is not None:
            print(f"leaf {_LEAF_SLUG!r}: already exists (id={leaf.id})")
        else:
            sibs = db.query(Category).filter(Category.parent_id == dept.id).all()
            next_sort = max((c.sort_order or 0 for c in sibs), default=0) + 1
            print(f"leaf {_LEAF_SLUG!r}: CREATE level-1 under {_DEPT_SLUG} "
                  f"(id={dept.id}), sort={next_sort}")

        ent = db.get(Entity, _SCUBA_EID)
        prim = None
        if ent is None or _SCUBA_GUARD not in (ent.name or "").lower():
            print(f"re-home: entity {_SCUBA_EID} missing or name mismatch — SKIP re-home")
        else:
            prim = db.query(EntityCategory).filter_by(
                entity_id=ent.id, is_primary=True).one_or_none()
            cur = db.get(Category, prim.category_id) if prim else None
            print(f"re-home: {ent.name!r} primary {cur.slug if cur else '(none)'} -> {_LEAF_SLUG}")

        if not writing:
            print("\nDRY RUN — nothing written. Re-run with --apply --confirm after approval.")
            return 0

        if leaf is None:
            sibs = db.query(Category).filter(Category.parent_id == dept.id).all()
            next_sort = max((c.sort_order or 0 for c in sibs), default=0) + 1
            leaf = Category(slug=_LEAF_SLUG, name=_LEAF_NAME, level=1,
                            parent_id=dept.id, sort_order=next_sort)
            db.add(leaf)
            db.flush()
        if prim is not None and prim.category_id != leaf.id:
            print(f"  snapshot: entity {_SCUBA_EID} ec={prim.id} {prim.category_id} -> {leaf.id}")
            prim.category_id = leaf.id
        db.commit()
        print(f"\nAPPLIED: leaf {_LEAF_SLUG!r} (id={leaf.id}); Scuba Training re-homed. Reversible.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
