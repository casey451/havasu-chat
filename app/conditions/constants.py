"""Cache source keys + TTL defaults for external conditions (Phase 8a)."""

from __future__ import annotations

SOURCE_AIRNOW = "airnow_86403"
SOURCE_NWS_CURRENT = "nws_current"
SOURCE_NWS_ALERTS = "nws_alerts_lhc_zone"
SOURCE_NWS_FORECAST = "nws_forecast_daily"
# Retired fetch source (2026-07-02 audit): the NWS "tonight period" sunset was
# fetched every cron tick (~192 NWS calls/day for a points+forecast pair) but
# read by NOTHING — api_payload's sunset comes from Open-UV or the computed
# astronomical sun.py. The key constant stays so stale cache rows keep a name;
# it is no longer in SOURCE_KEYS and has no fetcher.
SOURCE_NWS_SUNSET = "nws_sunset"
SOURCE_USGS = "usgs_09427500"
# Gas is WRITTEN by the gas-prices workflow (scripts/gas_prices_pull.py), not
# fetched by the conditions cron — it has no _FETCHERS entry, so it must stay
# OUT of SOURCE_KEYS. It used to be listed there, which made every 15-minute
# `--all` tick raise "unknown conditions source: gas_prices_lhc" (~96 error
# logs/day, masking real failures).
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

# Reclamation RISE water temperature at Parker Dam (item 6127). Parker Dam
# impounds Lake Havasu, so this is the representative main-lake reading and the
# PREFERRED water-temp source over the Bill Williams USGS gage (09426630), which
# has published the -100000 missing-data sentinel since 2026-05-21. Gated at the
# fetcher on FEATURE_FLAG_WATER_TEMP_RISE_6127 (v4.6: default ON; a falsy env var
# disables it and suppresses HTTP).
# See app/conditions/rise_water_temp.py.
SOURCE_RISE_WATER_TEMP = "rise_water_temp_6127"

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

# The sources the conditions cron actually fetches: every key here MUST have a
# _FETCHERS entry in app/conditions/fetcher.py (SOURCE_GAS and SOURCE_NEWS_LOCAL
# are written by their own dedicated pulls; SOURCE_NWS_SUNSET is retired).
SOURCE_KEYS: tuple[str, ...] = (
    SOURCE_AIRNOW,
    SOURCE_NWS_CURRENT,
    SOURCE_NWS_ALERTS,
    SOURCE_NWS_FORECAST,
    SOURCE_USGS,
    SOURCE_USGS_WATER_TEMP,
    SOURCE_RISE_WATER_TEMP,
    SOURCE_OPENUV,
)

TTL_BY_SOURCE: dict[str, int] = {
    SOURCE_AIRNOW: 1800,
    SOURCE_NWS_CURRENT: 1800,
    SOURCE_NWS_ALERTS: 900,
    SOURCE_NWS_FORECAST: 86400,
    SOURCE_USGS: 3600,
    # Same 3600s TTL as the lake-gauge USGS source -- water temperature is a
    # slow-moving signal (instrument cadence is hourly at most for 00010).
    SOURCE_USGS_WATER_TEMP: 3600,
    # RISE posts a daily Parker Dam water temp; refetch a few times a day.
    SOURCE_RISE_WATER_TEMP: 21600,
    SOURCE_OPENUV: 3600,
    # Gas is pulled by scripts/gas_prices_pull.py (gas-prices.yml), NOT the
    # conditions cron, so this TTL never drives a refetch — it ONLY feeds the
    # cache row's ``is_stale`` flag. ``app.gas.service.board_from_cache`` computes
    # ``is_stale = age > GAS_STALE_AFTER_HOURS OR row.is_stale``, so a TTL SHORTER
    # than ``GAS_STALE_AFTER_HOURS`` silently wins and undercuts the documented
    # threshold. It MUST stay >= GAS_STALE_AFTER_HOURS*3600 (asserted in
    # tests/test_gas_service.py). 2026-07-08: was 28800 (8h) < the 10h threshold,
    # so every early morning read "stale" during the normal overnight pull gap and
    # tripped the post-deploy freshness canary. Now 12h, matching the threshold.
    SOURCE_GAS: 43200,
    # News refreshes on a ~hourly pull; the ticker still shows the last good
    # headlines past TTL (staleness only drives an optional "updated" hint).
    SOURCE_NEWS_LOCAL: 3600,
}

# Gas is crowd-sourced (GasBuddy) and pulled 3x/day by gas-prices.yml at
# 06:00 / 13:00 / 20:00 America/Phoenix (cron ``0 3,13,20`` UTC, AZ = UTC-7).
# The largest normal inter-run gap is the overnight 20:00 -> 06:00 stretch, ~10h,
# and GitHub's scheduler routinely lags each slot 10-30 min. The staleness
# threshold must exceed that gap (+ lag), or the banner flags a false "stale"
# every morning between the widening gap and the 06:00 refresh — the 2026-07-08
# canary red (the 03:00-UTC pull ran at 04:01, canary at 12:49 UTC / 05:49 MST
# saw a 9h-old-but-fine payload flagged stale). 12h gives ~1.5h margin over the
# gap yet still flags a genuine two-missed-pulls outage, well under the canary's
# 24h hard ceiling (GAS_MAX_AGE_HOURS). Keep TTL_BY_SOURCE[SOURCE_GAS] in lockstep
# (see the note there). See staleness_label() and app.gas.service.
GAS_STALE_AFTER_HOURS = 12

NWS_USER_AGENT = "havasu-chat/1.0 (contact: support@havasu-chat.example.com)"
LHC_LAT = 34.4839
LHC_LON = -114.3225
# Primary Lake Havasu City ZIP — used by the keyless EPA Envirofacts UV-index
# fallback (app/conditions/epa_uv.py) when OPENUV_API_KEY is unset.
LHC_ZIP = "86403"

# ── Human-facing "where this number comes from" source pages (v4.7 conditions
# provenance, Casey 2026-07-05). Rendered as the click-through on each conditions
# tile so every value is traceable. Temp + Wind share the NWS KHII observation
# page; Water is the USBR RISE Parker Dam item (6127) — a different source from
# temp/wind, by design; UV links to the EPA UV-index page. Sunset is computed
# astronomically (app/conditions/sun.py) so it has no external source page and
# stays unlinked (an honest omission rather than a fabricated link).
SOURCE_PAGE_NWS_KHII = "https://forecast.weather.gov/data/obhistory/KHII.html"
SOURCE_PAGE_RISE_WATER_TEMP = "https://data.usbr.gov/rise/#/items/6127"
SOURCE_PAGE_UV = "https://www.epa.gov/sunsafety/uv-index-1"
