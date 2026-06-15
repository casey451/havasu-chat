"""B7 — provider locality classification (is_local tri-state).

Covers the geo signal, the city-token signal, the OR combination, and the
NULL-when-no-signal rule, plus that the is_local column is registered.
"""

from __future__ import annotations

from app.core.locality import (
    city_signal,
    classify_is_local,
    geo_signal,
)
from app.db.database import Base

# Coordinates: ~2 km from the LHC civic anchor (in-area) and ~37 km out (Parker).
_IN_AREA = (34.48, -114.30)
_PARKER = (34.150, -114.289)  # out of the 32 km radius, still in-region (<150 km)


def test_geo_signal() -> None:
    assert geo_signal(*_IN_AREA) is True
    assert geo_signal(*_PARKER) is False
    assert geo_signal(None, None) is None
    # Mis-geocode / far coords are untrustworthy → no signal (not a false "not local").
    assert geo_signal(0.0, 0.0) is None


def test_city_signal() -> None:
    assert city_signal("2126 McCulloch Blvd N, Lake Havasu City, AZ 86403") is True
    assert city_signal("100 Main St, Parker, AZ 85344") is False
    assert city_signal("100 Main St") is None
    assert city_signal("") is None
    assert city_signal(None) is None


def test_classify_or_combination() -> None:
    # geo in-area OR city local → local.
    assert classify_is_local("Lake Havasu City, AZ", *_IN_AREA) is True
    # geo out-of-area BUT city local → local (the OR rule).
    assert classify_is_local("Lake Havasu City, AZ", *_PARKER) is True
    # geo out-of-area AND city out-of-area → not local.
    assert classify_is_local("Parker, AZ", *_PARKER) is False
    # No usable signal → unknown (NULL).
    assert classify_is_local("100 Main St", None, None) is None
    assert classify_is_local(None, None, None) is None


def test_is_local_column_registered() -> None:
    cols = set(Base.metadata.tables["providers"].columns.keys())
    assert "is_local" in cols
