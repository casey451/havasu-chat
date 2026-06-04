"""rise_water_temp — Bureau of Reclamation RISE water temperature at Parker Dam.

source-expansion #15. The flaky Bill Williams USGS gage (09426630) has been
publishing the -100000 sentinel since 5/21. The authoritative "is the lake warm
enough to swim" signal is Reclamation's RISE catalog item **6127** (daily water
temperature in °F at Parker Dam):

    https://data.usbr.gov/rise/api/result?itemId=6127&dateTime[after]=...
    (send ``Accept: application/json``)

This mirrors app/conditions/usgs_water_temp.py: an alternate water-temp source
behind its own feature flag (``FEATURE_FLAG_WATER_TEMP_RISE_6127``, default OFF).
When OFF the fetcher returns an empty payload and makes NO HTTP request.

INERT build-only module: NOT wired into the live fetcher registry (that
registration is the integration step). NEEDS_PROD_VERIFY: the RISE result
endpoint failed from the research sandbox's datacenter IP — re-verify from prod
(or via the proxy env pattern) before wiring.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "rise_water_temp"
RESULT_URL = "https://data.usbr.gov/rise/api/result"
PARKER_DAM_WATER_TEMP_ITEM = 6127
FEATURE_FLAG_ENV_VAR = "FEATURE_FLAG_WATER_TEMP_RISE_6127"
_LIMITER = SourceLimiter("rise_water_temp", qps=0.5)


def feature_enabled() -> bool:
    return os.environ.get(FEATURE_FLAG_ENV_VAR, "false").lower() in {"true", "1", "yes", "on"}


def _f_to_c(f: float | None) -> float | None:
    if f is None:
        return None
    return round((f - 32.0) * 5.0 / 9.0, 1)


def _empty_payload(*, feature_on: bool) -> dict[str, Any]:
    return {
        "item_id": PARKER_DAM_WATER_TEMP_ITEM,
        "water_temp_f": None,
        "water_temp_c": None,
        "observed_at": None,
        "feature_enabled": feature_on,
        "history": [],
    }


def parse_result(payload: Any) -> dict[str, Any]:
    """Parse a RISE JSON:API result payload; pick the most-recent reading."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return _empty_payload(feature_on=True)

    readings: list[tuple[datetime, float]] = []
    history: list[dict[str, Any]] = []
    for item in data:
        attrs = item.get("attributes") if isinstance(item, dict) else None
        if not isinstance(attrs, dict):
            continue
        result = attrs.get("result")
        ts = attrs.get("dateTime") or attrs.get("date_time")
        if result is None or ts is None:
            continue
        try:
            value = float(result)
            when = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            continue
        readings.append((when, value))
        history.append({"observed_at": str(ts), "value_f": value})

    if not readings:
        return _empty_payload(feature_on=True)

    when, value_f = max(readings, key=lambda r: r[0])
    return {
        "item_id": PARKER_DAM_WATER_TEMP_ITEM,
        "water_temp_f": round(value_f, 1),
        "water_temp_c": _f_to_c(value_f),
        "observed_at": when.isoformat(),
        "feature_enabled": True,
        "history": history,
    }


def fetch_rise_water_temp(*, lookback_days: int = 14, client: httpx.Client | None = None) -> dict[str, Any]:
    """Fetch the latest Parker Dam water temp. No HTTP when the feature flag is OFF."""
    if not feature_enabled():
        return _empty_payload(feature_on=False)

    after = (date.today() - timedelta(days=lookback_days)).isoformat()
    params = {"itemId": str(PARKER_DAM_WATER_TEMP_ITEM), "dateTime[after]": after}
    headers = {"Accept": "application/json", "User-Agent": "havasu-chat/1.0 source-expansion"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(RESULT_URL, params=params, timeout=20.0))
        if resp is None:
            logger.warning("rise_water_temp.fetch_returned_none")
            return _empty_payload(feature_on=True)
        resp.raise_for_status()
        return parse_result(resp.json())
    finally:
        if owns:
            c.close()


def _utc_today() -> date:  # pragma: no cover - tiny shim for determinism in tests
    return datetime.now(UTC).date()
