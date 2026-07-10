"""Pre-launch remediation — the CONFIRMED subset of the 2026-07-10 deep-verify pass.

Targeted and ID-driven (a fixed manifest, NOT a lint sweep), so it can only ever
touch these three rows, and only when each still matches its expected title — a
churned/re-pointed id is skipped with a warning rather than mutated blindly. Every
value here was cold-re-confirmed against the source on 2026-07-10:

  QUARANTINE (source can't be re-confirmed → status live -> pending_review):
    * "Pilates with Purpose"    — momence source URL is a 404; the stored URL is
      malformed ("momence.com/%7C/…", a leaked "|" delimiter).
    * "Monthly Council Meeting" — allevents source returns 410 Gone (deleted).

  FIX (source is live and authoritative):
    * "HAVASIS FREE SWIM DAY"   — shown at 00:00 (renders with no time); the
      allevents source startDate is 12:00. Retime 00:00 -> 12:00 AND normalize the
      ALL-CAPS title -> "Havasis Free Swim Day".

Quarantine is reversible (undo CSV restores the old status); the retime/retitle
undo CSV carries the old values. Re-runs are idempotent (a row already in its
target state is skipped).

PROD DB WRITE — defaults to dry-run. ``--apply`` writes and emits an undo CSV
(CLAUDE.md: dry-run -> show counts -> Casey approves -> apply). The repo .env
DATABASE_URL is Railway's internal host, so the live run happens in CI
(prelaunch-remediation-apply workflow) where the DB secret resolves.

    .venv\\Scripts\\python.exe scripts/prelaunch_remediation_2026_07_10.py          # dry-run
    .venv\\Scripts\\python.exe scripts/prelaunch_remediation_2026_07_10.py --apply  # writes
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

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_UNDO_CSV = "prelaunch_remediation_undo_2026-07-10.csv"
_HELD_STATUS = "pending_review"

# Quarantine: (event_id, expected-title substring, reason). The substring guards
# against acting on a re-pointed id.
_QUARANTINE: list[tuple[str, str, str]] = [
    ("9115b486-bf19-4b56-89c6-6e1dcc5fe71a", "Pilates with Purpose",
     "momence source URL 404 (malformed 'momence.com/%7C/…')"),
    ("9bb5dc87-b73b-4d3c-90b5-cb1ce1c6345f", "Monthly Council Meeting",
     "allevents source 410 Gone"),
]

# Fix: event_id -> (expected-title substring, new start_time or None, new title or None, reason).
_FIX: dict[str, tuple[str, time | None, str | None, str]] = {
    "8a7f358d-915a-4ed1-9a5f-5dcc69b0e328": (
        "FREE SWIM DAY", time(12, 0), "Havasis Free Swim Day",
        "site 00:00 (no time); allevents source startDate 12:00; ALL-CAPS title",
    ),
}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass
    p = argparse.ArgumentParser(description="Pre-launch remediation (2026-07-10 confirmed subset).")
    p.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = p.parse_args(argv)
    dry = not args.apply

    undo_rows: list[dict] = []
    quarantined = retimed = retitled = skipped = missing = 0

    with SessionLocal() as db:
        # ── quarantines ──
        for eid, expect, reason in _QUARANTINE:
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
                print(f"[idempotent] {ev.title!r} already status={ev.status!r}; SKIP")
                skipped += 1
                continue
            print(f"[quarantine] {ev.date} {ev.title!r} (status live -> {_HELD_STATUS}) — {reason}")
            undo_rows.append({"event_id": eid, "action": "quarantine", "field": "status",
                              "old_value": ev.status, "new_value": _HELD_STATUS, "title": ev.title})
            quarantined += 1
            if not dry:
                ev.status = _HELD_STATUS

        # ── fixes ──
        for eid, (expect, new_time, new_title, reason) in _FIX.items():
            ev = db.get(Event, eid)
            if ev is None:
                print(f"[missing] {eid} — not found; SKIP ({expect})")
                missing += 1
                continue
            if expect.lower() not in (ev.title or "").lower():
                print(f"[guard] {eid} title {ev.title!r} != expected {expect!r}; SKIP")
                skipped += 1
                continue
            print(f"[fix] {ev.date} {ev.title!r} — {reason}")
            if new_time is not None and ev.start_time != new_time:
                print(f"    start_time {ev.start_time} -> {new_time}")
                undo_rows.append({"event_id": eid, "action": "retime", "field": "start_time",
                                  "old_value": ev.start_time.isoformat() if ev.start_time else "",
                                  "new_value": new_time.isoformat(), "title": ev.title})
                retimed += 1
                if not dry:
                    ev.start_time = new_time
            if new_title is not None and ev.title != new_title:
                print(f"    title {ev.title!r} -> {new_title!r}")
                undo_rows.append({"event_id": eid, "action": "retitle", "field": "title",
                                  "old_value": ev.title, "new_value": new_title, "title": new_title})
                retitled += 1
                if not dry:
                    ev.title = new_title

        if not dry:
            db.commit()

    if not dry and undo_rows:
        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["event_id", "action", "field", "old_value", "new_value", "title"])
            w.writeheader()
            w.writerows(undo_rows)

    verb = "would" if dry else "DID"
    print(f"\nsummary — {verb}: quarantine {quarantined}, retime {retimed}, retitle {retitled}"
          f"  (skipped {skipped}, missing {missing})")
    if dry:
        print("DRY RUN — no DB writes. Re-run with --apply (prod-data gate).")
    else:
        print(f"APPLIED. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
