"""Load Lake Havasu golf venues + hours into the catalog.

Mirrors :mod:`scripts.lakehavasu_pickleball_load`:

  * **Facilities** -> Providers via the shared dup-prevention funnel
    :func:`app.contrib.scraper_ingest.decide_ingest` (insert / merge / hold).
    New rows carry the ``golf`` subcategory + ``outdoors-parks-trails`` Tier-1
    category. Respects the in-town geo-fence (the module curates only in-area
    venues; the out-of-area courses the repo prunes are never emitted).

  * **Hours** -> all-day Events per venue on a rolling forward window, pruned as
    they age (``prune_golf_hours_events``), tagged ``activity:golf`` +
    ``facet:hours`` + ``venue-kind:*`` (+ ``indoor:true`` for simulators).

Usage::

    python -m scripts.lhc_golf_load --dry-run
    python -m scripts.lhc_golf_load
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.contrib.approval_service import approve_contribution_as_event  # noqa: E402
from app.contrib.ingest_base import EntityPayload  # noqa: E402
from app.contrib.ingest_reconciler import log_ambiguous_reconcile  # noqa: E402
from app.contrib.lhc_golf import (  # noqa: E402
    DEFAULT_CATEGORY_SLUG,
    LEGACY_CATEGORY,
    SOURCE_NAME,
    SUBCATEGORY,
    GolfEventSpec,
    GolfVenue,
    facility_to_entity_payload,
    golf_facilities,
    golf_hours_event_specs,
)
from app.contrib.scraper_ingest import decide_ingest  # noqa: E402
from app.db import contribution_store as cs  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import (  # noqa: E402
    create_provider_and_entity,
    sync_provider_entity_from_legacy,
)
from app.db.models import Category, Contribution, Event, Provider  # noqa: E402
from app.db.seed_helpers import derive_provider_slug  # noqa: E402
from app.schemas.contribution import ContributionCreate, EventApprovalFields  # noqa: E402

logger = logging.getLogger(__name__)

CONTRIBUTION_SOURCE = "operator_backfill"  # auto-approve tier (venue/official data)


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
    """Supplement empty contact fields on an update hit; never clobber data."""
    for f in fields:
        incoming = kwargs.get(f)
        if incoming is None or incoming == "":
            continue
        if getattr(prov, f) in (None, ""):
            setattr(prov, f, incoming)


def ingest_facilities(
    venues: list[GolfVenue], *, db: Any, category_slug: str, dry_run: bool
) -> dict[str, int]:
    counts = {"found": len(venues), "inserted": 0, "inserted_pending": 0,
              "updated": 0, "reconcile_skipped": 0}
    payloads = [facility_to_entity_payload(v, category_slug=category_slug) for v in venues]
    if not payloads:
        return counts

    cat_id = db.scalars(select(Category.id).where(Category.slug == category_slug)).first()
    if cat_id is None:
        raise ValueError(
            f"Unknown category_slug {category_slug!r}: no Category row found. "
            "Aborting to avoid inserting providers with category_id=None."
        )
    # decide_ingest is read-only, so the dry-run runs the SAME insert/update/hold
    # decision against live rows and reports the HONEST would-counts (a golf course
    # already in the directory shows as 'updated', not a phantom new insert).
    for payload in payloads:
        decision = decide_ingest(db, payload)
        kwargs = _provider_kwargs(decision.payload, category_id=cat_id)

        if decision.action == "update" and decision.existing_id:
            prov = db.scalars(
                select(Provider).where(Provider.entity_id == decision.existing_id).limit(1)
            ).first()
            if prov is None:
                counts["reconcile_skipped"] += 1
                continue
            logger.info("facility update: %s -> %s", payload.name, prov.provider_name)
            counts["updated"] += 1
            if dry_run:
                continue
            _fill_gaps(prov, kwargs)
            sync_provider_entity_from_legacy(db, prov)
            continue

        if decision.should_hide:
            kwargs["draft"] = True
            kwargs["pending_review"] = True
            counts["inserted_pending"] += 1
            logger.info("facility pending (ambiguous, held for review): %s", payload.name)
            if not dry_run:
                log_ambiguous_reconcile(decision.reconcile, context="lhc_golf_load")
        else:
            counts["inserted"] += 1
            logger.info("facility insert (new): %s", payload.name)
        if dry_run:
            continue
        slug = derive_provider_slug(db, kwargs["provider_name"])
        provider = Provider(**kwargs, slug=slug, last_google_scraped_at=None)
        db.add(provider)
        create_provider_and_entity(db, provider)
    if not dry_run:
        db.commit()
    return counts


# ---------------------------------------------------------------------------
# Hours -> Events (contribution + auto-approve)
# ---------------------------------------------------------------------------
def _existing_source_url(db: Any, url: str | None) -> bool:
    if not url:
        return False
    if db.scalar(select(Contribution.id).where(Contribution.source_url == url).limit(1)) is not None:
        return True
    if db.scalar(select(Event.id).where(Event.source_url == url).limit(1)) is not None:
        return True
    return False


def ingest_events(specs: list[GolfEventSpec], *, db: Any, dry_run: bool) -> dict[str, int]:
    counts = {"found": len(specs), "imported": 0, "skipped_duplicate": 0,
              "skipped_invalid": 0, "approval_failed": 0}
    for spec in specs:
        src_url = cs.normalize_submission_url(f"{spec.event_url}#{spec.source_anchor}")
        if _existing_source_url(db, src_url):
            counts["skipped_duplicate"] += 1
            continue
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
            logger.warning("invalid golf event spec %s: %s", spec.title, e)
            continue
        if dry_run:
            counts["imported"] += 1
            continue
        try:
            created = cs.create_contribution(db, create)
            # Pass the canonical golf tags (activity:golf + facet:hours +
            # venue-kind:* [+ indoor:true]) straight through to the event.
            approve_contribution_as_event(db, created.id, approve, spec.tags or ["activity:golf"])
            db.commit()
            counts["imported"] += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            counts["approval_failed"] += 1
            logger.warning("approve golf event %s failed: %s", spec.title, e)
    return counts


HOURS_PRUNE_GRACE_DAYS = 2


def prune_golf_hours_events(
    *, db: Any, today: date | None = None, grace_days: int = HOURS_PRUNE_GRACE_DAYS
) -> int:
    """Hard-delete golf hours Event rows older than ``today - grace`` (the rolling
    window republishes them each run; mirrors the pickleball open-play pruner)."""
    today = today or date.today()
    cutoff = today - timedelta(days=max(0, grace_days))
    q = db.query(Event).filter(Event.source_url.like("%golfhours|%"), Event.date < cutoff)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run(
    *, dry_run: bool, category_slug: str = DEFAULT_CATEGORY_SLUG, today: date | None = None
) -> dict[str, dict[str, int]]:
    venues = golf_facilities()
    event_specs = golf_hours_event_specs(today=today)
    results: dict[str, dict[str, int]] = {}
    with SessionLocal() as db:
        results["facilities"] = ingest_facilities(
            venues, db=db, category_slug=category_slug, dry_run=dry_run
        )
        results["events"] = ingest_events(event_specs, db=db, dry_run=dry_run)
        results["events"]["pruned_hours"] = (
            0 if dry_run else prune_golf_hours_events(db=db, today=today)
        )
    return results


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Ingest Lake Havasu golf venues + hours")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--category-slug", default=DEFAULT_CATEGORY_SLUG)
    args = p.parse_args()

    results = run(dry_run=bool(args.dry_run), category_slug=args.category_slug)
    print("--- lhc_golf_load summary ---")
    for section, counts in results.items():
        print(f"[{section}]")
        for k, v in counts.items():
            print(f"  {k}: {v}")
    if args.dry_run:
        print("[lhc_golf_load] dry-run: no DB writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
