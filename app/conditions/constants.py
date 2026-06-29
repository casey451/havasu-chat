"""Cache source keys + TTL defaults for external conditions (Phase 8a)."""

from __future__ import annotations

SOURCE_AIRNOW = "airnow_86403"
SOURCE_NWS_CURRENT = "nws_current"
SOURCE_NWS_ALERTS = "nws_alerts_lhc_zone"
SOURCE_NWS_FORECAST = "nws_forecast_daily"
SOURCE_NWS_SUNSET = "nws_sunset"
SOURCE_USGS = "usgs_09427500"
SOURCE_GAS = "gas_prices_lhc"

# V1.5 wave 3 (2026-05-23): USGS water-temperature alt-source for station
# 09426630 ("Bill Williams River at Lake Havasu, abv HWY-95, AZ"). Wired
# into SOURCE_KEYS / TTL_BY_SOURCE here; gated at fetcher + api_payload
# layers via FEATURE_FLAG_WATER_TEMP_GAGE_09426630 (default OFF). When the
# flag is OFF the cron still calls the fetcher each tick but the fetcher
# short-circuits to an empty payload before any HTTP request, and the
# api_payload reader skips emission so /api/conditions is unchanged.
# See app/conditions/usgs_water_temp.py module docstring for context.
SOURCE_USGS_WATER_TEMP = "usgs_water_temp_09426630"

# Optional UV index (Open-UV, https://www.openuv.io/). Key-gated on
# OPENUV_API_KEY: when the key is unset the fetcher makes NO HTTP call (returns
# an empty payload) and api_payload/view_model skip the UV chip — so the cron is
# safe to call it every tick. The hourly TTL keeps usage within the 50-req/day
# free tier (~24 calls/day). See app/conditions/openuv.py.
SOURCE_OPENUV = "openuv_index"

# Local news aggregate (source-expansion #6 → live, Casey 2026-06-29). A single
# cache row holding the merged, deduped, recency-sorted headline list from every
# wired local news source (News-Herald sitemap, City newsflash, River Scene,
# Sheriff press). Deliberately NOT in SOURCE_KEYS — the conditions cron must not
# reach out to news endpoints. A dedicated pull (scripts/news_pull.py →
# app.news.store.pull_local_news) populates it. Only headlines + links + dates
# are stored; article bodies are never persisted (paywall/copyright rule 6, see
# app/contrib/news_herald.py).
SOURCE_NEWS_LOCAL = "news_local"

SOURCE_KEYS: tuple[str, ...] = (
    SOURCE_AIRNOW,
    SOURCE_NWS_CURRENT,
    SOURCE_NWS_ALERTS,
    SOURCE_NWS_FORECAST,
    SOURCE_NWS_SUNSET,
    SOURCE_USGS,
    SOURCE_USGS_WATER_TEMP,
    SOURCE_OPENUV,
    SOURCE_GAS,
)

TTL_BY_SOURCE: dict[str, int] = {
    SOURCE_AIRNOW: 1800,
    SOURCE_NWS_CURRENT: 1800,
    SOURCE_NWS_ALERTS: 900,
    SOURCE_NWS_FORECAST: 86400,
    SOURCE_NWS_SUNSET: 86400,
    SOURCE_USGS: 3600,
    # Same 3600s TTL as the lake-gauge USGS source -- water temperature is a
    # slow-moving signal (instrument cadence is hourly at most for 00010).
    SOURCE_USGS_WATER_TEMP: 3600,
    SOURCE_OPENUV: 3600,
    SOURCE_GAS: 28800,
    # News refreshes on a ~hourly pull; the ticker still shows the last good
    # headlines past TTL (staleness only drives an optional "updated" hint).
    SOURCE_NEWS_LOCAL: 3600,
}

# Gas prices refresh on a roughly-daily cadence (86400s TTL), so the generic 2h
# staleness threshold flagged every fresh fetch as "stale". Allow a full day plus
# headroom before the gas banner reads stale (G-2). See staleness_label().
GAS_STALE_AFTER_HOURS = 10

NWS_USER_AGENT = "havasu-chat/1.0 (contact: support@havasu-chat.example.com)"
LHC_LAT = 34.4839
LHC_LON = -114.3225
# Primary Lake Havasu City ZIP — used by the keyless EPA Envirofacts UV-index
# fallback (app/conditions/epa_uv.py) when OPENUV_API_KEY is unset.
LHC_ZIP = "86403"
