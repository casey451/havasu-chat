"""Backfill ``Provider.is_local`` (B7 locality tri-state).

Classifies every provider as local / not-local / unknown via
``app.core.locality.classify_is_local`` — local if the geo is within the LHC
in-area radius OR the address carries a local city token; NULL when neither
signal is usable.

DEFAULT IS DRY-RUN: prints the class distribution and writes NOTHING. The
dry-run reads only ``id / address / lat / lng`` (a column projection), so it is
safe to run BEFORE the ``is_local`` column exists (e.g. against current prod, to
preview the counts). ``--apply`` requires the column to exist (run only after the
b7islocalcol migration is deployed); it writes the value and saves a
``is_local_backfill_snapshot_*.json`` undo file first.

Usage (Windows):

    .venv\\Scripts\\python.exe scripts\\backfill_is_local.py            # DRY RUN
    .venv\\Scripts\\python.exe scripts\\backfill_is_local.py --apply --confirm
    .venv\\Scripts\\python.exe scripts\\backfill_is_local.py --all      # include drafts/inactive
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.locality import classify_is_local  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402


def _label(v: bool | None) -> str:
    return "local" if v is True else ("not_local" if v is False else "unknown")


def _sanitized_target() -> str:
    """The DB host/db the SessionLocal will hit, with credentials stripped."""
    try:
        from app.db.database import engine

        url = engine.url
        return f"{url.host}:{url.port or ''}/{url.database}"
    except Exception:
        return "(unknown)"


def dry_run(*, include_all: bool = False) -> Counter:
    """Classify every provider and report the distribution. No DB writes; reads
    only the columns the classifier needs, so it works without the is_local
    column present."""
    db = SessionLocal()
    counts: Counter = Counter()
    try:
        q = db.query(Provider.id, Provider.address, Provider.lat, Provider.lng)
        if not include_all:
            q = q.filter(Provider.is_active.is_(True), Provider.draft.is_(False))
        for _pid, address, lat, lng in q.yield_per(500):
            counts[_label(classify_is_local(address, lat, lng))] += 1
    finally:
        db.close()
    total = sum(counts.values())
    print(f"[DRY-RUN (no writes)] target={_sanitized_target()} scope="
          f"{'all' if include_all else 'active,non-draft'} providers={total}")
    for label in ("local", "not_local", "unknown"):
        n = counts.get(label, 0)
        pct = (100 * n // total) if total else 0
        print(f"  {label}: {n} ({pct}%)")
    return counts


def apply(*, include_all: bool = False) -> int:
    """Write is_local for every provider whose value would change. Saves an undo
    snapshot of the prior values first. Requires the is_local column to exist."""
    db = SessionLocal()
    changed = 0
    snapshot: list[dict[str, object]] = []
    try:
        q = db.query(Provider)
        if not include_all:
            q = q.filter(Provider.is_active.is_(True), Provider.draft.is_(False))
        for provider in q.yield_per(500):
            new = classify_is_local(provider.address, provider.lat, provider.lng)
            if new == provider.is_local:
                continue
            snapshot.append({"id": provider.id, "old": provider.is_local, "new": new})
            provider.is_local = new
            changed += 1
        if snapshot:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = _ROOT / f"is_local_backfill_snapshot_{stamp}.json"
            path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            print(f"[APPLY] undo snapshot written: {path.name} ({len(snapshot)} rows)")
        db.commit()
    finally:
        db.close()
    print(f"[APPLY] target={_sanitized_target()} changed {changed} rows")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--confirm", action="store_true", help="required alongside --apply")
    parser.add_argument("--all", action="store_true", help="include drafts and inactive rows")
    args = parser.parse_args()
    if args.apply:
        if not args.confirm:
            print("Refusing to write without --confirm. Re-run with --apply --confirm.")
            sys.exit(2)
        apply(include_all=args.all)
    else:
        dry_run(include_all=args.all)


if __name__ == "__main__":
    main()
