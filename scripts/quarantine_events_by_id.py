"""Quarantine specific LIVE event rows by id (pull them from the public calendar).

The inverse of ``scripts/approve_pending_events.py``: that publishes a pending
contribution by id; this pulls a *live* Event out of the public calendar/ICS by
id, moving ``status="live" -> "pending_review"`` (exactly what the parks-rec
quarantine scripts do, and what ``app/events/permalink.py`` treats as hidden).

Why this exists: the nightly ``prelaunch-verify`` source audit
(``scripts/prelaunch_verify.py``) flags live events whose source now disagrees
(dead link, changed/gone date, redirect to a generic homepage) with
``proposed_action="quarantine"`` and a stable event id. Acting on those was
one-off-script-per-finding until now; this is the standing, id-scoped,
reversible tool so a confirmed bad row can be held for review without shipping a
bespoke remediation each time.

Guarded + reversible (CLAUDE.md dry-run -> counts -> approve -> apply):
  * dry-run by default; ``--apply`` writes.
  * each id only acts on a row still ``status="live"`` -- a row already
    pending/expired/deleted is a NO-OP, so re-runs are safe and idempotent.
  * ``--undo-json`` writes a snapshot (id + old status) before commit; restore
    with ``--undo-from <file> --apply``.

Usage:
    python scripts/quarantine_events_by_id.py --ids "9dd3a8af-...."            # dry-run
    python scripts/quarantine_events_by_id.py --ids "id1,id2" --apply --undo-json undo.json
    python scripts/quarantine_events_by_id.py --undo-from undo.json --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_LIVE = "live"
_HELD = "pending_review"


def _parse_ids(raw: list[str] | None) -> list[str]:
    """Flatten repeated --ids and split on comma/space; preserve order, dedupe."""
    out: list[str] = []
    seen: set[str] = set()
    for chunk in raw or []:
        for tok in chunk.replace(",", " ").split():
            if tok and tok not in seen:
                seen.add(tok)
                out.append(tok)
    return out


def _quarantine(db, ids: list[str], *, apply: bool, undo_json: str | None, reason: str) -> int:
    snapshots: list[dict[str, Any]] = []
    held = skipped = missing = 0
    for eid in ids:
        ev = db.get(Event, eid)
        if ev is None:
            print(f"  MISSING  {eid[:8]}: no such event — skip")
            missing += 1
            continue
        if ev.status != _LIVE:
            print(f"  NO-OP    {eid[:8]}: status={ev.status!r} (not live) — skip")
            skipped += 1
            continue
        verb = "QUARANTINE" if apply else "would quarantine"
        print(f"  {verb:16s} {eid[:8]}: {ev.status!r} -> {_HELD!r}  "
              f"{str(ev.date)} {ev.start_time or ''}  {(ev.title or '')[:48]!r}")
        if apply:
            snapshots.append({"id": ev.id, "old_status": ev.status,
                              "title": ev.title, "date": str(ev.date), "reason": reason})
            ev.status = _HELD
        held += 1

    total = len(ids)
    if not apply:
        print(f"\nDRY RUN: would_quarantine={held} skipped={skipped} missing={missing} of {total}. "
              f"Pass --apply to write.")
        return held
    db.commit()
    print(f"\nAPPLIED: quarantined={held} skipped={skipped} missing={missing} of {total}.")
    if undo_json:
        Path(undo_json).write_text(json.dumps(snapshots, indent=2), encoding="utf-8")
        print(f"undo snapshot -> {undo_json} ({len(snapshots)} row(s)); "
              f"restore with --undo-from {undo_json} --apply")
    return held


def _undo(db, *, undo_from: str, apply: bool) -> int:
    rows = json.loads(Path(undo_from).read_text(encoding="utf-8"))
    print(f"restoring {len(rows)} row(s) from {undo_from}:")
    n = 0
    for snap in rows:
        ev = db.get(Event, snap["id"])
        if ev is None:
            print(f"  MISSING {snap['id'][:8]} — skip")
            continue
        ev.status = snap["old_status"]
        print(f"  restored {ev.id[:8]} -> {snap['old_status']!r}")
        n += 1
    if apply:
        db.commit()
        print(f"APPLIED: restored {n} row(s).")
    else:
        print("DRY RUN: no writes.")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Quarantine live events by id (gated, reversible).")
    p.add_argument("--ids", action="append", metavar="IDS",
                   help="event ids to quarantine (space/comma-separated; repeatable)")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--undo-json", help="on apply, write an undo snapshot to this path")
    p.add_argument("--undo-from", help="restore status from a prior undo snapshot")
    p.add_argument("--reason", default="", help="free-text reason recorded in the undo snapshot")
    args = p.parse_args(argv)

    with SessionLocal() as db:
        if args.undo_from:
            _undo(db, undo_from=args.undo_from, apply=args.apply)
            return 0
        ids = _parse_ids(args.ids)
        if not ids:
            p.error("provide --ids or --undo-from")
        _quarantine(db, ids, apply=args.apply, undo_json=args.undo_json, reason=args.reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
