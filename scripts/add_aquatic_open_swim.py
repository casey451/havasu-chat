"""Capture the LHC Aquatic Center summer Open Swim schedule (audit #6/#7).

Source: the city's own page, https://www.lhcaz.gov/parks-recreation/aquatic-center
  "Open swim schedule for June and July is noon to 4 pm daily with the exception
   of Tuesdays and Thursdays."

So Open Swim = 12:00–16:00 on Mon/Wed/Fri/Sat/Sun (weekends included — this also
closes the #7 weekend gap), seasonal June–July. Added as a recurring Schedule on
the canonical "Lake Havasu City Aquatic Center" entity with an explicit
end_date=2026-07-31 so the seasonal-window guard in
app/events/class_occurrences.py stops it rendering in August (no stale data).
The class-occurrence bridge + is_dropin_rec route "Open Swim" to Things to Do.

Idempotent (skips if an Open Swim schedule already exists). Reversible (delete
the row). Per CLAUDE.md: dry-run -> show -> approve -> --apply.

    .venv\\Scripts\\python.exe scripts\\add_aquatic_open_swim.py           # dry-run
    .venv\\Scripts\\python.exe scripts\\add_aquatic_open_swim.py --apply
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider, Schedule  # noqa: E402

PROVIDER_SLUG = "lake-havasu-city-aquatic-center"
DAYS = ["monday", "wednesday", "friday", "saturday", "sunday"]
START_T, END_T = time(12, 0), time(16, 0)
SEASON_START, SEASON_END = date(2026, 6, 1), date(2026, 7, 31)
NOTES = "Open Swim"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit (prod-data INSERT)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        prov = db.scalar(select(Provider).where(Provider.slug == PROVIDER_SLUG))
        if prov is None:
            print(f"ABORT: provider '{PROVIDER_SLUG}' not found.")
            return
        eid = prov.entity_id
        existing = db.scalars(
            select(Schedule).where(Schedule.entity_id == eid, Schedule.notes.ilike("open swim%"))
        ).all()
        if existing:
            print(f"SKIP: an Open Swim schedule already exists on {eid[:8]}: "
                  f"{[(s.id, s.notes, s.days_of_week) for s in existing]}")
            return

        print(f"ADD Schedule on entity {eid[:8]} ({prov.provider_name}):")
        print(f"    notes={NOTES!r} days={DAYS} {START_T}-{END_T} "
              f"season={SEASON_START}..{SEASON_END} (weekends included)")
        if not args.apply:
            print("\nDRY-RUN: would insert 1 Schedule. Re-run with --apply.")
            return

        now = datetime.now(UTC)
        db.add(
            Schedule(
                entity_id=eid, schedule_type="recurring", days_of_week=DAYS,
                start_time=START_T, end_time=END_T,
                start_date=SEASON_START, end_date=SEASON_END,
                notes=NOTES, created_at=now, updated_at=now,
            )
        )
        db.commit()
        print("\nAPPLIED: inserted Open Swim schedule (seasonal, ends 2026-07-31). "
              "Reversible: delete the row.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
