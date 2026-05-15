"""Filter and load enriched Google Places rows into the providers table.

Phase 5 of the LHC business pull. Reads
scripts/output/places_pull/enrichment_enriched.jsonl, optionally narrows to
one Tier-1 category via ``--category`` (the enrichment file may carry rows
from several domains' scrapes), filters by LHC ZIP codes per the locked list
(86403/86404/86405/86406), and upserts each survivor into the providers table.

Upsert key: `google_place_id`. Matches existing rows by Place ID and
UPDATEs them; inserts new rows otherwise. Stamps `last_google_scraped_at`
on every write.

Idempotent — re-running on the same input produces the same DB state.

Usage:
    python -m scripts.places_load --dry-run                      # parse + filter only, no DB writes
    python -m scripts.places_load --category eat-drink --dry-run # preview one Tier-1 slice
    python -m scripts.places_load --category eat-drink           # load one Tier-1 slice
    python -m scripts.places_load                                # filter + load every domain

Environment:
    Uses whatever DB the app is configured against (DATABASE_URL or local
    SQLite). Run `alembic upgrade head` first if you haven't already.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.google_places_scraper import (  # noqa: E402
    DISCOVERY_CATEGORY_TO_DOMAINS,
    enrichment_row_to_entity_payload,
)
from app.contrib.google_types_mapping import (  # noqa: E402
    map_google_types_to_slug_and_place_type,
)
from app.contrib.ingest_reconciler import (  # noqa: E402
    log_ambiguous_reconcile,
    reconcile_hit,
)
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import (  # noqa: E402
    create_provider_and_entity,
    sync_provider_entity_from_legacy,
)
from app.db.models import Category, Entity, EntityCategory, Location, Provider  # noqa: E402
from app.db.seed_helpers import derive_provider_slug  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_INPUT_PATH = (
    Path(__file__).parent / "output" / "places_pull" / "enrichment_enriched.jsonl"
)
LHC_ZIPS = {"86403", "86404", "86405", "86406"}
ENRICHMENT_VERSION = "places_api_new_2026-05-06"


def load_enriched(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def filter_by_category(
    rows: list[dict[str, Any]], category_slug: str
) -> list[dict[str, Any]]:
    """Keep only rows whose discovery domain maps to the given Tier-1 slug.

    Mirrors ``places_discovery``'s ``--category`` behaviour: the slug is
    resolved through ``DISCOVERY_CATEGORY_TO_DOMAINS`` to one or more
    ``_first_seen_domain`` values, and rows outside those domains are dropped.
    This keeps a per-category load scoped to its category even when
    ``enrichment_enriched.jsonl`` carries rows from other domains' scrapes.
    """
    domains = DISCOVERY_CATEGORY_TO_DOMAINS.get(category_slug)
    if domains is None:
        known = ", ".join(sorted(DISCOVERY_CATEGORY_TO_DOMAINS))
        raise SystemExit(
            f"Unknown --category {category_slug!r}. Expected one of: {known}"
        )
    return [r for r in rows if r.get("_first_seen_domain", "") in domains]


def filter_by_zip(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep only rows in LHC ZIPs. Return (kept, drop_reason_counts)."""
    kept: list[dict[str, Any]] = []
    drops: Counter[str] = Counter()
    for row in rows:
        zip_code = row.get("zip")
        if zip_code in LHC_ZIPS:
            kept.append(row)
        elif zip_code is None:
            drops["no_zip"] += 1
        else:
            drops[f"non_lhc:{zip_code}"] += 1
    return kept, dict(drops)


def row_to_provider_kwargs(row: dict[str, Any]) -> dict[str, Any]:
    """Map an enriched row to the kwargs for Provider construction.

    `category` is NOT NULL on the providers table. Use the domain label
    from the discovery sweep (e.g. food_drink, lake_recreation) as a
    coarse-grained value; finer Google taxonomy lives in
    google_primary_category and google_categories.
    """
    domain = row.get("_first_seen_domain") or "uncategorized"
    return {
        "provider_name": row["display_name"],
        "category": domain,
        "address": row.get("formatted_address"),
        "phone": row.get("phone"),
        "website": row.get("website"),
        "google_place_id": row["place_id"],
        "google_primary_category": row.get("primary_type"),
        "google_categories": row.get("types") or None,
        "google_rating": row.get("rating"),
        "google_review_count": row.get("review_count"),
        "google_review_snippets": row.get("review_snippets") or None,
        "google_photo_refs": row.get("photo_refs") or None,
        "google_hours": row.get("regular_opening_hours") or None,
        "lat": row.get("lat"),
        "lng": row.get("lng"),
        "zip": row.get("zip"),
        "source": "google_places",
        "enrichment_version": ENRICHMENT_VERSION,
        "is_active": True,
        "verified": False,
        "draft": False,
        "pending_review": False,
        "tier": "free",
    }


