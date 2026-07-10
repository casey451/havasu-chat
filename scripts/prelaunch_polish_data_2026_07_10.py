"""Pre-launch polish data fixes (Casey 2026-07-10 decisions #2/#3/#4).

Targeted + query-driven, title-guarded, idempotent, reversible via undo CSV:

  #2 missing times (source-grounded, not guessed):
     * "Summer Free Movies … Teenage Mutant Ninja Turtles" (all-day) → 09:30 AM,
       the Star Cinemas summer-series time already published on /movies.
     * "Tiny Tots - Open Gym Play" 2026-07-22 (no time) → 10:00 AM, matching the
       same-titled P&R sibling occurrence (58246e56) from the same source.
  #3 Telesis venue: location_name is a bare street address → "Telesis Preparatory
     Academy" (a named venue; the address geocodes for directions).
  #4 the ~20 generically-venued P&R rows: normalize bare "Lake Havasu" →
     "Lake Havasu City Parks & Recreation" — the accepted, honest, lint-clean
     department default (Casey: adequate for launch; instructor-field capture is a
     post-launch improvement).

PROD DB WRITE — defaults to dry-run. ``--apply`` writes + emits an undo CSV. Runs
in CI (prelaunch-polish-data-apply workflow) where the DB secret resolves.

    .venv\\Scripts\\python.exe scripts/prelaunch_polish_data_2026_07_10.py          # dry-run
    .venv\\Scripts\\python.exe scripts/prelaunch_polish_data_2026_07_10.py --apply  # writes
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import or_  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_UNDO_CSV = "prelaunch_polish_data_undo_2026-07-10.csv"
_PR_GENERIC = "lake havasu"
_PR_DEFAULT_VENUE = "Lake Havasu City Parks & Recreation"

# id -> (expected-title substring, new start_time)
_RETIME: dict[str, tuple[str, time]] = {
    "c255d8cb-7d0e-42f5-ab0e-b0ebfabb279c": ("Teenage Mutant Ninja Turtles", time(9, 30)),
    "35bb5fac-291f-4fba-be3d-15da0d466ab2": ("Tiny Tots", time(10, 0)),
}
# id -> (expected-title substring, new location_name)
_RENAME_VENUE: dict[str, tuple[str, str]] = {
    "20ed5f40-1faa-428c-86b3-649e6c7e8876": ("Telesis", "Telesis Preparatory Academy"),
}


def _set_venue(ev: Event, name: str) -> None:
    ev.location_name = name
    ev.location_normalized = name.lower().strip()


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass
    p = argparse.ArgumentParser(description="Pre-launch polish data fixes (2026-07-10).")
    p.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = p.parse_args(argv)
    dry = not args.apply

    undo: list[dict] = []
    retimed = revenued = normalized = skipped = missing = 0

    with SessionLocal() as db:
        # #2 retime
        for eid, (expect, new_t) in _RETIME.items():
            ev = db.get(Event, eid)
            if ev is None:
                print(f"[missing] retime {eid} ({expect})")
                missing += 1
                continue
            if expect.lower() not in (ev.title or "").lower():
                print(f"[guard] retime {eid} title {ev.title!r} != {expect!r}; SKIP")
                skipped += 1
                continue
            if ev.start_time == new_t:
                print(f"[idempotent] {ev.title[:32]!r} already {new_t}; SKIP")
                skipped += 1
                continue
            print(f"[retime] {ev.date} {ev.title[:40]!r}: {ev.start_time} -> {new_t}")
            undo.append({"event_id": eid, "field": "start_time",
                         "old": str(ev.start_time), "new": str(new_t), "title": ev.title})
            retimed += 1
            if not dry:
                ev.start_time = new_t

        # #3 rename venue
        for eid, (expect, name) in _RENAME_VENUE.items():
            ev = db.get(Event, eid)
            if ev is None:
                print(f"[missing] venue {eid} ({expect})")
                missing += 1
                continue
            if expect.lower() not in (ev.title or "").lower():
                print(f"[guard] venue {eid} title {ev.title!r} != {expect!r}; SKIP")
                skipped += 1
                continue
            if (ev.location_name or "") == name:
                print(f"[idempotent] {ev.title[:32]!r} venue already {name!r}; SKIP")
                skipped += 1
                continue
            print(f"[venue] {ev.title[:40]!r}: {ev.location_name!r} -> {name!r}")
            undo.append({"event_id": eid, "field": "location_name",
                         "old": ev.location_name or "", "new": name, "title": ev.title})
            revenued += 1
            if not dry:
                _set_venue(ev, name)

        # #4 normalize bare "Lake Havasu" P&R venues to the department default
        pr = (
            db.query(Event)
            .filter(Event.status == "live")
            .filter(or_(Event.event_url.ilike("%/185/parks-recreation#cal%"),
                        Event.source.ilike("%parks_rec%")))
            .all()
        )
        for ev in pr:
            if (ev.location_name or "").strip().lower() != _PR_GENERIC:
                continue
            print(f"[normalize] {ev.date} {ev.title[:34]!r}: {ev.location_name!r} -> {_PR_DEFAULT_VENUE!r}")
            undo.append({"event_id": ev.id, "field": "location_name",
                         "old": ev.location_name or "", "new": _PR_DEFAULT_VENUE, "title": ev.title})
            normalized += 1
            if not dry:
                _set_venue(ev, _PR_DEFAULT_VENUE)

        if not dry:
            db.commit()

    if not dry and undo:
        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["event_id", "field", "old", "new", "title"])
            w.writeheader()
            w.writerows(undo)

    verb = "would" if dry else "DID"
    print(f"\nsummary — {verb}: retime {retimed}, rename-venue {revenued}, "
          f"normalize-PR-venue {normalized}  (skipped {skipped}, missing {missing})")
    if dry:
        print("DRY RUN — no DB writes. Re-run with --apply (prod-data gate).")
    else:
        print(f"APPLIED. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
