"""The /group/<slug> operational filter chips now actually filter (Casey 2026-06-29).

These smoke-test that wiring `_apply_python_filters` / `_apply_classes_sports_filters`
into the route keeps it healthy under each filter param (no crash, still 200) and
that the unfiltered page is unaffected. Per-filter band logic is covered in
test_classes_audience_filter.py.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.groups.themed_group_stream import _when_window
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize(
    "qs",
    [
        "",  # unfiltered baseline
        "open=now",
        "verified=1",
        "mobile=1",
        "free=1",
        "late=1",
        "npi=1",
        "open=now&verified=1",
    ],
)
def test_operational_filters_keep_route_healthy(client: TestClient, qs: str) -> None:
    url = "/group/on-the-water-group" + (f"?{qs}" if qs else "")
    assert client.get(url).status_code == 200


@pytest.mark.parametrize("qs", ["youth=1", "adults=1", "youth=1&drop_in=1"])
def test_classes_audience_filters_keep_route_healthy(client: TestClient, qs: str) -> None:
    # health-fitness-group leads with the classes-sports-recreation category, so it
    # exercises _apply_classes_sports_filters.
    assert client.get(f"/group/health-fitness-group?{qs}").status_code == 200


@pytest.mark.parametrize(
    "qs", ["when=today", "when=this-weekend", "when=this-week", "when=next-month"]
)
def test_events_when_filters_keep_route_healthy(client: TestClient, qs: str) -> None:
    # things-to-do-group includes the events category, exercising the date-windowed,
    # events-only card stream.
    assert client.get(f"/group/things-to-do-group?{qs}").status_code == 200


def test_when_window_maps_chips_to_dates() -> None:
    mon = date(2026, 6, 29)  # a Monday
    assert _when_window("today", mon) == (mon, mon)
    assert _when_window("this-weekend", mon) == (date(2026, 7, 4), date(2026, 7, 5))
    assert _when_window("this-week", mon) == (mon, date(2026, 7, 5))
    assert _when_window("next-month", mon) == (date(2026, 7, 1), date(2026, 7, 31))
    assert _when_window(None, mon) is None
    assert _when_window("bogus", mon) is None
