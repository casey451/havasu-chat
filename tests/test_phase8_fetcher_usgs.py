"""Phase 8a — USGS OGC fetcher (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.conditions import usgs


def test_fetch_usgs_parses_gauge_and_storage() -> None:
    calls: list[str] = []

    def fake_retry(fn):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "features": [
                {
                    "properties": {
                        "value": 450.2 if len(calls) == 0 else 589000.0,
                        "datetime": "2026-05-21T12:00:00Z",
                    }
                }
            ]
        }
        calls.append("x")
        fn()
        return resp

    with patch.object(usgs._USGS_LIMITER, "call_with_retry", side_effect=fake_retry):
        data = usgs.fetch_usgs_lake_havasu()

    assert data["lake_gauge_ft"] == 450.2
    assert data["lake_storage_acft"] == 589000.0
