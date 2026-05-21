"""Per-alert-type threshold constants (Phase 8a)."""

from __future__ import annotations

import os

HEAT_ADVISORY_NWS_EVENT_PATTERNS: tuple[str, ...] = (
    "Heat Advisory",
    "Excessive Heat Warning",
    "Heat Watch",
)

HEAT_ADVISORY_FORECAST_THRESHOLD_F: float = float(
    os.environ.get("HEAT_ADVISORY_FORECAST_THRESHOLD_F", "110.0")
)

HEAT_ADVISORY_INDEX_FLOOR_F: float | None = (
    float(os.environ["HEAT_ADVISORY_INDEX_FLOOR_F"])
    if os.environ.get("HEAT_ADVISORY_INDEX_FLOOR_F")
    else None
)

AQI_ALERT_THRESHOLD: int = int(os.environ.get("AQI_ALERT_THRESHOLD", "150"))

AIRNOW_ZIP = os.environ.get("AIRNOW_ZIP", "86403")
AIRNOW_DISTANCE_MI: int = int(os.environ.get("AIRNOW_DISTANCE_MI", "100"))

LAKE_HAZARD_NWS_KEYWORDS: tuple[str, ...] = (
    "flash flood",
    "flood warning",
    "flood advisory",
    "lake wind",
    "high wind",
    "wind advisory",
    "blowing dust",
    "dust storm",
    "severe thunderstorm",
)

LAKE_HAZARD_GAUGE_DROP_FT: float = float(
    os.environ.get("LAKE_HAZARD_GAUGE_DROP_FT", "2.0")
)

LHC_NWS_ZONE_ID = os.environ.get("LHC_NWS_ZONE_ID", "AZZ002")
USGS_LAKE_HAVASU_SITE = os.environ.get("USGS_LAKE_HAVASU_SITE", "09427500")
USGS_PARAMETER_CODES: tuple[str, ...] = tuple(
    c.strip()
    for c in os.environ.get("USGS_PARAMETER_CODES", "00065,00054").split(",")
    if c.strip()
)

ALERT_DEDUPE_WINDOW_HOURS: int = int(os.environ.get("ALERT_DEDUPE_WINDOW_HOURS", "6"))

ALERT_TYPES_V1: tuple[str, ...] = ("heat_advisory", "aqi_alert", "lake_hazard")
EVENT_TRAFFIC_DEFERRED = "event_traffic"
