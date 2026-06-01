"""Google Places (New) fuelOptions fallback for gas prices.

Secondary source for the gas-prices feed (see ``app/contrib/gas_prices.py``).
Used to fill gaps when GasBuddy is blocked or is missing a station we already
know about as a Provider.

The Places API (New) ``fuelOptions`` field returns the most recent posted
price per fuel type for a station, with an ``updateTime``. We reuse the
project's existing ``GOOGLE_PLACES_API_KEY`` and the same Place Details
endpoint already used by ``app/contrib/places_client.py``.

ASCII-only by project convention.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FUEL_FIELD_MASK = "id,displayName,formattedAddress,location,fuelOptions"
DISCOVERY_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,nextPageToken"
)
DISCOVERY_QUERY = "gas stations in Lake Havasu City, AZ"
MAX_DISCOVERY_PAGES = 3
REQUEST_TIMEOUT = 15.0

# Google FuelType enum -> our canonical grade keys. Grades GasBuddy/our UI
# care about; everything else (E85, LPG, SP95, ...) is ignored for V1.
_FUEL_TYPE_TO_GRADE: dict[str, str] = {
    "REGULAR_UNLEADED": "regular",
    "MIDGRADE": "midgrade",
    "PREMIUM": "premium",
    "DIESEL": "diesel",
    "TRUCK_DIESEL": "diesel",
}


def _api_key() -> str:
    return (os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()


def _money_to_float(price: dict[str, Any] | None) -> float | None:
    """Convert a google.type.Money ({units, nanos}) to a float dollar amount."""
    if not isinstance(price, dict):
        return None
    try:
        units = int(price.get("units") or 0)
    except (TypeError, ValueError):
        units = 0
    try:
        nanos = int(price.get("nanos") or 0)
    except (TypeError, ValueError):
        nanos = 0
    if units == 0 and nanos == 0:
        return None
    return round(units + nanos / 1_000_000_000, 3)


def fetch_fuel_options(place_id: str, *, client: httpx.Client | None = None) -> dict[str, Any] | None:
    """Return normalized fuel prices for one Google place_id, or None.

    Shape: ``{"prices": {grade: float}, "update_time": iso_or_None}``.
    Returns None when the key is missing, the request fails, or Google has no
    fuel data for the station.
    """
    key = _api_key()
    if not key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not set")
    if not place_id:
        return None

    owns_client = client is None
    client = client or httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        resp = client.get(
            PLACE_DETAILS_URL.format(place_id=place_id),
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FUEL_FIELD_MASK},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.debug("Places fuelOptions %s -> HTTP %s", place_id, resp.status_code)
            return None
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:  # pragma: no cover - network dependent
        logger.warning("Places fuelOptions failed for %s: %s", place_id, exc)
        return None
    finally:
        if owns_client:
            client.close()

    fuel = body.get("fuelOptions") if isinstance(body, dict) else None
    fuel_prices = fuel.get("fuelPrices") if isinstance(fuel, dict) else None
    if not isinstance(fuel_prices, list):
        return None

    prices: dict[str, float] = {}
    update_time: str | None = None
    for fp in fuel_prices:
        if not isinstance(fp, dict):
            continue
        grade = _FUEL_TYPE_TO_GRADE.get(str(fp.get("type") or ""))
        if not grade:
            continue
        amount = _money_to_float(fp.get("price"))
        if amount is None:
            continue
        # Keep the lowest seen per grade (some stations report multiple).
        if grade not in prices or amount < prices[grade]:
            prices[grade] = amount
        ut = fp.get("updateTime")
        if isinstance(ut, str) and (update_time is None or ut > update_time):
            update_time = ut

    if not prices:
        return None
    return {"prices": prices, "update_time": update_time}


def discover_gas_stations(
    *, client: httpx.Client | None = None, query: str = DISCOVERY_QUERY
) -> list[dict[str, Any]]:
    """Text-search Google Places for LHC gas stations (independent of catalog).

    Returns ``[{place_id, name, address, lat, lng}, ...]``. Lets the Google
    fallback work even when no gas_station Providers exist yet. Raises
    RuntimeError if the key is missing.
    """
    key = _api_key()
    if not key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not set")

    owns_client = client is None
    client = client or httpx.Client(timeout=REQUEST_TIMEOUT)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    page_token: str | None = None
    try:
        for _ in range(MAX_DISCOVERY_PAGES):
            body: dict[str, Any] = {"textQuery": query}
            if page_token:
                body["pageToken"] = page_token
            try:
                resp = client.post(
                    PLACES_TEXT_SEARCH_URL,
                    headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": DISCOVERY_FIELD_MASK},
                    json=body,
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code != 200:
                    logger.warning("Places discovery HTTP %s", resp.status_code)
                    break
                data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:  # pragma: no cover - network
                logger.warning("Places discovery failed: %s", exc)
                break
            for pl in data.get("places") or []:
                if not isinstance(pl, dict):
                    continue
                pid = pl.get("id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                loc = pl.get("location") or {}
                out.append(
                    {
                        "place_id": pid,
                        "name": (pl.get("displayName") or {}).get("text") or "Gas station",
                        "address": pl.get("formattedAddress"),
                        "lat": loc.get("latitude"),
                        "lng": loc.get("longitude"),
                    }
                )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    finally:
        if owns_client:
            client.close()
    logger.info("Places discovery found %d gas stations", len(out))
    return out
