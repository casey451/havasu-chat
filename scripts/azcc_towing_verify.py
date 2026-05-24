"""Cross-reference auto-rv-fuel towing carriers with AZCC eCorp business search.

V1.5 Trust-Signal Verifier Bundle wave 3, ticket #21 per
``outputs/v1_5_carries_inventory.md``. Mirrors the wave-1
:mod:`scripts.azdhs_verify` pattern — same CLI shape, same fuzzy-match
threshold, same ``Provider.verified`` / ``verification_method`` /
``last_verified_at`` / ``attributes`` write semantics.

Towing carriers live under category ``auto-rv-fuel`` (no separate towing slug).
A sub-trade keyword filter narrows candidates before AZCC lookup.

Usage:
    python -m scripts.azcc_towing_verify --dry-run
    python -m scripts.azcc_towing_verify --limit 50
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

from app.contrib.azcc_towing_client import fetch_azcc_entity_search  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import sync_provider_entity_from_legacy  # noqa: E402
from app.db.models import Category, Provider  # noqa: E402

logger = logging.getLogger(__name__)

CATEGORY_SLUG = "auto-rv-fuel"
MATCH_THRESHOLD = 86
VERIFICATION_METHOD = "scraper"

_TOWING_KEYWORDS = frozenset({
    "towing",
    "tow",
    "wrecker",
    "roadside",
    "recovery",
})


def _is_towing_candidate(prov: Provider) -> bool:
    name_lower = (prov.provider_name or "").lower()
    return any(kw in name_lower for kw in _TOWING_KEYWORDS)


def _azcc_candidate_names(entry: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("entity_name", "businessName", "entityName", "name"):
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


def _best_azcc_match(
    provider_name: str,
    registry: list[dict[str, Any]],
) -> tuple[dict[str, Any], int] | None:
    best_entry: dict[str, Any] | None = None
    best_score = 0
    for entry in registry:
        for cand in _azcc_candidate_names(entry):
            score = int(
                fuzz.token_sort_ratio(
                    provider_name, cand, processor=utils.default_process
                )
            )
            if score > best_score:
                best_score = score
                best_entry = entry
    if best_entry is None or best_score < MATCH_THRESHOLD:
        return None
    return (best_entry, best_score)


def _auto_rv_providers_query(db: Session, *, limit: int | None) -> list[Provider]:
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


def _azcc_payload(entry: dict[str, Any], score: int) -> dict[str, Any]:
    fields = (
        "corp_id",
        "entity_name",
        "businessName",
        "entityName",
        "status",
        "entityStatus",
        "entityType",
        "county",
        "formationDate",
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
        "skipped_not_towing": 0,
    }
    now = datetime.now(UTC)
    with SessionLocal() as db:
        providers = _auto_rv_providers_query(db, limit=limit)
        counts["candidates"] = len(providers)
        for prov in providers:
            if not _is_towing_candidate(prov):
                counts["skipped_not_towing"] += 1
                continue

            existing = (prov.attributes or {}).get("azcc") if prov.attributes else None
            existing_corp = (existing or {}).get("corp_id") if isinstance(existing, dict) else None
            if existing_corp:
                counts["skipped_already"] += 1
                continue

            registry = fetch_azcc_entity_search(client, name=prov.provider_name)
            match = _best_azcc_match(prov.provider_name, registry)
            if match is None:
                counts["skipped_no_match"] += 1
                logger.info(
                    "azcc_towing_verify no_match",
                    extra={
                        "provider": prov.provider_name,
                        "skip_reason": "no_match",
                        "registry_size": len(registry),
                    },
                )
                continue

            entry, score = match
            corp_id = str(entry.get("corp_id") or "").strip()
            if not corp_id:
                counts["skipped_no_match"] += 1
                continue

            counts["matched"] += 1
            if dry_run:
                logger.info(
                    "azcc_towing_verify dry_run match",
                    extra={
                        "provider": prov.provider_name,
                        "corp_id": corp_id,
                        "name_score": score,
                    },
                )
                continue

            attrs = _merge_attributes(
                prov.attributes if isinstance(prov.attributes, dict) else None,
                {"azcc": _azcc_payload(entry, score)},
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

    print("--- azcc_towing_verify summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
