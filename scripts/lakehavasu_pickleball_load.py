"""Load Lake Havasu City Pickleball Association (LHCPBA) content into the catalog.

One source, three targets (each via the established, idempotent path):

  * **Facilities** -> Providers, through the shared dup-prevention funnel
    :func:`app.contrib.scraper_ingest.decide_ingest` (insert / merge / hold),
    exactly like ``scripts.usapickleball_load``. New rows carry the
    ``racquet-sports`` subcategory + ``classes-sports-recreation`` Tier-1 category.

  * **Activities** (round robins, lessons, clinics) -> recurring Programs, via
    ``contribution_store.create_contribution`` +
    ``approval_service.approve_contribution_as_program`` (mirrors
    ``app.contrib.parks_rec_loader``). Dedup on a synthesized ``source_url``.

  * **Open play** -> all-day Events per venue on a rolling forward window, pruned
    as they age (``prune_open_play_events``). Derived from the facility list, so
    no headless browser is needed.

  * **PickleFest** -> a dated, timed Event, via ``approve_contribution_as_event``.

A facility that confidently matches an existing provider (e.g. the Aquatic
Center already seeded by the aquatics scraper) is merged into that row rather
than duplicated.

Usage::

    python -m scripts.lakehavasu_pickleball_load --dry-run
    python -m scripts.lakehavasu_pickleball_load
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, time, timedelta
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
    open_play_event_specs,
)
from app.contrib.lhc_aquatic_pickleball import (  # noqa: E402
    AQUATIC_VENUE_NAME,
    fetch_aquatic_open_play,
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


def _norm(s: str | None) -> str | None:
    return " ".join((s or "").lower().split()) or None


def _same_venue(prov: Provider, payload: EntityPayload) -> bool:
    """True when an ambiguous reconcile hit is confidently the SAME venue --
    identical normalized name or identical normalized address. Used to fold
    pickleball details into an existing row (e.g. the Aquatic Center already
    seeded by the aquatics scraper) instead of creating a duplicate."""
    if (n := _norm(prov.provider_name)) and n == _norm(payload.name):
        return True
    if (a := _norm(prov.address)) and a == _norm(payload.address):
        return True
    return False


def _merge_pickleball_into(prov: Provider, payload: EntityPayload) -> None:
    """Additively note pickleball use on an existing provider's description
    (never clobbers; only appends if not already mentioned)."""
    desc = (prov.description or "").strip()
    if "pickleball" in desc.lower():
        return
    note = (
        "Also a Lake Havasu City Pickleball Association open-play venue -- see "
        f"{payload.website or 'lakehavasupickleball.com/places-to-play'}."
    )
    prov.description = f"{desc} {note}".strip()[:5000]


def ingest_facilities(
    facilities: list[Facility],
    *,
    db: Any,
    category_slug: str,
    dry_run: bool,
) -> dict[str, int]:
    counts = {"found": len(facilities), "inserted": 0, "inserted_pending": 0,
              "updated": 0, "merged": 0, "reconcile_skipped": 0}
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
            # Ambiguous hit: if it's confidently the same venue as an existing
            # row (e.g. the Aquatic Center already seeded by the aquatics
            # scraper), fold pickleball use into that row instead of creating a
            # hidden duplicate. Otherwise hold it for review as before.
            if decision.existing_id:
                existing = db.scalars(
                    select(Provider).where(Provider.entity_id == decision.existing_id).limit(1)
                ).first()
                if existing is not None and _same_venue(existing, decision.payload):
                    _merge_pickleball_into(existing, decision.payload)
                    sync_provider_entity_from_legacy(db, existing)
                    counts["merged"] += 1
                    continue
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
        # All-day events use start_time=00:00 + end_time=None (Ask Hava's all-day
        # convention; see app/v1/serializers.py). Timed events carry real
        # start/end clock times (e.g. Aquatic Center open play from the City PDF);
        # specs with no explicit time fall back to a generic daytime start.
        if spec.all_day:
            start, end = time(0, 0), None
        elif spec.start_time:
            sh, sm = spec.start_time.split(":")
            start = time(int(sh), int(sm))
            if spec.end_time:
                eh, em = spec.end_time.split(":")
                end = time(int(eh), int(em))
            else:
                end = None
        else:
            start, end = time(8, 0), None
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
                event_time_start=start,
                event_time_end=end,
                source=CONTRIBUTION_SOURCE,
            )
            approve = EventApprovalFields(
                title=spec.title,
                description=spec.description,
                date=spec.date,
                end_date=spec.end_date,
                start_time=start,
                end_time=end,
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


OPEN_PLAY_PRUNE_GRACE_DAYS = 2


def prune_open_play_events(
    *, db: Any, today: date | None = None, grace_days: int = OPEN_PLAY_PRUNE_GRACE_DAYS
) -> int:
    """Hard-delete open-play all-day Event rows older than ``today - grace``.

    Open-play events are republished on a rolling forward window each run, so the
    aged-out occurrences are dropped here to prevent unbounded accumulation
    (mirrors ``parks_rec_loader.prune_stale_aquatic``). Scope is limited to rows
    whose ``source_url`` carries the ``openplay|`` marker."""
    today = today or date.today()
    cutoff = today - timedelta(days=max(0, grace_days))
    q = db.query(Event).filter(
        Event.source_url.like("%openplay|%"),
        Event.date < cutoff,
    )
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


def prune_aquatic_allday(*, db: Any, dry_run: bool = False) -> int:
    """Remove superseded all-day Aquatic Center open-play rows.

    The Aquatic Center now publishes **timed** open play parsed from the City
    Open Gym PDF (anchor ``openplay|aquatic|...``). The legacy all-day rows
    (anchor ``openplay|<venue name>|<date>``) are obsolete and would otherwise
    duplicate the timed rows, so they are removed regardless of date. Matched
    on the old venue-name anchor only; the new timed rows are untouched. In
    dry-run we report the would-delete count without writing."""
    # source_url is normalised (lower-cased) on write, so match lower-case.
    pattern = f"%openplay|{AQUATIC_VENUE_NAME.lower()}|%"
    q = db.query(Event).filter(Event.source_url.like(pattern))
    if dry_run:
        return int(q.count() or 0)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run(
    *,
    dry_run: bool,
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
        # Aquatic Center timed open play from the City's stable Open Gym PDF.
        # Wrapped so a city-site hiccup never aborts the run; fetched inside
        # the try so the shared client is still open.
        try:
            aquatic_specs = fetch_aquatic_open_play(client=client)
        except Exception as e:  # noqa: BLE001
            logger.warning("aquatic open-gym schedule fetch failed: %s", e)
            aquatic_specs = []
    finally:
        if own_client:
            client.close()

    # Aquatic Center open play (timed, from the City PDF) replaces the
    # all-day placeholders for that venue; venues with no machine-readable
    # schedule stay all-day.
    allday_venues = (
        [f for f in facilities if f.name != AQUATIC_VENUE_NAME]
        if aquatic_specs
        else facilities
    )
    event_specs = (
        event_specs
        + aquatic_specs
        + open_play_event_specs(allday_venues, today=today)
    )

    results: dict[str, dict[str, int]] = {}
    with SessionLocal() as db:
        results["facilities"] = ingest_facilities(
            facilities, db=db, category_slug=category_slug, dry_run=dry_run
        )
        results["programs"] = ingest_programs(program_specs, db=db, dry_run=dry_run)
        results["events"] = ingest_events(event_specs, db=db, dry_run=dry_run)
        results["events"]["pruned_open_play"] = (
            0 if dry_run else prune_open_play_events(db=db, today=today)
        )
        results["events"]["pruned_aquatic_allday"] = prune_aquatic_allday(
            db=db, dry_run=dry_run
        )
    return results


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Ingest LakeHavasuPickleball.com content")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--category-slug", default=DEFAULT_CATEGORY_SLUG)
    args = p.parse_args()

    results = run(
        dry_run=bool(args.dry_run),
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
