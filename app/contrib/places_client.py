"""Google Places API (New) client for provider enrichment (Phase 5.2)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from rapidfuzz.distance import Levenshtein

logger = logging.getLogger(__name__)

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Cost control: only fields required for Tier 2 / operator review (no wildcard).
PLACES_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.internationalPhoneNumber,"
    "places.regularOpeningHours,places.websiteUri,places.types,places.location,places.businessStatus"
)


def _naive_utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _places_api_key() -> str:
    return (os.getenv("GOOGLE_PLACES_API_KEY") or "").strip()


@dataclass
class PlacesLookupResult:
    status: str  # "success" | "no_match" | "low_confidence" | "error" | "not_attempted"
    place_id: str | None = None
    display_name: str | None = None
    formatted_address: str | None = None
    phone: str | None = None
    website_uri: str | None = None
    regular_opening_hours: dict[str, Any] | None = None
    types: list[str] | None = None
    location: dict[str, Any] | None = None
    business_status: str | None = None
    raw_response: dict[str, Any] | None = None
    error_message: str | None = None
    queried_at: datetime = field(default_factory=_naive_utc_now)


def _display_name_text(place: dict[str, Any]) -> str:
    dn = place.get("displayName")
    if isinstance(dn, dict):
        t = dn.get("text")
        if isinstance(t, str):
            return t.strip()
    if isinstance(dn, str):
        return dn.strip()
    return ""


def _place_to_flat(place: dict[str, Any]) -> dict[str, Any]:
    """Shallow-normalized dict for storage (avoid logging elsewhere)."""
    return dict(place)


def lookup_provider(
    name: str,
    location_context: str = "Lake Havasu City, AZ",
    *,
    timeout_seconds: float = 15.0,
) -> PlacesLookupResult:
    """Query Places (New) Text Search for a provider submission."""
    now = _naive_utc_now()
    key = _places_api_key()
    if not key:
        logger.warning("places_client: GOOGLE_PLACES_API_KEY unset; skipping lookup")
        return PlacesLookupResult(status="not_attempted", queried_at=now)

    qname = (name or "").strip()
    if not qname:
        return PlacesLookupResult(
            status="no_match",
            raw_response={"places": [], "reason": "empty_name"},
            queried_at=now,
        )

    text_query = f"{qname} {location_context}".strip()
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": PLACES_FIELD_MASK,
    }
    body = {"textQuery": text_query}

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            r = client.post(PLACES_SEARCH_URL, headers=headers, json=body)
    except httpx.TimeoutException:
        return PlacesLookupResult(
            status="error",
            error_message="timeout",
            queried_at=_naive_utc_now(),
        )
    except httpx.RequestError as e:
        return PlacesLookupResult(
            status="error",
            error_message=f"request_error:{e!s}",
            queried_at=_naive_utc_now(),
        )

    try:
        data = r.json()
    except Exception:
        return PlacesLookupResult(
            status="error",
            error_message=f"invalid_json_http_{r.status_code}",
            queried_at=_naive_utc_now(),
        )

    if r.status_code < 200 or r.status_code >= 300:
        return PlacesLookupResult(
            status="error",
            error_message=f"http_{r.status_code}",
            raw_response=data if isinstance(data, dict) else None,
            queried_at=_naive_utc_now(),
        )

    places = data.get("places") if isinstance(data, dict) else None
    if not isinstance(places, list) or len(places) == 0:
        return PlacesLookupResult(
            status="no_match",
            raw_response=data if isinstance(data, dict) else {"places": []},
            queried_at=_naive_utc_now(),
        )

    first = places[0]
    if not isinstance(first, dict):
        return PlacesLookupResult(
            status="error",
            error_message="invalid_place_shape",
            queried_at=_naive_utc_now(),
        )

    disp = _display_name_text(first)
    dist = Levenshtein.normalized_distance(qname.lower(), disp.lower()) if disp else 1.0
    conf_ok = dist < 0.3
    status = "success" if conf_ok else "low_confidence"

    pid = first.get("id")
    if isinstance(pid, str):
        place_id = pid
    else:
        place_id = None

    phone = first.get("internationalPhoneNumber")
    if not isinstance(phone, str):
        phone = None
    website = first.get("websiteUri")
    if not isinstance(website, str):
        website = None
    addr = first.get("formattedAddress")
    if not isinstance(addr, str):
        addr = None
    types = first.get("types")
    if not isinstance(types, list):
        types = None
    else:
        types = [str(t) for t in types if isinstance(t, str)]
    loc = first.get("location")
    if not isinstance(loc, dict):
        loc = None
    hours = first.get("regularOpeningHours")
    if not isinstance(hours, dict):
        hours = None
    biz = first.get("businessStatus")
    if not isinstance(biz, str):
        biz = None

    return PlacesLookupResult(
        status=status,
        place_id=place_id,
        display_name=disp or None,
        formatted_address=addr,
        phone=phone,
        website_uri=website,
        regular_opening_hours=hours,
        types=types,
        location=loc,
        business_status=biz,
        raw_response=data if isinstance(data, dict) else _place_to_flat(first),
        queried_at=_naive_utc_now(),
    )
