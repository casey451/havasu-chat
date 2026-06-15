"""Locality classification (B7) — is a provider in the Lake Havasu service area?

Pure + dependency-free so it is unit-testable and importable from the ops
backfill script. Tri-state by design (``True`` / ``False`` / ``None``): a row
with neither usable geo nor a recognizable city stays ``None`` ("unknown") and
must never be assumed out-of-area.

Casey's rule (2026-06-14): local if EITHER the geo is in-area OR the address
carries a local city token; not-local only when a signal exists and none say
local; NULL when both signals are missing.
"""

from __future__ import annotations

import math

# Civic anchor + in-area radius mirror app/categories/queries.py (the 32 km
# out-of-area threshold already used for the card distance hint). Duplicated as
# plain constants to keep this module dependency-free for the ops script.
_REF_LAT = 34.4839
_REF_LNG = -114.3225
IN_AREA_KM = 32.0
# Beyond this the coordinates aren't trustworthy (the 9e6 geo-less sentinel, or a
# mis-geocode); geo then yields NO signal rather than a false "not local".
_FAR_KM = 150.0

#: Address substrings that positively mark a LOCAL row.
_LOCAL_TOKENS: tuple[str, ...] = ("lake havasu", "havasu city")
#: Surrounding-region towns — a positive "not local" city signal even when geo
#: is missing. (Parker / Kingman / Blythe are the out-of-area cluster the audit
#: flagged on Havasu listings; the rest are nearby AZ/CA towns.)
_OUT_OF_AREA_TOKENS: tuple[str, ...] = (
    "parker",
    "kingman",
    "blythe",
    "bullhead",
    "needles",
    "quartzsite",
    "golden valley",
    "fort mohave",
    "mohave valley",
    "topock",
    "yuma",
)


def _distance_km(lat: float, lng: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(_REF_LAT), math.radians(lat)
    dp = math.radians(lat - _REF_LAT)
    dl = math.radians(lng - _REF_LNG)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geo_signal(lat: float | None, lng: float | None) -> bool | None:
    """``True`` in-area, ``False`` out-of-area, ``None`` when geo is missing or
    the coordinates are too far to be trustworthy."""
    if lat is None or lng is None:
        return None
    try:
        km = _distance_km(float(lat), float(lng))
    except (TypeError, ValueError):
        return None
    if km >= _FAR_KM:
        return None
    return km < IN_AREA_KM


def city_signal(address: str | None) -> bool | None:
    """``True`` local city token, ``False`` known out-of-area town, ``None`` when
    the address is empty or names no recognizable city."""
    addr = (address or "").lower()
    if not addr:
        return None
    if any(tok in addr for tok in _LOCAL_TOKENS):
        return True
    if any(tok in addr for tok in _OUT_OF_AREA_TOKENS):
        return False
    return None


def classify_is_local(
    address: str | None, lat: float | None, lng: float | None
) -> bool | None:
    """Tri-state locality for one provider (see module docstring)."""
    signals = [s for s in (geo_signal(lat, lng), city_signal(address)) if s is not None]
    if not signals:
        return None
    return any(signals)
