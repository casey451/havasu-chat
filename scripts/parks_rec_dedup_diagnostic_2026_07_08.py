"""READ-ONLY diagnostic (2026-07-08): pin the exact rows behind the three
spot-checks — the Afternoon Enrichment double, the Kids Pizza Party pair, and the
corrected Glow — plus a general series/session duplicate scan over LIVE P&R
events. SELECTs only; WRITES NOTHING.

    .venv\\Scripts\\python.exe scripts/parks_rec_dedup_diagnostic_2026_07_08.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402


def _hr(t: str) -> None:
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def _events_like(db, like: str) -> None:
    rows = db.execute(text(
        "SELECT id, status, date, end_date, start_time, is_recurring, rrule, "
        "location_name, source, event_url, host, created_at "
        "FROM events WHERE lower(title) LIKE :like ORDER BY date, start_time"
    ), {"like": like}).fetchall()
    if not rows:
        print("  (no events)")
    for r in rows:
        print(f"  {str(r[0])[:8]} [{r[1]}] date={r[2]} end={r[3]} start={r[4]} "
              f"recur={r[5]} rrule={(r[6] or '')[:28]!r}")
        print(f"        venue={r[7]!r} source={r[8]!r} host={r[10]!r} created={r[11]}")
        print(f"        event_url={(r[9] or '')[:80]}")


def _programs_like(db, like: str) -> None:
    try:
        rows = db.execute(text(
            "SELECT id, title, activity_category, schedule_days, schedule_note, "
            "location_name, source FROM programs WHERE lower(title) LIKE :like"
        ), {"like": like}).fetchall()
    except Exception as e:  # noqa: BLE001
        print(f"  programs query failed: {type(e).__name__}: {e}")
        return
    if not rows:
        print("  (no programs)")
    for r in rows:
        print(f"  prog {str(r[0])[:8]} title={r[1]!r} cat={r[2]!r} days={r[3]!r} "
              f"note={(r[4] or '')[:30]!r} venue={r[5]!r} source={r[6]!r}")


def main() -> int:
    with SessionLocal() as db:
        _hr("A) Afternoon Enrichment — events (any date) + programs")
        print(" events:")
        _events_like(db, "%afternoon enrichment%")
        print(" programs:")
        _programs_like(db, "%afternoon enrichment%")

        _hr("B) Kids Pizza Party — events")
        _events_like(db, "%pizza party%")

        _hr("C) Glow — events")
        _events_like(db, "%glow%")

        _hr("D) LIVE P&R events sharing a normalized_title (series/session dup candidates)")
        rows = db.execute(text(
            "SELECT normalized_title, count(*) n, "
            "string_agg(DISTINCT to_char(date, 'YYYY-MM-DD') || '@' || "
            "to_char(start_time, 'HH24:MI'), ', ') AS occ "
            "FROM events WHERE status='live' AND "
            "(source LIKE '%parks_rec%' OR event_url LIKE '%/185/Parks-Recreation#cal|%') "
            "GROUP BY normalized_title HAVING count(*) > 1 ORDER BY n DESC, normalized_title"
        )).fetchall()
        if not rows:
            print("  (no live P&R title collisions)")
        for r in rows:
            print(f"  n={r[1]:<3} {r[0]!r}")
            print(f"        occ: {(r[2] or '')[:150]}")

        _hr("E) EXACT-dup live P&R events (same normalized_title + date + start_time)")
        rows = db.execute(text(
            "SELECT normalized_title, date, start_time, count(*) n "
            "FROM events WHERE status='live' AND "
            "(source LIKE '%parks_rec%' OR event_url LIKE '%/185/Parks-Recreation#cal|%') "
            "GROUP BY normalized_title, date, start_time HAVING count(*) > 1 "
            "ORDER BY n DESC"
        )).fetchall()
        if not rows:
            print("  (no exact live P&R dups)")
        for r in rows:
            print(f"  n={r[3]}  {r[0]!r} @ {r[1]} {r[2]}")
    print("\n(read-only diagnostic complete — no writes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
