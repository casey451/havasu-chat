"""AZDHS Licensed Facilities ArcGIS FeatureServer read-only client (Phase 5.4
follow-up; V1.5 Trust-Signal Verifier Bundle wave 1, ticket #17 per
``outputs/v1_5_carries_inventory.md``).

Synchronous GET against the public ArcGIS Online FeatureServer that mirrors
Arizona Department of Health Services' Salesforce-backed
``Datamart.vw_SF_CC_Active_Providers`` table. No auth. Layer 17 is "Child
Care Facility"; sibling layers cover Hospitals / LTC / Residential / etc.
The same data is what AZ Care Check (``azcarecheck.azdhs.gov``) and the
ADHS GIS Web AppBuilder (``azdhs.gov/gis/adhs-licensed-facilities/``) both
render — the FeatureServer is the structured mirror.

Pagination is standard ArcGIS: ``resultOffset`` + ``resultRecordCount``
(``maxRecordCount=1000`` per service metadata) with explicit
``orderByFields=OBJECTID`` for stable ordering. For Mohave County alone
the dataset is well under 1000 rows so single fetch suffices today, but
the loop handles pagination defensively for future county expansion.

Mohave County records ride the geocoded ``N_*`` mirror per the dataset's
Data FAQ #5 (geocoded, not manual) — we filter on ``N_COUNTY``, not the
raw operator-typed ``COUNTY``. License-expiration is ``null`` on most
post-2019 perpetual-rule records per Data FAQ #1 (don't treat null
expiration as expired).
"""

from __future__ import annotations

import logging
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

AZDHS_CHILDCARE_FEATURE_SERVER: Final[str] = (
    "https://services1.arcgis.com/mpVYz37anSdrK4d8/arcgis/rest/services/"
    "AZLicensedFacilities/FeatureServer/17/query"
)

DEFAULT_PAGE_SIZE: Final[int] = 1000
DEFAULT_COUNTY: Final[str] = "MOHAVE COUNTY"

# Geocoded county field per Data FAQ #5 (operator-typed COUNTY is unreliable).
COUNTY_FIELD: Final[str] = "N_COUNTY"

# Fields we read for verification + provenance.
DEFAULT_OUT_FIELDS: Final[tuple[str, ...]] = (
    "FACILITY_NAME",
    "LICENSE_NUMBER",
    "FACID",
    "TYPE",
    "LICENSE_TYPE",
    "OPERATION_STATUS",
    "license_expiration",
    "License_Effective",
    "Capacity",
    "CAPACITY_INT",
    "Telephone",
    "ADDRESS",
    "CITY",
    "ZIP",
    "N_ADDRESS",
    "N_CITY",
    "N_COUNTY",
    "N_ZIP",
    "N_FULLADDR",
    "N_LAT",
    "N_LON",
    "RUN_DATE",
)


def fetch_azdhs_childcare_for_county(
    client: httpx.Client,
    *,
    county: str = DEFAULT_COUNTY,
    active_only: bool = True,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Return ``attributes`` dict for every AZDHS childcare facility in
    ``county`` (geocoded ``N_COUNTY`` match; pass like ``"MOHAVE COUNTY"``).

    ``active_only=True`` adds ``OPERATION_STATUS='Active'`` to the where
    clause. Defaults match the V1.5 wave 1 verifier scope (Mohave County,
    active facilities only).
    """
    where = f"{COUNTY_FIELD}='{county}'"
    if active_only:
        where = f"{where} AND OPERATION_STATUS='Active'"

    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        params: dict[str, str | int] = {
            "where": where,
            "outFields": ",".join(DEFAULT_OUT_FIELDS),
            "f": "json",
            "returnGeometry": "false",
            "orderByFields": "OBJECTID",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }
        resp = client.get(AZDHS_CHILDCARE_FEATURE_SERVER, params=params, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()

        # ArcGIS returns errors inside a 200 OK body under ``error``.
        err = data.get("error")
        if err:
            raise RuntimeError(
                f"AZDHS FeatureServer error: code={err.get('code')} "
                f"message={err.get('message')} details={err.get('details')}"
            )

        features = data.get("features") or []
        if not features:
            break
        # ArcGIS feature shape is {"attributes": {...}, "geometry": ...}.
        # We requested returnGeometry=false so each feature is just {"attributes": {...}}.
        out.extend(f.get("attributes") or {} for f in features)
        # ``exceededTransferLimit`` true means another page exists. Some
        # services omit the flag; fall back to size-equals-page-size signal.
        if not data.get("exceededTransferLimit") and len(features) < page_size:
            break
        offset += page_size

    logger.info(
        "azdhs_client.fetch_complete",
        extra={"county": county, "active_only": active_only, "total": len(out)},
    )
    return out
