"""CMS NPPES NPI Registry read-only client (Phase 5 health-wellness-care).

Synchronous GET against the public JSON API — no auth. Pagination uses
``skip`` / ``limit`` until ``results`` is empty.
"""

from __future__ import annotations

import logging
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

NPI_REGISTRY_API: Final[str] = "https://npiregistry.cms.hhs.gov/api/"
DEFAULT_VERSION: Final[str] = "2.1"
DEFAULT_PAGE_SIZE: Final[int] = 200


def fetch_npi_results_for_city(
    client: httpx.Client,
    *,
    city: str,
    state: str,
    version: str = DEFAULT_VERSION,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Return every ``results[]`` row for ``city`` + ``state`` (all pages)."""
    out: list[dict[str, Any]] = []
    skip = 0
    while True:
        params: dict[str, str | int] = {
            "version": version,
            "city": city,
            "state": state,
            "limit": page_size,
            "skip": skip,
        }
        resp = client.get(NPI_REGISTRY_API, params=params, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("results") or []
        if not batch:
            break
        out.extend(batch)
        if len(batch) < page_size:
            break
        skip += page_size
    logger.info(
        "npi_client.fetch_complete",
        extra={"city": city, "state": state, "total": len(out)},
    )
    return out
