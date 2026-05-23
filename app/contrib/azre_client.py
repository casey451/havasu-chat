"""Lake Havasu City Vacation Rentals public MapService client (V1.5
Trust-Signal Verifier Bundle wave 1, ticket #19).

Arizona has NO state-level short-term-rental registry — A.R.S. § 9-500.39
(SB1168, 2022; superseded HB2672) delegates STR registration to cities /
counties. The Arizona Department of Real Estate (ADRE, ``azre.gov``)
regulates licensed agents / brokers / developers only; ``azre.gov/srtu``
404s. So this client targets the **City of Lake Havasu City** public
vacation rental registry, which is the substantive jurisdiction for
LHC-area rentals.

Endpoint discovered 2026-05-23 via:

1. ArcGIS Experience config: ``https://www.arcgis.com/sharing/rest/content/items/972198b0ad944f5f8550754d12f08d31/data?f=json``
2. → references Web Map ``6cfd1497bb154ac28e58323fe2bbbdf9`` on ``LHC.maps.arcgis.com``
3. → Web Map data includes ``operationalLayers[]`` with the
   ``VacationRentalsPublicMapService/MapServer`` URL below
4. → Layer 1 ("Vacation Rentals") is the actual records layer

Per City Code Ch. 5.20 (effective 2023-03-01): all STR permits in LHC
require $250/yr registration. City FAQ at ``lhcaz.gov/172/Vacation-Rentals``:
"The information provided on the registration application will be made
public." Records carry permit-equivalent fields (Status, Parcel #,
Formatted Address) plus operator-supplied emergency-contact fields.

**PII boundary** — the registry exposes ``USER_Emergency_Contact``
(person name) + ``USER_Emergency_Contact_Phone`` + ``USER_Emergency_Contact_Email``.
These are declared public by the City but they are not needed for a
trust-signal verifier and we do NOT store them. ``DEFAULT_OUT_FIELDS``
below intentionally excludes the three emergency-contact fields; the
verifier only needs the regulatory-record fields (Status, Parcel #,
Address) to attach a "verified registered rental" signal.

Endpoint is hosted by the city directly; no rate limit headers
observed; standard ArcGIS pagination via ``resultOffset`` +
``resultRecordCount`` (``maxRecordCount=2000`` per service metadata).
For LHC-only the dataset is currently 545 active rentals so two pages
of fetch suffices today; the loop handles pagination defensively for
future growth.
"""

from __future__ import annotations

import logging
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

AZRE_LHC_VACATION_RENTAL_FEATURE_SERVER: Final[str] = (
    "https://lhcgis.lhcaz.gov/server/rest/services/VacationRentals/"
    "VacationRentalsPublicMapService/MapServer/1/query"
)

DEFAULT_PAGE_SIZE: Final[int] = 2000

# Fields we read for verification + provenance. Intentionally EXCLUDES the
# three USER_Emergency_Contact* fields per the module docstring PII boundary.
DEFAULT_OUT_FIELDS: Final[tuple[str, ...]] = (
    "ObjectID",
    "Status",
    "Score",
    "Match_addr",
    "USER_Parcel_Number",
    "USER_FormattedAddress",
    "USER_Business_State",
    "USER_Business_Postal",
    "BusinessCity",
    "AccountNumber",
)


def fetch_azre_lhc_vacation_rentals(
    client: httpx.Client,
    *,
    matched_only: bool = True,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Return ``attributes`` dict for every City of Lake Havasu City
    registered vacation rental.

    ``matched_only=True`` adds ``Status='M'`` to the where clause —
    'M' is the City's geocode-Match status code (per sample data, rows
    with Score=100 + Status='M' are confirmed-address registrations).
    Defaults match V1.5 wave 1 scope (LHC city + match-confirmed only).

    Returns an empty list on transport error or non-JSON response —
    parallels :func:`app.contrib.azdhs_client.fetch_azdhs_childcare_for_county`
    fail-soft semantics so the verifier can record skipped_no_match
    rather than crashing the whole pass.
    """
    where = "Status='M'" if matched_only else "1=1"

    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        params: dict[str, str | int] = {
            "where": where,
            "outFields": ",".join(DEFAULT_OUT_FIELDS),
            "f": "json",
            "returnGeometry": "false",
            "orderByFields": "ObjectID",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }
        resp = client.get(AZRE_LHC_VACATION_RENTAL_FEATURE_SERVER, params=params, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()

        # ArcGIS returns errors inside a 200 OK body under ``error``.
        err = data.get("error")
        if err:
            raise RuntimeError(
                f"AZRE LHC FeatureServer error: code={err.get('code')} "
                f"message={err.get('message')} details={err.get('details')}"
            )

        features = data.get("features") or []
        if not features:
            break
        out.extend(f.get("attributes") or {} for f in features)
        # ``exceededTransferLimit`` true means another page exists.
        if not data.get("exceededTransferLimit") and len(features) < page_size:
            break
        offset += page_size

    logger.info(
        "azre_client.fetch_complete",
        extra={"matched_only": matched_only, "total": len(out)},
    )
    return out
