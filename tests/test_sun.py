"""Astronomical sunset calculation for Lake Havasu City (site review §4c).

Reference values cross-checked against the NOAA solar calculator for the city's
coordinates (34.4839 N, 114.3225 W, MST/UTC-7): summer solstice ~7:53 PM, winter
solstice ~5:30 PM, March equinox ~6:48 PM.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from app.conditions.sun import sunset_utc

_PHX = ZoneInfo("America/Phoenix")


def _local(d: date):
    return sunset_utc(d).astimezone(_PHX)


def test_sunset_is_utc_aware() -> None:
    assert sunset_utc(date(2026, 6, 21)).tzinfo is not None


def test_summer_solstice_sunset_late_evening() -> None:
    s = _local(date(2026, 6, 21))
    assert s.hour == 19 and 45 <= s.minute <= 59  # ~7:53 PM


def test_winter_solstice_sunset_early_evening() -> None:
    s = _local(date(2026, 12, 21))
    assert s.hour == 17 and 20 <= s.minute <= 40  # ~5:30 PM


def test_equinox_sunset_mid_evening() -> None:
    s = _local(date(2026, 3, 20))
    assert s.hour == 18 and 40 <= s.minute <= 55  # ~6:48 PM


def test_summer_sunset_is_later_than_winter() -> None:
    assert _local(date(2026, 6, 21)).timetz() > _local(date(2026, 12, 21)).timetz()
