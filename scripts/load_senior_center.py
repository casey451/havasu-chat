"""Load Lake Havasu Senior Center activities into the Seniors calendar section.

Idempotent loader (run weekly by .github/workflows/senior-center.yml). Unlike
the contributions-queue scrapers, this writes ``Event`` rows DIRECTLY via the
same dual-write helper the approval path uses (app.db.entity_dual_write.
create_event_and_entity) -- because the recurring activities need an ``rrule``
to expand across the calendar, and the contributions/approval path drops the
rrule.

Every row is tagged ``"senior"`` (so the Seniors overlay on /events-ui picks it
up) and stamped ``Event.source = "lhc_senior_center"`` for idempotent re-runs.

Usage:
  python -m scripts.load_senior_center            # dry-run (default; safe)
  python -m scripts.load_senior_center --dry-run  # explicit dry-run
  python -m scripts.load_senior_center --apply     # write to the database

Safety: defaults to dry-run. Per repo policy, run --dry-run against prod first,
review the counts, then --apply.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import create_event_and_entity  # noqa: E402
from app.db.models import Event  # noqa: E402
from app.events import senior_center as sc  # noqa: E402
from app.schemas.event import EventCreate  # noqa: E402


def _find_existing(db, spec: sc.SeniorEventSpec) -> Event | None:
    norm = spec.title.lower().strip()
    stmt = select(Event).where(
        Event.source == sc.SOURCE, Event.normalized_title == norm
    )
    if not spec.is_recurring:
        # A one-off is keyed by (title, date); a recurring row is keyed by title
        # alone (its single anchor row carries the rrule).
        stmt = stmt.where(Event.date == spec.date)
    return db.scalars(stmt).first()


def _apply_fields(ev: Event, spec: sc.SeniorEventSpec) -> None:
    ev.description = spec.description
    ev.date = spec.date
    ev.end_date = spec.end_date
    ev.start_time = spec.start_time
    ev.end_time = spec.end_time
    ev.rrule = spec.rrule
    ev.is_recurring = spec.is_recurring
    ev.tags = list(spec.tags)
    ev.cost = spec.cost
    ev.status = "live"
    ev.scraped_at = datetime.now(UTC)


def _upsert(db, spec: sc.SeniorEventSpec, *, dry_run: bool) -> str:
    existing = _find_existing(db, spec)
    if existing is not None:
        if dry_run:
            return "would_update"
        _apply_fields(existing, spec)
        db.commit()
        return "updated"

    if dry_run:
        return "would_create"

    ec = EventCreate(
        title=spec.title,
        date=spec.date,
        end_date=spec.end_date,
        start_time=spec.start_time,
        end_time=spec.end_time,
        location_name=sc.VENUE_NAME,
        description=spec.description,
        event_url=spec.event_url,
        source_url=sc.EVENTS_URL,
        tags=list(spec.tags),
        is_recurring=spec.is_recurring,
        source=sc.SOURCE,
        status="live",
        created_by="admin",
    )
    ev = Event.from_create(ec)
    ev.is_recurring = spec.is_recurring
    ev.rrule = spec.rrule
    ev.cost = spec.cost
    ev.verified = True
    ev.scraped_at = datetime.now(UTC)
    db.add(ev)
    create_event_and_entity(db, ev)
    db.flush()
    db.commit()
    return "created"


def run(*, dry_run: bool, html: str | None = None) -> dict[str, int]:
    specs = sc.collect(html=html)
    today = date.today()
    counts: dict[str, int] = {}
    for spec in specs:
        # Skip one-off specials whose date has already passed.
        if not spec.is_recurring and spec.date < today:
            counts["skipped_past"] = counts.get("skipped_past", 0) + 1
            continue
        try:
            with SessionLocal() as db:
                action = _upsert(db, spec, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001 - one bad row must not abort the run
            print(f"error: {spec.title!r}: {exc}", file=sys.stderr)
            action = "error"
        counts[action] = counts.get(action, 0) + 1
    counts["total_specs"] = len(specs)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load senior center activities")
    parser.add_argument("--apply", action="store_true", help="write to the database")
    parser.add_argument("--dry-run", action="store_true", help="preview only (default)")
    args = parser.parse_args(argv)

    dry_run = not args.apply or args.dry_run
    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"=== load_senior_center [{mode}] ===")
    counts = run(dry_run=dry_run)
    for action, n in sorted(counts.items()):
        print(f"  {action}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
