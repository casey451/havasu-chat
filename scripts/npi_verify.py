"""Cross-reference health-wellness-care providers with the CMS NPI registry.

Reads Provider rows tied to category ``health-wellness-care``, fetches all
NPI practitioners/organizations registered in Lake Havasu City, AZ via
:mod:`app.contrib.npi_client`, fuzzy-matches on name, then stamps:

- ``verified = True``
- ``verification_method = 'npi_registry'`` (CHECK-safe)
- ``last_verified_at = now()``
- ``attributes['npi_number']`` (string; no dedicated column exists)

Usage:
    python -m scripts.npi_verify --dry-run
    python -m scripts.npi_verify --limit 20
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

from app.contrib.npi_client import fetch_npi_results_for_city  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import sync_provider_entity_from_legacy  # noqa: E402
from app.db.models import Category, Provider  # noqa: E402

logger = logging.getLogger(__name__)

CITY = "Lake Havasu City"
STATE = "AZ"
CATEGORY_SLUG = "health-wellness-care"
MATCH_THRESHOLD = 86


def _npi_candidate_names(entry: dict[str, Any]) -> list[str]:
    basic = entry.get("basic") or {}
    names: list[str] = []
    et = entry.get("enumeration_type")
    if et == "NPI-2":
        org = (basic.get("organization_name") or "").strip()
        if org:
            names.append(org)
    else:
        parts = [basic.get("first_name"), basic.get("middle_name"), basic.get("last_name")]
        joined = " ".join(str(p).strip() for p in parts if p).strip()
        if joined:
            names.append(joined)
    for block in entry.get("other_names") or []:
        if not isinstance(block, dict):
            continue
        on = (block.get("organization_name") or "").strip()
        if on:
            names.append(on)
        fn = (block.get("first_name") or "").strip()
        ln = (block.get("last_name") or "").strip()
        if fn or ln:
            names.append(f"{fn} {ln}".strip())
    # de-dupe case-insensitively while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return out


def _best_npi_match(provider_name: str, registry: list[dict[str, Any]]) -> tuple[dict[str, Any], int] | None:
    # rapidfuzz 3.x changed the default: no preprocessing. Without an
    # explicit ``processor``, ``fuzz.token_set_ratio`` is case-sensitive
    # AND retains punctuation -- so "Acacia Family Practice" vs
    # "ACACIA FAMILY PRACTICE, INC" scores ~25 instead of ~95. Phase 5.4
    # §3 dispatch surfaced this with 0/20 matches on first dry-run.
    # ``utils.default_process`` lowercases + strips non-alphanumerics +
    # collapses whitespace -- the rapidfuzz 2.x default behavior the
    # threshold (86) was originally tuned against.
    best_entry: dict[str, Any] | None = None
    best_score = 0
    for entry in registry:
        for cand in _npi_candidate_names(entry):
            score = int(
                fuzz.token_set_ratio(
                    provider_name, cand, processor=utils.default_process
                )
            )
            if score > best_score:
                best_score = score
                best_entry = entry
    if best_entry is None or best_score < MATCH_THRESHOLD:
        return None
    return (best_entry, best_score)


def _health_providers_query(db: Session, *, limit: int | None) -> list[Provider]:
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
    registry = fetch_npi_results_for_city(client, city=CITY, state=STATE)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        providers = _health_providers_query(db, limit=limit)
        counts["candidates"] = len(providers)
        for prov in providers:
            existing_npi = (prov.attributes or {}).get("npi_number") if prov.attributes else None
            if prov.verified and prov.verification_method == "npi_registry" and existing_npi:
                counts["skipped_already"] += 1
                continue
            match = _best_npi_match(prov.provider_name, registry)
            if match is None:
                counts["skipped_no_match"] += 1
                continue
            entry, score = match
            npi_num = str(entry.get("number") or "").strip()
            if not npi_num:
                counts["skipped_no_match"] += 1
                continue
            counts["matched"] += 1
            if dry_run:
                logger.info(
                    "npi_verify dry_run match",
                    extra={"provider": prov.provider_name, "npi": npi_num, "score": score},
                )
                continue
            attrs = _merge_attributes(
                prov.attributes if isinstance(prov.attributes, dict) else None,
                {
                    "npi_number": npi_num,
                    "npi_match_score": score,
                },
            )
            prov.attributes = attrs
            prov.verified = True
            prov.verification_method = "npi_registry"
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

    print("--- npi_verify summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
