"""Correct the "Stength" -> "Strength" typo on live Split Finger rows (2026-07-15).

The RunSwift source misspells the recurring class "Strength/Conditioning/Agility"
as "Stength/Conditioning/Agility", and the connector passed the vendor title
through verbatim. The connector is now fixed at the root
(``app/events/scrapers/split_finger.py`` ``_clean_source_name``) so re-scrapes
publish it correctly; this repairs the rows that already landed with the typo.

Reuses the connector's exact ``_SOURCE_TITLE_FIXES`` so the backfill and the
scraper can never drift. Per touched Event row: ``title`` and (because it is a
stored column set to ``title.lower().strip()`` and used by ``find_duplicate``)
``normalized_title`` are recomputed, plus ``description`` if it carried the typo.
Pending contributions are fixed too so an approve-later can't republish it.

Gated + reversible (CLAUDE.md dry-run -> counts -> approve -> apply). GUARDED:
only touches a row whose text still contains the typo, so it is idempotent. Writes
an undo snapshot before commit.

Usage:
    python scripts/fix_split_finger_title_typo_2026_07_15.py                    # DRY RUN
    python scripts/fix_split_finger_title_typo_2026_07_15.py --apply --undo-json undo.json
    python scripts/fix_split_finger_title_typo_2026_07_15.py --undo-from undo.json --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution, Event  # noqa: E402
from app.events.scrapers.split_finger import _SOURCE_TITLE_FIXES  # noqa: E402

_SOURCE = "split_finger"


def _fix_text(s: str | None) -> str | None:
    if not s:
        return s
    out = s
    for pat, repl in _SOURCE_TITLE_FIXES:
        out = pat.sub(repl, out)
    return out


def _fix_events(db, *, apply: bool, snapshots: list[dict[str, Any]]) -> int:
    rows = db.query(Event).filter(Event.source == _SOURCE).all()
    changed = 0
    by_status: Counter[str] = Counter()
    for ev in sorted(rows, key=lambda e: (str(e.date), e.title or "")):
        new_title = _fix_text(ev.title)
        new_desc = _fix_text(ev.description)
        if new_title == ev.title and new_desc == ev.description:
            continue
        by_status[ev.status] += 1
        print(f"  event {ev.status:14s} {str(ev.date)}  {ev.title!r} -> {new_title!r}")
        if apply:
            snapshots.append({
                "kind": "event", "id": ev.id, "old_title": ev.title,
                "old_normalized_title": ev.normalized_title, "old_description": ev.description,
            })
            if new_title != ev.title:
                ev.title = new_title or ev.title
                ev.normalized_title = (new_title or "").lower().strip()
            if new_desc != ev.description:
                ev.description = new_desc or ev.description
        changed += 1
    if by_status:
        print(f"  event rows by status: {dict(by_status)}")
    return changed


def _fix_contributions(db, *, apply: bool, snapshots: list[dict[str, Any]]) -> int:
    rows = (
        db.query(Contribution)
        .filter(Contribution.source == _SOURCE, Contribution.status == "pending")
        .all()
    )
    changed = 0
    for c in rows:
        new_name = _fix_text(c.submission_name)
        new_notes = _fix_text(c.submission_notes)
        if new_name == c.submission_name and new_notes == c.submission_notes:
            continue
        print(f"  contrib pending id={c.id}  {c.submission_name!r} -> {new_name!r}")
        if apply:
            snapshots.append({
                "kind": "contribution", "id": c.id,
                "old_submission_name": c.submission_name, "old_submission_notes": c.submission_notes,
            })
            c.submission_name = new_name or c.submission_name
            c.submission_notes = new_notes
        changed += 1
    return changed


def _run(db, *, apply: bool, undo_json: str | None) -> int:
    snapshots: list[dict[str, Any]] = []
    print("=== Events ===")
    n_ev = _fix_events(db, apply=apply, snapshots=snapshots)
    print("=== Pending contributions ===")
    n_c = _fix_contributions(db, apply=apply, snapshots=snapshots)
    total = n_ev + n_c
    if not apply:
        print(f"\nDRY RUN: would update {n_ev} event row(s) + {n_c} pending contribution(s) "
              f"= {total} total. Pass --apply to write.")
        return total
    db.commit()
    print(f"\nAPPLIED: {n_ev} event(s) + {n_c} contribution(s) = {total} row(s) updated.")
    if undo_json:
        Path(undo_json).write_text(json.dumps(snapshots, indent=2), encoding="utf-8")
        print(f"undo snapshot -> {undo_json} ({len(snapshots)} row(s))")
    return total


def _undo(db, *, undo_from: str, apply: bool) -> int:
    rows = json.loads(Path(undo_from).read_text(encoding="utf-8"))
    print(f"restoring {len(rows)} row(s) from {undo_from}:")
    n = 0
    for snap in rows:
        if snap["kind"] == "event":
            ev = db.get(Event, snap["id"])
            if ev is None:
                continue
            ev.title = snap["old_title"]
            ev.normalized_title = snap["old_normalized_title"]
            ev.description = snap["old_description"]
        else:
            c = db.get(Contribution, snap["id"])
            if c is None:
                continue
            c.submission_name = snap["old_submission_name"]
            c.submission_notes = snap["old_submission_notes"]
        n += 1
    if apply:
        db.commit()
        print(f"APPLIED: restored {n} row(s).")
    else:
        print("DRY RUN: no writes.")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fix split_finger 'Stength' typo (gated).")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--undo-json", help="on apply, write an undo snapshot to this path")
    p.add_argument("--undo-from", help="restore from a prior undo snapshot")
    args = p.parse_args(argv)
    with SessionLocal() as db:
        if args.undo_from:
            _undo(db, undo_from=args.undo_from, apply=args.apply)
        else:
            _run(db, apply=args.apply, undo_json=args.undo_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