def _resolve_category_id(
    row: dict[str, Any], category_id_by_slug: dict[str, int]
) -> int | None:
    """Resolve a Tier-1 ``Category.id`` for a Google Places enriched row.

    Routes via ``map_google_types_to_slug_and_place_type`` (the operator-
    maintained ``app/contrib/google_types_mapping.py`` table). Rows whose
    ``types[]`` don't map to any Tier-1 slug stay ``None`` — that's the
    intended Phase 5 operator-queue behavior per ``google_types_mapping``'s
    docstring.

    Without this resolution + a downstream ``EntityCategory`` row, entities
    do not appear at ``/category/<slug>`` (route filters strictly via
    ``EntityCategory`` join — see
    ``app/api/routes/category_pages.py:_select_entities_for_category``).
    """
    types = row.get("types") or []
    if not types and row.get("primary_type"):
        types = [row["primary_type"]]
    slug, _ = map_google_types_to_slug_and_place_type(list(types))
    if slug is None:
        return None
    return category_id_by_slug.get(slug)


def _ensure_entity_category(
    session: Any, entity_id: str, category_id: int | None
) -> bool:
    """Idempotent EntityCategory upsert on the UPDATE branch.

    The Phase 1D dual-write hook only creates an ``EntityCategory`` on
    fresh ``Provider`` INSERT. The UPDATE branch (re-running the load
    after the fix landed; or matching an existing ``google_place_id``)
    needs to ensure the link exists when ``Provider.category_id`` is
    populated. Returns ``True`` if a new row was inserted.
    """
    if category_id is None:
        return False
    existing = session.scalars(
        select(EntityCategory).where(
            EntityCategory.entity_id == entity_id,
            EntityCategory.category_id == category_id,
        )
    ).first()
    if existing is not None:
        return False
    session.add(
        EntityCategory(
            entity_id=entity_id,
            category_id=category_id,
            is_primary=True,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    return True


def upsert(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Bulk upsert keyed on google_place_id.

    Strategy:
      1. Fetch all existing rows by google_place_id IN (...) — one query.
      2. UPDATE matched rows in place.
      3. INSERT the rest as new rows.
    Both branches stamp `last_google_scraped_at = now()` and
    `updated_at` (auto via onupdate).
    """
    skipped_no_name = 0
    valid_rows: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("display_name"):
            skipped_no_name += 1
            continue
        if not row.get("place_id"):
            skipped_no_name += 1
            continue
        valid_rows.append(row)

    counts: dict[str, int] = {
        "input": len(rows),
        "skipped_no_name": skipped_no_name,
        "inserted": 0,
        "updated": 0,
        "reconcile_skipped_ambiguous": 0,
        "reconcile_merged_geo": 0,
        "category_id_set": 0,
        "category_id_unmapped": 0,
        "entity_category_inserted": 0,
    }

    if not valid_rows:
        return counts

    place_ids = [row["place_id"] for row in valid_rows]
    now = datetime.now(UTC)

    with SessionLocal() as session:
        # One-shot Category lookup for the run — Tier-1 slug -> id table is
        # tiny + immutable during a load. Used by ``_resolve_category_id``
        # to translate Google ``types[]`` to ``Provider.category_id`` so
        # the dual-write hook (or ``_ensure_entity_category`` on UPDATE)
        # creates the EntityCategory link the ``/category/<slug>`` route
        # filters by. Pre-fix, all newly-loaded Providers landed with
        # ``category_id=None`` and never appeared at the route — surfaced
        # by the Phase 5.2 §0 + diagnose_category_id_gap.py finding.
        category_id_by_slug: dict[str, int] = {
            c.slug: c.id for c in session.scalars(select(Category)).all()
        }

        # Phase 1C: match upsert keys on legacy ``google_place_id`` or ENTITY
        # ``locations.google_place_id`` (backfilled Places rows).
        existing_by_pid: dict[str, Provider] = {}
        for p in (
            session.query(Provider)
            .filter(Provider.google_place_id.in_(place_ids))
            .all()
        ):
            if p.google_place_id:
                existing_by_pid[p.google_place_id] = p
        for p, loc_pid in (
            session.query(Provider, Location.google_place_id)
            .join(Entity, Provider.entity_id == Entity.id)
            .join(Location, Location.entity_id == Entity.id)
            .filter(Location.google_place_id.in_(place_ids))
            .all()
        ):
            existing_by_pid[loc_pid] = p

        for row in valid_rows:
            pid = row["place_id"]
            kwargs = row_to_provider_kwargs(row)
            cat_id = _resolve_category_id(row, category_id_by_slug)
            kwargs["category_id"] = cat_id
            if cat_id is not None:
                counts["category_id_set"] += 1
            else:
                counts["category_id_unmapped"] += 1
            if pid in existing_by_pid:
                provider = existing_by_pid[pid]
                payload = enrichment_row_to_entity_payload(row)
                rec = reconcile_hit(session, payload)
                log_ambiguous_reconcile(rec, context=f"places_load update branch place_id={pid}")
                for field, value in kwargs.items():
                    setattr(provider, field, value)
                provider.last_google_scraped_at = now
                sync_provider_entity_from_legacy(session, provider)
                if _ensure_entity_category(session, provider.entity_id, cat_id):
                    counts["entity_category_inserted"] += 1
                if rec.action == "update" and rec.merge_fields:
                    ent = session.get(Entity, provider.entity_id)
                    if ent is not None:
                        if "name" in rec.merge_fields:
                            ent.name = str(rec.merge_fields["name"])[:255]
                        if "description" in rec.merge_fields:
                            ent.description = rec.merge_fields["description"]
                        if "source" in rec.merge_fields:
                            ent.source = str(rec.merge_fields["source"])[:64]
                counts["updated"] += 1
            else:
                payload = enrichment_row_to_entity_payload(row)
                rec = reconcile_hit(session, payload)
                if rec.action == "ambiguous":
                    log_ambiguous_reconcile(rec, context=f"places_load insert branch place_id={pid}")
                    counts["reconcile_skipped_ambiguous"] += 1
                    continue
                if rec.action == "update" and rec.existing_id:
                    prov = session.scalars(
                        select(Provider).where(Provider.entity_id == rec.existing_id).limit(1)
                    ).first()
                    if prov is None:
                        logger.warning(
                            "places_load reconcile update without provider row entity_id=%s",
                            rec.existing_id,
                        )
                        counts["reconcile_skipped_ambiguous"] += 1
                        continue
                    for field, value in kwargs.items():
                        setattr(prov, field, value)
                    prov.last_google_scraped_at = now
                    sync_provider_entity_from_legacy(session, prov)
                    if _ensure_entity_category(session, rec.existing_id, cat_id):
                        counts["entity_category_inserted"] += 1
                    if rec.merge_fields:
                        ent = session.get(Entity, rec.existing_id)
                        if ent is not None:
                            if "name" in rec.merge_fields:
                                ent.name = str(rec.merge_fields["name"])[:255]
                            if "description" in rec.merge_fields:
                                ent.description = rec.merge_fields["description"]
                            if "source" in rec.merge_fields:
                                ent.source = str(rec.merge_fields["source"])[:64]
                    counts["reconcile_merged_geo"] += 1
                    counts["updated"] += 1
                    continue
                slug = derive_provider_slug(session, kwargs["provider_name"])
                provider = Provider(**kwargs, slug=slug, last_google_scraped_at=now)
                session.add(provider)
                create_provider_and_entity(session, provider)
                # Dual-write hook auto-inserts EntityCategory when
                # ``provider.category_id is not None``; count it here for
                # the load summary.
                if cat_id is not None:
                    counts["entity_category_inserted"] += 1
                counts["inserted"] += 1

        session.commit()

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument(
        "--category",
        default=None,
        metavar="SLUG",
        help="Tier-1 taxonomy slug (e.g. eat-drink). Filters enriched rows by "
        "their discovery domain (via DISCOVERY_CATEGORY_TO_DOMAINS) before the "
        "ZIP filter. Omit to load every domain in the enrichment file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + filter only. No DB writes.",
    )
    args = parser.parse_args()

    rows = load_enriched(args.input)
    print(f"[load] enriched rows: {len(rows)}")

    if args.category:
        rows = filter_by_category(rows, args.category)
        print(f"[load] after --category {args.category} filter: {len(rows)} rows")

    kept, drops = filter_by_zip(rows)
    print(f"[load] after ZIP filter: {len(kept)} kept, {sum(drops.values())} dropped")

    if drops:
        print("[load] drop reason breakdown:")
        no_zip = drops.pop("no_zip", 0)
        if no_zip:
            print(f"    no_zip: {no_zip}")
        # Group spillover ZIPs together for readability.
        sorted_drops = sorted(drops.items(), key=lambda kv: -kv[1])
        for reason, count in sorted_drops[:20]:
            print(f"    {reason}: {count}")
        if len(sorted_drops) > 20:
            other = sum(c for _, c in sorted_drops[20:])
            print(f"    other ({len(sorted_drops) - 20} more reasons): {other}")

    if args.dry_run:
        print("[load] dry-run complete; no DB writes")
        return 0

    counts = upsert(kept)
    print()
    print("--- load summary ---")
    print(f"input rows:         {counts['input']}")
    print(f"skipped (no name):  {counts['skipped_no_name']}")
    print(f"inserted (new):     {counts['inserted']}")
    print(f"updated (existing): {counts['updated']}")
    print(f"reconcile skipped (ambiguous): {counts['reconcile_skipped_ambiguous']}")
    print(f"reconcile merged (geo):        {counts['reconcile_merged_geo']}")
    print(f"category_id resolved (Tier 1): {counts['category_id_set']}")
    print(f"category_id unmapped (operator queue): {counts['category_id_unmapped']}")
    print(f"EntityCategory rows inserted:  {counts['entity_category_inserted']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
