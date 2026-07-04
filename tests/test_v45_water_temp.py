"""v4.5 PR-6 — water-temp reliability (the "dependable gauge").

The Reclamation RISE service (Parker Dam item 6127) is a JSON:API endpoint: it
406s on ``Accept: application/json`` and only serves ``application/vnd.api+json``.
The fetcher was sending the wrong header, so the water tile silently omitted even
with the feature flag ON. These pins guard the fix + the retry-once + the
throttled WATER_TEMP_STALE observability log + the 6h staleness window.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from app.conditions import api_payload, rise_water_temp
from app.conditions.staleness import staleness_label


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(rise_water_temp.FEATURE_FLAG_ENV_VAR, "true")


def _rise_body(temp_f: float | None) -> dict:
    data = []
    if temp_f is not None:
        data = [
            {
                "attributes": {
                    "result": temp_f,
                    "dateTime": "2026-07-04T07:00:00",
                }
            }
        ]
    return {"data": data}


def test_rise_fetch_sends_jsonapi_accept_header() -> None:
    """The request must carry Accept: application/vnd.api+json (else RISE 406s)."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["accept"] = request.headers.get("accept", "")
        return httpx.Response(200, json=_rise_body(80.7))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = rise_water_temp.fetch_rise_water_temp(client=client)

    assert seen["accept"] == "application/vnd.api+json"
    assert result["water_temp_f"] == 80.7
    assert result["water_temp_c"] == 27.1
    assert result["feature_enabled"] is True


def test_rise_fetch_retries_once_on_empty_reading() -> None:
    """A first empty parse triggers exactly one retry; the second reading wins."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        # First hit: no data (transient). Second hit: a real reading.
        return httpx.Response(200, json=_rise_body(None if calls["n"] == 1 else 79.0))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = rise_water_temp.fetch_rise_water_temp(client=client)

    assert calls["n"] == 2  # retried exactly once
    assert result["water_temp_f"] == 79.0


def test_rise_fetch_gives_up_after_one_retry() -> None:
    """Two empty parses -> honest empty payload, no infinite retry."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_rise_body(None))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = rise_water_temp.fetch_rise_water_temp(client=client)

    assert calls["n"] == 2  # one try + one retry, then stop
    assert result["water_temp_f"] is None
    assert result["feature_enabled"] is True


def test_water_temp_staleness_window_is_six_hours() -> None:
    """Water temp uses a 6h window (a 3h-old daily reading is NOT stale)."""
    from datetime import datetime, timedelta

    now = datetime(2026, 7, 4, 12, 0, 0)
    _, three_h_stale = staleness_label(
        now - timedelta(hours=3), now, stale_after_hours=api_payload._WATER_TEMP_STALE_AFTER_HOURS
    )
    _, seven_h_stale = staleness_label(
        now - timedelta(hours=7), now, stale_after_hours=api_payload._WATER_TEMP_STALE_AFTER_HOURS
    )
    assert three_h_stale is False
    assert seven_h_stale is True


def test_water_temp_stale_log_is_throttled(caplog: pytest.LogCaptureFixture) -> None:
    """The WATER_TEMP_STALE marker logs at most once per hour (process-wide)."""
    from datetime import datetime, timedelta

    api_payload._last_water_temp_stale_log = None  # reset the module throttle
    t0 = datetime(2026, 7, 4, 12, 0, 0)
    with caplog.at_level(logging.WARNING, logger="app.conditions.api_payload"):
        api_payload._log_water_temp_stale(t0, "stale_reading", "Reclamation · Parker Dam")
        api_payload._log_water_temp_stale(t0 + timedelta(minutes=30), "stale_reading", "x")
        api_payload._log_water_temp_stale(t0 + timedelta(hours=2), "stale_reading", "x")
    markers = [r for r in caplog.records if "WATER_TEMP_STALE" in r.getMessage()]
    assert len(markers) == 2  # first fires, +30min throttled, +2h fires again
