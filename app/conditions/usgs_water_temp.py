"""USGS OGC API water-temperature fetcher -- Bill Williams at Lake Havasu, 09426630 (V1.5 wave 3).

The primary USGS source (09427500) tracked at app/conditions/usgs.py reports
only gauge height (00065) + storage (00054); it does NOT publish water
temperature. USGS station 09426630 ("Bill Williams River at Lake Havasu, abv
HWY-95, AZ") is the nearest station that reports water temperature via
parameter_code=00010 (degrees Celsius only).

Per V1.5 wave-3 recon banked at outputs/session_handoff_2026-05-23_v11.md
section 3:

- Period of record: 2023-05-23 to 2026-05-21 (~3yr; recent reading is a
  sentinel).
- The station reports a -100000 SENTINEL VALUE when the gage is malfunctioning
  or data is unavailable. The fetcher filters this sentinel out and reports
  water_temp_c=None / water_temp_f=None in that case (history entry is still
  emitted with is_sentinel=True for audit visibility).
- Geographic positioning: tributary backwater of Lake Havasu at HWY-95,
  ~25mi south of Lake Havasu City. Thermal regime diverges from the
  Colorado-mainstem 09427500 gage.
- Feature-flag gated via FEATURE_FLAG_WATER_TEMP_GAGE_09426630 (default OFF).
  When OFF, fetcher returns an empty payload signal and does NOT make any
  HTTP request.

INTEGRATION STATUS: this module is NOT wired into the SourceLimiter chain
in app/conditions/fetcher.py / constants.py SOURCE_KEYS / TTL_BY_SOURCE in
v11. Wiring is a separate next-session 1-line addition to those three places
when the feature is ready for prod activation. Until then, the cron does not
call this fetcher and api_payload.py does not read its cache row, so prod
behavior is unchanged regardless of whether the env flag is on or off.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

_USGS_LIMITER = SourceLimiter("usgs_water_temp", qps=0.5)
_OGC_BASE = "https://api.waterdata.usgs.gov/ogcapi/v0"
_OGC_COLLECTION = "latest-continuous"

# USGS missing-data sentinel for instrument-reported instantaneous values.
# When the gage is offline or returns no valid measurement, USGS publishes
# this as a placeholder in the time series. Treat as None / not-available.
_USGS_MISSING_SENTINEL = -100000.0

FEATURE_FLAG_ENV_VAR = "FEATURE_FLAG_WATER_TEMP_GAGE_09426630"


def feature_enabled() -> bool:
    """True iff FEATURE_FLAG_WATER_TEMP_GAGE_09426630 is set to a truthy value."""
    return os.environ.get(FEATURE_FLAG_ENV_VAR, "false").lower() in {
        "true",
        "1",
        "yes",
        "on",
    }


def _is_sentinel(value: float) -> bool:
    """USGS publishes -100000 as the missing-data placeholder for instantaneous values."""
    return abs(value - _USGS_MISSING_SENTINEL) < 1.0


def _c_to_f(celsius: float | None) -> float | None:
    if celsius is None:
        return None
    return celsius * 9.0 / 5.0 + 32.0


def _empty_payload(site: str, *, feature_on: bool) -> dict[str, Any]:
    return {
        "site": site,
        "water_temp_c": None,
        "water_temp_f": None,
        "observed_at": None,
        "feature_enabled": feature_on,
        "history": [],
    }


def fetch_usgs_water_temp_09426630() -> dict[str, Any]:
    """Fetch latest water temperature from USGS station 09426630.

    Returns a dict with:

    - site: station code (default 09426630; overridable via USGS_WATER_TEMP_SITE)
    - water_temp_c: latest temperature reading in degrees C, or None if
      unavailable, sentinel-valued, or feature disabled
    - water_temp_f: same value converted to degrees F, or None
    - observed_at: ISO timestamp of the reading, or None
    - feature_enabled: bool -- copy of the flag at fetch time (for audit /
      downstream UI gating)
    - history: list of dicts (parameter_code + value + observed_at +
      is_sentinel)

    When FEATURE_FLAG_WATER_TEMP_GAGE_09426630 is OFF (default), returns an
    empty payload with feature_enabled=False and makes NO HTTP request. This
    is the safe default for prod until the operator flips the flag.
    """
    site = os.environ.get("USGS_WATER_TEMP_SITE", "09426630")

    if not feature_enabled():
        return _empty_payload(site, feature_on=False)

    parameter_code = "00010"  # Water temperature, degrees Celsius

    water_temp_c: float | None = None
    observed_at: str | None = None
    history: list[dict[str, Any]] = []

    with httpx.Client(timeout=15.0) as client:

        def _inner(c: httpx.Client = client) -> httpx.Response:
            return c.get(
                f"{_OGC_BASE}/collections/{_OGC_COLLECTION}/items",
                params={
                    "monitoring_location_id": f"USGS-{site}",
                    "parameter_code": parameter_code,
                    "limit": 2,
                },
            )

        response = _USGS_LIMITER.call_with_retry(_inner)
        if response is None:
            logger.warning(
                "usgs_water_temp.fetch_returned_none site=%s", site
            )
            return _empty_payload(site, feature_on=True)
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features") or []
        for feat in features:
            if not isinstance(feat, dict):
                continue
            props = feat.get("properties") or {}
            value = props.get("value")
            ts = props.get("datetime") or props.get("time")
            if value is None:
                continue
            try:
                val_f = float(value)
            except (TypeError, ValueError):
                continue
            sentinel = _is_sentinel(val_f)
            history.append(
                {
                    "parameter_code": parameter_code,
                    "value": None if sentinel else val_f,
                    "observed_at": ts,
                    "is_sentinel": sentinel,
                }
            )
            if water_temp_c is None and not sentinel:
                water_temp_c = val_f
                observed_at = ts

    return {
        "site": site,
        "water_temp_c": water_temp_c,
        "water_temp_f": _c_to_f(water_temp_c),
        "observed_at": observed_at,
        "feature_enabled": True,
        "history": history,
    }
