"""Create the level-1 ``mortgage-lenders`` leaf under ``professional-and-financial``.

Audit 2026-07-06 (T3.3): ~15 mortgage brokers / loan officers are mis-shelved under
``banks-and-credit-unions``. A mortgage lender is not a bank, so they get a dedicated
leaf. Mirrors ``scripts/create_vacation_rentals_leaf.py`` exactly: inserts EXACTLY one
Category row (or no-ops if it already exists), never runs the full seed. The leaf is
also recorded in ``docs/proposals/taxonomy-seed.json`` so a future full seed stays
consistent; ``leaf_copy`` / ``leaf_query`` wiring ships in the same PR.

DEFAULT IS DRY-RUN. ``--apply`` requires ``--confirm``. Writes a JSON rollback snapshot.

    .venv\\Scripts\\python.exe scripts\\create_mortgage_leaf_2026_07_06.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\create_mortgage_leaf_2026_07_06.py --apply --confirm  # writes
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category  # noqa: E402

DEPT_SLUG = "professional-and-financial"
NEW_LEAF_SLUG = "mortgage-lenders"
NEW_LEAF_NAME = "Mortgage Lenders"


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def plan_leaf_action(existing_by_slug: dict[str, dict]) -> tuple[str, str]:
    """Pure planner (no DB): returns (action, message), action ∈ insert/noop/abort."""
    dept = existing_by_slug.get(DEPT_SLUG)
    if dept is None or dept["level"] != 0:
        return ("abort", f"level-0 department {DEPT_SLUG!r} not found — cannot parent the leaf")
    leaf = existing_by_slug.get(NEW_LEAF_SLUG)
    if leaf is not None:
        if leaf["level"] == 1 and leaf["parent_id"] == dept["id"]:
            return ("noop", f"{NEW_LEAF_SLUG!r} already a level-1 leaf under {DEPT_SLUG}")
        return ("abort", f"{NEW_LEAF_SLUG!r} already exists as level={leaf['level']} "
                         f"parent_id={leaf['parent_id']} — refusing to mutate it")
    return ("insert", f"insert level-1 {NEW_LEAF_SLUG!r} under {DEPT_SLUG} id={dept['id']}")


def run(*, apply: bool = False, confirm: bool = False, snapshot_dir: Path | None = None, session=None) -> Counter:
    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")
        cats = session.query(Category).all()
        existing_by_slug = {c.slug: {"id": c.id, "level": c.level, "parent_id": c.parent_id} for c in cats}
        action, message = plan_leaf_action(existing_by_slug)
        counts[action] += 1
        print(f"plan: {action.upper()} — {message}")
        if action != "insert":
            return counts

        dept_id = existing_by_slug[DEPT_SLUG]["id"]
        sort_order = sum(1 for c in cats if c.level == 1 and c.parent_id == dept_id)
        print(f"  -> slug={NEW_LEAF_SLUG!r} name={NEW_LEAF_NAME!r} level=1 parent_id={dept_id} sort_order={sort_order}")

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            return counts

        leaf = Category(slug=NEW_LEAF_SLUG, name=NEW_LEAF_NAME, level=1, sort_order=sort_order)
        leaf.parent_id = dept_id
        session.add(leaf)
        session.flush()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"create_mortgage_leaf_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps({
            "created": [{"id": leaf.id, "slug": leaf.slug, "name": leaf.name,
                         "level": leaf.level, "parent_id": leaf.parent_id}],
            "rollback": f"DELETE FROM categories WHERE id = {leaf.id};",
        }, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path} (created id={leaf.id})")
        session.commit()
        counts["committed"] += 1
        print(f"\nAPPLIED — created {NEW_LEAF_SLUG!r} (id={leaf.id}) under {DEPT_SLUG}.")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
