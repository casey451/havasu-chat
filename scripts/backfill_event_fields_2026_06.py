"""DRY-RUN backfill: report (and optionally apply) the 2026-06 event field fixes.

Reports how many existing live Events WOULD gain a recovered start time, venue,
cost, image, or host — and how many would have their tag set change (automotive /
boating / music guard) — WITHOUT writing anything by default.

  python scripts/backfill_event_fields_2026_06.py                 # dry-run preview (default)
  python scripts/backfill_event_fields_2026_06.py --dry-run       # explicit preview
  python scripts/backfill_event_fields_2026_06.py --apply --yes    # persist (requires BOTH flags)

Safety: dry-run is the default. ``--apply`` ALSO requires the explicit ``--yes``
confirmation flag, per the repo rule (dry-run -> show counts -> approval -> apply).
This script does NOT fetch the network — it works only from data already on the
row (title, description, source JSON-LD is not re-pulled). Time/venue recovery
uses the description prose extractors; cost uses title+description; host uses the
raw title; image is taken from the row's existing image_url (no change unless a
future enrich step set rec.image_url, so image is reported as informational only).

Counts reported:
  total                 live events scanned
  would_set_time        midnight/None start_time a body time would fill
  would_set_venue       generic/empty venue a body venue would fill
  would_set_cost        empty cost a price parse would fill
  would_set_host        empty host a class-title instructor name would fill
  would_change_tags     rows whose recomputed tag set differs
  rows_changed          rows with >=1 change
"""

from __future__ import annotations

import argparse
import sys
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.contrib.event_ingest import _cost_for_record, _host_from_title, _tags
from app.contrib.event_record import (
    EventRecord,
    canonicalize_venue,
    extract_time_from_text,
    extract_venue_from_text,
)
from app.db.database import SessionLocal
from app.db.models import Event

_MIDNIGHT = time(0, 0)
_GENERIC_VENUES = {"", "lake havasu city", "lake havasu"}


def _record_from_event(ev: Event) -> EventRecord:
    return EventRecord(
        source=(ev.source or "backfill"),
        title=ev.title or "",
        start_date=ev.date,
        start_time=ev.start_time,
        end_date=ev.end_date,
        end_time=ev.end_time,
        venue_name=ev.location_name,
        url=ev.source_url or ev.event_url,
        description=ev.description or "",
        tags=list(ev.tags or []),
        image_url=ev.image_url,
        raw={},
    )


def run(*, apply: bool) -> dict[str, int]:
    counts = {
        "total": 0,
        "would_set_time": 0,
        "would_set_venue": 0,
        "would_set_cost": 0,
        "would_set_host": 0,
        "would_change_tags": 0,
        "rows_changed": 0,
    }
    with SessionLocal() as db:
        events = (
            db.execute(select(Event).where(Event.status == "live").order_by(Event.id))
            .scalars()
            .all()
        )
        for ev in events:
            counts["total"] += 1
            rec = _record_from_event(ev)

            new_time = None
            if ev.start_time is None or ev.start_time == _MIDNIGHT:
                t = extract_time_from_text(rec.description)
                if t is not None and t != _MIDNIGHT:
                    new_time = t

            new_venue = None
            if (ev.location_name or "").strip().lower() in _GENERIC_VENUES:
                v = extract_venue_from_text(rec.description)
                v = canonicalize_venue(v) if v else None
                if v and v.strip().lower() not in _GENERIC_VENUES:
                    new_venue = v

            new_cost = None
            if not ev.cost:
                c = _cost_for_record(rec)
                if c:
                    new_cost = c

            new_host = None
            if not getattr(ev, "host", None):
                h = _host_from_title(ev.title)
                if h:
                    new_host = h

            existing_tags = list(ev.tags or [])
            recomputed = _tags(rec)
            tags_change = sorted(recomputed) != sorted(existing_tags)

            row_changed = any(
                (new_time, new_venue, new_cost, new_host, tags_change)
            )
            if not row_changed:
                continue

            if new_time:
                counts["would_set_time"] += 1
            if new_venue:
                counts["would_set_venue"] += 1
            if new_cost:
                counts["would_set_cost"] += 1
            if new_host:
                counts["would_set_host"] += 1
            if tags_change:
                counts["would_change_tags"] += 1
            counts["rows_changed"] += 1

            print(f"--- event {ev.id}  {ev.title!r}")
            if new_time:
                print(f"  start_time: {ev.start_time} -> {new_time}")
            if new_venue:
                print(f"  location_name: {ev.location_name!r} -> {new_venue!r}")
            if new_cost:
                print(f"  cost: {ev.cost!r} -> {new_cost!r}")
            if new_host:
                print(f"  host: {getattr(ev, 'host', None)!r} -> {new_host!r}")
            if tags_change:
                print(f"  tags: {existing_tags} -> {recomputed}")

            if apply:
                if new_time:
                    ev.start_time = new_time
                if new_venue:
                    ev.location_name = new_venue
                if new_cost:
                    ev.cost = new_cost
                if new_host:
                    ev.host = new_host
                if tags_change:
                    ev.tags = recomputed
        if apply:
            db.commit()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply", action="store_true", help="persist changes (also requires --yes)"
    )
    ap.add_argument("--dry-run", action="store_true", help="explicit preview (default)")
    ap.add_argument(
        "--yes",
        action="store_true",
        help="explicit confirmation required alongside --apply",
    )
    args = ap.parse_args()
    apply = args.apply and not args.dry_run
    if apply and not args.yes:
        print(
            "refusing to apply without explicit --yes confirmation "
            "(dry-run -> show counts -> approval -> apply)",
            file=sys.stderr,
        )
        sys.exit(2)
    counts = run(apply=apply)
    print("\nbackfill_event_fields_2026_06 complete")
    for k, v in counts.items():
        print(f"  {k:<20} {v}")
    if not apply:
        print("  (dry run -- no database writes; re-run with --apply --yes to persist)")


if __name__ == "__main__":
    main()
