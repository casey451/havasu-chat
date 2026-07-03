"""Finding 29 (v4.4 PR-1): the home gas figure and /gas must agree, always.

Pre-v4.4 the home chip and /gas each read the SOURCE_GAS row on their own path:
the home chip re-sorted ``data["stations"]`` while /gas rendered the pull-curated
``data["cheapest"]``, so a station in ``stations`` but not ``cheapest`` could make
home show $3.95 while /gas showed $4.19. v4.4 collapses both onto ONE
``app.gas.service.GasBoard`` whose ``cheapest("reg")`` derives from ``stations``,
so every surface shows the same figure *by construction*. This test pins that
parity, plus the board's honest filter (a station with no valid regular price
never surfaces anywhere).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.conditions.cache import CacheReadResult
from app.conditions.constants import SOURCE_GAS
from app.main import app


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _divergent_payload() -> dict:
    """Raw ``stations`` holds a valid-priced station ($3.95) that the pull's
    curated ``cheapest`` omits (cheapest[0] = $4.19) — the exact shape that used
    to split the two surfaces. The single board makes both derive from
    ``stations``, so both now show the true minimum, $3.95."""
    cheapest0 = {"name": "Curated Cheapest", "station_name": "Curated Cheapest",
                 "address": "1 Main", "prices": {"regular": 4.19}}
    cheapest1 = {"name": "Second", "station_name": "Second",
                 "address": "2 Main", "prices": {"regular": 4.25}}
    true_min = {"name": "True Min", "station_name": "True Min",
                "address": "3 Main", "prices": {"regular": 3.95}}
    return {
        "station_count": 3,
        "city_avg": {"regular": 4.30, "midgrade": 4.60, "premium": 4.90},
        "cheapest": [cheapest0, cheapest1],
        "stations": [true_min, cheapest0, cheapest1],
    }


def _priceless_payload() -> dict:
    """A station with no valid regular price ($0) must never surface: the honest
    filter drops it, so the cheapest shown is the next real price ($4.19)."""
    junk = {"name": "Junk", "station_name": "Junk", "address": "9 Main",
            "prices": {"regular": 0}}
    real = {"name": "Real", "station_name": "Real", "address": "1 Main",
            "prices": {"regular": 4.19}}
    return {"station_count": 2, "city_avg": {"regular": 4.19},
            "cheapest": [real], "stations": [junk, real]}


def _fake_read(payload: dict):
    def _inner(db, source, *, now=None):  # noqa: ANN001, ANN202 - test stub signature
        if source == SOURCE_GAS:
            return CacheReadResult(data=payload, fetched_at=_now(), ttl_seconds=86400, is_stale=False)
        return None

    return _inner


def test_home_and_gas_agree_on_cheapest_by_construction() -> None:
    fake = _fake_read(_divergent_payload())
    with (
        patch("app.home.redesign.read_source", side_effect=fake),
        patch("app.api.routes.gas.read_source", side_effect=fake),
    ):
        with TestClient(app) as client:
            home = client.get("/home").text
            gas = client.get("/gas").text

    # Both surfaces derive the cheapest from the same board -> both show the true
    # minimum ($3.95). The pre-v4.4 split (home $3.95 vs /gas $4.19) is gone.
    assert "$3.95" in home
    assert "$3.95" in gas
    assert 'id="gasPanel"' in home  # the v4 gas top-5 expander


def test_priceless_station_never_surfaces() -> None:
    fake = _fake_read(_priceless_payload())
    with (
        patch("app.home.redesign.read_source", side_effect=fake),
        patch("app.api.routes.gas.read_source", side_effect=fake),
    ):
        with TestClient(app) as client:
            home = client.get("/home").text
            gas = client.get("/gas").text
    # The $0 station is filtered out; the cheapest shown is the next real price.
    assert "$4.19" in home
    assert "$4.19" in gas
    assert "$0.00" not in home
    assert "$0.00" not in gas


def test_home_band_excludes_gas_other_surfaces_keep_it() -> None:
    """P3: the home conditions band is weather-only (include_gas=False); gas is a
    separate chip. Every other surface keeps gas inline (default include_gas=True)."""
    from app.db.database import SessionLocal
    from app.home.router import _gas_chip, _utility_chips

    fake = _fake_read(_divergent_payload())
    with patch("app.home.router.read_source", side_effect=fake):
        with SessionLocal() as db:
            weather_only = _utility_chips(db, include_gas=False)
            with_gas = _utility_chips(db, include_gas=True)
            gas_chip = _gas_chip(db)
    assert all(c["kind"] != "gas" for c in weather_only)
    assert any(c["kind"] == "gas" for c in with_gas)
    # The single board surfaces the true minimum, $3.95 (not the curated $4.19).
    assert gas_chip is not None and gas_chip["value"] == "$3.95"
