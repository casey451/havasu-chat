"""
Verify marquee-event coverage (source-expansion #13 note).

We deliberately do NOT build dedicated scrapers for Havasu 95 Speedway, Desert
Storm, the Balloon Festival, or the Boat Show — those marquee events are expected
to arrive via the existing RiverScene / golakehavasu scrapers. This READ-ONLY
script checks that assumption: it queries the events table for upcoming entries
matching each marquee name and prints any gaps, so Casey can confirm the
assumption holds (or flag a marquee event that needs its own source).

Read-only: runs SELECTs only, never writes. No --apply.

  python scripts/verify_marquee_event_coverage.py
  python scripts/verify_marquee_event_coverage.py --horizon-days 365
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

# Marquee event -> substring matched against Event.normalized_title (lowercased,
# non-alphanumerics collapsed to spaces by normalize_event_title).
MARQUEE_PATTERNS: dict[str, str] = {
    "Havasu 95 Speedway": "speedway",
    "Desert Storm": "desert storm",
    "Balloon Festival": "balloon",
    "Boat Show": "boat show",
}


def match_rows(rows) -> dict[str, list[str]]:
    """Pure matcher: bucket (title, normalized_title, date) rows by marquee name."""
    found: dict[str, list[str]] = {label: [] for label in MARQUEE_PATTERNS}
    for label, needle in MARQUEE_PATTERNS.items():
        for title, normalized, ev_date in rows:
            if needle in (normalized or "").lower():
                found[label].append(f"{title} ({ev_date.isoformat()})")
    return found


def check_coverage(horizon_days: int = 365, *, today: date | None = None) -> dict[str, list[str]]:
    today = today or date.today()
    horizon = today + timedelta(days=horizon_days)
    with SessionLocal() as db:
        rows = db.execute(
            select(Event.title, Event.normalized_title, Event.date)
            .where(Event.date >= today, Event.date <= horizon, Event.status == "live")
        ).all()
    return match_rows(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--horizon-days", type=int, default=365)
    args = p.parse_args(argv)

    found = check_coverage(args.horizon_days)
    print("=== marquee event coverage (read-only) ===")
    gaps = []
    for label, matches in found.items():
        if matches:
            print(f"[OK]  {label}: {len(matches)} upcoming")
            for m in matches[:3]:
                print(f"        - {m}")
        else:
            print(f"[GAP] {label}: no upcoming events found")
            gaps.append(label)
    if gaps:
        print(f"\n{len(gaps)} marquee event(s) have NO upcoming coverage: {', '.join(gaps)}")
        print("Confirm whether RiverScene/golakehavasu should cover these, or a dedicated source is needed.")
    else:
        print("\nAll marquee events have upcoming coverage — assumption holds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
