"""
Read-only diagnostic: cross-check live golakehavasu events against existing
Events in the DB and report the closest match for each, so a "36 imported /
0 merged" dry-run can be judged (genuinely no overlap vs reconciler thresholds
too strict).

Writes NOTHING. For each parsed golakehavasu event it prints, among existing
Events on the SAME calendar date:
  * best fuzzy title ratio (rapidfuzz token_sort_ratio, same scorer the
    reconciler uses; >= 85 would merge),
  * the start-time delta in minutes (the reconciler's window is 30),
  * the matched event's source + venue,
so near-misses (e.g. ratio 80, or same title but 45-min-apart times) are visible.

Usage:
    python scripts/golakehavasu_dedup_audit.py
    python scripts/golakehavasu_dedup_audit.py --limit 10
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from rapidfuzz import fuzz
from sqlalchemy import select

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.golakehavasu import (  # noqa: E402
    REQUEST_TIMEOUT,
    USER_AGENT,
    fetch_and_parse_event,
    fetch_sitemap_urls,
)
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.scrapers.base import normalize_event_title  # noqa: E402


def _time_delta_minutes(a, b) -> int | None:
    if a is None or b is None:
        return None
    da = datetime.combine(date(2000, 1, 1), a)
    db = datetime.combine(date(2000, 1, 1), b)
    return int(abs((da - db).total_seconds()) // 60)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        urls = fetch_sitemap_urls(client=client)
        if args.limit is not None:
            urls = urls[: args.limit]

        with_same_date = 0
        strong_match = 0  # ratio >= 85 AND within 30 min -> reconciler would merge
        near_miss = 0  # ratio >= 70 but would NOT merge (time/threshold)

        with SessionLocal() as session:
            for url in urls:
                ev = fetch_and_parse_event(url, client=client, today=date.today())
                if ev is None:
                    continue
                same_date = list(
                    session.scalars(select(Event).where(Event.date == ev.start_date)).all()
                )
                if not same_date:
                    print(f"[no same-date event] {ev.start_date}  {ev.title}")
                    continue
                with_same_date += 1
                norm = normalize_event_title(ev.title)
                best = max(
                    same_date,
                    key=lambda c: fuzz.token_sort_ratio(
                        normalize_event_title(c.normalized_title or c.title), norm
                    ),
                )
                ratio = fuzz.token_sort_ratio(
                    normalize_event_title(best.normalized_title or best.title), norm
                )
                delta = _time_delta_minutes(ev.start_time, best.start_time)
                merges = ratio >= 85 and (delta is not None and delta <= 30)
                flag = "MERGE" if merges else ("near?" if ratio >= 70 else "")
                if merges:
                    strong_match += 1
                elif ratio >= 70:
                    near_miss += 1
                print(
                    f"[{flag:5}] {ev.start_date} r={ratio:3.0f} dt={delta}m "
                    f"src={best.source!r} :: '{ev.title}' ~ '{best.title}'"
                )

        print("\n--- audit summary ---")
        print(f"events_checked:        {len(urls)}")
        print(f"with_same_date_event:  {with_same_date}")
        print(f"would_merge (>=85,<=30m): {strong_match}")
        print(f"near_miss (>=70, no merge): {near_miss}")
        print("(read-only: no DB writes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
