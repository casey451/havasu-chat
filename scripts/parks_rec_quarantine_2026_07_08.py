"""WS6.3 follow-up — generalized quarantine of bad LIVE Parks & Rec vision events.

Supersedes ``scripts/parks_rec_quarantine_2026_07_07.py`` (which flagged only a
00:00 midnight start and a permissive venue check). This version drives off the
shared, tested lint (:mod:`app.events.lint`) so the rules live in ONE place:

  * ``ampm_flip``          — a 12 AM–8 AM start at a non-24h venue that is NOT a
    known-early activity (lap swim / sunrise kayak / a gym open are whitelisted).
    Catches "Kids Pizza Party Cooking Class" @ 5:15 AM (the live fixture) and the
    older "Glow in the Dark Painting" @ 5:30 AM.
  * ``venue_not_facility`` — a P&R "Where" that is not a NAMED facility: a bare
    room ("Kitchen"), a room code, or a mis-mapped instructor ("Jane Camlin").
    (``is_known_facility(strict=True)`` — stricter than the #750 ingest guard,
    which deliberately keeps place-ish strings to avoid over-holding.)
  * ``venue_hours_as_event`` — a row whose text reads as open-hours, not a dated
    occurrence.
  * ``instructor_in_body``  — interim, name-scoped: the venue OR composed
    description still carries a known scrambled instructor ("Jane Camlin"), so the
    time is equally untrustworthy. (The general fix is Phase 1: WebTrac as the
    datetime authority.)

Only currently-LIVE P&R vision events are selected; already-held rows are skipped,
so re-runs are idempotent. Flagged rows move ``status="live" -> "pending_review"``
(out of the public calendar/ICS, into the /admin review queue) — fully reversible
via the undo CSV.

PROD DB WRITE — defaults to dry-run. ``--apply`` writes and emits an undo CSV
(CLAUDE.md: dry-run -> show counts -> Casey approves -> apply). The repo .env
DATABASE_URL is Railway's internal host, so the live run happens in CI
(parks-rec-quarantine workflow) where the DB secret resolves.

    .venv\\Scripts\\python.exe scripts/parks_rec_quarantine_2026_07_08.py          # dry-run
    .venv\\Scripts\\python.exe scripts/parks_rec_quarantine_2026_07_08.py --apply  # writes
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import or_, select  # noqa: E402

from app.contrib.lhc_parks_rec_calendar import is_known_facility  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.lint import lint_event  # noqa: E402

_UNDO_CSV = "parks_rec_quarantine_undo_2026-07-08.csv"
_HELD_STATUS = "pending_review"

# Known scrambled instructor tokens — Casey confirmed "Jane Camlin" is an
# instructor, not a venue. Interim signal until Phase 1 (WebTrac authority).
_INSTRUCTOR_TOKENS: frozenset[str] = frozenset({"camlin"})


def _pr_vision_events(db):
    """Currently-live Parks & Rec vision events (calendar + flyer synthetic URLs).

    The P&R synthetic "#cal|" URL lives in ``event_url`` (``source_url`` is empty
    for these rows), so filter on both plus the source tag — the same reliable
    P&R marker the 07-07 backfill settled on.
    """
    _CAL = "%/185/Parks-Recreation#cal|%"
    stmt = (
        select(Event)
        .where(
            Event.status == "live",
            or_(
                Event.source.like("%parks_rec%"),
                Event.event_url.like(_CAL),
                Event.source_url.like(_CAL),
            ),
        )
        .order_by(Event.date, Event.id)
    )
    return list(db.scalars(stmt).all())


def _reasons(ev: Event) -> list[str]:
    """Quarantine reasons for one row: the shared lint plus the interim
    instructor-token signal."""
    reasons = [f.rule for f in lint_event(ev)]
    body = f"{ev.location_name or ''} {ev.description or ''}".lower()
    if any(tok in body for tok in _INSTRUCTOR_TOKENS):
        reasons.append("instructor_in_body")
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
    print("  by reason (a row may trip more than one):")
    for reason, n in sorted(by_reason.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"    {reason:<22} {n}")
    print("  by source:")
    for src, n in sorted(by_source.items()):
        print(f"    {src:<24} {n}")
    print("\nDISTINCT VENUES (all scanned) — [KEEP]=named facility (strict) / [hold]=not:")
    for venue, n in sorted(venue_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        verdict = "KEEP" if is_known_facility(venue, strict=True) else "hold"
        print(f"  {n:>3}  [{verdict}]  {venue!r}")

    print("\nsample (first 20) — the events that would leave the public calendar:")
    for row in undo_rows[:20]:
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
