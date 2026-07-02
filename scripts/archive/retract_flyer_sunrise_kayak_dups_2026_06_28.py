"""Retract 2 flyer-OCR 'Sunrise Kayak' rows that duplicate their WebTrac twin.

The WebTrac -> catalog pipeline already ingests the structured, authoritative
"Sunrise Kayak <date>" events (register.lhcaz.gov, FMID). The parks_rec_calendar
vision/OCR scraper ALSO produced a generic "Sunrise Kayak" row for the same
date/time/venue ($8, 06:00, Rotary Park) -- a lower-fidelity duplicate (its
OCR'd age range even disagrees with the registration system's). PR #605 stops
these auto-publishing going forward; this retracts the two that are already live.

Strictly scoped to two event ids, each guarded: must be source containing a
vision token, must carry the lhcaz.gov/185 calendar URL (the OCR synthetic URL,
NOT the register.lhcaz.gov WebTrac one), and a distinct WebTrac twin (same date,
register URL) must exist and stay live. Retract = status 'live' -> 'duplicate'
(reversible; the same status the cross-source dedup uses). Snapshots before-state.

Dry-run by default. --apply writes (Casey approved). READ-ONLY otherwise.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import or_

from app.db.database import SessionLocal
from app.db.models import Event

# (flyer dup id-prefix, expected date) -> retract; keep its WebTrac twin.
_TARGETS = [
    ("343b423d", "2026-07-14"),
    ("7d73f07a", "2026-06-02"),
]
_VISION = ("parks_rec_calendar", "parks_rec_flyers", "senior_center_flyers")
_OCR_URL = "lhcaz.gov/185"
_WEBTRAC_URL = "register.lhcaz.gov"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (gated)")
    args = ap.parse_args()

    snapshot: list[dict] = []
    to_write: list[Event] = []
    with SessionLocal() as db:
        for prefix, expect_date in _TARGETS:
            ev = db.query(Event).filter(Event.id.like(prefix + "%")).one_or_none()
            if ev is None:
                print(f"!! {prefix} NOT FOUND — skip")
                continue
            # Guards — refuse anything that doesn't look exactly like the OCR dup.
            problems = []
            if str(ev.date) != expect_date:
                problems.append(f"date {ev.date} != {expect_date}")
            if not any(v in (ev.source or "") for v in _VISION):
                problems.append(f"source {ev.source!r} not a vision row")
            if _OCR_URL not in (ev.event_url or "") + (ev.source_url or ""):
                problems.append("no OCR calendar URL")
            if _WEBTRAC_URL in (ev.event_url or "") + (ev.source_url or ""):
                problems.append("carries WebTrac URL (merged singleton — refuse)")
            if ev.status != "live":
                problems.append(f"status {ev.status!r} != live")
            # The structured WebTrac twin must exist and be live.
            twin = (
                db.query(Event)
                .filter(
                    Event.date == ev.date,
                    Event.status == "live",
                    Event.id != ev.id,
                    or_(
                        Event.event_url.like(f"%{_WEBTRAC_URL}%"),
                        Event.source_url.like(f"%{_WEBTRAC_URL}%"),
                    ),
                    Event.title.like("Sunrise Kayak%"),
                )
                .first()
            )
            if twin is None:
                problems.append("no live WebTrac twin found — refuse")

            if problems:
                print(f"!! {prefix} {ev.title!r} ({ev.date}) SKIPPED: {'; '.join(problems)}")
                continue

            print("-" * 60)
            print(f"RETRACT flyer dup  id={ev.id} {ev.title!r} ({ev.date})")
            print(f"  src={ev.source!r}  status live -> duplicate")
            print(f"  KEEP WebTrac twin id={twin.id} {twin.title!r}")
            snapshot.append(
                {"id": ev.id, "title": ev.title, "date": str(ev.date),
                 "old_status": ev.status, "new_status": "duplicate", "twin_id": twin.id}
            )
            to_write.append(ev)

        print("=" * 60)
        print(f"rows that would change: {len(to_write)}")
        if args.apply and to_write:
            snap = Path("scripts/_snapshots/retract_flyer_sunrise_kayak_2026_06_28.json")
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            for ev in to_write:
                ev.status = "duplicate"
            db.commit()
            print(f"APPLIED. snapshot -> {snap}")
        else:
            print("DRY-RUN (no writes).")


if __name__ == "__main__":
    main()
