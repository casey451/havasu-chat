"""Restore entity_categories primaries from a leaf-backfill snapshot (gated).

``backfill_leaf_categories.py --apply`` writes a rollback snapshot of every
``entity_categories`` row it touched (BEFORE the change). This reverses that run:
it re-sets each snapshot row's ``is_primary`` to its recorded value and clears
``is_primary`` on any row the backfill INSERTED (not in the snapshot), so each
affected entity's rendered primary returns to its pre-backfill state.

Use it to undo the 2026-06-12 backfill that mis-reassigned ~122 entities from
noisy secondary google types (Dillard's → shoes, etc.) before re-running the
fixed (primary-type-only) backfill.

DEFAULT IS DRY-RUN: prints what it would change, writes nothing. ``--apply``
requires ``--confirm`` and wraps the restore in ONE transaction. Prints the
sanitized DB target every run (the repo .env can point DATABASE_URL at prod).

    .venv\\Scripts\\python.exe scripts\\restore_leaf_backfill.py --snapshot leaf_backfill_snapshot_<stamp>.json
    .venv\\Scripts\\python.exe scripts\\restore_leaf_backfill.py --snapshot leaf_backfill_snapshot_<stamp>.json --apply --confirm

PROD GATE (CLAUDE.md): dry-run, show Casey the counts, get approval, THEN a human
runs --apply --confirm. The agent never runs --apply against prod.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import EntityCategory  # noqa: E402


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def run(
    *,
    snapshot_path: Path,
    apply: bool = False,
    confirm: bool = False,
    session=None,
) -> Counter:
    """Restore primaries from ``snapshot_path``. Dry-run by default."""
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}")
        print(f"snapshot:  {snapshot_path}\n")

        snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        # id -> recorded is_primary; and the set of affected entities.
        want_primary: dict[int, bool] = {int(r["id"]): bool(r["is_primary"]) for r in snapshot}
        entity_ids = {r["entity_id"] for r in snapshot}
        snap_by_entity: dict[str, set[int]] = defaultdict(set)
        for r in snapshot:
            snap_by_entity[r["entity_id"]].add(int(r["id"]))
        counts["snapshot_rows"] = len(snapshot)
        counts["entities"] = len(entity_ids)

        rows = (
            session.query(EntityCategory)
            .filter(EntityCategory.entity_id.in_(list(entity_ids)))
            .all()
        )
        to_restore: list[tuple[EntityCategory, bool]] = []  # (row, target is_primary)
        for ec in rows:
            if ec.id in want_primary:
                target = want_primary[ec.id]
                if ec.is_primary != target:
                    to_restore.append((ec, target))
                    counts["restore_snapshot_rows"] += 1
            else:
                # inserted by the backfill (not in snapshot) -> demote.
                if ec.is_primary:
                    to_restore.append((ec, False))
                    counts["demote_inserted_rows"] += 1

        print("restore plan:")
        print(f"  {counts.get('restore_snapshot_rows', 0):>5}  snapshot rows whose is_primary differs now")
        print(f"  {counts.get('demote_inserted_rows', 0):>5}  backfill-inserted rows to demote (is_primary=False)")
        print(f"  {len(to_restore):>5}  total rows to change")
        print(f"  {counts['entities']:>5}  entities affected\n")

        if not apply:
            print("DRY RUN — no rows written. Re-run with --apply --confirm to restore.")
            return counts
        if not confirm:
            print(
                f"REFUSING TO WRITE — --apply requires --confirm. Target is "
                f"{_sanitized_target()}."
            )
            return counts

        for ec, target in to_restore:
            ec.is_primary = target
        session.commit()
        counts["rows_changed"] = len(to_restore)
        print(f"RESTORED — {len(to_restore)} rows reverted in one transaction.")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Restore primaries from a leaf-backfill snapshot.")
    ap.add_argument("--snapshot", type=Path, required=True, help="Path to the snapshot JSON.")
    ap.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    ap.add_argument("--confirm", action="store_true", help="Required with --apply.")
    args = ap.parse_args(argv)
    run(snapshot_path=args.snapshot, apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
