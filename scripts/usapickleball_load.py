"""Load USA Pickleball / Places2Play court listings into providers + ENTITY graph.

Net-new coverage vertical (Item D cross-source dedup audit follow-up). Mirrors
:mod:`scripts.golakehavasu_partners_load` but routes every write through the
shared dup-prevention funnel :func:`app.contrib.scraper_ingest.decide_ingest`
instead of calling ``reconcile_hit`` directly -- so an ambiguous match lands
HIDDEN (``draft=True`` + ``pending_review=True``) for admin review rather than
being inserted as a visible duplicate.

Pipeline: ``/search?q=<query>`` -> court rows -> per-place lat/lng enrichment ->
:class:`EntityPayload` (``source="usapickleball"``) -> ``decide_ingest`` ->
insert / merge / hold. New rows carry the ``racquet-sports`` subcategory and the
``classes-sports-recreation`` Tier-1 category.

Usage:
    python -m scripts.usapickleball_load --dry-run
    python -m scripts.usapickleball_load --query "Lake Havasu City"
    python -m scripts.usapickleball_load --query 86403 --limit 25
    python -m scripts.usapickleball_load --no-enrich   # skip lat/lng detail fetch
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import select

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.ingest_base import EntityPayload  # noqa: E402
from app.contrib.ingest_reconciler import log_ambiguous_reconcile  # noqa: E402
from app.contrib.scraper_ingest import decide_ingest  # noqa: E402
from app.contrib.usapickleball import (  # noqa: E402
    DEFAULT_CATEGORY_SLUG,
    LEGACY_CATEGORY,
    REQUEST_TIMEOUT,
    SUBCATEGORY,
    USER_AGENT,
    enrich_latlng,
    fetch_search,
    place_to_entity_payload,
)
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import (  # noqa: E402
    create_provider_and_entity,
    sync_provider_entity_from_legacy,
)
from app.db.models import Category, Entity, Provider  # noqa: E402
from app.db.seed_helpers import derive_provider_slug  # noqa: E402

logger = logging.getLogger(__name__)


def _provider_kwargs(
    payload: EntityPayload,
    *,
    category_id: int | None,
) -> dict[str, Any]:
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
    clobber richer existing data (usapickleball is low SOURCE_PRIORITY)."""
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


def ingest_places(
    *,
    query: str,
    category_slug: str,
    dry_run: bool,
    limit: int | None,
    enrich: bool = True,
    http_client: httpx.Client | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {
        "found": 0,
        "payloads_ready": 0,
        "inserted": 0,
        "inserted_pending": 0,
        "updated": 0,
        "reconcile_skipped": 0,
    }

    def _run(client: httpx.Client) -> dict[str, int]:
        places = fetch_search(query, client=client)
        if limit is not None:
            places = places[:limit]
        counts["found"] = len(places)
        if enrich:
            for place in places:
                try:
                    enrich_latlng(place, client=client)
                except Exception as e:  # noqa: BLE001
                    logger.warning("latlng enrich failed for place %s: %s", place.place_id, e)

        payloads = [place_to_entity_payload(p, category_slug=category_slug) for p in places]
        counts["payloads_ready"] = len(payloads)
        if dry_run or not payloads:
            return counts

        with SessionLocal() as session:
            cat_id = session.scalars(
                select(Category.id).where(Category.slug == category_slug)
            ).first()
            for payload in payloads:
                decision = decide_ingest(session, payload)
                kwargs = _provider_kwargs(decision.payload, category_id=cat_id)

                if decision.action == "update" and decision.existing_id:
                    prov = session.scalars(
                        select(Provider).where(Provider.entity_id == decision.existing_id).limit(1)
                    ).first()
                    if prov is None:
                        logger.warning(
                            "usapickleball update without provider entity_id=%s",
                            decision.existing_id,
                        )
                        counts["reconcile_skipped"] += 1
                        continue
                    _fill_gaps(prov, kwargs)
                    sync_provider_entity_from_legacy(session, prov)
                    _apply_merge_fields(session, decision.existing_id, decision.reconcile.merge_fields)
                    counts["updated"] += 1
                    continue

                # insert (genuinely new) OR ambiguous (held for review)
                if decision.should_hide:
                    log_ambiguous_reconcile(decision.reconcile, context="usapickleball_load")
                    kwargs["draft"] = True
                    kwargs["pending_review"] = True
                    counts["inserted_pending"] += 1
                else:
                    counts["inserted"] += 1
                slug = derive_provider_slug(session, kwargs["provider_name"])
                provider = Provider(**kwargs, slug=slug, last_google_scraped_at=None)
                session.add(provider)
                create_provider_and_entity(session, provider)
            session.commit()
        return counts

    if http_client is not None:
        return _run(http_client)
    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        return _run(client)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Ingest USA Pickleball / Places2Play courts")
    p.add_argument("--query", default="Lake Havasu City", help="Places2Play search query")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None, help="Cap number of court listings")
    p.add_argument(
        "--category-slug",
        default=DEFAULT_CATEGORY_SLUG,
        help="Tier-1 slug for new Provider.category_id + EntityCategory FK",
    )
    p.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip per-place lat/lng detail fetch (faster; weaker geo reconcile)",
    )
    args = p.parse_args()

    counts = ingest_places(
        query=args.query,
        category_slug=args.category_slug,
        dry_run=bool(args.dry_run),
        limit=args.limit,
        enrich=not args.no_enrich,
    )
    print("--- usapickleball_load summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    if args.dry_run:
        print("[usapickleball_load] dry-run: no DB writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
