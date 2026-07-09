"""Soft-deactivate specific entities by id (DRY-RUN by default; gated).

A small, reversible ``is_active = False`` for entity ids a human has confirmed —
e.g. the straggler duplicates surfaced by ``find_near_dups.py`` that
``dedup_entities.py`` correctly would not auto-merge. Pass ids inline or via a
CSV that has an ``entity_id`` column.

DEFAULT IS DRY-RUN. ``--apply`` requires ``--confirm``. Writes a rollback
snapshot of the affected ids on apply. Prints the sanitized DB target.

    .venv\\Scripts\\python.exe scripts\\deactivate_entities.py --ids id1,id2,id3
    .venv\\Scripts\\python.exe scripts\\deactivate_entities.py --csv confirmed_dups.csv --apply --confirm

PROD GATE (CLAUDE.md): dry-run → show Casey → approval → apply. The agent never
runs --apply against prod.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Entity  # noqa: E402


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def ids_from_csv(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as f:
        return [
            (row.get("entity_id") or "").strip()
            for row in csv.DictReader(f)
            if (row.get("entity_id") or "").strip()
        ]


def run(*, ids: list[str], apply: bool = False, confirm: bool = False,
        snapshot_dir: Path | None = None, session=None) -> Counter:
    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")
        ids = sorted({i for i in ids if i})
        counts["requested"] = len(ids)
        found = session.query(Entity).filter(
            Entity.id.in_(ids), Entity.is_active.is_(True)
        ).all()
        counts["active_matches"] = len(found)
        print(f"requested ids:            {len(ids)}")
        print(f"active matches to disable: {len(found)}\n")
        for e in found[:50]:
            print(f"  {e.id}  {e.name}")

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            return counts

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap = snapshot_dir / f"deactivate_snapshot_{stamp}.json"
        snap.write_text(
            json.dumps([{"entity_id": e.id, "is_active": True} for e in found], indent=2),
            encoding="utf-8",
        )
        print(f"\nrollback snapshot: {snap} ({len(found)} ids)")
        for e in found:
            e.is_active = False
        session.commit()
        counts["deactivated"] = len(found)
        print(f"\nAPPLIED — {len(found)} entities deactivated (reversible).")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Soft-deactivate entities by id (dry-run by default).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ids", help="Comma-separated entity ids.")
    g.add_argument("--csv", type=Path, help="CSV with an entity_id column.")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)
    ids = ids_from_csv(args.csv) if args.csv else [s.strip() for s in args.ids.split(",")]
    run(ids=ids, apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
