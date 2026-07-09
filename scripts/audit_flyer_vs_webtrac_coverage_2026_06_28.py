"""Read-only audit: which live flyer/OCR events are already covered by WebTrac.

The WebTrac -> catalog pipeline (``app.contrib.parks_rec_loader`` via the
``parks-rec-scrapes`` cron) already ingests Parks & Rec programs structurally:
recurring sections -> Program (class path), single-day sections -> Event, both
carrying a ``register.lhcaz.gov`` URL. The vision/flyer OCR sources
(parks_rec_calendar / parks_rec_flyers / senior_center_flyers) ingest the SAME
content off calendar/flyer images -- lower fidelity, and the cause of the
cross-contaminated descriptions.

PR #605 stops those OCR sources from auto-publishing (they now land pending).
This audit classifies the rows that are ALREADY live so Casey can decide the
cleanup: a flyer row that WebTrac already covers is redundant (dismiss); one with
no WebTrac equivalent is genuinely flyer-only (keep / review).

READ-ONLY. No writes. Classifies each live flyer-originated event as:
  * webtrac_url   -- the row itself already carries a register.lhcaz.gov URL
                     (the reconciler merged the OCR row onto the WebTrac one)
  * webtrac_match -- a distinct WebTrac-sourced Event (same normalized title +
                     date) or Program (title overlap + weekday) covers it
  * flyer_only    -- no WebTrac equivalent found (e.g. full-moon fishing, public
                     open swim) -> stays on the review-gated path
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import or_

from app.db.database import SessionLocal
from app.db.models import Event, Program

VISION_SOURCES = ("parks_rec_calendar", "parks_rec_flyers", "senior_center_flyers")
_WEBTRAC_URL = "register.lhcaz.gov"
_WD_LETTER = {0: "monday", 1: "tuesday", 2: "wednesday", 3: "thursday", 4: "friday", 5: "saturday", 6: "sunday"}


def _norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def _has_webtrac_url(ev: Event) -> bool:
    blob = (ev.event_url or "") + (ev.source_url or "")
    return _WEBTRAC_URL in blob


def main() -> None:
    with SessionLocal() as db:
        flyer = (
            db.query(Event)
            .filter(or_(*[Event.source.like(f"%{s}%") for s in VISION_SOURCES]), Event.status == "live")
            .all()
        )
        # WebTrac-sourced catalog rows to match against.
        wt_events = db.query(Event).filter(
            or_(Event.event_url.like(f"%{_WEBTRAC_URL}%"), Event.source_url.like(f"%{_WEBTRAC_URL}%"))
        ).all()
        wt_event_keys = {(_norm(e.title), e.date) for e in wt_events}
        wt_programs = db.query(Program).filter(
            Program.contact_url.like(f"%{_WEBTRAC_URL}%"), Program.is_active.is_(True)
        ).all()

        def _program_covers(ev: Event) -> bool:
            t = _norm(ev.title)
            wd = _WD_LETTER.get(ev.date.weekday()) if ev.date else None
            for p in wt_programs:
                pt = _norm(p.title)
                if not pt or not t:
                    continue
                if pt in t or t in pt:
                    days = [d.lower() for d in (p.schedule_days or [])]
                    if not days or (wd and wd in days):
                        return True
            return False

        rows: list[tuple[str, Event]] = []
        for ev in flyer:
            if _has_webtrac_url(ev):
                rows.append(("webtrac_url", ev))
            elif (_norm(ev.title), ev.date) in wt_event_keys or _program_covers(ev):
                rows.append(("webtrac_match", ev))
            else:
                rows.append(("flyer_only", ev))

        verdicts = Counter(v for v, _ in rows)
        print("=" * 72)
        print(f"live flyer-originated events: {len(flyer)}")
        print(f"WebTrac catalog: {len(wt_events)} events, {len(wt_programs)} active programs")
        print("classification:")
        for v in ("webtrac_url", "webtrac_match", "flyer_only"):
            print(f"  {v:<14} {verdicts.get(v, 0)}")
        print("=" * 72)
        for verdict in ("webtrac_url", "webtrac_match", "flyer_only"):
            sample = [e for v, e in rows if v == verdict]
            print(f"\n[{verdict}] {len(sample)} rows:")
            for ev in sample:
                print(f"  {ev.date}  {ev.source:<30} {ev.title[:42]!r}")


if __name__ == "__main__":
    main()
