"""Correct the mis-dated "America 250" event (a July-1 celebration re-stamped onto
2026-07-12). Gated + reversible — the standard dry-run → approve → apply flow.

Background (2026-07-12): the Parks & Rec vision scraper re-read the July calendar
flyer and placed "Havasu Celebrates America 250 - Pizza Party, Open Swim, and
Proclamation" (the July-1 survivor kept by ``dedup_america250_2026_07_01.py``,
Event id ``d2ff5ad0-…``) into the July-12 cell. The row was physically re-dated:
live ``/events.ics`` served ``DTSTART=20260712T120000`` with the permalink anchor
``…#cal|2026-07-12|…``. That put a stale copy of a past event on today's calendar.

It's a one-off (the ICS date histogram shows no pile-up on 2026-07-12, and there is
no ``date.today()`` day-default in the ingest paths), so no fleet-wide guard is
needed — just this single row.

Fix: restore the true date (2026-07-12 → 2026-07-01), realign the permalink anchor,
and set ``status='expired'`` — the exact end-state ``expire_past_events`` would
reach for a past-dated row, applied now so it leaves every surface immediately. A
guard refuses to touch the row unless it is in the known-bad state (id + title +
date=2026-07-12 + status=live), so the op is safe to re-run and cannot clobber a
row a later scrape has already changed.

Usage:
  python scripts/fix_america250_redate_2026_07_12.py                 # DRY RUN (default)
  python scripts/fix_america250_redate_2026_07_12.py --apply --undo-csv undo.csv
  python scripts/fix_america250_redate_2026_07_12.py --undo-from undo.csv --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

EVENT_ID = "d2ff5ad0-1ede-4445-9227-4255d5dbb784"
WRONG_DATE = date(2026, 7, 12)
TRUE_DATE = date(2026, 7, 1)
TITLE_MARKER = "america 250"
EXPIRED = "expired"

_WRONG_ANCHOR = f"|{WRONG_DATE.isoformat()}|"
_TRUE_ANCHOR = f"|{TRUE_DATE.isoformat()}|"


def _realign_url(event_url: str | None) -> str | None:
    """Swap the ``#cal|YYYY-MM-DD|…`` date token from the wrong date to the true one.

    Only the exact wrong-date token is replaced, so an already-correct or otherwise
    shaped URL is left untouched.
    """
    if not event_url:
        return event_url
    return event_url.replace(_WRONG_ANCHOR, _TRUE_ANCHOR)


def _in_bad_state(ev: Event) -> bool:
    """True only for the specific mis-dated, still-live America-250 row."""
    return (
        ev.date == WRONG_DATE
        and ev.status == "live"
        and TITLE_MARKER in (ev.title or "").lower()
    )


def _apply_correction(db, *, apply: bool, undo_csv: str | None) -> int:
    ev = db.get(Event, EVENT_ID)
    if ev is None:
        print(f"ABORT: event {EVENT_ID} not found (already fixed, or wrong DB?).")
        return 0
    print(f"target: {ev.id}")
    print(f"  title  : {ev.title!r}")
    print(f"  date   : {ev.date}  status: {ev.status}")
    print(f"  url    : {ev.event_url!r}")
    if not _in_bad_state(ev):
        print(
            "NO-OP: row is not in the known-bad state "
            f"(need date={WRONG_DATE}, status='live', title~'{TITLE_MARKER}'). "
            "Nothing to correct."
        )
        return 0

    new_url = _realign_url(ev.event_url)
    print("planned correction:")
    print(f"  date   : {ev.date} -> {TRUE_DATE}")
    print(f"  status : {ev.status} -> {EXPIRED}")
    print(f"  url    : {ev.event_url!r} -> {new_url!r}")

    if not apply:
        print("\nDRY RUN: no writes (pass --apply to correct 1 row).")
        return 1

    undo = [(ev.id, ev.date.isoformat(), ev.status, ev.event_url or "")]
    ev.date = TRUE_DATE
    ev.status = EXPIRED
    ev.event_url = new_url or ""
    db.commit()
    print("APPLIED: corrected 1 row (date restored + expired).")
    if undo_csv:
        with open(undo_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "old_date", "old_status", "old_event_url"])
            w.writerows(undo)
        print(f"undo CSV -> {undo_csv} (1 row)")
    return 1


def _undo(db, *, undo_from: str, apply: bool) -> int:
    with open(undo_from, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    print(f"restoring {len(rows)} row(s) from {undo_from}:")
    n = 0
    for row in rows:
        ev = db.get(Event, row["id"])
        if ev is None:
            print(f"  MISSING {row['id']} (skipped)")
            continue
        old_date = date.fromisoformat(row["old_date"])
        print(
            f"  {ev.id}: date {ev.date}->{old_date}, status {ev.status}->{row['old_status']}"
        )
        if apply:
            ev.date = old_date
            ev.status = row["old_status"]
            ev.event_url = row["old_event_url"]
        n += 1
    if apply:
        db.commit()
        print(f"APPLIED: restored {n} row(s).")
    else:
        print("DRY RUN: no writes.")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Restore + expire the mis-dated America-250 event (2026-07-12 -> 2026-07-01)."
    )
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--undo-csv", help="on apply, write an undo CSV to this path")
    p.add_argument("--undo-from", help="restore date/status/url from a prior undo CSV")
    args = p.parse_args(argv)
    with SessionLocal() as db:
        if args.undo_from:
            _undo(db, undo_from=args.undo_from, apply=args.apply)
        else:
            _apply_correction(db, apply=args.apply, undo_csv=args.undo_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
