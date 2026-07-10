"""Backfill the real facility onto Parks & Rec vision events whose ``location_name``
is the generic "Lake Havasu" — the 2026-07-10 pre-launch systemic venue gap.

The vision pipeline extracted the facility into the DESCRIPTION ("… At Aquatic
Center. For Ages 8-12. …") but wrote the generic city name to ``location_name``.
This backfills location_name FROM that description-embedded "At {venue}." — a
source-grounded fix, not a guess — but ONLY when the extracted venue validates as
a real facility (:func:`is_known_facility`, non-strict: accepts real sub-facilities
like "Rotary Park Swim Area" while still rejecting the instructor-scramble
"Jane Camlin" and non-P&R partnership venues like "Relics & Rods"). Rows whose
"At {X}" is an instructor or an unrecognized place are LEFT generic (they need
staff / a vision re-extraction) — quarantining a real event over an imprecise-but-
not-wrong venue would be worse than leaving it.

Query-driven and idempotent (re-runnable): selects LIVE P&R vision events whose
location_name is exactly the generic "Lake Havasu". Reversible via undo CSV.

PROD DB WRITE — defaults to dry-run. ``--apply`` writes + emits an undo CSV. Runs
in CI (parks-rec-venue-backfill-apply workflow) where the DB secret resolves.

    .venv\\Scripts\\python.exe scripts/parks_rec_venue_backfill_2026_07_10.py          # dry-run
    .venv\\Scripts\\python.exe scripts/parks_rec_venue_backfill_2026_07_10.py --apply  # writes
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import or_  # noqa: E402

from app.contrib.lhc_parks_rec_calendar import is_known_facility  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_UNDO_CSV = "parks_rec_venue_backfill_undo_2026-07-10.csv"
_GENERIC = "lake havasu"  # the specific generic value to replace (NOT the dept default)
# "Title. At <venue>. For <audience>. Cost: …" — capture the venue between "At " and the next period.
_AT_RE = re.compile(r"\bAt\s+([^.]+?)\.", re.IGNORECASE)
# A bare room code ("Room 153/154") or a single generic word ("Pool", "Gym") is
# NOT a navigable venue — it's no better than the generic city name, so reject it
# even though is_known_facility(non-strict) would accept it. Real named
# sub-facilities ("Rotary Park Swim Area") have a proper name and pass.
_ROOM_CODE_RE = re.compile(r"^room\s*\d", re.IGNORECASE)
_TOO_GENERIC = {"pool", "gym", "gymnasium", "kitchen", "field", "park", "room",
                "court", "courts", "lobby", "patio", "office"}


def facility_from_description(description: str | None) -> str | None:
    """Return the description's "At {venue}." value when it validates as a real,
    NAMED P&R facility; else None. Instructor-scramble ("Jane Camlin"),
    non-facility partnership venues ("Relics & Rods"), bare room codes
    ("Room 153/154") and single generic words ("Pool") are all rejected."""
    if not description:
        return None
    m = _AT_RE.search(description)
    if not m:
        return None
    venue = m.group(1).strip()
    if _ROOM_CODE_RE.match(venue) or venue.lower() in _TOO_GENERIC:
        return None
    return venue if is_known_facility(venue, strict=False) else None


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass
    p = argparse.ArgumentParser(description="Backfill facility venue onto generic P&R vision events.")
    p.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = p.parse_args(argv)
    dry = not args.apply

    undo_rows: list[dict] = []
    scanned = fixed = no_facility = 0
    with SessionLocal() as db:
        events = (
            db.query(Event)
            .filter(Event.status == "live")
            .filter(
                or_(
                    Event.event_url.ilike("%/185/parks-recreation#cal%"),
                    Event.source.ilike("%parks_rec%"),
                )
            )
            .all()
        )
        for ev in events:
            if (ev.location_name or "").strip().lower() != _GENERIC:
                continue
            scanned += 1
            facility = facility_from_description(ev.description)
            if not facility:
                no_facility += 1
                continue
            print(f"[backfill] {ev.date} {ev.title[:34]!r}: {ev.location_name!r} -> {facility!r}")
            undo_rows.append({"event_id": ev.id, "title": ev.title,
                              "date": ev.date.isoformat() if ev.date else "",
                              "old_venue": ev.location_name, "new_venue": facility})
            fixed += 1
            if not dry:
                ev.location_name = facility
        if not dry:
            db.commit()

    if not dry and undo_rows:
        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(undo_rows[0].keys()))
            w.writeheader()
            w.writerows(undo_rows)

    verb = "would backfill" if dry else "BACKFILLED"
    print(f"\nsummary — generic 'Lake Havasu' P&R events scanned: {scanned}")
    print(f"  {verb} to a real facility: {fixed}")
    print(f"  left generic (instructor/unknown 'At X' — needs staff/vision): {no_facility}")
    if dry:
        print("DRY RUN — no DB writes. Re-run with --apply (prod-data gate).")
    else:
        print(f"APPLIED. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
