"""Insert ONLY the two source-parity leaves, under the department prod actually
uses — WITHOUT running the full taxonomy seed (which would restructure the live
nav; see docs/audits/2026-07/TAXONOMY_DEPARTMENT_DRIFT_2026-07-03.md).

Prod parents the outdoors + attractions family under ``things-to-do-and-
attractions`` (``outdoors-and-recreation`` does not exist as a prod department),
so both new leaves are homed there to match the live structure.

Idempotent: skips a leaf that already exists (regardless of parent). DRY-RUN by
default; ``--apply --confirm`` writes. Reversible: delete the 2 Category rows.

Usage:
    .venv\\Scripts\\python.exe scripts\\seed_parity_leaves.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\seed_parity_leaves.py --apply --confirm
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category  # noqa: E402

PARENT_SLUG = "things-to-do-and-attractions"
LEAVES = [
    ("wildlife-and-nature", "Wildlife & Nature"),
    ("event-venues", "Event Venues"),
]


def _target() -> str:
    url = os.environ.get("DATABASE_URL", "")
    return ("…@" + url.split("@", 1)[1]) if "@" in url else (url or "(sqlite)")


def run(*, apply: bool = False, confirm: bool = False, session=None) -> int:
    own = session is None
    session = session or SessionLocal()
    inserted = 0
    try:
        print(f"DB target: {_target()}\n")
        parent = session.scalar(select(Category).where(Category.slug == PARENT_SLUG))
        if parent is None:
            print(f"ABORT: parent department '{PARENT_SLUG}' not found in this DB.")
            return 1
        # next sort_order after existing children
        existing_children = session.scalars(
            select(Category).where(Category.parent_id == parent.id)
        ).all()
        next_sort = max((c.sort_order or 0 for c in existing_children), default=-1) + 1

        for slug, name in LEAVES:
            row = session.scalar(select(Category).where(Category.slug == slug))
            if row is not None:
                print(f"  skip (exists): {slug} (level={row.level}, parent_id={row.parent_id})")
                continue
            print(f"  INSERT: {slug} -> '{name}' under {PARENT_SLUG} (sort={next_sort})")
            inserted += 1
            if apply and confirm:
                session.add(
                    Category(slug=slug, name=name, level=1, parent_id=parent.id, sort_order=next_sort)
                )
            next_sort += 1

        print(f"\nwould insert: {inserted} leaf row(s)")
        if not (apply and confirm):
            print("DRY RUN: nothing written. Re-run with --apply --confirm to insert.")
            if apply and not confirm:
                print("REFUSING TO WRITE — --apply requires --confirm.")
        else:
            session.commit()
            print("APPLIED.")
        return 0
    finally:
        if own:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    return run(apply=args.apply, confirm=args.confirm)


if __name__ == "__main__":
    raise SystemExit(main())
