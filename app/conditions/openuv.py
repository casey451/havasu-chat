"""Open-UV API client — UV index for Lake Havasu (optional, key-gated).

UV index is not available from NWS or AirNow, so it comes from Open-UV
(https://www.openuv.io/). This source is OPTIONAL and gated on the
``OPENUV_API_KEY`` env var: with no key, ``fetch_openuv_index`` returns an empty
payload and makes NO HTTP call, so the conditions cron is safe to call it on
every tick regardless of configuration (mirrors the USGS water-temp gating).

When ``OPENUV_API_KEY`` is set the operator gets a UV tile in the home utility
strip. The free tier is 50 requests/day; the source TTL (1h) keeps usage to ~24
calls/day. The strip degrades gracefully when the key is unset, the API errors,
or the response is unusable.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.conditions.constants import LHC_LAT, LHC_LON

logger = logging.getLogger(__name__)

_OPENUV_URL = "https://api.openuv.io/api/v1/uv"


def _api_key() -> str:
    return (os.environ.get("OPENUV_API_KEY") or "").strip()


def _get(*, timeout: float = 10.0) -> dict[str, Any]:
    """Raw Open-UV GET. Returns {} when no key is configured (no HTTP call).

    Any transport/HTTP/parse error degrades to {} rather than raising. This is
    load-bearing: the orchestrator in ``app/conditions/uv.py`` only reaches the
    keyless EPA fallback when this branch returns empty instead of propagating.
    A raised error here (e.g. a 403 from an exhausted free-tier key or a rate
    limit) would otherwise blank the UV tile entirely instead of falling back.
    """
    key = _api_key()
    if not key:
        return {}
    headers = {"x-access-token": key, "Accept": "application/json"}
    params = {"lat": LHC_LAT, "lng": LHC_LON}
    try:
        with httpx.Client() as client:
            response = client.get(_OPENUV_URL, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("conditions.openuv.fetch_failed", exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _uv_severity(uv: float) -> str:
    """WHO UV-index exposure bands → conditions-strip severity."""
    if uv < 3:
        return "good"
    if uv < 6:
        return "moderate"
    if uv < 8:
        return "warning"
    return "severe"


def _sun_times(result: dict[str, Any]) -> dict[str, str]:
    """Extract true astronomical sunrise/sunset ISO timestamps from a UV result.

    Open-UV's ``/uv`` response carries a ``sun_info.sun_times`` block whose
    ``sunset``/``sunrise`` are real astronomical values (UTC ISO-8601), unlike
    the NWS tonight-period startTime we use as a fallback. We surface these so
    api_payload can render an accurate sunset on the conditions strip.
    """
    sun_info = result.get("sun_info")
    sun_times = sun_info.get("sun_times") if isinstance(sun_info, dict) else None
    if not isinstance(sun_times, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("sunset", "sunrise"):
        val = sun_times.get(key)
        if isinstance(val, str) and val.strip():
            out[f"{key}_iso"] = val.strip()
    return out


def fetch_openuv_index() -> dict[str, Any]:
    """Return ``{"uv_index", "uv_max", "uv_severity", "sunset_iso", "sunrise_iso"}`` or ``{}``.

    Empty when ``OPENUV_API_KEY`` is unset or the response is unusable. Never
    makes an HTTP call without a key, so the cron can call it unconditionally.
    The sun-time keys are present only when Open-UV returns a usable
    ``sun_info.sun_times`` block; api_payload prefers them over the NWS sunset
    approximation when available.
    """
    if not _api_key():
        return {}
    raw = _get()
    result = raw.get("result") if isinstance(raw, dict) else None
    if not isinstance(result, dict):
        return {}
    out: dict[str, Any] = {}
    uv = result.get("uv")
    if isinstance(uv, (int, float)):
        out["uv_index"] = round(float(uv), 1)
        out["uv_severity"] = _uv_severity(float(uv))
    uv_max = result.get("uv_max")
    if isinstance(uv_max, (int, float)):
        out["uv_max"] = round(float(uv_max), 1)
    out.update(_sun_times(result))
    return out
