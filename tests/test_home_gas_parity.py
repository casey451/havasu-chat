"""Finding 29: the home gas chip must equal the /gas page's cheapest, exactly.

The home conditions chip and /gas both read the SOURCE_GAS cache row, but the
home chip used to re-sort ``data["stations"]`` itself while /gas renders the
pull-curated ``data["cheapest"]`` list. A station the pull excluded from
``cheapest`` (e.g. one missing a real regular price) could then surface as the
home chip's "cheapest" while /gas showed a different, higher figure (live: home
$3.95 vs /gas $4.19). The fix points the home chip at the same ``data["cheapest"]``
source, so the two always agree. This test pins that parity.
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
    """A payload whose raw ``stations`` contains a cheaper station ($3.95) that the
    pull-curated ``cheapest`` list deliberately excludes (cheapest[0] = $4.19)."""
    cheapest0 = {"name": "Real Cheapest", "station_name": "Real Cheapest",
                 "address": "1 Main", "prices": {"regular": 4.19}}
    cheapest1 = {"name": "Second", "station_name": "Second",
                 "address": "2 Main", "prices": {"regular": 4.25}}
    phantom = {"name": "Phantom", "station_name": "Phantom",
               "address": "3 Main", "prices": {"regular": 3.95}}
    return {
        "station_count": 3,
        "city_avg": {"regular": 4.30, "midgrade": 4.60, "premium": 4.90},
        "cheapest": [cheapest0, cheapest1],
        "stations": [phantom, cheapest0, cheapest1],
    }


def _fake_read(payload: dict):
    def _inner(db, source, *, now=None):  # noqa: ANN001, ANN202 - test stub signature
        if source == SOURCE_GAS:
            return CacheReadResult(data=payload, fetched_at=_now(), ttl_seconds=86400, is_stale=False)
        return None

    return _inner


def test_home_gas_chip_matches_gas_cheapest() -> None:
    fake = _fake_read(_divergent_payload())
    with (
        patch("app.home.router.read_source", side_effect=fake),
        patch("app.api.routes.gas.read_source", side_effect=fake),
    ):
        with TestClient(app) as client:
            home = client.get("/home?theme=lake").text
            gas = client.get("/gas?theme=lake").text

    # Home chip shows the pull-curated cheapest ($4.19), same as /gas — never the
    # raw-stations minimum ($3.95) the excluded phantom station would have given.
    assert "$4.19" in home
    assert "$3.95" not in home
    assert "$4.19" in gas
