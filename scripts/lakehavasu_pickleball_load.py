"""Load Lake Havasu City Pickleball Association (LHCPBA) content into the catalog.

One source, three targets (each via the established, idempotent path):

  * **Facilities** -> Providers, through the shared dup-prevention funnel
    :func:`app.contrib.scraper_ingest.decide_ingest` (insert / merge / hold),
    exactly like ``scripts.usapickleball_load``. New rows carry the
    ``racquet-sports`` subcategory + ``classes-sports-recreation`` Tier-1 category.

  * **Activities + open-play schedule** -> recurring Programs, via
    ``contribution_store.create_contribution`` +
    ``approval_service.approve_contribution_as_program`` (mirrors
    ``app.contrib.parks_rec_loader``). Dedup on a synthesized ``source_url``.

  * **PickleFest** -> a dated Event, via ``approve_contribution_as_event``.

The recurring open-play schedule comes from the JS calendar widget and needs a
headless browser; pass ``--skip-calendar`` to run the network-light parts only
(useful locally without ``playwright install``).

Usage::

    python -m scripts.lakehavasu_pickleball_load --dry-run
    python -m scripts.lakehavasu_pickleball_load --skip-calendar
    python -m scripts.lakehavasu_pickleball_load
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import select

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.approval_service import (  # noqa: E402
    approve_contribution_as_event,
    approve_contribution_as_program,
)
from app.contrib.ingest_base import EntityPayload  # noqa: E402
from app.contrib.ingest_reconciler import log_ambiguous_reconcile  # noqa: E402
from app.contrib.lakehavasu_pickleball import (  # noqa: E402
    DEFAULT_CATEGORY_SLUG,
    LEGACY_CATEGORY,
    ORG_NAME,
    REQUEST_TIMEOUT,
    SOURCE_NAME,
    SUBCATEGORY,
    USER_AGENT,
    EventSpec,
    Facility,
    ProgramSpec,
    facility_to_entity_payload,
    fetch_activities,
    fetch_facilities,
    fetch_tournaments,
)
from app.contrib.scraper_ingest import decide_ingest  # noqa: E402
from app.db import contribution_store as cs  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import (  # noqa: E402
    create_provider_and_entity,
    sync_provider_entity_from_legacy,
)
from app.db.models import Category, Contribution, Entity, Event, Provider  # noqa: E402
from app.db.seed_helpers import derive_provider_slug  # noqa: E402
from app.schemas.contribution import (  # noqa: E402
    ContributionCreate,
    EventApprovalFields,
    ProgramApprovalFields,
)

logger = logging.getLogger(__name__)

# Contribution.source must be a value in the ContributionSource Literal; the
# scraper-specific tag lives on the Provider/Entity (source="lakehavasu_pickleball")
# via decide_ingest. "operator_backfill" is the auto-approve tier parks-rec uses.
CONTRIBUTION_SOURCE = "operator_backfill"
DEFAULT_PROGRAM_TIME = "00:00"  # placeholder for programs with no fixed clock time
# Assumed session length when a program has a known start but no published end,
# so we never record a misleading "ends at midnight" interval.
DEFAULT_SESSION_MINUTES = 120


def _add_minutes(hhmm: str, minutes: int) -> str:
    """Add ``minutes`` to an 'HH:MM' clock string, wrapping past midnight."""
    total = (int(hhmm[:2]) * 60 + int(hhmm[3:5]) + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _schedule_window(start: str | None, end: str | None) -> tuple[str, str]:
    """Return ('HH:MM', 'HH:MM') start/end for a program's schedule.

    ProgramApprovalFields requires both times, but we must not fabricate a
    midnight end for a session that has a real start (CodeRabbit flag). So when
    the end is unknown but the start is known, assume DEFAULT_SESSION_MINUTES;
    when neither is known, both default to 00:00 -- a zero-length placeholder
    that reads as "no fixed time" rather than a bogus overnight interval.
    """
    if start and not end:
        return start, _add_minutes(start, DEFAULT_SESSION_MINUTES)
    if not start:
        return DEFAULT_PROGRAM_TIME, (end or DEFAULT_PROGRAM_TIME)
    return start, end


# ---------------------------------------------------------------------------
# Facilities -> Providers (decide_ingest funnel)
# ---------------------------------------------------------------------------


def _provider_kwargs(payload: EntityPayload, *, category_id: int | None) -> dict[str, Any]:
    return {
        "provider_name": payload.name,
        "category": payload.legacy_category or LEGACY_CATEGORY,
        "category_id": category_id,
        "subcategory": SUBCATEGORY,
        "address": payload.address,
        "phone": payload.phone,
        "website": payload.website,
        "description": payload.description,
        "google_place_id": None,
        "lat": payload.lat,
        "lng": payload.lng,
        "zip": None,
        "source": payload.source,
        "enrichment_version": None,
        "is_active": True,
        "verified": False,
        "draft": False,
        "pending_review": False,
        "tier": "free",
    }


def _fill_gaps(
    prov: Provider,
    kwargs: dict[str, Any],
    *,
    fields: tuple[str, ...] = ("phone", "website", "address", "description"),
) -> None:
    """Supplement empty contact fields on a reconcile ``update`` hit; never
    clobber richer existing data."""
    for f in fields:
        incoming = kwargs.get(f)
        if incoming is None or incoming == "":
            continue
        current = getattr(prov, f)
        if current is None or current == "":
            setattr(prov, f, incoming)


def _apply_merge_fields(session: Any, entity_id: str, merge_fields: dict[str, Any] | None) -> None:
    if not merge_fields:
        return
    ent = session.get(Entity, entity_id)
    if ent is None:
        return
    if "name" in merge_fields:
        ent.name = str(merge_fields["name"])[:255]
    if "description" in merge_fields:
        ent.description = merge_fields["description"]
    if "source" in merge_fields:
        ent.source = str(merge_fields["source"])[:64]


def ingest_facilities(
    facilities: list[Facility],
    *,
    db: Any,
    category_slug: str,
    dry_run: bool,
) -> dict[str, int]:
    counts = {"found": len(facilities), "inserted": 0, "inserted_pending": 0,
              "updated": 0, "reconcile_skipped": 0}
    payloads = [facility_to_entity_payload(f, category_slug=category_slug) for f in facilities]
    if dry_run or not payloads:
        counts["inserted"] = len(payloads)  # would-insert estimate for dry-run
        return counts

    cat_id = db.scalars(select(Category.id).where(Category.slug == category_slug)).first()
    if cat_id is None:
        raise ValueError(
            f"Unknown category_slug {category_slug!r}: no Category row found. "
            "Aborting to avoid inserting providers with category_id=None."
        )
    for payload in payloads:
        decision = decide_ingest(db, payload)
        kwargs = _provider_kwargs(decision.payload, category_id=cat_id)

        if decision.action == "update" and decision.existing_id:
            prov = db.scalars(
                select(Provider).where(Provider.entity_id == decision.existing_id).limit(1)
            ).first()
            if prov is None:
                logger.warning("%s update without provider entity_id=%s",
                               SOURCE_NAME, decision.existing_id)
                counts["reconcile_skipped"] += 1
                continue
            _fill_gaps(prov, kwargs)
            sync_provider_entity_from_legacy(db, prov)
            _apply_merge_fields(db, decision.existing_id, decision.reconcile.merge_fields)
            counts["updated"] += 1
            continue

        if decision.should_hide:
            log_ambiguous_reconcile(decision.reconcile, context="lakehavasu_pickleball_load")
            kwargs["draft"] = True
            kwargs["pending_review"] = True
            counts["inserted_pending"] += 1
        else:
            counts["inserted"] += 1
        slug = derive_provider_slug(db, kwargs["provider_name"])
        provider = Provider(**kwargs, slug=slug, last_google_scraped_at=None)
        db.add(provider)
        create_provider_and_entity(db, provider)
    db.commit()
    return counts


# ---------------------------------------------------------------------------
# Programs + Events (contribution + auto-approve)
# ---------------------------------------------------------------------------


def _existing_source_url(db: Any, url: str | None) -> bool:
    if not url:
        return False
    if db.scalar(select(Contribution.id).where(Contribution.source_url == url).limit(1)) is not None:
        return True
    if db.scalar(select(Event.id).where(Event.source_url == url).limit(1)) is not None:
        return True
    return False


def _program_source_url(spec: ProgramSpec) -> str:
    base = spec.contact_url
    anchor = spec.source_anchor or spec.title
    return cs.normalize_submission_url(f"{base}#{anchor}")


def ingest_programs(
    specs: list[ProgramSpec],
    *,
    db: Any,
    dry_run: bool,
) -> dict[str, int]:
    counts = {"found": len(specs), "imported": 0, "skipped_duplicate": 0,
              "skipped_invalid": 0, "approval_failed": 0}
    for spec in specs:
        src_url = _program_source_url(spec)
        if _existing_source_url(db, src_url):
            counts["skipped_duplicate"] += 1
            continue
        try:
            create = ContributionCreate(
                entity_type="program",
                submission_name=spec.title[:200],
                submission_url=spec.contact_url,
                source_url=src_url,
                submission_category_hint=SOURCE_NAME,
                submission_notes=spec.description,
                source=CONTRIBUTION_SOURCE,
            )
            sched_start, sched_end = _schedule_window(spec.start_time, spec.end_time)
            approve = ProgramApprovalFields(
                title=spec.title[:300],
                description=spec.description,
                schedule_days=spec.schedule_days,
                schedule_start_time=sched_start,
                schedule_end_time=sched_end,
                location_name=spec.location_name,
                location_address=spec.location_address,
                cost=spec.cost,
                provider_name=ORG_NAME,
                contact_url=spec.contact_url,
                tags=spec.tags,
            )
        except Exception as e:  # noqa: BLE001
            counts["skipped_invalid"] += 1
            logger.warning("invalid program spec %s: %s", spec.title, e)
            continue
        if dry_run:
            counts["imported"] += 1
            continue
        try:
            created = cs.create_contribution(db, create)
            approve_contribution_as_program(db, created.id, approve, spec.activity_category)
            db.commit()
            counts["imported"] += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            counts["approval_failed"] += 1
            logger.warning("approve program %s failed: %s", spec.title, e)
    return counts


def ingest_events(
    specs: list[EventSpec],
    *,
    db: Any,
    dry_run: bool,
) -> dict[str, int]:
    counts = {"found": len(specs), "imported": 0, "skipped_duplicate": 0,
              "skipped_invalid": 0, "approval_failed": 0}
    for spec in specs:
        src_url = cs.normalize_submission_url(f"{spec.event_url}#{spec.source_anchor}")
        if _existing_source_url(db, src_url):
            counts["skipped_duplicate"] += 1
            continue
        try:
            create = ContributionCreate(
                entity_type="event",
                submission_name=spec.title[:200],
                submission_url=spec.event_url,
                source_url=src_url,
                submission_category_hint=SOURCE_NAME,
                submission_notes=spec.description,
                event_date=spec.date,
                event_end_date=spec.end_date,
                event_time_start=time(8, 0),
                source=CONTRIBUTION_SOURCE,
            )
            approve = EventApprovalFields(
                title=spec.title,
                description=spec.description,
                date=spec.date,
                end_date=spec.end_date,
                start_time=time(8, 0),
                location_name=spec.location_name,
                event_url=spec.event_url,
                source_url=src_url,
            )
        except Exception as e:  # noqa: BLE001
            counts["skipped_invalid"] += 1
            logger.warning("invalid event spec %s: %s", spec.title, e)
            continue
        if dry_run:
            counts["imported"] += 1
            continue
        try:
            created = cs.create_contribution(db, create)
            approve_contribution_as_event(db, created.id, approve, ["sports"])
            db.commit()
            counts["imported"] += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            counts["approval_failed"] += 1
            logger.warning("approve event %s failed: %s", spec.title, e)
    return counts


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run(
    *,
    dry_run: bool,
    skip_calendar: bool,
    category_slug: str = DEFAULT_CATEGORY_SLUG,
    http_client: httpx.Client | None = None,
    today: date | None = None,
) -> dict[str, dict[str, int]]:
    own_client = http_client is None
    client = http_client or httpx.Client(
        timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    )
    try:
        facilities = fetch_facilities(client=client)
        program_specs = fetch_activities(client=client)
        event_specs = fetch_tournaments(client=client, today=today)
    finally:
        if own_client:
            client.close()

    if not skip_calendar:
        try:
            from app.contrib.lakehavasu_pickleball_calendar import (
                fetch_calendar_occurrences,
                group_open_play,
            )

            occurrences = fetch_calendar_occurrences(months=1)
            program_specs = program_specs + group_open_play(occurrences)
        except Exception as e:  # noqa: BLE001
            logger.warning("open-play calendar step skipped: %s", e)

    results: dict[str, dict[str, int]] = {}
    with SessionLocal() as db:
        results["facilities"] = ingest_facilities(
            facilities, db=db, category_slug=category_slug, dry_run=dry_run
        )
        results["programs"] = ingest_programs(program_specs, db=db, dry_run=dry_run)
        results["events"] = ingest_events(event_specs, db=db, dry_run=dry_run)
    return results


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Ingest LakeHavasuPickleball.com content")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--skip-calendar",
        action="store_true",
        help="Skip the JS open-play calendar (no headless browser needed)",
    )
    p.add_argument("--category-slug", default=DEFAULT_CATEGORY_SLUG)
    args = p.parse_args()

    results = run(
        dry_run=bool(args.dry_run),
        skip_calendar=bool(args.skip_calendar),
        category_slug=args.category_slug,
    )
    print("--- lakehavasu_pickleball_load summary ---")
    for section, counts in results.items():
        print(f"[{section}]")
        for k, v in counts.items():
            print(f"  {k}: {v}")
    if args.dry_run:
        print("[lakehavasu_pickleball_load] dry-run: no DB writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
