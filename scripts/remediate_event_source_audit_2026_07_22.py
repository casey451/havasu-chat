"""Remediate the high-confidence items from the 2026-07-22 source-audit triage.

Gated + reversible — the standard dry-run -> counts -> Casey approves -> apply
flow (CLAUDE.md). Every fix is GUARDED: it only touches a row still in the
exact known-bad state the 2026-07-22 nightly audit saw (id + the specific
wrong value), so the op is idempotent and cannot clobber a row a later scrape
already changed. A full undo snapshot (JSON) of every touched row's relevant
fields is written before commit.

Scope — the triage of prelaunch-verify run #13's 209 findings (breakdown and
per-item provenance in docs/audits/2026-07/EVENT_SOURCE_AUDIT_TRIAGE_2026-07-22.md):

  1. time    3 fixes the audit itself verified against the source's JSON-LD
             (Crosscutt 20:00->20:30, Cirque gala 00:00->19:00, Lizard Peak
             Scramble 06:30->06:45).
  2. title   3 ALL-CAPS titles -> branded / title case (Hav-A-Sis x2 matching
             their other listing's branding, Havasu Heroes festival).
  3. venue   Two series storing a bare street address as the venue: Lake
             Havasu Farmers Market ('2144 McCulloch…') -> 'The KAWS, Downtown
             Lake Havasu' (the market's own stated venue, per its site);
             Grace Arts shows ('2146 McCulloch Blvd' — their own theater's
             address) -> 'Grace Arts Live'.
  4. dedup   11 same-date twin pairs among far-future marquee events (the
             month-view duplicates): loser -> status='duplicate', survivor
             absorbs provenance via combine_sources — the Crosscutt/collapse
             convention. Survivor choice: higher source priority, else the
             fuller/official title.

Deliberately NOT touched (see the triage doc): the two season_out_of_season
flags (the names are plausibly the events' real names), the Parade of Homes
venue (needs a human read of its description), and all ~180 systemic findings
(SOURCE_IS_HOMEPAGE / UNVERIFIABLE / UNREACHABLE repeats — those need the
audit-policy change proposed in the doc, not row edits).

Usage:
  python -m scripts.remediate_event_source_audit_2026_07_22                  # DRY RUN
  python -m scripts.remediate_event_source_audit_2026_07_22 --apply          # write
  python -m scripts.remediate_event_source_audit_2026_07_22 --undo-from FILE --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.contrib.event_reconciler import combine_sources  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

# --- fix lists (ids + expected values from discrepancies.csv, run #13) -------

TIME_FIXES: list[tuple[str, time, time]] = [
    # (event_id, expected current start, corrected start) — audit JSON-LD values
    ("29e9105e-b901-4606-ab5d-bcd3b3ced3c2", time(20, 0), time(20, 30)),  # Crosscutt @ Flying X 08-01
    ("fad143e1-bb8d-4a6c-8950-3691efc833b7", time(0, 0), time(19, 0)),  # Cirque de Masquerade 09-11
    ("0e5cf483-3fdb-426f-9bd0-c256c0098605", time(6, 30), time(6, 45)),  # Lizard Peak Scramble 10-17
]

TITLE_FIXES: list[tuple[str, str, str]] = [
    # (event_id, expected current title, new title)
    (
        "1f30b11d-255e-4ddf-b758-9ee986acb38c",
        "HAVASIS CHAT & CRAFT",
        "Hav-A-Sis Chat & Craft",
    ),
    (
        "1d657f64-c08d-4177-9d86-8711d5727bad",
        "HAVASIS END OF SUMMER LUNCH",
        "Hav-A-Sis End of Summer Lunch",
    ),
    (
        "20f041d7-7575-45df-96a4-c4d8dac4b382",
        "HAVASU HEROES COUNTRY MUSIC FESTIVAL FEATURING MATT FARRIS",
        "Havasu Heroes Country Music Festival featuring Matt Farris",
    ),
]

# Series venue rules: (title guard, location_name prefix guard, new venue name)
VENUE_RULES: list[tuple[str, str, str]] = [
    ("Lake Havasu Farmers Market", "2144 McCulloch", "The KAWS, Downtown Lake Havasu"),
    ("", "2146 McCulloch Blvd", "Grace Arts Live"),  # Grace Arts shows (any title)
]

# (survivor_id, loser_id, note) — same-date twins; guards re-check both rows.
MERGES: list[tuple[str, str, str]] = [
    (
        "fad143e1-bb8d-4a6c-8950-3691efc833b7",
        "58339216-0c70-4539-9e6e-1c9a1bfa9a71",
        "Cirque gala 09-11: keep the row carrying the corrected 19:00 time",
    ),
    (
        "fad143e1-bb8d-4a6c-8950-3691efc833b7",
        "c4c58b53-d9e1-46fc-966b-d9375373053e",
        "Cirque gala 09-11: 'Don't Be Greedy Gala' is the same event's alt title",
    ),
    (
        "e9743895-2335-428f-bb18-c9d1c8dc86f2",
        "58f0902d-7c8c-473d-ae99-0a82270dadff",
        "Sleepless in Havasu 09-11: keep the fuller 'Michael Alan' listing",
    ),
    (
        "313a98d0-237b-4669-9f95-0e92241cde49",
        "530ae81a-09ea-4ae3-ab62-5f0dc7110b3e",
        "Pro Watercross 09-25: near-identical titles",
    ),
    (
        "3be32e75-a7aa-4540-894a-e1ac2cc1908f",
        "86cbd5f7-c21f-4f8f-8440-f8739a6c535f",
        "IJSBA World Finals 10-03: keep river_scene (higher source priority)",
    ),
    (
        "cb893f1a-b49f-4709-be9a-e657d874522b",
        "4ad468b1-6675-4e57-9d37-7059fbe9c728",
        "Beard & Mustache 10-17: keep the 55th Anniversary title",
    ),
    (
        "c11355f0-f25b-4dc7-8326-738b4a01f1d1",
        "615cf3d6-e8d1-4455-984a-5acda28b33d9",
        "Witch Paddle 10-25: keep the clean title over '2026 Witch Paddle'",
    ),
    (
        "b65d90b3-1984-470c-b8f3-fc76b67b492b",
        "cc8fa82f-cf67-4d15-9931-c83aeca54bd5",
        "Parade of Lights 12-12: keep the specific 'Boat Parade of Lights'",
    ),
    (
        "52660d79-0898-410d-b69b-7d93e2a836df",
        "ee4b3198-a8a5-41e6-a2e3-0d38bf2ae322",
        "Balloon Festival 2027-01-21: keep the official '& Fair' title",
    ),
    (
        "b7df9692-f39b-4591-88d7-59df5e38d9a1",
        "c78f0b9b-80a1-48b1-8ede-b4cb221401dd",
        "Winterfest 2027-02-06: keep chamber '41st Annual' (higher priority)",
    ),
    (
        "d74c96e6-e682-445f-b9bd-640af844f3a0",
        "e1db2fd3-46a1-43b5-a63c-ddceacef8032",
        "All Abilities Resource Fair 09-05: same-source twin, keep fuller title",
    ),
]

_SNAPSHOT_FIELDS = (
    "title",
    "normalized_title",
    "start_time",
    "location_name",
    "location_normalized",
    "status",
    "source",
)


def _snapshot(ev: Event) -> dict[str, Any]:
    out: dict[str, Any] = {"id": ev.id}
    for f in _SNAPSHOT_FIELDS:
        v = getattr(ev, f)
        out[f] = v.isoformat() if isinstance(v, time) else v
    return out


def _restore(ev: Event, snap: dict[str, Any]) -> None:
    for f in _SNAPSHOT_FIELDS:
        v = snap[f]
        if f == "start_time" and isinstance(v, str):
            v = time.fromisoformat(v)
        setattr(ev, f, v)


def _undo(db: Any, *, undo_from: str, apply: bool) -> int:
    snaps = json.loads(Path(undo_from).read_text(encoding="utf-8"))
    n = 0
    for snap in snaps:
        ev = db.get(Event, snap["id"])
        if ev is None:
            print(f"  MISSING {snap['id']} — skipped", file=sys.stderr)
            continue
        print(f"  restore {snap['id'][:8]} '{(snap.get('title') or '')[:40]}'")
        if apply:
            _restore(ev, snap)
        n += 1
    if apply:
        db.commit()
        print(f"RESTORED {n} rows from {undo_from}")
    else:
        print(f"DRY RUN — would restore {n} rows. Re-run with --apply.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Remediate 2026-07-22 source-audit triage (gated).")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--undo-from", help="restore from a prior undo snapshot instead")
    args = p.parse_args(argv)

    with SessionLocal() as db:
        if args.undo_from:
            return _undo(db, undo_from=args.undo_from, apply=args.apply)

        undo: list[dict[str, Any]] = []
        planned = skipped = 0

        def guard_fail(what: str, why: str) -> None:
            nonlocal skipped
            skipped += 1
            print(f"  SKIP  {what}: {why}")

        # 1. time fixes -----------------------------------------------------
        for eid, expect, new in TIME_FIXES:
            ev = db.get(Event, eid)
            if ev is None:
                guard_fail(f"time {eid[:8]}", "row not found")
                continue
            if ev.start_time != expect:
                guard_fail(f"time {eid[:8]}", f"start_time is {ev.start_time}, expected {expect}")
                continue
            print(f"  time  {eid[:8]} '{(ev.title or '')[:40]}' {expect} -> {new}")
            planned += 1
            if args.apply:
                undo.append(_snapshot(ev))
                ev.start_time = new

        # 2. title fixes ----------------------------------------------------
        for eid, expect, new in TITLE_FIXES:
            ev = db.get(Event, eid)
            if ev is None:
                guard_fail(f"title {eid[:8]}", "row not found")
                continue
            if (ev.title or "") != expect:
                guard_fail(f"title {eid[:8]}", f"title is {(ev.title or '')[:40]!r}, expected known ALL-CAPS")
                continue
            print(f"  title {eid[:8]} {expect[:34]!r} -> {new[:40]!r}")
            planned += 1
            if args.apply:
                undo.append(_snapshot(ev))
                ev.title = new
                ev.normalized_title = new.lower()

        # 3. series venue names ---------------------------------------------
        for title_guard, addr_prefix, venue in VENUE_RULES:
            stmt = select(Event).where(Event.status == "live")
            rows = [
                ev
                for ev in db.scalars(stmt)
                if (ev.location_name or "").startswith(addr_prefix)
                and (not title_guard or (ev.title or "") == title_guard)
            ]
            for ev in rows:
                print(
                    f"  venue {str(ev.id)[:8]} {ev.date} '{(ev.title or '')[:34]}' "
                    f"{(ev.location_name or '')[:26]!r} -> {venue!r}"
                )
                planned += 1
                if args.apply:
                    undo.append(_snapshot(ev))
                    ev.location_name = venue
                    ev.location_normalized = venue.lower()

        # 4. twin merges ----------------------------------------------------
        for surv_id, loser_id, note in MERGES:
            surv, loser = db.get(Event, surv_id), db.get(Event, loser_id)
            if surv is None or loser is None:
                guard_fail(f"merge {surv_id[:8]}<-{loser_id[:8]}", "row(s) not found")
                continue
            if loser.status != "live":
                guard_fail(f"merge {surv_id[:8]}<-{loser_id[:8]}", f"loser status is {loser.status!r}")
                continue
            if surv.status != "live":
                guard_fail(f"merge {surv_id[:8]}<-{loser_id[:8]}", f"survivor status is {surv.status!r}")
                continue
            if surv.date != loser.date:
                guard_fail(f"merge {surv_id[:8]}<-{loser_id[:8]}", "dates differ — not the same occurrence")
                continue
            print(
                f"  dedup {surv.date} keep {surv_id[:8]} '{(surv.title or '')[:34]}' "
                f"<- retire {loser_id[:8]} '{(loser.title or '')[:34]}'  ({note})"
            )
            planned += 1
            if args.apply:
                undo.append(_snapshot(surv))
                undo.append(_snapshot(loser))
                loser.status = "duplicate"
                surv.source = combine_sources(surv.source or "", loser.source or "")

        print(f"\nplanned={planned}  skipped_by_guard={skipped}")
        if not args.apply:
            print("DRY RUN — no DB writes. Re-run with --apply to write (prod-data gate).")
            return 0

        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        undo_path = f"remediate_event_source_audit_undo_{stamp}.json"
        Path(undo_path).write_text(json.dumps(undo, indent=1), encoding="utf-8")
        db.commit()
        print(f"APPLIED {planned} fixes. Undo snapshot: {undo_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
