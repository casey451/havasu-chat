"""Seed: Havasu Stitchers Quilt Guild — description + recurring meeting events.

USAGE
-----
    python -m scripts.seed_havasu_stitchers              # dry-run (default)
    python -m scripts.seed_havasu_stitchers --commit     # persist

Closes the 2026-06-04 visitor gap "when does the quilt guild meet"
(gap_template; see session notes GAP_INVESTIGATION_2026-06-07). The entity
``havasu-stitchers-quilt-guild`` landed via schedule_hunt on 2026-06-03 as a
bare shell (no description, hours, or events); this seed fills the
description and adds the guild's two recurring gatherings.

Source of truth: https://www.havasustitchers.com/ (fetched 2026-06-07). The
site's "Upcoming Events" block (Jun-Aug 2026) pins both rules, including the
explicit July anomaly ("On Wednesday this month only!" -> 8 Jul 2026), which
is encoded as exdate 2026-07-09 + rdate 2026-07-08.

Idempotent: the entity update is keyed on slug (description set only when
empty); events are upserted on (normalized_title, location_normalized).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Entity, Event  # noqa: E402
from app.events.scrapers.base import normalize_event_title  # noqa: E402

logger = logging.getLogger(__name__)

SEED_SOURCE = "seed_havasu_stitchers"
ENTITY_SLUG = "havasu-stitchers-quilt-guild"
ENTITY_NAME = "Havasu Stitchers Quilt Guild"
SOURCE_URL = "https://www.havasustitchers.com/events"

ENTITY_DESCRIPTION = (
    "Local quilt guild founded in 1992, an affiliate of the Arizona Quilters "
    "Guild. Monthly general meetings feature educational demonstrations, "
    "lectures, show and tell, and raffles; the guild also runs community "
    "outreach sewing sessions and a biennial quilt show (next: February "
    "2028). Guests are welcome at general meetings ($5 guest charge). "
    "Contact: info@havasustitchers.com."
)

# Each entry maps straight onto Event columns (see app/db/models.py). The
# recurrence engine (app/events/recurrence.py) expands rrule from the seed
# ``date`` as DTSTART and honors rdate/exdate ISO date strings.
SEED_EVENTS: tuple[dict, ...] = (
    {
        "title": "Havasu Stitchers General Member Meeting",
        "date": date(2026, 6, 11),
        "start_time": time(18, 0),
        "location_name": (
            "Mohave College, 1977 Acoma Blvd West, Room 600, "
            "Lake Havasu City, AZ 86403"
        ),
        "description": (
            "Monthly general meeting of the Havasu Stitchers quilt guild: "
            "educational demonstrations, lectures, show and tell, and "
            "raffles. Guests are welcome ($5 guest charge); arrive a little "
            "early to socialize."
        ),
        "rrule": "FREQ=MONTHLY;BYDAY=2TH",
        # July 2026 meets Wednesday the 8th instead of the 2nd Thursday.
        "exdate": ["2026-07-09"],
        "rdate": ["2026-07-08"],
        "tags": ["community", "classes", "recurring"],
    },
    {
        "title": "Havasu Stitchers Community Outreach Sewing",
        "date": date(2026, 6, 17),
        "start_time": time(10, 0),
        "location_name": (
            "Lake Havasu City Aquatic Center, 100 Park Avenue, "
            "Room 153/154, Lake Havasu City, AZ 86403"
        ),
        "description": (
            "Monthly community outreach sewing session hosted by the Havasu "
            "Stitchers quilt guild."
        ),
        "rrule": "FREQ=MONTHLY;BYDAY=3WE",
        "exdate": None,
        "rdate": None,
        "tags": ["community", "recurring"],
    },
)


def _normalize_location(location_name: str) -> str:
    # Same shape as the scraper-side venue normalization (lowercase,
    # alphanumeric tokens) so cross-source dedupe keys stay comparable.
    return normalize_event_title(location_name)


def _upsert_entity_description(db: Session, counts: dict[str, int]) -> None:
    entity = db.scalars(select(Entity).where(Entity.slug == ENTITY_SLUG)).first()
    now = datetime.now(UTC)
    if entity is None:
        # Prod has this row (schedule_hunt 2026-06-03); creating here keeps
        # the seed self-contained on empty dev DBs.
        entity = Entity(
            entity_type="commercial",
            slug=ENTITY_SLUG,
            name=ENTITY_NAME,
            description=ENTITY_DESCRIPTION,
            source=SEED_SOURCE,
            last_verified_at=now,
        )
        db.add(entity)
        counts["entity_created"] += 1
        return
    if not entity.description:
        entity.description = ENTITY_DESCRIPTION
        entity.last_verified_at = now
        counts["entity_updated"] += 1
    else:
        counts["entity_unchanged"] += 1


def _upsert_event(db: Session, spec: dict, counts: dict[str, int]) -> None:
    normalized_title = normalize_event_title(spec["title"])
    location_normalized = _normalize_location(spec["location_name"])
    existing = db.scalars(
        select(Event).where(
            Event.normalized_title == normalized_title,
            Event.location_normalized == location_normalized,
        )
    ).first()
    if existing is not None:
        counts["events_existing"] += 1
        return
    db.add(
        Event(
            title=spec["title"],
            normalized_title=normalized_title,
            date=spec["date"],
            start_time=spec["start_time"],
            location_name=spec["location_name"],
            location_normalized=location_normalized,
            description=spec["description"],
            event_url=SOURCE_URL,
            source_url=SOURCE_URL,
            tags=list(spec["tags"]),
            status="live",
            source=SEED_SOURCE,
            verified=True,
            created_by=SEED_SOURCE,
            is_recurring=True,
            rrule=spec["rrule"],
            rdate=spec["rdate"],
            exdate=spec["exdate"],
            last_verified_at=datetime.now(UTC),
        )
    )
    counts["events_created"] += 1


def run_seed(*, dry_run: bool = True) -> dict[str, int]:
    counts = {
        "entity_created": 0,
        "entity_updated": 0,
        "entity_unchanged": 0,
        "events_created": 0,
        "events_existing": 0,
    }
    with SessionLocal() as db:
        # no_autoflush: keeps the dry-run truly read-only (autoflush would
        # otherwise INSERT pending rows mid-loop — and fail on a readonly
        # role). Commit mode flushes everything at db.commit().
        with db.no_autoflush:
            _upsert_entity_description(db, counts)
            for spec in SEED_EVENTS:
                _upsert_event(db, spec, counts)
        if dry_run:
            db.rollback()
        else:
            db.commit()
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No-op flag; dry-run is already the default (use --commit to persist).",
    )
    parser.add_argument("--commit", action="store_true", help="Persist the batch.")
    args = parser.parse_args()
    dry_run = not args.commit
    stats = run_seed(dry_run=dry_run)
    mode = "DRY-RUN" if dry_run else "COMMITTED"
    logger.info("[%s] %s", mode, ", ".join(f"{k}={v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
