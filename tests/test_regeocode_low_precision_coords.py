"""Tests for scripts/regeocode_low_precision_coords.py.

Covers: precision detection (float-safe), Geocoding API response parsing via a
mocked httpx transport, address usability/suffixing, and the dry-run /
--apply / idempotency contract against the isolated test DB.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Provider
from scripts import regeocode_low_precision_coords as regeo

_SOURCE = "test-regeo"

# Full-precision coords inside the script's sanity bbox.
_PRECISE = (34.481234, -114.351234)


# ---------------------------------------------------------------------------
# Precision detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "max_decimals", "expected"),
    [
        (34.48, 2, True),  # the truncated-prod-row shape
        (-114.35, 2, True),
        (34.0, 2, True),  # zero decimals is also low-precision
        (34.4812, 2, False),
        (-114.351234, 2, False),
        (34.484, 3, True),  # threshold is configurable
        (34.4841, 3, False),
        (None, 2, False),  # no coordinate != truncated coordinate
    ],
)
def test_has_low_precision(value, max_decimals, expected) -> None:
    assert regeo.has_low_precision(value, max_decimals) is expected


def test_is_low_precision_pair_requires_both_axes() -> None:
    assert regeo.is_low_precision_pair(34.48, -114.35) is True
    # one precise axis -> not a truncation candidate
    assert regeo.is_low_precision_pair(34.48, -114.351234) is False
    assert regeo.is_low_precision_pair(34.481234, -114.35) is False
    assert regeo.is_low_precision_pair(None, -114.35) is False


# ---------------------------------------------------------------------------
# Address usability
# ---------------------------------------------------------------------------


def test_usable_address_suffixes_bare_street_address() -> None:
    p = Provider(provider_name="x", category="auto", address="2851 Saratoga Ave")
    assert regeo.usable_address(p) == f"2851 Saratoga Ave, {regeo.CITY_SUFFIX}"


def test_usable_address_keeps_full_address() -> None:
    p = Provider(
        provider_name="x", category="auto", address="2851 Saratoga Ave, Lake Havasu City, AZ"
    )
    assert regeo.usable_address(p) == "2851 Saratoga Ave, Lake Havasu City, AZ"


def test_usable_address_none_or_blank() -> None:
    assert regeo.usable_address(Provider(provider_name="x", category="auto", address=None)) is None
    assert regeo.usable_address(Provider(provider_name="x", category="auto", address="  ")) is None


# ---------------------------------------------------------------------------
# Geocoding API parsing (mocked transport — no network)
# ---------------------------------------------------------------------------


def _client_returning(payload: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "maps.googleapis.com"
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_geocode_address_parses_ok_response() -> None:
    payload = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": 34.481234, "lng": -114.351234}}}],
    }
    with _client_returning(payload) as client:
        assert regeo.geocode_address(client, "2851 Saratoga Ave", "test-key") == _PRECISE


def test_geocode_address_zero_results_returns_none() -> None:
    with _client_returning({"status": "ZERO_RESULTS", "results": []}) as client:
        assert regeo.geocode_address(client, "nowhere", "test-key") is None


def test_geocode_address_hard_failure_raises_without_leaking_key() -> None:
    with _client_returning({"status": "REQUEST_DENIED", "results": []}) as client:
        with pytest.raises(RuntimeError) as exc_info:
            regeo.geocode_address(client, "2851 Saratoga Ave", "test-key")
    assert "test-key" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# run(): dry-run / apply / idempotency against the test DB
# ---------------------------------------------------------------------------


@pytest.fixture
def _seeded_providers():
    """One truncated-coords row, one precise row, one truncated row w/o address."""
    with SessionLocal() as db:
        rows = [
            Provider(
                id="regeo-trunc-1",
                provider_name="Regeo Truncated",
                category="auto",
                address="100 Main St, Lake Havasu City, AZ",
                lat=34.48,
                lng=-114.35,
                source=_SOURCE,
            ),
            Provider(
                id="regeo-precise-1",
                provider_name="Regeo Precise",
                category="auto",
                address="200 Main St, Lake Havasu City, AZ",
                lat=34.477712,
                lng=-114.339301,
                source=_SOURCE,
            ),
            Provider(
                id="regeo-noaddr-1",
                provider_name="Regeo No Address",
                category="auto",
                address=None,
                lat=34.49,
                lng=-114.36,
                source=_SOURCE,
            ),
        ]
        db.add_all(rows)
        db.commit()
    yield
    with SessionLocal() as db:
        for p in db.scalars(select(Provider).where(Provider.source == _SOURCE)).all():
            db.delete(p)
        db.commit()


def _coords(provider_id: str) -> tuple[float, float]:
    with SessionLocal() as db:
        p = db.get(Provider, provider_id)
        return (p.lat, p.lng)


def _run_with_mock_geocoder(monkeypatch, *, apply: bool) -> dict[str, int]:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    monkeypatch.setattr(regeo, "geocode_address", lambda *a, **k: _PRECISE)
    return regeo.run(apply=apply, sleep_s=0.0)


def test_run_dry_run_reports_but_writes_nothing(monkeypatch, _seeded_providers) -> None:
    counts = _run_with_mock_geocoder(monkeypatch, apply=False)
    assert counts["changed"] >= 1  # at least our truncated row
    assert counts["skipped_no_address"] >= 1
    # nothing written
    assert _coords("regeo-trunc-1") == (34.48, -114.35)
    assert _coords("regeo-precise-1") == (34.477712, -114.339301)


def test_run_apply_writes_then_rerun_is_noop(monkeypatch, _seeded_providers) -> None:
    counts = _run_with_mock_geocoder(monkeypatch, apply=True)
    assert counts["changed"] >= 1
    assert _coords("regeo-trunc-1") == _PRECISE
    # precise row untouched; no-address row untouched
    assert _coords("regeo-precise-1") == (34.477712, -114.339301)
    assert _coords("regeo-noaddr-1") == (34.49, -114.36)

    # Idempotency: the fixed row no longer selects; nothing changes on re-run.
    rerun = _run_with_mock_geocoder(monkeypatch, apply=True)
    assert rerun["changed"] == 0
    assert _coords("regeo-trunc-1") == _PRECISE


def test_run_rejects_out_of_bounds_result(monkeypatch, _seeded_providers) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    monkeypatch.setattr(regeo, "geocode_address", lambda *a, **k: (40.7128, -74.0060))  # NYC
    counts = regeo.run(apply=True, sleep_s=0.0)
    assert counts["out_of_bounds"] >= 1
    assert counts["changed"] == 0
    assert _coords("regeo-trunc-1") == (34.48, -114.35)  # not written


def test_run_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        regeo.run(apply=False)
