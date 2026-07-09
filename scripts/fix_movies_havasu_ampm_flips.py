"""Correct AM/PM-flipped Movies Havasu showtimes (a 4 PM show the source labels
"4 AM"). Gated + reversible — the standard dry-run → approve → apply flow.

Movies Havasu's own site systematically mislabels some afternoon matinees as AM
(verified 2026-07-08: Moana at "4:00 AM" on six dates). Our parser is faithful —
the flip is upstream — so the WS6 showtime lint QUARANTINES those rows (they never
display). This one-off corrects the already-stored bad rows to their real PM time
by the unambiguous AM→PM flip (+12h: 04:00 → 16:00), so the matinee shows at the
right time instead of being hidden. The deployed lint then protects the fix: the
next scrape re-reads "4 AM", quarantines it, and never overwrites the corrected row.

Only rows the lint flags (before 9 AM at Movies Havasu, not a whitelisted
kids-series) AND with an AM clock (< 12:00, so +12h is a valid PM time) are
touched. Idempotent: a second run finds nothing (corrected rows are ≥ 9 AM).

Usage:
  python scripts/fix_movies_havasu_ampm_flips.py                 # DRY RUN (default)
  python scripts/fix_movies_havasu_ampm_flips.py --apply --undo-csv undo.csv
  python scripts/fix_movies_havasu_ampm_flips.py --undo-from undo.csv --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import MovieShowtime  # noqa: E402
from app.events.lint import is_kids_series, suspect_showtime  # noqa: E402

SOURCE = "movies_havasu"
_NOON = time(12, 0)


def _shift_12h(t: time) -> time:
    return (datetime.combine(datetime(2000, 1, 1), t) + timedelta(hours=12)).time()


def _flip_candidates(db) -> list[MovieShowtime]:
    """Movies Havasu rows the showtime lint flags AND that carry an AM clock, so a
    +12h correction yields a valid PM time."""
    rows = db.scalars(select(MovieShowtime).where(MovieShowtime.source == SOURCE)).all()
    out = []
    for r in rows:
        kids = bool(getattr(r, "is_free", False)) or is_kids_series(r.film_title, r.tags)
        if suspect_showtime(r.show_time, kids_series=kids) and r.show_time < _NOON:
            out.append(r)
    return out


def _apply_correction(db, *, apply: bool, undo_csv: str | None) -> int:
    rows = _flip_candidates(db)
    print(f"found {len(rows)} flipped Movies Havasu showtime(s) to correct (+12h):")
    undo: list[tuple[str, str]] = []
    for r in sorted(rows, key=lambda x: (x.show_date, x.show_time, x.film_title)):
        new_t = _shift_12h(r.show_time)
        print(f"  {r.show_date.isoformat()}  {r.film_title:<24} {r.show_time.isoformat()} -> {new_t.isoformat()}  [{r.id}]")
        undo.append((r.id, r.show_time.isoformat()))
        if apply:
            r.show_time = new_t
    if apply:
        db.commit()
        print(f"APPLIED: corrected {len(rows)} row(s).")
        if undo_csv and undo:
            with open(undo_csv, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["id", "old_show_time"])
                w.writerows(undo)
            print(f"undo CSV -> {undo_csv} ({len(undo)} rows)")
    else:
        print("DRY RUN: no writes (pass --apply to correct).")
    return len(rows)


def _undo(db, *, undo_from: str, apply: bool) -> int:
    with open(undo_from, encoding="utf-8") as fh:
        pairs = [(row["id"], row["old_show_time"]) for row in csv.DictReader(fh)]
    print(f"restoring {len(pairs)} row(s) from {undo_from}:")
    n = 0
    for rid, old in pairs:
        r = db.get(MovieShowtime, rid)
        if r is None:
            print(f"  MISSING {rid} (skipped)")
            continue
        old_t = time.fromisoformat(old)
        print(f"  {rid}: {r.show_time.isoformat()} -> {old_t.isoformat()}")
        if apply:
            r.show_time = old_t
        n += 1
    if apply:
        db.commit()
        print(f"APPLIED: restored {n} row(s).")
    else:
        print("DRY RUN: no writes.")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Correct AM/PM-flipped Movies Havasu showtimes (+12h)")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--undo-csv", help="on apply, write an undo CSV to this path")
    p.add_argument("--undo-from", help="restore show_time from a prior undo CSV")
    args = p.parse_args(argv)
    with SessionLocal() as db:
        if args.undo_from:
            _undo(db, undo_from=args.undo_from, apply=args.apply)
        else:
            _apply_correction(db, apply=args.apply, undo_csv=args.undo_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
