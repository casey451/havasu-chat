"""Backfill tags + derived category on the live Split Finger events (2026-07-14).

The 33 Split Finger schedule events were approved out of the review queue on
2026-07-14 via ``scripts/approve_pending_events.py``, which recovers tags from a
``Categories:`` notes line — but the split_finger contributions carried none (the
connector's ``payload.tags`` were dropped by ``event_payload_to_contribution``
before this was fixed). So they published with ``tags=[]`` and a NULL
``Event.category``: they render on the venue / calendar / /family/camps surfaces
but not under event-category facets (``/events?category=sports-and-fitness``).

This restores what a tagged approval would have written, per row:
  * ``Event.tags``     — the connector's own tags: ``_CAMP_TAGS`` (sports, youth,
    camp) for camp rows, ``_CLASS_TAGS`` (sports, fitness) for classes, decided by
    the same ``_CAMP_KEYWORD_RE`` title gate the connector uses.
  * ``Event.category`` — ``derive_event_category(tags)`` (== "sports-and-fitness"
    for both, since "sports" leads each tuple) — exactly what
    ``approve_contribution_as_event`` stamps.

Gated + reversible (CLAUDE.md dry-run -> counts -> approve -> apply). GUARDED:
only touches a live split_finger event that still has NO tags, so it is
idempotent and cannot clobber a row a later edit already tagged. Writes an undo
snapshot (id + old tags + old category) before commit.

Usage:
    python scripts/backfill_split_finger_event_tags_2026_07_14.py                    # DRY RUN
    python scripts/backfill_split_finger_event_tags_2026_07_14.py --apply --undo-json undo.json
    python scripts/backfill_split_finger_event_tags_2026_07_14.py --undo-from undo.json --apply
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

from app.contrib.source_category_map import derive_event_category  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.scrapers.split_finger import (  # noqa: E402
    _CAMP_KEYWORD_RE,
    _CAMP_TAGS,
    _CLASS_TAGS,
)

_SOURCE = "split_finger"


def _tags_for_title(title: str | None) -> list[str]:
    """Camp vs class by the same keyword gate the connector applies to titles."""
    if _CAMP_KEYWORD_RE.search(title or ""):
        return list(_CAMP_TAGS)
    return list(_CLASS_TAGS)


def _candidates(db) -> list[Event]:
    """Live split_finger events that still have no tags (the un-tagged rows)."""
    rows = (
        db.query(Event)
        .filter(Event.source == _SOURCE, Event.status == "live")
        .all()
    )
    return [ev for ev in rows if not ev.tags]


def _backfill(db, *, apply: bool, undo_json: str | None) -> int:
    events = _candidates(db)
    print(f"live split_finger events with empty tags: {len(events)}")
    snapshots: list[dict[str, Any]] = []
    changed = 0
    by_cat: dict[str, int] = {}
    for ev in sorted(events, key=lambda e: (str(e.date), e.title or "")):
        tags = _tags_for_title(ev.title)
        category = derive_event_category(tags)
        kind = "camp " if _CAMP_KEYWORD_RE.search(ev.title or "") else "class"
        print(f"  {kind} {str(ev.date)}  {(ev.title or '')[:42]:42s} -> tags={tags} category={category!r}")
        by_cat[category or "None"] = by_cat.get(category or "None", 0) + 1
        if apply:
            snapshots.append({"id": ev.id, "old_tags": list(ev.tags or []),
                              "old_category": ev.category})
            ev.tags = tags
            ev.category = category
        changed += 1

    print(f"\n  category distribution: {by_cat}")
    if not apply:
        print(f"\nDRY RUN: {changed} event(s) would be tagged. Pass --apply to write.")
        return changed
    db.commit()
    print(f"\nAPPLIED: {changed} event(s) tagged.")
    if undo_json:
        Path(undo_json).write_text(json.dumps(snapshots, indent=2), encoding="utf-8")
        print(f"undo snapshot -> {undo_json} ({len(snapshots)} row(s)); "
              f"restore with --undo-from {undo_json} --apply")
    return changed


def _undo(db, *, undo_from: str, apply: bool) -> int:
    rows = json.loads(Path(undo_from).read_text(encoding="utf-8"))
    print(f"restoring {len(rows)} row(s) from {undo_from}:")
    n = 0
    for snap in rows:
        ev = db.get(Event, snap["id"])
        if ev is None:
            print(f"  MISSING {snap['id'][:8]} — skip")
            continue
        ev.tags = list(snap.get("old_tags") or [])
        ev.category = snap.get("old_category")
        print(f"  restored {ev.id[:8]} -> tags={ev.tags} category={ev.category!r}")
        n += 1
    if apply:
        db.commit()
        print(f"APPLIED: restored {n} row(s).")
    else:
        print("DRY RUN: no writes.")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Backfill split_finger event tags/category (gated).")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--undo-json", help="on apply, write an undo snapshot to this path")
    p.add_argument("--undo-from", help="restore from a prior undo snapshot")
    args = p.parse_args(argv)
    with SessionLocal() as db:
        if args.undo_from:
            _undo(db, undo_from=args.undo_from, apply=args.apply)
        else:
            _backfill(db, apply=args.apply, undo_json=args.undo_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
