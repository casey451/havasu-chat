"""Quarantine the 6 Parks & Rec vision events whose title's weekday contradicts
their date — the 2026-07-10 pre-launch deep-verify `weekday_mismatch` findings.

These are a systematic vision-OCR grid off-by-one: every one is exactly ±1 day
from the weekday named in its title (a weekly "Creative Mondays" class listed on
Sun/Tue; "Fishing Fridays" listed on Sat). They are FLYER-ONLY rows — the WebTrac
canary stays green on them because WebTrac has no registration twin, so there is
NO authoritative source to re-date them from here. Rather than GUESS a corrected
date (CLAUDE.md: don't guess), we quarantine (status live -> pending_review): the
wrong-dated row leaves the public calendar and lands in /admin, where staff re-date
it from the flyer and republish. Fully reversible via the undo CSV.

Targeted by ID (a fixed manifest, NOT a lint sweep) so it can only touch these 6 —
crucially it does NOT sweep the ~37 generic-venue P&R rows that the now-merged
`venue_not_facility` lint would otherwise pull in. Each row is title-guarded and
idempotent.

PROD DB WRITE — defaults to dry-run. ``--apply`` writes + emits an undo CSV. Runs
in CI (parks-rec-weekday-quarantine-apply workflow) where the DB secret resolves.

    .venv\\Scripts\\python.exe scripts/parks_rec_weekday_quarantine_2026_07_10.py          # dry-run
    .venv\\Scripts\\python.exe scripts/parks_rec_weekday_quarantine_2026_07_10.py --apply  # writes
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_UNDO_CSV = "parks_rec_weekday_quarantine_undo_2026-07-10.csv"
_HELD_STATUS = "pending_review"

# (event_id, expected-title substring, note) — the 6 weekday_mismatch rows.
_ROWS: list[tuple[str, str, str]] = [
    ("996a64a3-f587-4f82-8421-3527fab70161", "Creative Mondays", "listed Sun 2026-07-12, title says Monday"),
    ("380a3d19-1541-4f28-876f-647f2db9199c", "Creative Mondays", "listed Tue 2026-07-14, title says Monday"),
    ("fa677ff5-4ea2-4e71-a30f-3140d07409e9", "Fishing Fridays", "listed Sat 2026-07-18, title says Friday"),
    ("55956341-87fc-4ba5-a298-a43f56ace76a", "Creative Mondays", "listed Sun 2026-07-19, title says Monday"),
    ("047fe916-59fd-4516-847b-d61d9a76f1be", "Creative Mondays", "listed Sun 2026-07-19, title says Monday"),
    ("30435722-a684-41cb-8c71-e45f8d7b928e", "Creative Mondays", "listed Sun 2026-07-26, title says Monday"),
]


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass
    p = argparse.ArgumentParser(description="Quarantine the 6 P&R weekday-mismatch rows.")
    p.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = p.parse_args(argv)
    dry = not args.apply

    undo_rows: list[dict] = []
    quarantined = skipped = missing = 0
    with SessionLocal() as db:
        for eid, expect, note in _ROWS:
            ev = db.get(Event, eid)
            if ev is None:
                print(f"[missing] {eid} — not found; SKIP ({expect})")
                missing += 1
                continue
            if expect.lower() not in (ev.title or "").lower():
                print(f"[guard] {eid} title {ev.title!r} != expected {expect!r}; SKIP")
                skipped += 1
                continue
            if ev.status != "live":
                print(f"[idempotent] {ev.title!r} ({ev.date}) already status={ev.status!r}; SKIP")
                skipped += 1
                continue
            print(f"[quarantine] {ev.date} {ev.title!r} (live -> {_HELD_STATUS}) — {note}")
            undo_rows.append({"event_id": eid, "title": ev.title,
                              "date": ev.date.isoformat() if ev.date else "",
                              "old_status": ev.status, "new_status": _HELD_STATUS, "note": note})
            quarantined += 1
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
    print(f"\nsummary — {verb}: {quarantined}  (skipped {skipped}, missing {missing})")
    if dry:
        print("DRY RUN — no DB writes. Re-run with --apply (prod-data gate).")
    else:
        print(f"APPLIED. Undo CSV: {_UNDO_CSV}  (restore: set status back to old_status)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
