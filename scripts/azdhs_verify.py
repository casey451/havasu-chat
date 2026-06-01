"""Cross-reference health-wellness-care providers with the AZDHS Licensed
Facilities (Child Care) registry.

V1.5 Trust-Signal Verifier Bundle wave 1, ticket #17 per
``outputs/v1_5_carries_inventory.md`` (AZDHS childcare-license registry,
cat-12 highest-yield / high-anxiety category). Mirrors the Phase-5.4
:mod:`scripts.npi_verify` pattern verbatim — same CLI shape, same
fuzzy-match + threshold tuning, same ``Provider.verified`` /
``verification_method`` / ``last_verified_at`` / ``attributes`` write
semantics.

Reads Provider rows tied to category ``health-wellness-care``, fetches all
active AZDHS childcare facilities in Mohave County via
:mod:`app.contrib.azdhs_client`, fuzzy-matches on ``provider_name`` vs
``FACILITY_NAME``, then stamps:

- ``verified = True``
- ``verification_method = 'scraper'`` (mirrors the AZ ROC pattern; the
  ``ck_providers_verification_method`` CHECK constraint allowlists
  ``{manual, scraper, owner_confirmed, npi_registry, none, phone_call,
  in_person, web_form_submission, email_confirmation}``. Adding
  ``azdhs_childcare`` as a granular per-source enum would require a CHECK
  migration; deferred — the AZDHS-specific provenance below is sufficient
  to distinguish AZDHS-verified from AZ-ROC-verified providers at query
  time via attributes['azdhs'] presence.)
- ``last_verified_at = now()``
- ``attributes['azdhs']`` = dict with license number + facility id +
  capacity + license expiration + match score + facility status

Match threshold is 86 (same as NPI; see ``_best_azdhs_match`` for the
rapidfuzz tuning rationale).

Usage:
    python -m scripts.azdhs_verify --dry-run
    python -m scripts.azdhs_verify --limit 50
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

from app.contrib.azdhs_client import fetch_azdhs_childcare_for_county  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import sync_provider_entity_from_legacy  # noqa: E402
from app.db.models import Category, Provider  # noqa: E402

logger = logging.getLogger(__name__)

COUNTY = "MOHAVE COUNTY"
CATEGORY_SLUG = "health-wellness-care"
MATCH_THRESHOLD = 86
# 'scraper' is the AZ ROC pattern (Phase 5.3 ship at ``420f893``). The
# AZDHS provenance lives in ``attributes['azdhs']`` so query-time filters
# distinguish AZDHS-verified from AZ-ROC-verified via attribute presence,
# not verification_method enum value. Future schema work could add an
# 'azdhs_childcare' value to the CHECK constraint for finer-grained
# downstream filtering; deferred per the script docstring.
VERIFICATION_METHOD = "scraper"


def _azdhs_candidate_names(entry: dict[str, Any]) -> list[str]:
    """Return de-duplicated candidate display names for a registry row.

    AZDHS layer 17 ``FACILITY_NAME`` is single-string; no organization /
    DBA variants surface in the FeatureServer (those live in the
    Salesforce-backed AZ Care Check UI which we do not crawl). So this
    returns a 1-element list under normal conditions, but the helper
    matches the ``_npi_candidate_names`` shape so the scoring loop in
    ``_best_azdhs_match`` stays parallel.
    """
    name = (entry.get("FACILITY_NAME") or "").strip()
    if not name:
        return []
    return [name]


def _best_azdhs_match(
    provider_name: str,
    registry: list[dict[str, Any]],
) -> tuple[dict[str, Any], int] | None:
    """Pick the highest-scoring AZDHS row for ``provider_name``.

    Uses the same rapidfuzz tuning as :mod:`scripts.npi_verify` per the
    Phase 5.4 §3 dispatch findings:

    1. ``processor=utils.default_process`` — rapidfuzz 3.x dropped the
       implicit lowercase + punctuation strip, so without this the match
       is case-and-punctuation-sensitive and the 86 threshold (tuned
       against rapidfuzz 2.x default-preprocessing behavior) yields
       false negatives.
    2. ``token_sort_ratio`` rather than ``token_set_ratio`` — preserves
       token lengths so short AZDHS facility names don't trivially match
       long DBA-style provider names via the set-subset trick.
    """
    best_entry: dict[str, Any] | None = None
    best_score = 0
    for entry in registry:
        for cand in _azdhs_candidate_names(entry):
            score = int(fuzz.token_sort_ratio(provider_name, cand, processor=utils.default_process))
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


def _azdhs_payload(entry: dict[str, Any], score: int) -> dict[str, Any]:
    """Build the ``Provider.attributes['azdhs']`` payload from a matched row.

    Keeps every field that's useful for downstream display + audit. Strips
    None / empty-string keys to avoid storing empty noise.
    """
    fields = (
        "LICENSE_NUMBER",
        "FACID",
        "TYPE",
        "LICENSE_TYPE",
        "OPERATION_STATUS",
        "license_expiration",
        "License_Effective",
        "Capacity",
        "CAPACITY_INT",
        "N_FULLADDR",
        "RUN_DATE",
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
    registry = fetch_azdhs_childcare_for_county(client, county=COUNTY, active_only=True)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        providers = _health_providers_query(db, limit=limit)
        counts["candidates"] = len(providers)
        for prov in providers:
            # Idempotency gate: a provider is "already AZDHS-verified" iff
            # attributes['azdhs']['LICENSE_NUMBER'] is set. We do NOT also
            # require verification_method=='scraper' because AZ ROC verifier
            # uses the same scraper value but lives at attributes['az_roc']
            # — base the per-verifier idempotency on attribute provenance,
            # not on the shared verification_method enum.
            existing = (prov.attributes or {}).get("azdhs") if prov.attributes else None
            existing_lic = (
                (existing or {}).get("LICENSE_NUMBER") if isinstance(existing, dict) else None
            )
            if existing_lic:
                counts["skipped_already"] += 1
                continue
            match = _best_azdhs_match(prov.provider_name, registry)
            if match is None:
                counts["skipped_no_match"] += 1
                continue
            entry, score = match
            license_num = str(entry.get("LICENSE_NUMBER") or "").strip()
            if not license_num:
                counts["skipped_no_match"] += 1
                continue
            counts["matched"] += 1
            if dry_run:
                logger.info(
                    "azdhs_verify dry_run match",
                    extra={
                        "provider": prov.provider_name,
                        "facility": entry.get("FACILITY_NAME"),
                        "license_number": license_num,
                        "score": score,
                    },
                )
                continue
            attrs = _merge_attributes(
                prov.attributes if isinstance(prov.attributes, dict) else None,
                {"azdhs": _azdhs_payload(entry, score)},
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

    print("--- azdhs_verify summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
