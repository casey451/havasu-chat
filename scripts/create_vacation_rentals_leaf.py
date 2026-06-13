"""Create the level-1 ``vacation-rentals`` leaf under the ``lodging`` department.

QA diagnostic 2026-06-12 (Phase 4, realty judgment rows): three vacation-rental
property managers were approved to move into lodging, but the approved target
slug ``lodging-vacation-rentals`` turned out to be a *stale level-0 department*,
not a leaf — and no vacation-rentals leaf exists. Casey approved (2026-06-12)
creating a proper level-1 ``vacation-rentals`` leaf under the live ``lodging``
department, then retargeting ``recategorize_realty_to_lodging.py`` to it.

Surgical by design: this inserts exactly one Category row (or no-ops if it
already exists). It deliberately does NOT run the full ``seed_taxonomy.py``,
which would upsert the entire 126-leaf tree and could revert recent prod
relabels (#300/#301) if the seed JSON is stale. The leaf is also recorded in
``docs/proposals/taxonomy-seed.json`` so a future full seed stays consistent.

DEFAULT IS DRY-RUN: prints the planned action, writes NOTHING. ``--apply``
requires ``--confirm``. Every run prints the sanitized DB target, and an insert
writes a JSON rollback snapshot (the created id) first.

    .venv\\Scripts\\python.exe scripts\\create_vacation_rentals_leaf.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\create_vacation_rentals_leaf.py --apply --confirm  # writes

PROD GATE (CLAUDE.md): run the dry-run, show Casey the plan, get approval, THEN a
human runs --apply --confirm against prod. The agent never runs --apply against prod.
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

LODGING_DEPT_SLUG = "lodging"
NEW_LEAF_SLUG = "vacation-rentals"
NEW_LEAF_NAME = "Vacation Rentals"


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def plan_leaf_action(existing_by_slug: dict[str, dict]) -> tuple[str, str]:
    """Decide the action from the current categories (keyed by slug).

    Each value is a dict with ``id``, ``level`` and ``parent_id``. Pure (no DB)
    so it can be unit-tested. Returns ``(action, message)`` where action is one
    of ``insert`` / ``noop`` / ``abort``.
    """
    lodging = existing_by_slug.get(LODGING_DEPT_SLUG)
    if lodging is None or lodging["level"] != 0:
        return (
            "abort",
            f"level-0 department {LODGING_DEPT_SLUG!r} not found — cannot parent the leaf",
        )
    leaf = existing_by_slug.get(NEW_LEAF_SLUG)
    if leaf is not None:
        if leaf["level"] == 1 and leaf["parent_id"] == lodging["id"]:
            return ("noop", f"{NEW_LEAF_SLUG!r} already a level-1 leaf under lodging")
        return (
            "abort",
            f"{NEW_LEAF_SLUG!r} already exists as level={leaf['level']} "
            f"parent_id={leaf['parent_id']} — refusing to mutate it",
        )
    return ("insert", f"insert level-1 {NEW_LEAF_SLUG!r} under lodging id={lodging['id']}")


def run(
    *,
    apply: bool = False,
    confirm: bool = False,
    snapshot_dir: Path | None = None,
    session=None,
) -> Counter:
    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")

        cats = session.query(Category).all()
        existing_by_slug = {
            c.slug: {"id": c.id, "level": c.level, "parent_id": c.parent_id} for c in cats
        }
        action, message = plan_leaf_action(existing_by_slug)
        counts[action] += 1
        print(f"plan: {action.upper()} — {message}")

        if action != "insert":
            return counts  # noop / abort: nothing to write either way

        lodging_id = existing_by_slug[LODGING_DEPT_SLUG]["id"]
        sort_order = sum(
            1 for c in cats if c.level == 1 and c.parent_id == lodging_id
        )
        print(
            f"  -> slug={NEW_LEAF_SLUG!r} name={NEW_LEAF_NAME!r} level=1 "
            f"parent_id={lodging_id} sort_order={sort_order}"
        )

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(
                f"\nREFUSING TO WRITE — --apply requires --confirm. Target is "
                f"{_sanitized_target()}."
            )
            return counts

        leaf = Category(
            slug=NEW_LEAF_SLUG, name=NEW_LEAF_NAME, level=1, sort_order=sort_order
        )
        leaf.parent_id = lodging_id
        session.add(leaf)
        session.flush()  # assign id for the snapshot

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"create_vacation_rentals_leaf_snapshot_{stamp}.json"
        snap_path.write_text(
            json.dumps(
                {
                    "created": [
                        {
                            "id": leaf.id,
                            "slug": leaf.slug,
                            "name": leaf.name,
                            "level": leaf.level,
                            "parent_id": leaf.parent_id,
                        }
                    ],
                    "rollback": f"DELETE FROM categories WHERE id = {leaf.id};",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nrollback snapshot: {snap_path} (created id={leaf.id})")

        session.commit()
        counts["committed"] += 1
        print(f"\nAPPLIED — created {NEW_LEAF_SLUG!r} (id={leaf.id}) under lodging.")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    parser.add_argument("--confirm", action="store_true", help="Required with --apply.")
    args = parser.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
