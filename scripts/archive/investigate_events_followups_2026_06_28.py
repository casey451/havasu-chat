"""Read-only live-DB checks for the events follow-up re-audit (Items 3 & 4).

Item 3 — recurrence sanity: a recurring series should NOT mint a new Event.id
per day. Count DISTINCT Event.id per (normalized_title, location) over a 30-day
window for high-frequency venues; expect ~1 row per series, not ~30.

Item 4 — Parks & Rec description cross-contamination: pull the specific rows the
re-audit flagged (Strawberry Full Moon Fishing / Kids Fishing / Free Summer
Craft Series) and print title/source/date/tags/description verbatim so we can
see whether the blurbs are actually conflated or whether it was crawl noise.

READ-ONLY. No writes. Safe to run against prod.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, or_

from app.db.database import SessionLocal
from app.db.models import Event


def item3_recurrence_explosion(db) -> None:
    print("=" * 72)
    print("ITEM 3 — recurrence: DISTINCT Event.id per series over next 30 days")
    print("=" * 72)
    today = date.today()
    horizon = today + timedelta(days=30)
    rows = (
        db.query(Event)
        .filter(Event.date >= today, Event.date <= horizon, Event.status == "live")
        .all()
    )
    print(f"live events in window {today}..{horizon}: {len(rows)}")

    # Group by (normalized_title, location_normalized) -> distinct ids + dates.
    series: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"ids": set(), "dates": set()}
    )
    for ev in rows:
        key = (ev.normalized_title or ev.title or "", ev.location_normalized or "")
        series[key]["ids"].add(ev.id)
        series[key]["dates"].add(ev.date)

    # Surface anything that looks like per-day row minting: many distinct ids
    # AND many distinct dates for the same title+venue.
    suspicious = sorted(
        (
            (title_loc, d)
            for title_loc, d in series.items()
            if len(d["ids"]) >= 5 and len(d["dates"]) >= 5
        ),
        key=lambda kv: -len(kv[1]["ids"]),
    )
    if not suspicious:
        print("\nNo series with >=5 distinct ids across >=5 dates — recurring")
        print("series are read-time expansions, NOT per-day stored rows. CLEAN.")
    else:
        print("\nPotential per-day row explosion (>=5 ids over >=5 dates):")
        for (title, loc), d in suspicious[:15]:
            print(
                f"  ids={len(d['ids']):>3}  dates={len(d['dates']):>3}  "
                f"{title[:40]!r} @ {loc[:30]!r}"
            )

    # Also report the is_recurring flag population as a cross-check.
    rec_flag = db.query(func.count(Event.id)).filter(Event.is_recurring.is_(True)).scalar()
    print(f"\nEvents with is_recurring=True (any date): {rec_flag}")


def item4_parks_rec_contamination(db) -> None:
    print()
    print("=" * 72)
    print("ITEM 4 — Parks & Rec flagged rows (verbatim)")
    print("=" * 72)
    needles = ["strawberry", "kids fishing", "summer craft", "full moon fishing"]
    clause = or_(*[func.lower(Event.title).like(f"%{n}%") for n in needles])
    rows = db.query(Event).filter(clause).order_by(Event.date).all()
    if not rows:
        print("No rows match the flagged titles. Check needle list / source.")
    for ev in rows:
        print("-" * 72)
        print(f"title : {ev.title!r}")
        print(f"id    : {ev.id}")
        print(f"date  : {ev.date}   start={ev.start_time} end={ev.end_time}")
        print(f"source: {ev.source!r}   status={ev.status!r}")
        print(f"venue : {ev.location_name!r}")
        print(f"tags  : {ev.tags!r}")
        print(f"cost  : {ev.cost!r}")
        desc = (ev.description or "").strip()
        print(f"desc  : {desc!r}")


def main() -> None:
    with SessionLocal() as db:
        item3_recurrence_explosion(db)
        item4_parks_rec_contamination(db)


if __name__ == "__main__":
    main()
