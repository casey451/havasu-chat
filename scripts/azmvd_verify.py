"""Cross-reference auto-rv-fuel auto dealers with the AZ MVD Valid Dealer Report.

V1.5 Trust-Signal Verifier Bundle wave 3, ticket #20 per
``outputs/v1_5_carries_inventory.md``. Mirrors the wave-1
:mod:`scripts.azdhs_verify` bulk-registry pattern.

§3.1 probe (2026-05-24): uses ADOT's Valid Dealer Report (HTML table published
as ``.xls``) rather than the legacy dealer-locator UI or Playwright.

Usage:
    python -m scripts.azmvd_verify --dry-run
    python -m scripts.azmvd_verify --limit 50
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

from app.contrib.azmvd_client import fetch_azmvd_dealers  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import sync_provider_entity_from_legacy  # noqa: E402
from app.db.models import Category, Provider  # noqa: E402

logger = logging.getLogger(__name__)

CATEGORY_SLUG = "auto-rv-fuel"
MATCH_THRESHOLD = 86
VERIFICATION_METHOD = "scraper"

_DEALER_KEYWORDS = frozenset({
    "auto",
    "motor",
    "cars",
    "automotive",
    "dealer",
    "ford",
    "chevrolet",
    "chevy",
    "toyota",
    "honda",
    "nissan",
    "ram",
    "dodge",
    "jeep",
    "gm",
    "buick",
    "hyundai",
    "kia",
    "rv",
    "motorhome",
    "trailer",
})


def _is_dealer_candidate(prov: Provider) -> bool:
    name_lower = (prov.provider_name or "").lower()
    return any(kw in name_lower for kw in _DEALER_KEYWORDS)


def _dealer_candidate_names(entry: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("business_name", "doing_business_as"):
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


def _best_azmvd_match(
    provider_name: str,
    registry: list[dict[str, Any]],
) -> tuple[dict[str, Any], int] | None:
    best_entry: dict[str, Any] | None = None
    best_score = 0
    for entry in registry:
        for cand in _dealer_candidate_names(entry):
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


def _azmvd_payload(entry: dict[str, Any], score: int) -> dict[str, Any]:
    fields = (
        "dealer_number",
        "business_name",
        "doing_business_as",
        "dealership_license_status",
        "license_type",
        "city",
        "state",
        "zip",
        "street_address",
        "phone",
        "license_renewal_due",
    )
    payload: dict[str, Any] = {"match_score": score}
    for k in fields:
        v = entry.get(k)
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        payload[k] = v
    if entry.get("license_type"):
        payload["dealer_type"] = entry.get("license_type")
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
        "skipped_not_dealer": 0,
    }
    registry = fetch_azmvd_dealers(client)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        providers = _auto_rv_providers_query(db, limit=limit)
        counts["candidates"] = len(providers)
        for prov in providers:
            if not _is_dealer_candidate(prov):
                counts["skipped_not_dealer"] += 1
                continue

            existing = (prov.attributes or {}).get("azmvd") if prov.attributes else None
            existing_dealer = (
                (existing or {}).get("dealer_number") if isinstance(existing, dict) else None
            )
            if existing_dealer:
                counts["skipped_already"] += 1
                continue

            match = _best_azmvd_match(prov.provider_name, registry)
            if match is None:
                counts["skipped_no_match"] += 1
                continue

            entry, score = match
            dealer_number = str(entry.get("dealer_number") or "").strip()
            if not dealer_number:
                counts["skipped_no_match"] += 1
                continue

            counts["matched"] += 1
            if dry_run:
                logger.info(
                    "azmvd_verify dry_run match",
                    extra={
                        "provider": prov.provider_name,
                        "dealer_number": dealer_number,
                        "score": score,
                    },
                )
                continue

            attrs = _merge_attributes(
                prov.attributes if isinstance(prov.attributes, dict) else None,
                {"azmvd": _azmvd_payload(entry, score)},
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

    print("--- azmvd_verify summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
