"""EPA Envirofacts UV-index client — keyless UV fallback for Lake Havasu.

UV index is not available from NWS (the gridpoint payload carries wind/heat
fields but no UV) or AirNow, so the *primary* UV source is the key-gated Open-UV
API (``app/conditions/openuv.py``). When ``OPENUV_API_KEY`` is unset we still
want a UV tile, so this module provides a **keyless** fallback: the EPA's
Envirofacts hourly UV-index forecast, served free with no auth by ZIP code:

    https://data.epa.gov/efservice/getEnvirofactsUVHOURLY/ZIP/<zip>/JSON

Each record is one hour of the day's forecast, e.g.::

    {"ORDER": 5, "ZIP": "86403", "DATE_TIME": "JUN/04/2026 11 AM", "UV_VALUE": 8}

This is a *forecast* (not a live measurement), so it is strictly a fallback —
the orchestrator in ``app/conditions/uv.py`` prefers Open-UV when a key is
configured. The endpoint is keyless and cheap, so it is safe to poll on the
normal conditions cron cadence. Returns an empty payload (no exception) when the
endpoint errors or returns nothing usable, so the conditions strip degrades
gracefully.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from app.conditions.constants import LHC_ZIP
from app.core.timezone import LAKE_HAVASU_TZ

logger = logging.getLogger(__name__)

# https://www.epa.gov/enviro/web-services — Envirofacts UV REST service. The
# {zip} segment is interpolated; response is a JSON array of hourly records.
_EPA_UV_HOURLY_URL = "https://data.epa.gov/efservice/getEnvirofactsUVHOURLY/ZIP/{zip}/JSON"
_EPA_USER_AGENT = "havasu-chat/1.0 (+https://havasu-chat-production.up.railway.app)"


def _zip() -> str:
    return (os.environ.get("LHC_UV_ZIP") or LHC_ZIP).strip()


def _get(*, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Raw EPA hourly-UV GET. Returns a list of hourly records (possibly empty)."""
    url = _EPA_UV_HOURLY_URL.format(zip=_zip())
    headers = {"User-Agent": _EPA_USER_AGENT, "Accept": "application/json"}
    with httpx.Client() as client:
        response = client.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _parse_hour(date_time: str | None) -> int | None:
    """Parse the hour-of-day (0-23) from an EPA ``DATE_TIME`` like ``JUN/04/2026 11 AM``."""
    if not isinstance(date_time, str):
        return None
    parts = date_time.strip().split()
    # Expect [date, hour, meridiem]; tolerate extra/missing trailing tokens.
    if len(parts) < 3:
        return None
    try:
        hour = int(parts[-2])
    except ValueError:
        return None
    meridiem = parts[-1].upper()
    if meridiem == "PM" and hour != 12:
        hour += 12
    elif meridiem == "AM" and hour == 12:
        hour = 0
    if 0 <= hour <= 23:
        return hour
    return None


def fetch_epa_uv_index(*, now: datetime | None = None) -> dict[str, Any]:
    """Return ``{"uv_index", "uv_max"}`` (ints) or ``{}``.

    ``uv_max`` is the day's peak forecast UV; ``uv_index`` is the value forecast
    for the current Lake Havasu wall-clock hour, falling back to the peak when
    the current hour is not present in the response. Severity is left to the
    orchestrator so OpenUV and EPA share one WHO-band mapping.
    """
    now = now or datetime.now(LAKE_HAVASU_TZ)
    try:
        rows = _get()
    except Exception:  # pragma: no cover - network/parse errors degrade to empty
        logger.warning("conditions.epa_uv.fetch_failed", exc_info=True)
        return {}

    values: dict[int, int] = {}
    for row in rows:
        hour = _parse_hour(row.get("DATE_TIME"))
        raw = row.get("UV_VALUE")
        if hour is None or not isinstance(raw, (int, float)):
            continue
        values[hour] = int(raw)

    if not values:
        return {}

    uv_max = max(values.values())
    current = values.get(now.hour)
    uv_index = current if current is not None else uv_max
    return {"uv_index": uv_index, "uv_max": uv_max}
