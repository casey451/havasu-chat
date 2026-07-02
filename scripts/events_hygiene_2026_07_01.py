"""Phase-7 events hygiene: CVB-footer backfill, stale one-off retirement,
farmers-market recurring event (gated).

Data half of the Phase-7 code PR (master site audit §5 + [ASK #6] farmers-market
default = recurring event):

  1-footer   Strip the scraped CVB site-footer block ("…Stay Connected Go Lake
             Havasu Visitor Center 422 English Village…") from LIVE event
             descriptions. Ingest now cleans new rows via
             app.events.description_clean.strip_cvb_boilerplate; this repairs
             the ~29 existing golakehavasu rows (and any other source that
             picked it up).
  2-stale    Retire past ONE-OFF events still live and served (~166 in the
             master audit's crawl): status live -> deleted (the permitted
             retire value; the permalink then serves 410). Recurring series
             are untouched — their anchor date being past is normal.
  3-market   Create the Lake Havasu Farmers Market as a recurring event at
             The KAWS (2nd & 4th Saturdays, 8 AM–noon), so the calendar and
             event search finally carry the town's market. "farmers market"
             keeps its specialty-food retail fallback in search routing.

Usage:
    .venv\\Scripts\\python.exe scripts/events_hygiene_2026_07_01.py
    .venv\\Scripts\\python.exe scripts/events_hygiene_2026_07_01.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import func, or_, select  # noqa: E402

from app.core.timezone import now_lake_havasu  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events.description_clean import strip_cvb_boilerplate  # noqa: E402
from app.events.scrapers.base import normalize_event_title  # noqa: E402

_SNAP_DIR = _ROOT / "scripts" / "_snapshots"
SEED_SOURCE = "events_hygiene_2026_07_01"

_MARKET = {
    "title": "Lake Havasu City Farmers Market",
    "location_name": "The KAWS",
    "description": (
        "The town farmers market at The KAWS, 2144 McCulloch Blvd N — local "
        "produce, baked goods, crafts, and food vendors. Second and fourth "
        "Saturday of every month, 8 AM to noon."
    ),
    "event_url": "https://lakehavasufarmersmarket.com/",
    # Anchor = 2nd Saturday of July 2026; the RRULE carries it forward.
    "date": date(2026, 7, 11),
    "start_time": time(8, 0),
    "end_time": time(12, 0),
    "rrule": "FREQ=MONTHLY;BYDAY=2SA,4SA",
    "tags": ["events", "market"],
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phase-7 events hygiene (gated).")
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry run)")
    ap.add_argument("--confirm", action="store_true", help="required with --apply")
    args = ap.parse_args(argv)
    writing = args.apply and args.confirm
    if args.apply and not args.confirm:
        print("Refusing to write without --confirm. (dry-run below.)\n")

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print(f"PHASE-7 EVENTS HYGIENE — {'APPLY (writing)' if writing else 'DRY RUN'}")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    # Lake Havasu LOCAL date — a July-1 event is not "past" while it is still
    # July 1 in Arizona, even once UTC has rolled to July 2.
    today = now_lake_havasu().date()
    snap: dict = {"generated_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                  "db": redacted}

    with SessionLocal() as db:
        live = db.query(Event).filter(Event.status == "live").all()

        print("--- 1 strip CVB footer from live descriptions ---")
        footer_rows = [
            ev for ev in live
            if (ev.description or "")
            and strip_cvb_boilerplate(ev.description) != (ev.description or "").strip()
        ]
        for ev in footer_rows[:15]:
            print(f"  CLEAN  {ev.date}  {(ev.title or '')[:56]}")
        if len(footer_rows) > 15:
            print(f"  … +{len(footer_rows) - 15} more")
        print(f"  rows to clean: {len(footer_rows)}")
        snap["footer_cleaned"] = [
            {"id": ev.id, "old_description": ev.description} for ev in footer_rows
        ]

        print("\n--- 2 retire past one-off events (recurring series untouched) ---")
        stale = [
            ev for ev in live
            if not (ev.is_recurring or ev.rrule or ev.rdate)
            and (ev.end_date or ev.date) < today
        ]
        for ev in stale[:15]:
            print(f"  RETIRE  {ev.date}  {(ev.title or '')[:56]}")
        if len(stale) > 15:
            print(f"  … +{len(stale) - 15} more")
        print(f"  rows to retire (live -> deleted): {len(stale)}")
        snap["stale_retired"] = [ev.id for ev in stale]

        print("\n--- 3 farmers-market recurring event ([ASK #6] default) ---")
        norm_title = normalize_event_title(_MARKET["title"])
        existing = db.scalars(
            select(Event).where(
                or_(
                    Event.normalized_title == norm_title,
                    func.lower(Event.title).like("%farmers market%"),
                ),
                Event.status == "live",
                Event.is_recurring.is_(True),
            )
        ).first()
        create_market = existing is None
        if create_market:
            print(f"  CREATE  {_MARKET['title']!r} @ The KAWS — 2nd & 4th Sat, 8 AM–noon")
        else:
            print(f"  OK  recurring farmers market already live: {existing.title!r}")
        snap["market_created"] = create_market

        _SNAP_DIR.mkdir(parents=True, exist_ok=True)
        tag = "apply" if writing else "dryrun"
        snap_path = _SNAP_DIR / f"events_hygiene_2026_07_01_snapshot_{tag}_{snap['generated_utc']}.json"
        snap_path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        print(f"\nsnapshot written: {snap_path.relative_to(_ROOT)}")

        if not writing:
            print("\nDRY RUN — nothing written. Re-run with --apply --confirm after approval.")
            return 0

        # ---- write ----
        for ev in footer_rows:
            ev.description = strip_cvb_boilerplate(ev.description)
        for ev in stale:
            ev.status = "deleted"
        if create_market:
            db.add(Event(
                title=_MARKET["title"],
                normalized_title=norm_title,
                date=_MARKET["date"],
                start_time=_MARKET["start_time"],
                end_time=_MARKET["end_time"],
                location_name=_MARKET["location_name"],
                location_normalized=normalize_event_title(_MARKET["location_name"]),
                description=_MARKET["description"],
                event_url=_MARKET["event_url"],
                source_url=_MARKET["event_url"],
                tags=list(_MARKET["tags"]),
                status="live",
                source=SEED_SOURCE,
                verified=True,
                created_by=SEED_SOURCE,
                is_recurring=True,
                rrule=_MARKET["rrule"],
                last_verified_at=datetime.now(timezone.utc),
            ))
        db.commit()
        print("\nAPPLIED. Descriptions/status reversible from the snapshot; the "
              f"market row carries source={SEED_SOURCE!r}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
