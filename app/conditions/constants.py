"""Cache source keys + TTL defaults for external conditions (Phase 8a)."""

from __future__ import annotations

SOURCE_AIRNOW = "airnow_86403"
SOURCE_NWS_CURRENT = "nws_current"
SOURCE_NWS_ALERTS = "nws_alerts_lhc_zone"
SOURCE_NWS_FORECAST = "nws_forecast_daily"
SOURCE_NWS_SUNSET = "nws_sunset"
SOURCE_USGS = "usgs_09427500"

# V1.5 wave 3 (2026-05-23): USGS water-temperature alt-source for station
# 09426630 ("Bill Williams River at Lake Havasu, abv HWY-95, AZ"). NOT yet
# in SOURCE_KEYS / TTL_BY_SOURCE -- wiring is a separate 1-line addition
# when the operator flips FEATURE_FLAG_WATER_TEMP_GAGE_09426630=true.
# See app/conditions/usgs_water_temp.py module docstring for context.
SOURCE_USGS_WATER_TEMP = "usgs_water_temp_09426630"

SOURCE_KEYS: tuple[str, ...] = (
    SOURCE_AIRNOW,
    SOURCE_NWS_CURRENT,
    SOURCE_NWS_ALERTS,
    SOURCE_NWS_FORECAST,
    SOURCE_NWS_SUNSET,
    SOURCE_USGS,
)

TTL_BY_SOURCE: dict[str, int] = {
    SOURCE_AIRNOW: 1800,
    SOURCE_NWS_CURRENT: 1800,
    SOURCE_NWS_ALERTS: 900,
    SOURCE_NWS_FORECAST: 86400,
    SOURCE_NWS_SUNSET: 86400,
    SOURCE_USGS: 3600,
}

NWS_USER_AGENT = "havasu-chat/1.0 (contact: support@havasu-chat.example.com)"
LHC_LAT = 34.4839
LHC_LON = -114.3225
