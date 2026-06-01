"""Cross-reference shopping-essentials providers with BBB Lake Havasu City listings.

V1.5 Trust-Signal Verifier Bundle wave 4, ticket #23 per
``outputs/v1_5_carries_inventory.md``. Mirrors the wave-3
:mod:`scripts.azmvd_verify` bulk-registry pattern.

Usage:
    python -m scripts.bbb_verify --dry-run
    python -m scripts.bbb_verify --limit 50
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from typing import Any

import httpx
from rapidfuzz import fuzz, utils
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.bbb_client import fetch_bbb_businesses  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import sync_provider_entity_from_legacy  # noqa: E402
from app.db.models import Category, Provider  # noqa: E402

logger = logging.getLogger(__name__)

CATEGORY_SLUG = "shopping-essentials"
MATCH_THRESHOLD = 86
VERIFICATION_METHOD = "scraper"


def _bbb_candidate_names(entry: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("business_name", "name"):
        val = (entry.get(key) or "").strip()
        if val:
            out.append(val)
    seen: set[str] = set()
    deduped: list[str] = []
    for v in out:
        k = v.lower()
        if k not in seen:
            seen.add(k)
            deduped.append(v)
    return deduped


def _best_bbb_match(
    provider_name: str,
    registry: list[dict[str, Any]],
) -> tuple[dict[str, Any], int] | None:
    best_entry: dict[str, Any] | None = None
    best_score = 0
    for entry in registry:
        for cand in _bbb_candidate_names(entry):
            score = int(fuzz.token_sort_ratio(provider_name, cand, processor=utils.default_process))
            if score > best_score:
                best_score = score
                best_entry = entry
    if best_entry is None or best_score < MATCH_THRESHOLD:
        return None
    return (best_entry, best_score)


def _shopping_providers_query(db: Session, *, limit: int | None) -> list[Provider]:
    cid = db.scalars(select(Category.id).where(Category.slug == CATEGORY_SLUG)).first()
    q = select(Provider)
    if cid is not None:
        q = q.where(or_(Provider.category_id == cid, Provider.category == CATEGORY_SLUG))
    else:
        q = q.where(Provider.category == CATEGORY_SLUG)
    q = q.order_by(Provider.provider_name)
    if limit is not None:
        q = q.limit(limit)
    return db.scalars(q).all()


def _merge_attributes(existing: dict[str, Any] | None, updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing or {})
    merged.update(updates)
    return merged


def _bbb_payload(entry: dict[str, Any], score: int) -> dict[str, Any]:
    fields = (
        "business_id",
        "business_name",
        "accreditation_status",
        "rating",
        "profile_url",
        "category_slug",
    )
    payload: dict[str, Any] = {"match_score": score}
    for k in fields:
        v = entry.get(k)
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        payload[k] = v
    return payload


def run_verify(
    *,
    dry_run: bool,
    limit: int | None,
    client: httpx.Client,
) -> dict[str, int]:
    counts = {
        "candidates": 0,
        "matched": 0,
        "skipped_already": 0,
        "skipped_no_match": 0,
    }
    registry = fetch_bbb_businesses(client)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        providers = _shopping_providers_query(db, limit=limit)
        counts["candidates"] = len(providers)
        for prov in providers:
            existing = (prov.attributes or {}).get("bbb") if prov.attributes else None
            existing_id = (
                (existing or {}).get("business_id") if isinstance(existing, dict) else None
            )
            if existing_id:
                counts["skipped_already"] += 1
                continue

            match = _best_bbb_match(prov.provider_name, registry)
            if match is None:
                counts["skipped_no_match"] += 1
                logger.info(
                    "bbb_verify no_match",
                    extra={
                        "provider": prov.provider_name,
                        "skip_reason": "no_match",
                        "registry_size": len(registry),
                    },
                )
                continue

            entry, score = match
            business_id = str(entry.get("business_id") or "").strip()
            if not business_id:
                counts["skipped_no_match"] += 1
                continue

            counts["matched"] += 1
            if dry_run:
                logger.info(
                    "bbb_verify dry_run match",
                    extra={
                        "provider": prov.provider_name,
                        "business_id": business_id,
                        "name_score": score,
                    },
                )
                continue

            attrs = _merge_attributes(
                prov.attributes if isinstance(prov.attributes, dict) else None,
                {"bbb": _bbb_payload(entry, score)},
            )
            prov.attributes = attrs
            prov.verified = True
            prov.verification_method = VERIFICATION_METHOD
            prov.last_verified_at = now
            sync_provider_entity_from_legacy(db, prov)

        if not dry_run:
            db.commit()
    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None, metavar="N")
    args = p.parse_args()

    with httpx.Client() as client:
        counts = run_verify(dry_run=args.dry_run, limit=args.limit, client=client)

    print("--- bbb_verify summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
