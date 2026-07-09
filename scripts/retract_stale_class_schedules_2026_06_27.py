"""Retract stale / unverifiable class schedules from the calendar (2026-06-27).

Casey: "only add in classes we can verify are active." Several SEASONAL school-year
class grids were published by earlier sessions and are NOT verifiably running now
(late June = summer break). Pull them until a fresh new-season capture verifies
they're active again:

  * Ballet Havasu                  — 2025-26 season; recital was 5/31; registration
                                     not until Jul 12, classes resume ~Aug.
  * Universal Sonics Gymnastics    — captured with an explicit "off season, site
                                     calendar empty" note; published anyway.
  * Arizona Coast Performing Arts  — 2025-26 season; showcase ended May 15-17;
    (two duplicate entities)         summer status unverified.
  * For Dog's Sake! Training       — source says group classes are SUSPENDED.

NOT data loss: each class's ``schedule_scrape`` Contribution keeps its
``proposed_record``; this only deletes the rendered Schedule + Offering rows and
reverts the contribution to ``pending`` — so a fall re-capture/re-publish restores
it. Matches ONLY schedule rows whose title equals one of the venue's
schedule-hunt contribution titles, so non-schedule-hunt rows (e.g. Ballet's two
title-less schedules) are never touched.

Read-only by default. ``--apply`` is a destructive prod-data op: dry-run -> counts
-> Casey approves -> apply (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.schedule_publish import _utc_now_naive  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Contribution, Entity, Offering, Schedule  # noqa: E402

# entity_id -> human reason (kept explicit so nothing else is touched).
STALE_VENUES: dict[str, str] = {
    "203617c9-b6d8-4a35-9d95-90dfb21a0f6c": "Ballet Havasu (season grid; resumes ~Aug)",
    "ede0e325-5d43-4953-9f0e-caa30048aec6": "Universal Sonics Gymnastics (off season)",
    "07970984-d805-4627-9b97-ec5aa583527c": "Arizona Coast Performing Arts (season ended May)",
    "b67244d7-a277-488f-883d-4c14e8e6e5db": "Arizona Coast Performing Arts dup (season ended May)",
    "b1cbda16-5f03-49e3-a937-8ce858b51782": "For Dog's Sake! Training (group classes suspended)",
}


def _target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Perform the deletes (default: dry run).")
    args = ap.parse_args(argv)

    print(f"DB target: {_target()}\n")
    db = SessionLocal()
    try:
        tot_sched = tot_off = tot_contrib = 0
        for eid, reason in STALE_VENUES.items():
            ent = db.get(Entity, eid)
            label = ent.name if ent is not None else "(missing entity)"
            contribs = (
                db.query(Contribution)
                .filter(
                    Contribution.source == "schedule_scrape",
                    Contribution.status == "approved",
                    Contribution.created_entity_id == eid,
                )
                .all()
            )
            titles = {
                (c.proposed_record or {}).get("title")
                for c in contribs
                if isinstance(c.proposed_record, dict) and (c.proposed_record or {}).get("title")
            }
            scheds = (
                db.query(Schedule)
                .filter(Schedule.entity_id == eid, Schedule.notes.in_(titles))
                .all()
                if titles else []
            )
            offs = (
                db.query(Offering)
                .filter(Offering.entity_id == eid, Offering.name.in_(titles))
                .all()
                if titles else []
            )
            print(f"{label}  [{reason}]")
            print(f"  contributions={len(contribs)} -> revert to pending; "
                  f"schedules={len(scheds)} + offerings={len(offs)} -> delete")
            tot_sched += len(scheds)
            tot_off += len(offs)
            tot_contrib += len(contribs)

            if args.apply:
                for s in scheds:
                    db.delete(s)
                for o in offs:
                    db.delete(o)
                for c in contribs:
                    c.status = "pending"
                    c.created_entity_id = None
                    c.reviewed_at = _utc_now_naive()

        print(f"\nTOTAL: contributions={tot_contrib}  schedules={tot_sched}  offerings={tot_off}")
        if not args.apply:
            print("\nDRY RUN - no writes. Re-run with --apply.")
            return 0
        db.commit()
        print(f"\nAPPLIED - deleted {tot_sched} schedules + {tot_off} offerings; "
              f"reverted {tot_contrib} contributions to pending (re-publishable in fall).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
