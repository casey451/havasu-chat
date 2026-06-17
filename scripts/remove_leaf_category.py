"""Remove an EMPTY leaf Category row (targeted, gated, safety-guarded).

Teardown counterpart to a targeted leaf insert. Used to roll back the
``swim-and-aquatics`` leaf added 2026-06-17 and then shelved (no sustainable
data source — see relay handoff). Deleting a taxonomy row is destructive, so this
is gated and REFUSES to delete a leaf that is not genuinely empty:

  * the row must exist and be a leaf (``level == 1``);
  * it must have NO child categories;
  * it must have ZERO ``EntityCategory`` references (no listings filed on it).

If any guard trips, the row is reported and SKIPPED — never force-deleted.

  python scripts/remove_leaf_category.py            # preview (default)
  python scripts/remove_leaf_category.py --apply    # delete + undo snapshot

``--apply`` writes an undo snapshot (the deleted row's slug/name/parent_id/
sort_order, enough to re-insert it) to ``relay/`` before the commit. Dry-run
asserts zero deletes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, EntityCategory  # noqa: E402

# Leaf slugs to remove (only if empty).
REMOVE_SLUGS: list[str] = ["swim-and-aquatics"]


def _listing_count(db: Session, category_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(EntityCategory)
            .where(EntityCategory.category_id == category_id)
        )
        or 0
    )


def _child_count(db: Session, category_id: int) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(Category).where(Category.parent_id == category_id)
        )
        or 0
    )


def remove_leaves(db: Session, *, apply: bool, undo: list[dict[str, Any]]) -> Counter[str]:
    c: Counter[str] = Counter()

    for slug in REMOVE_SLUGS:
        c["total"] += 1
        row = db.scalars(select(Category).where(Category.slug == slug).limit(1)).first()
        if row is None:
            c["not_found"] += 1
            print(f"--- not_found (nothing to remove): {slug!r}")
            continue
        if row.level != 1:
            c["not_a_leaf"] += 1
            print(f"--- not_a_leaf (skip): {slug!r} level={row.level}")
            continue

        children = _child_count(db, row.id)
        listings = _listing_count(db, row.id)
        if children or listings:
            c["not_empty"] += 1
            print(
                f"--- not_empty (REFUSE): {slug!r} has {children} child(ren), "
                f"{listings} listing(s) — not deleting"
            )
            continue

        c["would_delete"] += 1
        print(
            f"--- DELETE: leaf {slug!r} (id={row.id}, parent_id={row.parent_id}, "
            f"sort_order={row.sort_order}) — 0 children, 0 listings"
        )
        if not apply:
            continue

        undo.append(
            {
                "op": "delete_category",
                "slug": row.slug,
                "name": row.name,
                "level": row.level,
                "parent_id": row.parent_id,
                "sort_order": row.sort_order,
            }
        )
        db.delete(row)
        db.flush()
        c["deleted"] += 1

    return c


def _write_undo(undo: list[dict[str, Any]], snapshot_dir: Path | None) -> Path:
    out_dir = snapshot_dir or (Path(__file__).resolve().parents[1] / "relay")
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = out_dir / f"_remove_leaf_category_undo_{datetime.now():%Y%m%dT%H%M%S}.json"
    snap.write_text(json.dumps(undo, indent=2), encoding="utf-8")
    return snap


def run(db: Session, *, apply: bool, snapshot_dir: Path | None = None) -> Counter[str]:
    undo: list[dict[str, Any]] = []
    print("\n=== REMOVE LEAF CATEGORY (empty leaves only) ===")
    c = remove_leaves(db, apply=apply, undo=undo)

    if apply and undo:
        snap = _write_undo(undo, snapshot_dir)
        db.commit()
        print(f"\ninfo: deleted {len(undo)} row(s); undo snapshot -> {snap}")
    elif apply:
        print("\ninfo: nothing to apply (no eligible rows).")

    print("\n--- summary ---")
    for k in ("total", "not_found", "not_a_leaf", "not_empty", "would_delete", "deleted"):
        print(f"  {k:14} {c[k]}")

    if not apply:
        assert c["deleted"] == 0, "dry-run must not persist"
    return c


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--dry-run", action="store_true", help="Preview without writing (default).")
    mode.add_argument("--apply", action="store_true", help="Delete + undo snapshot.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    with SessionLocal() as db:
        run(db, apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
