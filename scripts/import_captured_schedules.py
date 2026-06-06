"""Import captured class schedules -> draft program contributions.

Reads ``docs/scraper/captured_class_schedules.json`` (structured, source-verified
class grids for the schedule-hunt venues) and turns each class into a ``program``
:class:`~app.db.models.Contribution` carrying a ``ProgramApprovalFields``
``proposed_record`` — the SAME shape the scrape/ingest loop produces. From there
the normal flow takes over: it auto-publishes onto the venue entity if
``SCHEDULE_HUNT_AUTOPUBLISH`` is on, else it waits in ``/admin/contributions`` for
review. Publishing attaches a recurring Schedule + Offering, which the provider
profile now renders ("Classes & schedule").

Each class resolves its venue ``target_entity_id`` by name when that entity
already exists (so publishing lands on the right venue); when it doesn't resolve,
the contribution still lands pending with the venue name for manual linking.

Dedup: the ingest-side guard keys on (target_entity_id, proposed_record.title),
so re-running is idempotent and same-titled distinct slots must use distinct
titles in the dataset (e.g. "Adult No-Gi (Morning)" vs "(Night)").

Usage:
    python scripts/import_captured_schedules.py                 # dry-run (default)
    python scripts/import_captured_schedules.py --venue "Bridge City Combat"
    python scripts/import_captured_schedules.py --apply         # write (prod-data op!)

``--apply`` is a production-data operation: per CLAUDE.md, run the dry-run first,
show the counts, and get Casey's approval before applying.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.contrib.autopublish_policy import is_eligible  # noqa: E402
from app.contrib.schedule_publish import publish_contribution  # noqa: E402
from app.db import contribution_store as cs  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Entity  # noqa: E402
from app.schemas.contribution import ContributionCreate, ProgramApprovalFields  # noqa: E402

_DATASET = Path(__file__).resolve().parents[1] / "docs" / "scraper" / "captured_class_schedules.json"
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_SOURCE = "schedule_scrape"


@dataclass
class Counts:
    venues: int = 0
    classes_total: int = 0
    entity_resolved: int = 0
    entity_unresolved: int = 0
    created: int = 0
    published: int = 0
    duplicate: int = 0
    invalid: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def resolve_entity_id(db: Any, name: str) -> str | None:
    """Best-effort existing-venue match by normalised name (exact, then prefix)."""
    target = _norm_name(name)
    if not target:
        return None
    rows = db.execute(select(Entity.id, Entity.name).where(Entity.is_active.is_(True))).all()
    # Exact normalised match first, then a contains match (real entity, not a fixture).
    for eid, ename in rows:
        if _norm_name(ename) == target:
            return eid
    for eid, ename in rows:
        ne = _norm_name(ename)
        if ne and (target in ne or ne in target):
            return eid
    return None


def _days_label(days: list[str]) -> str:
    abbr = {d: d.capitalize() for d in _DAYS}
    ordered = [abbr[d] for d in _DAYS if d in {x.lower() for x in days}]
    return ", ".join(ordered)


def _to_program_fields(venue: dict, cls: dict) -> ProgramApprovalFields:
    title = str(cls["title"]).strip()
    days = [d.lower() for d in (cls.get("days") or []) if d.lower() in _DAYS]
    when = _days_label(days)
    desc = (
        f"{title} at {venue['provider_name']}"
        + (f" — {when} {cls['start']}–{cls['end']}." if when else ".")
        + " Recurring class; confirm current times with the venue."
    )
    return ProgramApprovalFields(
        title=title,
        description=desc,
        age_min=cls.get("age_min"),
        age_max=cls.get("age_max"),
        schedule_days=days,
        schedule_start_time=str(cls["start"]),
        schedule_end_time=str(cls["end"]),
        location_name=str(venue.get("location_name") or venue["provider_name"]),
        location_address=venue.get("location_address"),
        cost=cls.get("cost") or venue.get("cost"),
        provider_name=str(venue["provider_name"]),
        contact_phone=venue.get("contact_phone"),
        contact_email=venue.get("contact_email"),
        contact_url=venue.get("contact_url"),
        tags=list(venue.get("tags") or []),
    )


def import_schedules(*, dry_run: bool, only_venue: str | None = None) -> Counts:
    data = json.loads(_DATASET.read_text(encoding="utf-8"))
    venues = data.get("venues", [])
    counts = Counts()

    for venue in venues:
        if only_venue and _norm_name(venue["provider_name"]) != _norm_name(only_venue):
            continue
        counts.venues += 1
        with SessionLocal() as db:
            entity_id = resolve_entity_id(db, venue["provider_name"])
        if entity_id:
            counts.entity_resolved += 1
        else:
            counts.entity_unresolved += 1
        print(
            f"\n{venue['provider_name']} -> "
            + (f"entity {entity_id}" if entity_id else "NO entity match (lands pending)")
        )

        for cls in venue.get("classes", []):
            counts.classes_total += 1
            try:
                fields = _to_program_fields(venue, cls)
            except Exception as e:  # validation
                counts.invalid += 1
                print(f"  invalid: {cls.get('title')!r}: {e}", file=sys.stderr)
                continue

            contribution = ContributionCreate(
                entity_type="program",
                submission_name=f"{venue['provider_name']} — {fields.title}"[:200],
                source_url=venue.get("source_url"),
                submission_notes=fields.description,
                source=_SOURCE,  # type: ignore[arg-type]
                confidence=float(venue.get("confidence", 0.6)),
                target_entity_id=entity_id,
                proposed_record=fields.model_dump(),
                unverified=True,
            )

            label = f"  {fields.title} ({_days_label(fields.schedule_days)} {fields.schedule_start_time})"
            if dry_run:
                counts.created += 1
                print(f"{label}  [would create]")
                continue
            try:
                with SessionLocal() as db:
                    if entity_id and cs.has_pending_or_approved_program_dup(db, entity_id, fields.title):
                        counts.duplicate += 1
                        print(f"{label}  [duplicate — skipped]")
                        continue
                    row = cs.create_contribution(db, contribution)
                    db.commit()
                    counts.created += 1
                    # Mirror the ingest path: auto-publish onto the venue entity
                    # only when SCHEDULE_HUNT_AUTOPUBLISH is on AND the row clears
                    # the confidence bar; otherwise it waits in /admin/contributions.
                    if is_eligible(row) and publish_contribution(db, row).get("status") == "published":
                        counts.published += 1
                        print(f"{label}  [created + published]")
                    else:
                        print(f"{label}  [created — pending review]")
            except Exception as e:
                counts.errors += 1
                print(f"{label}  ERROR: {e}", file=sys.stderr)

    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="write contributions (prod-data op)")
    p.add_argument("--venue", default=None, help="only this venue (by name)")
    args = p.parse_args(argv)

    counts = import_schedules(dry_run=not args.apply, only_venue=args.venue)
    print("\n--- import_captured_schedules summary ---")
    for k, v in counts.as_dict().items():
        print(f"  {k:<18} {v}")
    if not args.apply:
        print("  (dry run — no DB writes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
