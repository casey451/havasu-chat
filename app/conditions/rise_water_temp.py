"""rise_water_temp — Bureau of Reclamation RISE water temperature at Parker Dam.

source-expansion #15. The flaky Bill Williams USGS gage (09426630) has been
publishing the -100000 sentinel since 5/21. The authoritative "is the lake warm
enough to swim" signal is Reclamation's RISE catalog item **6127** (daily water
temperature in °F at Parker Dam):

    https://data.usbr.gov/rise/api/result?itemId=6127&dateTime[after]=...
    (send ``Accept: application/json``)

This mirrors app/conditions/usgs_water_temp.py: an alternate water-temp source
behind its own feature flag (``FEATURE_FLAG_WATER_TEMP_RISE_6127``). As of v4.6
the CODE DEFAULT is ON — this is the dependable main-lake gauge, so it fetches
without operator action; setting the env var to a falsy value ("false"/"0")
still disables it. When disabled the fetcher returns an empty payload and makes
NO HTTP request; honest-omit hides the tile when there's no reading.

LIVE since 2026-06-29: wired into the fetcher registry
(app/conditions/fetcher.py) and PREFERRED by api_payload over the
sentinel-stuck Bill Williams USGS gage. (This docstring previously described
the pre-wiring inert state — audit doc-rot fix 2026-07-02.)
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
    # v4.6: default ON. RISE item 6127 is the reliable main-lake gauge (the Bill
    # Williams USGS gage is sentinel-stuck), so it fetches without operator
    # action. An explicit falsy env var still disables it.
    return os.environ.get(FEATURE_FLAG_ENV_VAR, "true").lower() in {"true", "1", "yes", "on"}


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


# RISE is a JSON:API service: it 406s on ``Accept: application/json`` and only
# serves ``application/vnd.api+json``. Sending the wrong Accept header silently
# broke the "dependable gauge" — the fetch 406'd and the water tile omitted even
# with the flag ON (v4.5 PR-6, verified with a live fetch on 2026-07-04:
# item 6127 = Parker Dam water temp, °F, returned 80.7°F @ 2026-07-04T07:00).
_ACCEPT = "application/vnd.api+json"


def fetch_rise_water_temp(*, lookback_days: int = 14, client: httpx.Client | None = None) -> dict[str, Any]:
    """Fetch the latest Parker Dam water temp. No HTTP when the feature flag is OFF.

    Retries once on a transport error or an empty/no-reading parse (on top of the
    limiter's status-code retries) so a single transient hiccup doesn't blank the
    water tile for a whole TTL window.
    """
    if not feature_enabled():
        return _empty_payload(feature_on=False)

    after = (date.today() - timedelta(days=lookback_days)).isoformat()
    params = {"itemId": str(PARKER_DAM_WATER_TEMP_ITEM), "dateTime[after]": after}
    headers = {"Accept": _ACCEPT, "User-Agent": "havasu-chat/1.0 source-expansion"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        for attempt in (1, 2):  # retry-once on transport error / empty parse
            try:
                resp = _LIMITER.call_with_retry(
                    lambda: c.get(RESULT_URL, params=params, headers=headers, timeout=20.0)
                )
            except httpx.HTTPError as exc:
                logger.warning("rise_water_temp.transport_error attempt=%s err=%s", attempt, exc)
                if attempt == 2:
                    return _empty_payload(feature_on=True)
                continue
            if resp is None:
                logger.warning("rise_water_temp.fetch_returned_none attempt=%s", attempt)
                if attempt == 2:
                    return _empty_payload(feature_on=True)
                continue
            resp.raise_for_status()
            parsed = parse_result(resp.json())
            if parsed.get("water_temp_f") is not None or attempt == 2:
                return parsed
            logger.warning("rise_water_temp.empty_reading attempt=%s — retrying once", attempt)
        return _empty_payload(feature_on=True)
    finally:
        if owns:
            c.close()


def _utc_today() -> date:  # pragma: no cover - tiny shim for determinism in tests
    return datetime.now(UTC).date()
