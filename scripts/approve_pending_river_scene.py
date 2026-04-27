"""
One-shot: approve all pending RiverScene event contributions into the events catalog.

  python scripts/approve_pending_river_scene.py

Maps each Contribution to EventApprovalFields the same way as Fix 1
(``app/contrib/river_scene_pull.py``): title, description, times, and URL
from the row; ``location_name`` from a ``Venue:`` line in
``submission_notes`` when present (as written by
``normalize_to_contribution``), else ``Lake Havasu``; tags from a
``Categories:`` line when present, else ``[]``. No re-fetch of source HTML.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.contrib.approval_service import approve_contribution_as_event
from app.db.database import SessionLocal
from app.db.models import Contribution
from app.schemas.contribution import EventApprovalFields

_DEFAULT_VENUE = "Lake Havasu"


def _venue_from_submission_notes(notes: str | None) -> str:
    if not notes:
        return _DEFAULT_VENUE
    for raw in notes.splitlines():
        line = raw.strip()
        low = line.lower()
        if low.startswith("venue:"):
            rest = line[6:].strip()
            if len(rest) >= 3:
                return rest
            return _DEFAULT_VENUE
    return _DEFAULT_VENUE


def _tags_from_submission_notes(notes: str | None) -> list[str]:
    if not notes:
        return []
    for raw in notes.splitlines():
        line = raw.strip()
        low = line.lower()
        if low.startswith("categories:"):
            rest = line[11:].strip()
            return [p.strip() for p in rest.split(",") if p.strip()]
    return []


def _fields_from_contribution(c: Contribution) -> tuple[EventApprovalFields, list[str]]:
    url = (c.submission_url or "").strip()
    if not url:
        raise ValueError("submission_url is required for event approval")
    if c.event_date is None or c.event_time_start is None:
        raise ValueError("event_date and event_time_start are required")
    notes = c.submission_notes or ""
    loc = _venue_from_submission_notes(notes)
    tags = _tags_from_submission_notes(notes)
    fields = EventApprovalFields(
        title=c.submission_name,
        description=notes,
        date=c.event_date,
        start_time=c.event_time_start,
        end_time=c.event_time_end,
        location_name=loc,
        event_url=url,
    )
    return fields, tags


def run_backfill() -> tuple[int, int, int]:
    """
    Approve all pending ``river_scene_import`` event contributions.
    Returns ``(pending_found, approved, failed)``.
    """
    approved = 0
    failed = 0
    with SessionLocal() as db:
        stmt = (
            select(Contribution)
            .where(
                Contribution.source == "river_scene_import",
                Contribution.status == "pending",
                Contribution.entity_type == "event",
            )
            .order_by(Contribution.id)
        )
        rows = list(db.execute(stmt).scalars().all())
        pending_found = len(rows)
        for c in rows:
            try:
                approve_fields, tags = _fields_from_contribution(c)
                ev = approve_contribution_as_event(db, c.id, approve_fields, tags)
                approved += 1
                print(f"info: approved contribution {c.id} -> event {ev.id}")
            except Exception as e:
                failed += 1
                print(
                    f"warning: could not approve contribution {c.id}: {e}",
                    file=sys.stderr,
                )

    print("Approve pending RiverScene contributions (complete)")
    print(f"  pending_found: {pending_found}")
    print(f"  approved:      {approved}")
    print(f"  failed:        {failed}")
    return pending_found, approved, failed


def main() -> int:
    run_backfill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
