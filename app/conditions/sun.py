"""Deterministic astronomical sunset for Lake Havasu City.

The conditions cache has no reliable sunset source: Open-UV carries a true
``sun_times.sunset`` but is often absent, and the NWS "sunset" row actually
stores the evening *forecast-period* start (~2h before real sunset), which read
as "Sunset 6:00 PM" in late June (site review §4c). This module computes sunset
from first principles for the city's fixed coordinates — no network, no
dependency — so the strip always shows a correct time.

NOAA sunrise/sunset approximation (the "sunrise equation"); accurate to ~1
minute, ample for a "Sunset 7:42 PM" readout.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

from app.conditions.constants import LHC_LAT, LHC_LON

# Standard sunset: the sun's upper limb at the horizon, including atmospheric
# refraction (the conventional −0.833° solar elevation).
_SUNSET_ELEVATION_DEG = -0.833
_OBLIQUITY_DEG = 23.4397  # mean obliquity of the ecliptic


def sunset_utc(day: date) -> datetime:
    """Sunset instant (tz-aware UTC) for Lake Havasu City on ``day``.

    Raises nothing; in the (impossible-for-this-latitude) polar day/night case
    the hour angle is clamped so a finite time is always returned.
    """
    # Julian Day Number at noon UTC for ``day`` (Fliegel–Van Flandern).
    a = (14 - day.month) // 12
    y = day.year + 4800 - a
    m = day.month + 12 * a - 3
    jdn = day.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045

    n = jdn - 2451545 + 0.0008  # days since J2000.0 (+ leap-second correction)
    # Mean solar time. LHC_LON is east-negative (-114.32), so subtracting it adds
    # the ~7.6h that solar noon lags UTC at this western longitude.
    j_star = n - LHC_LON / 360.0

    mean_anomaly = (357.5291 + 0.98560028 * j_star) % 360.0
    ma = math.radians(mean_anomaly)
    center = 1.9148 * math.sin(ma) + 0.0200 * math.sin(2 * ma) + 0.0003 * math.sin(3 * ma)
    ecliptic_lon = (mean_anomaly + center + 282.9372) % 360.0  # +180 +102.9372
    el = math.radians(ecliptic_lon)

    j_transit = 2451545.0 + j_star + 0.0053 * math.sin(ma) - 0.0069 * math.sin(2 * el)

    sin_decl = math.sin(el) * math.sin(math.radians(_OBLIQUITY_DEG))
    decl = math.asin(sin_decl)
    lat = math.radians(LHC_LAT)
    cos_hour = (math.sin(math.radians(_SUNSET_ELEVATION_DEG)) - math.sin(lat) * sin_decl) / (
        math.cos(lat) * math.cos(decl)
    )
    cos_hour = max(-1.0, min(1.0, cos_hour))  # guard polar day/night
    hour_angle = math.degrees(math.acos(cos_hour))

    j_set = j_transit + hour_angle / 360.0
    return datetime(2000, 1, 1, 12, tzinfo=UTC) + timedelta(days=j_set - 2451545.0)
