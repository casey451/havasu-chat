"""Filter and load enriched Google Places rows into the providers table.

Phase 5 of the LHC business pull. Reads
scripts/output/places_pull/enrichment_enriched.jsonl, filters by LHC ZIP
codes per the locked list (86403/86404/86405/86406), and upserts each
survivor into the providers table.

Upsert key: `google_place_id`. Matches existing rows by Place ID and
UPDATEs them; inserts new rows otherwise. Stamps `last_google_scraped_at`
on every write.

Idempotent — re-running on the same input produces the same DB state.

Usage:
    python -m scripts.places_load --dry-run   # parse + filter only, no DB writes
    python -m scripts.places_load             # filter + load

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

from app.contrib.google_places_scraper import enrichment_row_to_entity_payload  # noqa: E402
from app.contrib.ingest_reconciler import (  # noqa: E402
    log_ambiguous_reconcile,
    reconcile_hit,
)
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import (  # noqa: E402
    create_provider_and_entity,
    sync_provider_entity_from_legacy,
)
from app.db.models import Entity, Location, Provider  # noqa: E402
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

    counts = {
        "input": len(rows),
        "skipped_no_name": skipped_no_name,
        "inserted": 0,
        "updated": 0,
        "reconcile_skipped_ambiguous": 0,
        "reconcile_merged_geo": 0,
    }

    if not valid_rows:
        return counts

    place_ids = [row["place_id"] for row in valid_rows]
    now = datetime.now(UTC)

    with SessionLocal() as session:
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
            if pid in existing_by_pid:
                provider = existing_by_pid[pid]
                payload = enrichment_row_to_entity_payload(row)
                rec = reconcile_hit(session, payload)
                log_ambiguous_reconcile(rec, context=f"places_load update branch place_id={pid}")
                for field, value in kwargs.items():
                    setattr(provider, field, value)
                provider.last_google_scraped_at = now
                sync_provider_entity_from_legacy(session, provider)
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
                counts["inserted"] += 1

        session.commit()

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + filter only. No DB writes.",
    )
    args = parser.parse_args()

    rows = load_enriched(args.input)
    print(f"[load] enriched rows: {len(rows)}")

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
