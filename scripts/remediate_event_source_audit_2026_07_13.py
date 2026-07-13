"""Remediate the high-confidence defects from the 2026-07-13 event source audit.

Gated + reversible — the standard dry-run -> counts -> Casey approves -> apply
flow (CLAUDE.md). Every fix is GUARDED: it only touches a row still in the exact
known-bad state the audit saw (id + the specific wrong value), so the op is
idempotent and cannot clobber a row a later scrape already changed. A full undo
snapshot (JSON) of every touched row's relevant fields is written before commit.

Scope — only the fixes verified by re-fetching each source (see
docs/audits/2026-07/EVENT_SOURCE_AUDIT_2026-07-13.md):

  1. redate   Cirque de Masquerade Charity Gala  2026-09-12 -> 2026-09-11
              (source page: "Friday, September 11th, 2026"; Sep 11 is a Friday).
  2. repoint  London Bridge Days Parade  event_url/source_url
              https://londonbridgedays.com/parade/ (404) -> https://londonbridgedays.com/
              (the /parade/ deep link 404s; the site root is live).
  3. dedup    Crosscutt @ Flying X Saloon 2026-07-31 — retire the allevents.in
              duplicate (status=deleted); keep the go_lake_havasu row (already
              correct, 20:30). Casey chose keep-go_lake_havasu.
  4. venue    Four allevents rows storing the generic "Lake Havasu" -> the named
              venue the source page gives (Rotary Park / Mudshark / Southside /
              Llamaste Yoga).
  5. time     Shoreline to Skyline UTV Adventure  00:00 -> 18:00 (placeholder
              midnight; source says 6:00 PM).

Deliberately NOT auto-fixed (left for review): the 35 bare-address venues and 10
pickleball all-day rows (each needs a NAMED venue / real hours we can't derive),
the two allevents 15–30 min time nudges (our stored value isn't clearly wrong),
and past-dated-live rows (handled by the retuned expire cron).

Usage:
  python scripts/remediate_event_source_audit_2026_07_13.py                    # DRY RUN
  python scripts/remediate_event_source_audit_2026_07_13.py --apply --undo-json undo.json
  python scripts/remediate_event_source_audit_2026_07_13.py --undo-from undo.json --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_GENERIC_VENUES = {"", "lake havasu", "lake havasu city"}
# Snapshot these fields for undo (superset of everything any fix touches).
_SNAPSHOT_FIELDS = (
    "date", "status", "start_time", "location_name", "location_normalized",
    "event_url", "source_url",
)


def _named_venue_change(name: str) -> Callable[[Event], dict[str, Any]]:
    def _change(ev: Event) -> dict[str, Any]:
        return {"location_name": name, "location_normalized": name.lower().strip()}
    return _change


def _repoint_parade(ev: Event) -> dict[str, Any]:
    old, new = "londonbridgedays.com/parade/", "londonbridgedays.com/"
    out: dict[str, Any] = {}
    for field in ("event_url", "source_url"):
        val = getattr(ev, field, None)
        if val and old in val:
            out[field] = val.replace(old, new)
    return out


@dataclass
class Fix:
    event_id: str
    label: str
    guard: Callable[[Event], bool]
    change: Callable[[Event], dict[str, Any]]


def _title_has(sub: str) -> Callable[[Event], bool]:
    return lambda ev: sub in (ev.title or "").lower()


def _generic_venue(ev: Event) -> bool:
    return (ev.location_name or "").strip().lower() in _GENERIC_VENUES


FIXES: list[Fix] = [
    Fix(
        "fad143e1-bb8d-4a6c-8950-3691efc833b7",
        "redate Cirque gala 2026-09-12 -> 2026-09-11",
        lambda ev: ev.status == "live" and ev.date == date(2026, 9, 12) and "cirque" in (ev.title or "").lower(),
        lambda ev: {"date": date(2026, 9, 11)},
    ),
    Fix(
        "99a38686-d69e-4ed4-a12f-5a4c1fe7c66c",
        "repoint London Bridge Days Parade /parade/ (404) -> site root",
        lambda ev: ev.status == "live"
        and "londonbridgedays.com/parade/" in ((ev.event_url or "") + (ev.source_url or "")),
        _repoint_parade,
    ),
    Fix(
        "66ad5275-9c79-4713-a416-b468eb8758d3",
        "retire allevents Crosscutt dup (keep go_lake_havasu 8a83283d)",
        lambda ev: ev.status == "live" and ev.date == date(2026, 7, 31) and "crosscutt" in (ev.title or "").lower(),
        lambda ev: {"status": "deleted"},
    ),
    Fix(
        "c26f0760-45f9-49ac-8a9d-216607509360",
        "venue Yoga Nidra & Sound Bath -> Llamaste Yoga and Healing",
        lambda ev: ev.status == "live" and _generic_venue(ev) and "yoga nidra" in (ev.title or "").lower(),
        _named_venue_change("Llamaste Yoga and Healing"),
    ),
    Fix(
        "aafdf8f4-f0c2-4868-8a99-218b95a282ea",
        "venue Water Ballon War -> Rotary Park",
        lambda ev: ev.status == "live" and _generic_venue(ev) and "water ballon" in (ev.title or "").lower(),
        _named_venue_change("Rotary Park"),
    ),
    Fix(
        "78849908-5a31-4e38-a6f6-8bcf68e5211b",
        "venue Girls Night In -> Southside District",
        lambda ev: ev.status == "live" and _generic_venue(ev) and "girls night in" in (ev.title or "").lower(),
        _named_venue_change("Southside District"),
    ),
    Fix(
        "d113e223-fab7-416b-9485-cfaabbbf5048",
        "venue LHHS Reunion -> Mudshark Brewery and Public House",
        lambda ev: ev.status == "live" and _generic_venue(ev) and "reunion" in (ev.title or "").lower(),
        _named_venue_change("Mudshark Brewery and Public House"),
    ),
    Fix(
        "741b4a89-06ca-429e-b6c3-f51984560988",
        "time Shoreline to Skyline UTV Adventure 00:00 -> 18:00",
        lambda ev: ev.status == "live"
        and ev.start_time == time(0, 0)
        and "shoreline to skyline" in (ev.title or "").lower(),
        lambda ev: {"start_time": time(18, 0)},
    ),
]


def _snapshot(ev: Event) -> dict[str, Any]:
    snap: dict[str, Any] = {"id": ev.id}
    for f in _SNAPSHOT_FIELDS:
        v = getattr(ev, f, None)
        snap[f] = v.isoformat() if hasattr(v, "isoformat") else v
    return snap


def _coerce(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field == "date":
        return date.fromisoformat(value)
    if field == "start_time":
        return time.fromisoformat(value)
    return value


def _diff(ev: Event, changes: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """Only the fields whose value actually differs (idempotent no-op safe)."""
    return {k: (getattr(ev, k, None), v) for k, v in changes.items() if getattr(ev, k, None) != v}


def _apply(db, *, apply: bool, undo_json: str | None) -> int:
    snapshots: list[dict[str, Any]] = []
    changed_rows = 0
    for fix in FIXES:
        ev = db.get(Event, fix.event_id)
        head = f"[{fix.label}]"
        if ev is None:
            print(f"  MISSING {head}: {fix.event_id} not found — skip")
            continue
        if not fix.guard(ev):
            print(f"  NO-OP  {head}: row not in known-bad state (id {fix.event_id[:8]}) — skip")
            continue
        diff = _diff(ev, fix.change(ev))
        if not diff:
            print(f"  NO-OP  {head}: already correct — skip")
            continue
        print(f"  FIX    {head}")
        for field, (old, new) in diff.items():
            print(f"           {field}: {old!r} -> {new!r}")
        if apply:
            snapshots.append(_snapshot(ev))
            for field, (_old, new) in diff.items():
                setattr(ev, field, new)
        changed_rows += 1

    if not apply:
        print(f"\nDRY RUN: {changed_rows} row(s) would change. Pass --apply to write.")
        return changed_rows
    db.commit()
    print(f"\nAPPLIED: {changed_rows} row(s) changed.")
    if undo_json:
        Path(undo_json).write_text(json.dumps(snapshots, indent=2), encoding="utf-8")
        print(f"undo snapshot -> {undo_json} ({len(snapshots)} row(s))")
    return changed_rows


def _undo(db, *, undo_from: str, apply: bool) -> int:
    rows = json.loads(Path(undo_from).read_text(encoding="utf-8"))
    print(f"restoring {len(rows)} row(s) from {undo_from}:")
    n = 0
    for snap in rows:
        ev = db.get(Event, snap["id"])
        if ev is None:
            print(f"  MISSING {snap['id']} — skip")
            continue
        for field in _SNAPSHOT_FIELDS:
            if field in snap:
                setattr(ev, field, _coerce(field, snap[field]))
        print(f"  restored {ev.id[:8]}")
        n += 1
    if apply:
        db.commit()
        print(f"APPLIED: restored {n} row(s).")
    else:
        print("DRY RUN: no writes.")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Remediate 2026-07-13 event source audit (gated).")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--undo-json", help="on apply, write an undo snapshot to this path")
    p.add_argument("--undo-from", help="restore from a prior undo snapshot")
    args = p.parse_args(argv)
    with SessionLocal() as db:
        if args.undo_from:
            _undo(db, undo_from=args.undo_from, apply=args.apply)
        else:
            _apply(db, apply=args.apply, undo_json=args.undo_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
