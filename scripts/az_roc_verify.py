"""Cross-reference home-property-services providers with AZ ROC licenses.

Iterates Provider rows for ``home-property-services``, calls
:func:`app.contrib.az_roc_client.lookup_contractor` (v1 stub returns
``None`` until Playwright/XHR parsing exists), and on match stamps:

- ``verified = True``
- ``verification_method = 'scraper'`` (CHECK-safe; AZ ROC is automated lookup)
- ``last_verified_at = now()``
- ``attributes['az_roc']`` dict with license metadata

Conservative rate limit: **≥ 2.0s** between live HTTP lookups (~0.5 qps).
Lookups are memoized by **normalized provider name** so duplicate rows do not
re-hit the network.

Usage:
    python -m scripts.az_roc_verify --dry-run
    python -m scripts.az_roc_verify --limit 50
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.az_roc_client import AzRocMatch, lookup_contractor  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import sync_provider_entity_from_legacy  # noqa: E402
from app.db.models import Category, Provider  # noqa: E402

logger = logging.getLogger(__name__)

CATEGORY_SLUG = "home-property-services"
MIN_INTERVAL_S = 2.0

# Per kickoff §3 table — AZ ROC issues licenses only for these sub-trades.
# Storage, moving, locksmiths, cleaners, laundry, pest control, etc. are
# NOT licensed by AZ ROC and would just timeout the Playwright row-wait at
# 0 results. Filter them out upfront so the verifier doesn't waste cycles.
AZ_ROC_LICENSED_PRIMARY_TYPES: frozenset[str] = frozenset({
    "plumber",
    "electrician",
    "hvac_contractor",
    "general_contractor",
    "roofing_contractor",
})


def _home_providers_query(db: Session, *, limit: int | None) -> list[Provider]:
    cid = db.scalars(select(Category.id).where(Category.slug == CATEGORY_SLUG)).first()
    q = select(Provider)
    if cid is not None:
        q = q.where(or_(Provider.category_id == cid, Provider.category == CATEGORY_SLUG))
    else:
        q = q.where(Provider.category == CATEGORY_SLUG)
    # Phase 5.3 §3 sub-trade filter — only run AZ ROC lookup for primary_types
    # that AZ ROC actually licenses (kickoff §3 table). Skips storage, cleaners,
    # locksmiths, etc. that would otherwise just timeout at 0 results.
    q = q.where(Provider.google_primary_category.in_(AZ_ROC_LICENSED_PRIMARY_TYPES))
    q = q.order_by(Provider.provider_name)
    if limit is not None:
        q = q.limit(limit)
    return list(db.scalars(q).all())


def _merge_az_roc_attrs(existing: dict[str, Any] | None, roc: AzRocMatch) -> dict[str, Any]:
    merged = dict(existing or {})
    payload = {k: v for k, v in asdict(roc).items() if k != "raw"}
    if roc.raw is not None:
        payload["raw"] = roc.raw
    merged["az_roc"] = payload
    return merged


def run_verify(
    *,
    dry_run: bool,
    limit: int | None,
    client: httpx.Client,
    lookup_fn: Callable[[httpx.Client, str], AzRocMatch | None] = lookup_contractor,
) -> dict[str, int]:
    counts: dict[str, int] = {
        "candidates": 0,
        "matched": 0,
        "skipped_no_match": 0,
        "lookup_cache_hits": 0,
        "lookup_calls": 0,
    }
    by_name: dict[str, AzRocMatch | None] = {}
    last_request_mono: float | None = None
    now = datetime.now(UTC)

    def _throttle() -> None:
        nonlocal last_request_mono
        if last_request_mono is None:
            last_request_mono = time.monotonic()
            return
        elapsed = time.monotonic() - last_request_mono
        if elapsed < MIN_INTERVAL_S:
            time.sleep(MIN_INTERVAL_S - elapsed)
        last_request_mono = time.monotonic()

    with SessionLocal() as db:
        providers = _home_providers_query(db, limit=limit)
        counts["candidates"] = len(providers)
        for prov in providers:
            name_key = prov.provider_name.strip().lower()
            if name_key in by_name:
                m = by_name[name_key]
                counts["lookup_cache_hits"] += 1
            else:
                if not dry_run:
                    _throttle()
                m = lookup_fn(client, prov.provider_name)
                counts["lookup_calls"] += 1
                by_name[name_key] = m
            if m is None:
                counts["skipped_no_match"] += 1
                continue
            lic = (m.license_number or "").strip()
            if not lic:
                counts["skipped_no_match"] += 1
                continue
            counts["matched"] += 1
            if dry_run:
                logger.info(
                    "az_roc_verify dry_run match",
                    extra={"provider": prov.provider_name, "license": lic},
                )
                continue
            prov.attributes = _merge_az_roc_attrs(
                prov.attributes if isinstance(prov.attributes, dict) else None,
                m,
            )
            prov.verified = True
            prov.verification_method = "scraper"
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

    print("--- az_roc_verify summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
