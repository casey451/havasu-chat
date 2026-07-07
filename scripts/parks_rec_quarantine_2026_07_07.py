"""WS6b Phase 4 — quarantine already-published Parks & Rec vision events that the
new ingest guards would now HOLD (the golden "Glow in the Dark Painting" family:
instructor-as-venue, midnight/AM-flip times).

#748 hardened the INGEST path (future rows land held). This backfill catches the
rows that already went live BEFORE that fix and moves them from
``status="live"`` to ``status="pending_review"`` so the public calendar/ICS stops
showing a wrong "Where"/"When". A human (or the WebTrac authority, once wired)
resolves them from the /admin review queue; the change is fully reversible via
the undo CSV.

Quarantine reasons (a row can trip more than one):
  * ``non_facility_venue`` — ``location_name`` is not a known P&R facility (the
    scrambled-field signal; reuses ``lhc_parks_rec_calendar.is_known_facility``).
  * ``midnight_start``     — ``start_time`` is 00:00 (probable PM-entered-as-AM
    or a missing time; the §14.3 event-lint ``ampm_flip`` signal).

Only currently-LIVE P&R vision events are selected; already-held rows are
skipped, so re-runs are idempotent. The default venue ("Lake Havasu City Parks &
Recreation") is a valid facility and is NOT a ``non_facility_venue`` hit.

PROD DB WRITE — defaults to dry-run. ``--apply`` writes and emits an undo CSV
(CLAUDE.md: dry-run -> show counts -> Casey approves -> apply). The repo .env
DATABASE_URL is Railway's internal host, so the live run happens in CI
(parks-rec-quarantine workflow) where the DB secret resolves.

    .venv\\Scripts\\python.exe scripts/parks_rec_quarantine_2026_07_07.py          # dry-run
    .venv\\Scripts\\python.exe scripts/parks_rec_quarantine_2026_07_07.py --apply  # writes
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import or_, select  # noqa: E402

from app.contrib.lhc_parks_rec_calendar import is_known_facility  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_UNDO_CSV = "parks_rec_quarantine_undo_2026-07-07.csv"
_MIDNIGHT = time(0, 0)
_HELD_STATUS = "pending_review"


def _pr_vision_events(db):
    """Currently-live Parks & Rec vision events (calendar + flyer synthetic URLs)."""
    stmt = (
        select(Event)
        .where(
            Event.status == "live",
            or_(
                Event.source.like("%parks_rec%"),
                Event.source_url.like("%/185/Parks-Recreation#cal|%"),
            ),
        )
        .order_by(Event.date, Event.id)
    )
    return list(db.scalars(stmt).all())


def _reasons(ev: Event) -> list[str]:
    reasons: list[str] = []
    if not is_known_facility(ev.location_name):
        reasons.append("non_facility_venue")
    if ev.start_time == _MIDNIGHT:
        reasons.append("midnight_start")
    return reasons


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Quarantine bad live Parks & Rec vision events.")
    p.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = p.parse_args(argv)
    dry = not args.apply

    by_reason: Counter = Counter()
    by_source: Counter = Counter()
    venue_counts: Counter = Counter()
    undo_rows: list[dict] = []
    scanned = 0
    with SessionLocal() as db:
        events = _pr_vision_events(db)
        scanned = len(events)
        for ev in events:
            venue_counts[ev.location_name] += 1
            reasons = _reasons(ev)
            if not reasons:
                continue
            by_source[ev.source] += 1
            for r in reasons:
                by_reason[r] += 1
            undo_rows.append({
                "event_id": ev.id,
                "title": ev.title,
                "date": ev.date.isoformat() if ev.date else "",
                "start_time": ev.start_time.isoformat() if ev.start_time else "",
                "venue": ev.location_name,
                "source": ev.source,
                "reasons": "|".join(reasons),
                "old_status": ev.status,
            })
            if not dry:
                ev.status = _HELD_STATUS
        if not dry:
            db.commit()

    if not dry and undo_rows:
        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(undo_rows[0].keys()))
            w.writeheader()
            w.writerows(undo_rows)

    verb = "would quarantine" if dry else "QUARANTINED"
    print(f"parks-rec vision events scanned (status=live): {scanned}")
    print(f"{verb} (status live -> {_HELD_STATUS}): {len(undo_rows)}")
    print("  by reason (a row may trip both):")
    for reason, n in sorted(by_reason.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"    {reason:<20} {n}")
    print("  by source:")
    for src, n in sorted(by_source.items()):
        print(f"    {src:<24} {n}")
    print("\nDISTINCT VENUES (all scanned) — [KEEP]=real location / [hold]=rejected:")
    for venue, n in sorted(venue_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        verdict = "KEEP" if is_known_facility(venue) else "hold"
        print(f"  {n:>3}  [{verdict}]  {venue!r}")

    print("\nsample (first 15) — the events that would leave the public calendar:")
    for row in undo_rows[:15]:
        print(
            f"  {row['date']} {row['start_time']:<9} venue={row['venue']!r:<38} "
            f"[{row['reasons']}] {row['title']!r}"
        )
    if dry:
        print("\nDRY RUN — no DB writes. Re-run with --apply to quarantine (prod-data gate).")
    else:
        print(f"\nAPPLIED. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
