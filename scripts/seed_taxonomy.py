"""Seed the A.3 taxonomy tree into ``categories`` (idempotent, gated).

Reads ``docs/proposals/taxonomy-seed.json`` (15 departments + 126 leaves) and
upserts it into the flat ``categories`` table now that it carries ``parent_id``
+ ``level`` (migration b2d4f6a8c0e2):

* each department  -> level 0, parent_id NULL
* each leaf        -> level 1, parent_id = its department's id

Upsert is by ``slug``: an existing row is updated in place (name, level, parent,
sort_order), a missing row is inserted — so the script is safe to re-run and
legacy slugs are never deleted (Workstream B keeps them as 301 redirects).

DEFAULT IS DRY-RUN: prints what it would insert/update and the resulting tree
shape, writes nothing. ``--apply`` requires ``--confirm`` to write (the repo's
.env can point DATABASE_URL at prod — every run prints the sanitized target).

    .venv\\Scripts\\python.exe scripts\\seed_taxonomy.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\seed_taxonomy.py --apply --confirm  # writes
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category  # noqa: E402

DEFAULT_SEED = _ROOT / "docs" / "proposals" / "taxonomy-seed.json"


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def load_seed(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"taxonomy seed must be a JSON object, got {type(data).__name__}")
    return data


def run(*, apply: bool = False, confirm: bool = False, seed_path: Path | None = None,
        session=None) -> Counter:
    """Upsert the department/leaf tree. Dry-run (default) writes nothing."""
    seed_path = seed_path or DEFAULT_SEED
    seed = load_seed(seed_path)
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}")
        print(f"seed file: {seed_path}\n")

        existing = {c.slug: c for c in session.query(Category).all()}
        dept_count = len(seed)
        leaf_count = sum(len(d.get("leaves") or {}) for d in seed.values())
        print(f"seed: {dept_count} departments, {leaf_count} leaves")

        # --- Pass 1: departments (level 0) -------------------------------
        dept_slug_to_id: dict[str, int] = {}
        for dept_slug, dept in seed.items():
            name = dept["name"]
            sort = int(dept.get("sort", 0))
            row = existing.get(dept_slug)
            if row is None:
                row = Category(slug=dept_slug, name=name, sort_order=sort, level=0)
                row.parent_id = None
                session.add(row)
                session.flush()  # assign id for leaf parenting
                existing[dept_slug] = row
                counts["dept_insert"] += 1
            else:
                changed = (
                    row.name != name or row.sort_order != sort
                    or row.level != 0 or row.parent_id is not None
                )
                row.name, row.sort_order, row.level, row.parent_id = name, sort, 0, None
                counts["dept_update" if changed else "dept_unchanged"] += 1
            dept_slug_to_id[dept_slug] = row.id

        # --- Pass 2: leaves (level 1) ------------------------------------
        new_leaf_slugs: list[str] = []
        for dept_slug, dept in seed.items():
            parent_id = dept_slug_to_id[dept_slug]
            for i, (leaf_slug, leaf) in enumerate((dept.get("leaves") or {}).items()):
                name = leaf["name"]
                if leaf.get("new"):
                    new_leaf_slugs.append(leaf_slug)
                row = existing.get(leaf_slug)
                if row is None:
                    row = Category(slug=leaf_slug, name=name, sort_order=i, level=1)
                    row.parent_id = parent_id
                    session.add(row)
                    existing[leaf_slug] = row
                    counts["leaf_insert"] += 1
                else:
                    changed = (
                        row.name != name or row.level != 1
                        or row.parent_id != parent_id or row.sort_order != i
                    )
                    row.name, row.level, row.parent_id, row.sort_order = (
                        name, 1, parent_id, i,
                    )
                    counts["leaf_update" if changed else "leaf_unchanged"] += 1

        print("\nplanned changes:")
        for k in (
            "dept_insert", "dept_update", "dept_unchanged",
            "leaf_insert", "leaf_update", "leaf_unchanged",
        ):
            print(f"  {counts.get(k, 0):>4}  {k}")
        if new_leaf_slugs:
            print(f"\n[NEW] leaves (confirm keep/fold): {', '.join(new_leaf_slugs)}")

        if not apply:
            session.rollback()
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to seed.")
            return counts
        if not confirm:
            session.rollback()
            print(
                f"\nREFUSING TO WRITE — --apply requires --confirm. Target is "
                f"{_sanitized_target()}."
            )
            return counts

        session.commit()
        print("\nAPPLIED — taxonomy tree seeded/updated.")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    parser.add_argument("--confirm", action="store_true", help="Required with --apply.")
    parser.add_argument("--seed", type=Path, default=None, help="Override seed JSON path.")
    args = parser.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm, seed_path=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
