"""Phase 8a — USGS OGC fetcher (mocked).

Phase 8a.2 update (2026-05-21): USGS renamed the ``observations`` collection
to ``latest-continuous``. Three new tests verify the URL path is correct, the
new string-typed ``value`` field still parses, and the new ``time`` timestamp
key is honored alongside the legacy ``datetime`` key.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.conditions import usgs


class _FakeClient:
    """In-process stand-in for ``httpx.Client``.

    Every test in this module patches ``usgs.httpx.Client`` with this class so
    that driving ``fn()`` inside a ``call_with_retry`` fake exercises the real
    ``_inner`` closure WITHOUT a live request to api.waterdata.usgs.gov. Two of
    these "mocked" tests used to skip the Client patch and made real USGS
    calls, which flaked with ReadTimeout under parallel test load (T2.4).
    """

    captured_urls: list[str]

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get(self, url: str, **_kwargs):
        type(self).captured_urls.append(url)
        return MagicMock()


def _fresh_fake_client() -> type[_FakeClient]:
    """Per-test subclass so captured URLs don't leak between tests."""

    class _FakeClientT(_FakeClient):
        captured_urls: list[str] = []

    return _FakeClientT


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

    with patch.object(usgs.httpx, "Client", _fresh_fake_client()):
        with patch.object(usgs._USGS_LIMITER, "call_with_retry", side_effect=fake_retry):
            data = usgs.fetch_usgs_lake_havasu()

    assert data["lake_gauge_ft"] == 450.2
    assert data["lake_storage_acft"] == 589000.0


def test_fetch_usgs_uses_latest_continuous_collection_url() -> None:
    """Phase 8a.2: the URL path must point at the renamed ``latest-continuous``
    collection. The legacy ``observations`` collection returns HTTP 404 from USGS.
    """
    def fake_retry(fn):
        # Drive _inner so it actually hits the (patched) httpx Client and we
        # can capture the URL the fetcher requested.
        fn()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"features": []}
        return resp

    client_cls = _fresh_fake_client()
    with patch.object(usgs.httpx, "Client", client_cls):
        with patch.object(usgs._USGS_LIMITER, "call_with_retry", side_effect=fake_retry):
            usgs.fetch_usgs_lake_havasu()

    captured_urls = client_cls.captured_urls
    assert captured_urls, "fetcher did not issue any HTTP requests"
    for url in captured_urls:
        assert "/collections/latest-continuous/items" in url, (
            f"URL still pointing at deprecated path: {url}"
        )
        assert "/collections/observations/items" not in url, (
            f"URL still pointing at deprecated 'observations' collection: {url}"
        )


def test_fetch_usgs_parses_string_value_from_new_payload() -> None:
    """Phase 8a.2: the renamed ``latest-continuous`` collection returns the
    ``value`` as a STRING (e.g. ``"49.12"``), not a float. The parser already
    handles this via ``float(value)`` but we lock that in with a test.
    """
    calls: list[str] = []

    def fake_retry(fn):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        # Mimic the actual production payload shape observed at the new endpoint:
        # value is a string, timestamp key is 'time' (not 'datetime').
        resp.json.return_value = {
            "features": [
                {
                    "properties": {
                        "value": "49.12" if len(calls) == 0 else "591100",
                        "time": "2026-05-21T20:30:00+00:00",
                    }
                }
            ]
        }
        calls.append("x")
        fn()
        return resp

    with patch.object(usgs.httpx, "Client", _fresh_fake_client()):
        with patch.object(usgs._USGS_LIMITER, "call_with_retry", side_effect=fake_retry):
            data = usgs.fetch_usgs_lake_havasu()

    assert data["lake_gauge_ft"] == 49.12
    assert data["lake_storage_acft"] == 591100.0
    # Both history rows must have observed_at populated from the new 'time' key.
    assert all(item["observed_at"] == "2026-05-21T20:30:00+00:00" for item in data["history"])
