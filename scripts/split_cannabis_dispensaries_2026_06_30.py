"""Split cannabis dispensaries out of Smoke & Vape (search audit 3D).

`dispensary` landed on the combined smoke-vape-and-cannabis page, burying the 2
real dispensaries among 9 vape/smoke shops. This creates a `cannabis-dispensaries`
leaf (level-1 under Shopping & Retail) and repoints the 2 dispensaries' PRIMARY
entity_categories link onto it. The companion code PR points the `dispensary`
routing terms at the new leaf (smoke/vape terms stay on smoke-vape-and-cannabis).

Dry-run default; --apply --confirm gated. Idempotent; reversible.

Usage:
    .venv\\Scripts\\python.exe scripts/split_cannabis_dispensaries_2026_06_30.py
    .venv\\Scripts\\python.exe scripts/split_cannabis_dispensaries_2026_06_30.py --apply --confirm
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

_LEAF_SLUG = "cannabis-dispensaries"
_LEAF_NAME = "Cannabis Dispensaries"
_DEPT_SLUG = "shopping-and-retail"
# (entity_id, name-guard)
_DISPENSARIES = (
    ("1e2eb42c-b5d6-4446-a27e-7bee140d97c0", "story cannabis"),
    ("b7ffa7e5-8227-4bf5-9531-e0f0bbb4cc3f", "farm fresh"),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Split cannabis dispensaries (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 72)
    print(f"SPLIT CANNABIS DISPENSARIES — {'APPLY (writing)' if writing else 'DRY RUN'}")
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
            print(f"leaf {_LEAF_SLUG!r}: CREATE level-1 under {_DEPT_SLUG} (id={dept.id}), "
                  f"sort={max((c.sort_order or 0 for c in sibs), default=0) + 1}")

        moves = []
        for eid, guard in _DISPENSARIES:
            ent = db.get(Entity, eid)
            if ent is None or guard not in (ent.name or "").lower():
                print(f"  SKIP re-home {eid}: missing or name mismatch")
                continue
            prim = db.query(EntityCategory).filter_by(entity_id=eid, is_primary=True).one_or_none()
            cur = db.get(Category, prim.category_id) if prim else None
            print(f"  RE-HOME  {ent.name[:40]:40s} | {cur.slug if cur else '(none)'} -> {_LEAF_SLUG}")
            if prim is not None:
                moves.append(prim)

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
        for prim in moves:
            if prim.category_id != leaf.id:
                print(f"  snapshot: ec={prim.id} {prim.category_id} -> {leaf.id}")
                prim.category_id = leaf.id
        db.commit()
        print(f"\nAPPLIED: leaf {_LEAF_SLUG!r} (id={leaf.id}); {len(moves)} dispensaries re-homed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
