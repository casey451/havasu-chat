"""Cross-reference lodging-vacation-rentals providers with the City of Lake
Havasu City public Vacation Rentals registry.

V1.5 Trust-Signal Verifier Bundle wave 1, ticket #19 per
``outputs/v1_5_carries_inventory.md`` (AZRE vacation-rental license
registry; cat-10). Mirrors the Phase-5.4 :mod:`scripts.npi_verify` +
sibling :mod:`scripts.azdhs_verify` pattern: same CLI shape, same
threshold tuning, same ``Provider.verified`` /
``verification_method`` / ``last_verified_at`` / ``attributes`` write
semantics.

**Match key is ADDRESS**, not business name. Vacation rentals don't
have brand-style business names in the City registry — they're
identified by the operator-typed street address (``USER_FormattedAddress``)
+ parcel number (``USER_Parcel_Number``). Catalog providers are
matched on ``Provider.address`` (or ``address_normalized`` if
populated) vs the registry's ``Match_addr`` / ``USER_FormattedAddress``
via rapidfuzz token_sort_ratio + processor=default_process. Catalog
providers without an ``address`` are skipped with ``skipped_no_address``.

Threshold is 86 (parallel to NPI + AZDHS — same rapidfuzz tuning
rationale; address-matching is slightly less forgiving than name
matching because street/road/dr/ave variants matter, but the
default_process normalization handles those cases).

Reads Provider rows tied to category ``lodging-vacation-rentals``,
fetches all match-confirmed LHC vacation rentals via
:mod:`app.contrib.azre_client`, fuzzy-matches on ``provider.address``
vs ``USER_FormattedAddress``, then stamps:

- ``verified = True``
- ``verification_method = 'scraper'`` (mirrors the AZ ROC + AZDHS
  pattern; the CHECK constraint allowlist does not include a granular
  enum value for AZRE / LHC City verifiers; the per-source provenance
  in ``attributes['azre_lhc']`` distinguishes this from sibling
  verifiers at query time).
- ``last_verified_at = now()``
- ``attributes['azre_lhc']`` = dict with parcel #, formatted address,
  business postal, business city, status, score, AccountNumber, +
  match_score. Intentionally EXCLUDES the three USER_Emergency_Contact*
  fields per the :mod:`app.contrib.azre_client` PII boundary.

Usage:
    python -m scripts.azre_verify --dry-run
    python -m scripts.azre_verify --limit 50
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

from app.contrib.azre_client import fetch_azre_lhc_vacation_rentals  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import sync_provider_entity_from_legacy  # noqa: E402
from app.db.models import Category, Provider  # noqa: E402

logger = logging.getLogger(__name__)

CATEGORY_SLUG = "lodging-vacation-rentals"
MATCH_THRESHOLD = 86
VERIFICATION_METHOD = "scraper"


def _azre_candidate_addresses(entry: dict[str, Any]) -> list[str]:
    """Return de-duplicated candidate address strings for a registry row.

    The registry has two address-shaped fields: ``USER_FormattedAddress``
    (operator-typed, may have trailing whitespace) and ``Match_addr``
    (City geocoder output; canonical form). Both are tried so the
    fuzzy match has the best chance of hitting against operator-typed
    catalog addresses that may differ slightly (e.g. "2851 Saratoga Ave"
    vs "2851 SARATOGA AVE").
    """
    out: list[str] = []
    for k in ("USER_FormattedAddress", "Match_addr"):
        v = (entry.get(k) or "").strip()
        if v:
            out.append(v)
    # de-dupe case-insensitively while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for v in out:
        k = v.lower()
        if k not in seen:
            seen.add(k)
            deduped.append(v)
    return deduped


def _best_azre_match(
    provider_address: str,
    registry: list[dict[str, Any]],
) -> tuple[dict[str, Any], int] | None:
    """Pick the highest-scoring AZRE-LHC row for ``provider_address``.

    Uses the same rapidfuzz tuning as NPI + AZDHS per the Phase 5.4 §3
    dispatch findings: ``processor=utils.default_process`` for
    case-and-punctuation-insensitive matching + ``token_sort_ratio``
    to avoid the subset trap on short-address-vs-long-address matches.
    """
    best_entry: dict[str, Any] | None = None
    best_score = 0
    for entry in registry:
        for cand in _azre_candidate_addresses(entry):
            score = int(
                fuzz.token_sort_ratio(
                    provider_address, cand, processor=utils.default_process
                )
            )
            if score > best_score:
                best_score = score
                best_entry = entry
    if best_entry is None or best_score < MATCH_THRESHOLD:
        return None
    return (best_entry, best_score)


def _lodging_providers_query(db: Session, *, limit: int | None) -> list[Provider]:
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


def _azre_payload(entry: dict[str, Any], score: int) -> dict[str, Any]:
    """Build the ``Provider.attributes['azre_lhc']`` payload from a matched row.

    Per :mod:`app.contrib.azre_client` PII boundary, intentionally
    EXCLUDES the three USER_Emergency_Contact* fields even though they
    are present in the registry feature. Trust signal lives in the
    regulatory fields (Status, Parcel #, Address); contact info is
    not needed to attach "verified registered rental".
    """
    fields = (
        "ObjectID",
        "Status",
        "USER_Parcel_Number",
        "USER_FormattedAddress",
        "Match_addr",
        "USER_Business_State",
        "USER_Business_Postal",
        "BusinessCity",
        "AccountNumber",
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
        "skipped_no_address": 0,
    }
    registry = fetch_azre_lhc_vacation_rentals(client, matched_only=True)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        providers = _lodging_providers_query(db, limit=limit)
        counts["candidates"] = len(providers)
        for prov in providers:
            # Idempotency gate: same shape as AZDHS — base on AZRE-specific
            # provenance key presence (attributes['azre_lhc']['USER_Parcel_Number'])
            # rather than verification_method enum match, because the 'scraper'
            # value is shared with AZ ROC + AZDHS verifiers.
            existing = (prov.attributes or {}).get("azre_lhc") if prov.attributes else None
            existing_parcel = (existing or {}).get("USER_Parcel_Number") if isinstance(existing, dict) else None
            if existing_parcel:
                counts["skipped_already"] += 1
                continue

            # Provider.address is the raw operator-typed / Google-Places-imported
            # street address. (address_normalized lives on Entity, not Provider —
            # if we ever want the normalized form we'd join via Provider.entity_id;
            # for V1.5 wave 1 the raw address suffices since rapidfuzz with
            # default_process handles casing + punctuation + whitespace.)
            addr = (prov.address or "").strip()
            if not addr:
                counts["skipped_no_address"] += 1
                continue

            match = _best_azre_match(addr, registry)
            if match is None:
                counts["skipped_no_match"] += 1
                continue
            entry, score = match
            parcel = str(entry.get("USER_Parcel_Number") or "").strip()
            if not parcel:
                counts["skipped_no_match"] += 1
                continue
            counts["matched"] += 1
            if dry_run:
                logger.info(
                    "azre_verify dry_run match",
                    extra={
                        "provider": prov.provider_name,
                        "address": addr,
                        "parcel": parcel,
                        "score": score,
                    },
                )
                continue
            attrs = _merge_attributes(
                prov.attributes if isinstance(prov.attributes, dict) else None,
                {"azre_lhc": _azre_payload(entry, score)},
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

    print("--- azre_verify summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
