# "Today in Havasu" Conditions Panel + Protective Alerts — Design Memo

> **Status:** design only; no implementation, no migration. Output of the Opus-4.7-feature-locking design pass on 2026-05-14.
> **Source:** Opus 4.7 feature suggestions #1 ("Today in Havasu" conditions panel + chat awareness) and #8 (opt-in protective alerts) — both committed to V1 scope. Full feature text at `outputs/opus_47_feature_suggestions_response.md` §1 and §8.
> **Audience:** Cowork primary + Casey; future implementation-lane author (Cursor / CC).
> **Companion docs:** `docs/maintainability/place_model_design.md` (voice + structure anchor), `docs/maintainability/background_job_infrastructure_decision.md` (Option A LOCKED — this memo designs within that envelope), `docs/maintainability/account_lite_v01_design.md` (User schema + Resend flow that alerts plug into), `app/db/models.py` (Provider schema that alert venue-context mapping reads), `app/contrib/rate_limiter.py:39` (`SourceLimiter` pattern that external-conditions fetchers reuse), `app/main.py:246` (the existing async-loop pattern that scheduled fetches mirror).

---

## §1 Why these features exist (problem statement)

The directory's strategic bet — locked at pivot §1 and re-validated by the Opus 4.7 review at `outputs/opus_47_feature_suggestions_response.md` — is hyperlocal-context-depth. The product wins when it behaves like a thoughtful local who knows the weather, the lake, and the crowds; it loses when it looks like a generic Yelp shard for one city. The two features in this memo are the most direct expression of that bet on the conditions axis. Together they capture the texture moat that the strategic deck names by hand-waving and that Opus #1 + #8 named with concrete user moments: "is it a good lake day?", "is it too hot to hike Sara Park?", "AQI is climbing; here are three of your favorites that are indoor."

The "Today in Havasu" conditions panel (Opus #1) is a homepage strip plus a chat-accessible context layer showing real-time signals that actually drive Havasu decisions: lake surface temperature, channel wind, UV index, heat advisory level, air quality from AirNow, sunset and civil twilight, lake water level if a USGS gauge covers the relevant pool. The value is not the raw data — Google ships weather as a generic widget, the National Weather Service ships forecasts as raw JSON, AirNow ships AQI as a national map — the value is the *bundling*. A Lake-Havasu-specific decision needs lake temp **and** channel wind **and** UV **and** AQI **and** sunset, synthesized into one read. None of the generics do that synthesis; no national platform ever will, because the bundle that matters is location-specific. Phoenix needs different bundles. Boston needs different bundles. Havasu's bundle is the moat.

Protective alerts (Opus #8) compound on top. Once the conditions panel exists, the data pipeline that powers it can also fire alerts when conditions cross user-relevant thresholds: heat advisory issued, AQI deteriorating, lake hazard posted by the city, major-event traffic spilling into a known-crowded district. The alert itself is tone-defined — calm, protective, never promotional, no engagement-loop language. The differentiator vs. the National Weather Service push alert is the *venue context*: a generic push says "heat advisory in effect"; the Havasu alert says "heat advisory in effect through Saturday 8 PM — three of your favorites are indoor: Mudshark, the library, the Shops." The texture is the entire pitch.

The two features compound twice over. First, #1 unlocks #8 cheaply — alerts read from the same `external_conditions_cache` table the panel reads from. Second, both features unlock the heat-aware ranking shift that Opus #2 contemplates (`outputs/opus_47_feature_suggestions_response.md` §2): once the conditions cache exists, the chat tier-2 ranker can shift toward indoor venues without re-fetching anything. The marginal cost of #2 drops sharply once #1 + #8 land. The marginal cost of every future condition-driven feature drops the same way.

---

## §2 The external data sources

Each subsection covers: API endpoint, auth model, rate-limit posture, refresh frequency, what fields are extracted, what falls through to either "unavailable" UI or an operator-typed fallback.

### §2.1 AirNow (air quality / AQI)

- **API:** `https://www.airnowapi.org/aq/observation/zipCode/current/` (per the AirNow API docs at `https://docs.airnowapi.org/`).
- **Auth:** API key — free registration at `docs.airnowapi.org`. Single global key in `AIRNOW_API_KEY` env.
- **Rate limits:** 500 requests/hour per key per the AirNow ToS (verify before launch; the public docs page lists this number but operator should confirm). At our refresh cadence (30 min × 3 zip codes = 6 requests/hour) we are nowhere near the cap.
- **Refresh frequency:** every 30 minutes via Railway scheduled job. AQI moves on roughly that timescale; faster polling buys nothing and burns budget.
- **Coverage:** Lake Havasu City zip codes — primary `86403`, secondaries `86404` and `86406`. Open question §10 Q5 covers whether all three are worth polling or whether `86403` is sufficient for the city center.
- **Fields extracted:** `aqi_value` (int 0-500), `category_name` (one of "Good", "Moderate", "Unhealthy for Sensitive Groups", "Unhealthy", "Very Unhealthy", "Hazardous"), `dominant_pollutant` ("PM2.5", "Ozone", etc.), `reporting_area`, `observed_at`.
- **Fallback:** on fetch failure, panel renders "AQI: unavailable" with `last_known_value` timestamped. Alerts dispatch suppresses when AQI is in degraded state.

### §2.2 NWS (weather, heat advisory, sunset / civil twilight)

- **API:** `https://api.weather.gov/points/{lat},{lng}` resolves the gridpoint; subsequent calls hit `/gridpoints/{office}/{gridX},{gridY}` for forecast and `/alerts/active?point={lat},{lng}` for active alerts.
- **Auth:** none. NWS asks every consumer to identify itself via `User-Agent: havasu-chat (casey@havasu-chat.example.com)` — they reserve the right to block UAs they can't contact. Set this in the fetcher.
- **Rate limits:** no published hard cap; the docs say "be reasonable." We are.
- **Refresh frequency:** every 30 min for current conditions; daily at 04:00 local for the multi-day forecast; every 15 min for `/alerts/active` so heat/wind/lake advisories don't lag (alerts are the trigger surface for §5).
- **Fields extracted:** `temperature_f`, `heat_index_f`, `wind_speed_mph`, `wind_direction`, `relative_humidity`, `short_forecast` (e.g. "Hot and Sunny"), `uv_index` (if available; NWS exposes UV through the forecast object inconsistently — see §10 Q3), `active_alerts` (list of NWS alert objects — type, severity, headline, `effective`, `expires`), `sunrise`, `sunset`, `civil_dawn`, `civil_dusk`.
- **Fallback:** on fetch failure, panel renders cached values with a "Updated >1h ago" badge. NWS uptime is generally fine; outages are rare.

### §2.3 USGS Water Services (lake elevation, discharge, gauge water temp)

- **API:** `https://waterservices.usgs.gov/nwis/iv/` for instantaneous values; format `?sites={SITE_ID}&parameterCd=00010,00065,00060&format=json`.
- **Auth:** none.
- **Rate limits:** no published hard cap; conservative defaults apply.
- **Gauge IDs:** the specific Lake Havasu gauges need operator confirmation — see §10 Q1. Candidates: Parker Dam gauge (downstream control), the Bill Williams River inflow gauge, and any in-lake gauge USGS maintains. Without confirmed gauge IDs we cannot promise water_elevation_ft in V1.
- **Refresh frequency:** hourly. Lake elevation does not move on shorter timescales for our purposes.
- **Fields extracted:** `water_elevation_ft` (param `00065`), `discharge_cfs` (param `00060`), `gauge_water_temp_c` (param `00010`, if the gauge supports it — many do not).
- **Fallback:** on fetch failure or unconfirmed gauge, panel either hides the tile or labels it "Lake level: data pending." See §10 Q1.

### §2.4 Lake surface temperature (the hardest source)

NWS does not expose lake surface temperature for Lake Havasu directly. The candidate sources, in declining order of cleanness:

1. **NOAA NDBC** (National Buoy Data Center) if a buoy exists nearby — research says no NDBC buoy currently sits in Lake Havasu itself. Likely dead end.
2. **USGS gauge water temp** (§2.3) if any Lake Havasu gauge reports parameter `00010` — this is the cleanest automated path if it exists. Operator confirms which gauges report water-temp in §10 Q2.
3. **Scrape Lake Havasu Marina** (or another marina) if they publish water temp on a public-facing page. Brittle, polite-scrape-rate-limited via `SourceLimiter` (§4.2), and subject to layout drift.
4. **Operator-typed fallback** — Layer 5 in the layered-scrape strategy. Casey or a designated marina contact types the current value into the admin form on whatever cadence makes sense (probably weekly in summer, monthly otherwise). Tile renders "Lake temp: estimated, last operator update DATE."
5. **Algorithmic estimate** from ambient air temp + season as last resort. Marked clearly as estimate in the tile.

Recommendation: ship layer 4 (operator-typed) as the V1 default and add layer 2 (USGS gauge) the moment a confirmed gauge surfaces. Lake surface temp is a high-value field — the panel feels half-built without it — but it's also the field most likely to be wrong. Honest staleness labels matter more here than for any other tile.

### §2.5 Lake Havasu City emergency notifications

The City of Lake Havasu publishes emergency notifications (lake closures, hazmat events, road closures, evacuation guidance) via the city website. Whether they expose an RSS feed, a JSON endpoint, or only a human-readable web page needs operator research — see §10 Q4. Candidates: the city's homepage news section, the LHCFD social channels, the Mohave County emergency-management feed.

If a structured feed exists: fetch every 15 min, parse, store in `external_conditions_cache` keyed `lhc_emergency`. If only an unstructured page exists: scrape it daily with conservative polite-scrape rate-limiting via `SourceLimiter` (§4.2), and surface flagged keywords ("closure", "hazard", "advisory", "evacuation") for human review before any alert fires. **Important:** lake-hazard alerts must not fire on a false positive — operator-in-the-loop review for any city-source alert in V1.

---

## §3 Storage schema

Three new tables. Same naming and primary-key conventions as the existing schema (per `app/db/models.py` patterns): `String` UUID PKs for entity tables, `Integer` autoinc for join/log tables, `TZAwareDateTime` for time-window logic.

### §3.1 `external_conditions_cache` table

Single-row-per-source key/value table. The cache layer is two-tiered: an in-memory dict (5-minute TTL) wraps the DB cache; the DB cache TTL determines whether the Railway scheduled job actually needs to re-fetch on its next tick.

```python
class ExternalConditionsCache(Base):
    """Cached payload from one external conditions source.

    One row per source (e.g. 'airnow_86403', 'nws_havasu_grid', 'usgs_havasu_gauge',
    'lhc_emergency'). The 'data' JSON column carries the source's full response so
    downstream readers can extract whichever fields they need without a schema migration
    when the source adds a field. 'ttl_seconds' is the per-source freshness policy;
    'last_error' and 'error_count' drive the circuit-breaker logic in §4.3.
    """

    __tablename__ = "external_conditions_cache"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(TZAwareDateTime(), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)
```

Reads: a small `app/conditions/cache.py` module exposes `read_source(source) -> dict | None`. Short-lived in-memory cache (5-min TTL, process-local dict) wraps DB reads. On cache miss, DB lookup; on DB miss or stale row (older than `ttl_seconds`), reader either returns the stale row with `is_stale=True` to caller (panel renders staleness badge) or returns `None` if the row is missing entirely.

Writes: only the scheduled-job fetcher writes. UPSERT pattern keyed on `source`. Every successful fetch zeros `error_count` and clears `last_error`.

### §3.2 `alert_subscriptions` table

User-bound subscription rows. Plugs into the `User` table that account-lite v0.1 (`docs/maintainability/account_lite_v01_design.md` §4.1) introduces. Without account-lite, this table cannot exist — see §12 sequencing.

```python
class AlertSubscription(Base):
    """User's opt-in for one alert type with one delivery channel.

    A user opts into each alert_type independently. Snooze (paused_until)
    is per-subscription, not per-user, so a user can mute heat alerts for a week
    while keeping AQI alerts active. Unique on (user_id, alert_type) — one row
    per user per alert type; delivery_channel mutates in place.
    """

    __tablename__ = "alert_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "alert_type", name="uq_alert_subscriptions_user_type"),
        Index("ix_alert_subscriptions_user_id", "user_id"),
        Index("ix_alert_subscriptions_alert_type", "alert_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Allowed values: 'heat_advisory' | 'aqi_alert' | 'lake_hazard' | 'event_traffic'.
    # CHECK constraint at DB level.
    delivery_channel: Mapped[str] = mapped_column(String(8), nullable=False, default="email")
    # Allowed values: 'email' | 'sms' | 'both'. SMS deferred to V1.5 per §10 Q6.
    paused_until: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
```

### §3.3 `alerts_dispatched` table (audit log)

Every dispatch attempt — successful or otherwise — gets a row. Enables (a) the 6-hour dedupe logic in §5, (b) operator-side investigation of "did the user actually get the alert?", (c) future analytics on which alerts fire most often.

```python
class AlertDispatched(Base):
    """One audit row per alert send attempt.

    Suppressed dispatches (dedupe window active, subscription paused, condition
    recovered between trigger and dispatch) also get a row — delivery_status
    captures the disposition.
    """

    __tablename__ = "alerts_dispatched"
    __table_args__ = (
        Index("ix_alerts_dispatched_subscription_id", "subscription_id"),
        Index("ix_alerts_dispatched_dispatched_at", "dispatched_at"),
        Index("ix_alerts_dispatched_subscription_dispatched", "subscription_id", "dispatched_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alert_subscriptions.id"), nullable=False
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    # The condition snapshot that fired the trigger — NWS alert object, AQI
    # category + value, city emergency-feed item, etc. Stored so post-hoc
    # debugging ("why did this alert fire?") doesn't require re-fetching.
    dispatched_at: Mapped[datetime] = mapped_column(
        TZAwareDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )
    delivery_status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Allowed values: 'sent' | 'failed' | 'suppressed_dedupe' | 'suppressed_paused'.
    body_snippet: Mapped[str | None] = mapped_column(String(240), nullable=True)
    # First ~200 chars of the rendered email body. For debugging only.
    resend_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Resend's message id on successful send; null when failed/suppressed.
```

---

## §4 Fetch infrastructure

Per the background-job decision locked at `docs/maintainability/background_job_infrastructure_decision.md` §5 (Option A — Railway scheduled jobs + FastAPI `BackgroundTasks` with retry wrapper), the conditions fetcher does not introduce new infra primitives. It reuses three patterns the codebase already uses or plans to use.

### §4.1 Railway scheduled-job service

New script at `scripts/fetch_external_conditions.py`, invocable as `python -m scripts.fetch_external_conditions [--source SOURCE]`. Railway runs it on cron:

- Every 30 min: AirNow, NWS current conditions.
- Every 15 min: NWS `/alerts/active`, LHC emergency feed (if structured).
- Hourly: USGS water services.
- Daily 04:00 local: NWS multi-day forecast.

Either one parameterized Railway service driven by `$JOB_NAME` (one cron line per source) or one wide service that fetches all sources on a 15-min tick and lets per-source TTL gate work. Recommendation: the wide service. Fewer Railway line items; simpler to reason about; each source's `ttl_seconds` is the actual rate gate, so over-fetching is impossible. Per-source skip logic checks `fetched_at + ttl_seconds > now` and short-circuits.

### §4.2 Per-source rate limiting via `SourceLimiter`

Each source instantiates a `SourceLimiter` (`app/contrib/rate_limiter.py:39`) configured to that source's published rate-limit posture. The constants live in a new `app/conditions/sources.py` module alongside the per-source fetch functions:

```python
AIRNOW_LIMITER: Final = SourceLimiter("airnow", qps=0.5, max_retries=3)
NWS_LIMITER: Final = SourceLimiter("nws", qps=1.0, max_retries=3)
USGS_LIMITER: Final = SourceLimiter("usgs", qps=0.5, max_retries=2)
LHC_EMERGENCY_LIMITER: Final = SourceLimiter("lhc_emergency", qps=0.2, max_retries=2)
```

The QPS values are conservative on purpose — we are nowhere near the published limits and the polite default protects against an accidental tight loop in dev. The retry behavior is inherited from `SourceLimiter.call_with_retry` (`app/contrib/rate_limiter.py:113`): on 429 or 5xx the limiter retries with exponential backoff up to `backoff_cap_s`, then returns the final response to the caller. Per the locked decision at `app/contrib/rate_limiter.py:11-14`, the limiter does **not** raise on exhaustion — the conditions fetcher's caller decides how to envelope the failure (write `last_error` to the cache row, increment `error_count`, exit cleanly).

### §4.3 Failure handling + circuit breaker

Each source fetch is wrapped in a try/except. On exception or non-2xx final response:

1. Increment `external_conditions_cache.error_count`.
2. Write the truncated error to `last_error`.
3. Set `last_attempt_at = now` but leave `fetched_at` unchanged (so the panel's staleness badge keeps counting from the last *successful* fetch).
4. Do not raise — the next source in the same job run continues.

Circuit-breaker logic: when `error_count >= 3`, the source skips its next scheduled fetch attempt for `min(error_count * 1h, 6h)`. The script logs the skip with the structured-log shape `SourceLimiter` already emits at `app/contrib/rate_limiter.py:131-141`. On recovery (next successful fetch), `error_count` resets to zero.

The cache reader (§3.1) checks `error_count` indirectly via `fetched_at` age — if a source's last successful fetch is older than 2x its `ttl_seconds`, the panel renders the tile in a degraded state.

### §4.4 Why not asyncio loop instead

The existing `_hourly_cleanup_loop` pattern (`app/main.py:246`) is the cheaper alternative — run the fetcher inside the web process via `asyncio.create_task` in `lifespan`. We do **not** use it for conditions fetching for two reasons.

First, the conditions fetcher does outbound HTTP to four external services on every tick. Doing that work inside the web process competes with request-handling for the thread pool — the audit's §5.1 connection-pool concern at ~200 concurrent users gets worse when scheduled fetches share the pool. Second, the `_hourly_cleanup_loop` does a single fast DB UPDATE; conditions fetching does up to a dozen HTTP calls per tick, each subject to a multi-second timeout. The wrong tail-latency event in a fetcher can knock out a request thread.

`_hourly_cleanup_loop` remains the right pattern for cache-warming and other purely in-process schedulers — see `docs/maintainability/background_job_infrastructure_decision.md` §6.3. Conditions fetching is the wrong shape for it.

---

## §5 Alert dispatch infrastructure

Trigger evaluation is a separate Railway scheduled job — `scripts/evaluate_and_dispatch_alerts.py`, run every 15 min. The pipeline:

1. **Read the cache.** Pull current rows from `external_conditions_cache` for every source that any alert type depends on. Cheap — fewer than ten rows total.
2. **Evaluate triggers.** For each alert type, evaluate its threshold against the current data. Thresholds (§10 Q3 covers operator review of these):
   - `heat_advisory`: fires when NWS `/alerts/active` contains an item where `event` matches `Heat Advisory|Excessive Heat Warning|Heat Watch`. (§10 Q3: should also fire on bare `heat_index_f >= 110` even without an NWS alert? Recommendation: no — NWS-issued advisory is the cleaner signal and reduces false positives.)
   - `aqi_alert`: fires when AirNow `category_name` for `86403` is not in `{"Good", "Moderate"}` — i.e. "Unhealthy for Sensitive Groups" or worse.
   - `lake_hazard`: fires only on an `lhc_emergency` cache row whose payload matches keywords (`closure`, `hazard`, `advisory`, `evacuation`) AND has been operator-approved (§2.5 in-the-loop check). V1 is conservative — false positives on lake hazards are higher reputational risk than missed sends.
   - `event_traffic`: fires when the operator-curated `events` table has an active row tagged `traffic_impact=true` (this row source is operator-typed, not API-fetched — see §10 Q7).
3. **Match subscriptions.** For each fired trigger, `SELECT * FROM alert_subscriptions WHERE alert_type = ? AND (paused_until IS NULL OR paused_until < now)` joined to `users` WHERE `is_active = true`.
4. **Dedupe check.** For each candidate `(subscription_id, alert_type)`, check `alerts_dispatched` for any row in the last 6 hours with `delivery_status = 'sent'`. If found, skip and record a `delivery_status = 'suppressed_dedupe'` row. (§10 Q5: 6h reasonable? Recommend yes — heat advisories typically run 6-12 hours; we want one alert at the start, optionally one at extended hours; AQI events run similar timescales.)
5. **Render the body.** Per-alert-type Jinja template under `app/alerts/templates/`. The template invokes the venue-context mapping (§6) to insert the user's favorites into the body.
6. **Dispatch via Resend.** Reuse the `app/auth/email_sender.py` Resend integration that account-lite ships (see `docs/maintainability/account_lite_v01_design.md` §9). For V1, the dispatch is a synchronous Resend call inside the scheduled-job process — the job is already a background job; we are not running it on a request thread. Failures are logged + retried via `SourceLimiter`-equivalent retry logic, then recorded as `delivery_status = 'failed'`. No `Outbox` table for alerts in V1 — the 15-min cadence retries naturally on next tick, and the 6-hour dedupe window means we won't double-send if a transient failure clears.
7. **Audit log.** Every attempt (sent, failed, suppressed) writes a row to `alerts_dispatched`.

Conservative posture in V1: the script is the dispatch boundary. No alerts fire from inside the web process; no alerts fire from inside the conditions fetcher. The clear separation makes the system easy to disable in an emergency (Casey toggles the Railway cron schedule to off) and easy to dry-run (run the script with `--dry-run` flag — log what would have been sent, write nothing).

---

## §6 Condition-trigger → venue-context mapping

This is the texture moat. Generic NWS push alerts say "heat advisory active." Havasu alerts say:

> Heat advisory in effect through Saturday 8 PM. Three of your favorites are indoor:
>
> - **Mudshark Brewing** — downtown, open 11 AM-9 PM
> - **Lake Havasu Public Library** — free, open 9-5 today
> - **The Shops at Lake Havasu** — indoor, A/C

The mapping requires two pieces of data that don't yet exist in the schema and a third that does. **First**, the `Provider.heat_exposure` field — operator-tagged values `indoor` / `shaded` / `outdoor` / `water_adjacent` — which Opus #2 introduces (`outputs/opus_47_feature_suggestions_response.md` §2). Today the `Provider.attributes` JSON (`app/db/models.py:97`) is the catch-all for structured tags; a V1.0 implementation can read `attributes.heat_exposure` until Opus #2 promotes it to a first-class column. **Second**, the `UserFavorite` table from account-lite v0.1 (`docs/maintainability/account_lite_v01_design.md` §4.4) — gives us `(user_id, entity_type, entity_id)` rows we can query for "what does this user care about?" **Third**, the existing `Provider` fields for name, hours, district which already power the profile page.

Per alert type, the mapping shape:

- **`heat_advisory`:** find `UserFavorite` rows for this user where the linked Provider has `attributes.heat_exposure in ('indoor', 'shaded')`. Take the top 3-5 by some ranking signal (recently-favorited first, or `featured=True` first, or Hava's-pick-tagged first — see §10 Q4 for the operator call). If the user has fewer than 3 indoor favorites, optionally fall back to top indoor Providers citywide in the user's favorited categories.
- **`aqi_alert`:** same as heat — indoor venues from favorites. (AQI deterioration is bad for the same reasons heat is — outdoor activity becomes unwise.)
- **`lake_hazard`:** find `UserFavorite` rows where the linked Provider has `attributes.heat_exposure != 'water_adjacent'`. Surface alternatives that are NOT water-adjacent.
- **`event_traffic`:** find `UserFavorite` rows where the linked Provider's `district` does NOT match the affected district from the event row. Surface alternatives in unaffected districts.

The pattern is the same shape four times: "find favorites that match the inverse of the hazard condition, render the top 3-5." Implementation lives in `app/alerts/venue_context.py` as four small functions, plus a shared `top_alternative_venues(user, predicate, limit)` helper.

**Cold-start behavior.** A user who has just signed up and favorited zero venues gets an alert with no venue list — body falls back to a one-paragraph version: "Heat advisory in effect through Saturday 8 PM. We'll surface indoor options when you favorite a few places." This is honest and matches the calm-by-construction tone.

---

## §7 Chat awareness wiring

The chat's tier 2 / tier 3 pipeline (per `app/chat/unified_router.py`, `app/chat/tier2_formatter.py`, `app/chat/tier3_handler.py`) needs to read current conditions when answering location- or activity-shaped queries. The plumbing is additive, not replacement.

**Tier 2 (structured retrieval).** The existing tier-2 query builders accept a `conditions_context: dict | None` parameter — built once at the top of the chat request from `read_source(...)` calls against the cache (§3.1). When `conditions_context['heat_advisory_active']` is true, the ranker shifts toward Providers with `attributes.heat_exposure in ('indoor', 'shaded')` for activity-shaped queries ("kid activities", "things to do this afternoon"). When `conditions_context['aqi_category'] not in ('Good', 'Moderate')`, the same shift applies for any outdoor-leaning category. This is the same time-aware heuristic the existing code already uses for breakfast-vs-bars by hour — Opus #2's pattern, keyed on conditions instead of clock.

**Tier 3 (LLM synthesis).** The tier-3 prompt builder (`app/chat/tier3_handler.py`) gains a "current Lake Havasu conditions" preamble injected near the top of the system prompt. The preamble is 3-5 lines:

> Current conditions in Lake Havasu City as of HH:MM AM/PM:
> - Air: 108°F, heat index 115°F. **NWS heat advisory in effect until 8 PM.**
> - Lake: surface 84°F (estimated), wind 12 mph from the south.
> - Air quality: Moderate (PM2.5).
> - Sunset: 7:42 PM.

The LLM uses this naturally — answers to "is it a good lake day" cite the temps and wind; answers to "where should we eat tonight" prefer indoor venues without needing a rule; answers to "is it too hot to hike Sara Park" warn honestly. Crucially, the preamble carries the same staleness honesty the panel renders — if a source is stale, the preamble says so ("AQI data unavailable") and the LLM has explicit context not to invent numbers.

**Confabulation guardrails.** Conditions data is the kind of thing LLMs invent confidently when missing. The HALT-3 close-out work (audit Gap #2) matters here. The tier-3 prompt explicitly tells the model: do not state a temperature, AQI value, or advisory status that is not in the conditions preamble; if asked and the preamble lacks the field, say "I don't have current data on that."

---

## §8 Homepage display

A horizontal strip near the top of the homepage (above the fold, below the global header). On desktop: 6-8 condition tiles in a row; on mobile, a vertical stack. Each tile renders one signal:

- **Current temp + heat index** — color-coded green/yellow/red by heat-index band.
- **Lake water temp** — labeled clearly as `(estimated)` or `(operator-updated DATE)` when the source is layer 4 of §2.4.
- **Wind speed + direction** — directional arrow plus speed.
- **AQI** — category text + dominant pollutant ("Moderate — PM2.5"); color-coded per EPA palette.
- **Sunset time** — flips to "Civil twilight: HH:MM" within the final hour of daylight.
- **Active advisory** — only renders when NWS has an active alert; otherwise tile is absent (avoid empty-state noise).
- **Water level** — only when USGS gauge is confirmed (§10 Q1); otherwise tile absent.

**Staleness.** Each tile carries an "Updated N min ago" badge in small text. When `now - fetched_at > 2 * ttl_seconds`, the badge flips to "Updated >Nh ago" in muted color and the value renders in muted color too. Honest. The user knows when to trust it and when not to.

**Tap-to-expand.** Mobile tiles expand on tap to show the supporting detail (full forecast, hourly temp, the full text of an NWS alert). Desktop renders the detail in a hover-popover. Both reuse the existing component infrastructure — no new render layer.

**Where the panel lives in templates.** New partial `app/templates/_conditions_panel.html`, included from `app/templates/home.html` near the top. The partial is rendered server-side from a small view-model assembled in `app/home/conditions_view_model.py` — same pattern as the Provider profile view-model at `app/providers/view_models.py`.

---

## §9 Migration strategy

Single Alembic migration adds three tables — `external_conditions_cache`, `alert_subscriptions`, `alerts_dispatched` — plus the indexes in §3. The migration is **purely additive**:

- No existing table is touched.
- No data backfill — there are no historical conditions and no existing subscriptions to migrate.
- Reversible — `downgrade()` is three `op.drop_table()` calls.

CHECK constraints to declare at the DB level (operator-curated string enums; same pattern as `ck_providers_verification_method` per `app/db/models.py:115-119`):

- `alert_subscriptions.alert_type IN ('heat_advisory', 'aqi_alert', 'lake_hazard', 'event_traffic')`.
- `alert_subscriptions.delivery_channel IN ('email', 'sms', 'both')`.
- `alerts_dispatched.delivery_status IN ('sent', 'failed', 'suppressed_dedupe', 'suppressed_paused')`.

The migration depends on the `users` table from account-lite v0.1 — the `alert_subscriptions.user_id` FK requires it. Per §12 sequencing, this migration ships after account-lite and after the background-job infrastructure decision lands.

Plugs into the existing Resend integration that account-lite introduces (`docs/maintainability/account_lite_v01_design.md` §9) — same `app/auth/email_sender.py` module gains an `send_alert_email(user, alert_type, body)` sibling function. Same `RESEND_API_KEY` env var, same verified sender, new email templates under `app/alerts/templates/`.

---

## §10 Open questions for Casey

1. **USGS gauge ID for Lake Havasu.** Which USGS gauge specifically covers the relevant lake pool — Parker Dam, the Bill Williams inflow, or an in-lake gauge? The script needs at least one confirmed `SITE_ID`. Recommendation: operator opens `https://waterdata.usgs.gov/az/nwis/current` and identifies the gauges; we wire whichever reports `00065` (gage height) for elevation and `00010` (water temp) if any.

2. **Lake surface temperature source.** Does Lake Havasu Marina (or any other marina) publish water temp on a public-facing page we could scrape politely? If not, V1 ships with operator-typed lake temp (Layer 4 of §2.4) — Casey enters the value via the admin form on whatever cadence makes sense. Estimate: weekly in summer, monthly other seasons.

3. **Heat-advisory trigger threshold.** Fire on NWS-issued heat advisory only? OR also on bare `heat_index_f >= 110` even without an NWS alert? OR both (whichever fires first)? Recommendation: NWS-issued only. NWS is the authority; firing on a private threshold risks contradicting them and reducing trust. Confirm.

4. **Lake Havasu City emergency-notification feed.** Does the city publish an RSS feed, a JSON endpoint, a Twitter/X feed, a Nixle feed, or only a human-readable page? Operator research needed — `https://www.lhcaz.gov/` and similar. If only an unstructured page, V1 ships `lake_hazard` alert as operator-curated only (Casey manually inserts city-feed events into an `events` table tagged `traffic_impact=true` / equivalent).

5. **Alert dedupe window.** §5 step 4 proposes 6 hours. Reasonable, or shorter/longer? My read: 6h fits most NWS heat advisory durations (typically 8-14 hours so we send once at the start) and AQI deterioration timescales. A 12h window would suppress the "still active at hour 13" follow-up some users want; a 3h window risks duplicate sends within a single advisory event. Recommend 6h; confirm.

6. **SMS dispatch — V1 or V1.5?** Recommendation below in §11 — defer to V1.5. The `alert_subscriptions.delivery_channel` column ships with `'sms'` and `'both'` in the CHECK constraint enum so V1.5 is a code change, not a migration. Twilio integration cost + per-message cost + phone-number verification UI is real V1 scope creep for low marginal user value (email arrives instantly on phones with mail notifications enabled). Confirm V1.5 deferral.

7. **Event-traffic alert source.** §5 step 2 routes `event_traffic` through the operator-curated `events` table with a `traffic_impact=true` tag. The current `Event` model at `app/db/models.py` does not have such a tag — adding it is a small migration. Alternative: an entirely operator-typed `traffic_advisories` table separate from events. Recommendation: add the tag to `Event`; one-table is simpler, and traffic-impacting events ARE events.

8. **AirNow zip-code coverage.** Single zip (`86403`) or all three (`86403`, `86404`, `86406`)? Recommendation: single zip in V1 — AirNow data does not vary meaningfully across Lake Havasu City zips at the EPA's monitor resolution. Confirm.

9. **Favorites-source ranking for venue context (§6).** When the user has more than 3-5 indoor favorites, which subset is featured? Most-recently-favorited? Hava's-pick-tagged first? Operator preference?

10. **AirNow API key registration.** Operator action: Casey signs up at `https://docs.airnowapi.org/` for a key. What email to register under (founder personal vs. business)?

---

## §11 Effort estimate

Sub-lanes and effort sizing (mirrors the place-model memo `S`/`M`/`L` shape):

- **Schema migration + three ORM models (`ExternalConditionsCache`, `AlertSubscription`, `AlertDispatched`):** S (hours). Three tables, all additive, no backfill.

- **Per-source fetchers (`app/conditions/sources.py`) + AirNow + NWS + USGS clients:** M (1-2 days). Four HTTP clients wrapped in `SourceLimiter`. NWS gridpoint resolution adds one extra call per refresh; not material.

- **`scripts/fetch_external_conditions.py` + Railway cron service wiring:** S (hours). Wide-service shape per §4.1.

- **Cache reader module (`app/conditions/cache.py`) with two-tier (in-memory + DB) caching:** S (hours).

- **Conditions panel partial + view-model + homepage integration:** M (1-2 days). Mostly template + CSS; the data shape is fixed by the cache.

- **Chat tier-2 ranker shift on heat/AQI:** S-M (1 day). Wires `conditions_context` into the existing tier-2 ranker; the ranker is sensitive code (the chat tier-2 code is dense).

- **Chat tier-3 preamble injection:** S (hours). Adds the conditions block to the system prompt; matches existing preamble patterns.

- **Alert dispatch script (`scripts/evaluate_and_dispatch_alerts.py`):** M (2 days). Trigger evaluation + subscription matching + dedupe + per-type body rendering + Resend dispatch + audit logging.

- **Per-alert-type body templates + venue-context mapping (`app/alerts/venue_context.py`):** M (1-2 days). Four templates, four mapping functions sharing a helper; depends on `attributes.heat_exposure` being readable on Provider (Opus #2 dependency — see §12).

- **User-facing alert subscription UI (`/account/alerts`):** M (1-2 days). Toggle per alert type, snooze date-picker, opt-in/opt-out wiring. Plugs into the account-lite `/account` shell.

- **Lake-temp operator admin form:** S (hours). Single number input on an admin page; writes to `external_conditions_cache` row keyed `lake_temp_operator`.

- **Tests:** M (2 days). Fetcher unit tests with mocked HTTP; cache TTL behavior; trigger evaluation; dedupe; template rendering; end-to-end dispatch with mocked Resend.

**Total: 7-9 engineering days of focused work**, dispatchable as 2 parallel lanes:

- **Lane A — External-conditions infrastructure + homepage panel + chat wiring.** Roughly 4-5 days. Self-contained; depends only on the migration landing.
- **Lane B — Alert dispatch + subscription UI + venue-context mapping.** Roughly 3-4 days. Depends on Lane A's cache table existing, on account-lite shipping (User + UserFavorite tables), and on the `attributes.heat_exposure` field being populated for at least a sample of Providers (Opus #2 partial dependency — see §12).

Lane B can start once Lane A's schema is merged; the two lanes run in parallel from there.

---

## §12 Sequencing

**Lands after:**

- **Place model** (`docs/maintainability/place_model_design.md`) — alerts reference favorites which reference Providers + Places; the entity layer must exist first.
- **Account-lite v0.1** (`docs/maintainability/account_lite_v01_design.md`) — `User`, `UserFavorite`, and the Resend integration are all required surfaces.
- **Background-job infrastructure decision** — Option A is locked but the patterns (Railway cron, `BackgroundTasks` retry wrapper, `Outbox` for must-not-lose) need to exist as reusable primitives before this lane is dispatched.
- **Opus #2 (indoor/shaded/outdoor tagging)** at least partial — the venue-context mapping in §6 reads `Provider.attributes.heat_exposure`. If Opus #2 hasn't tagged anything yet, alerts ship with the cold-start fallback (§6) for every user, which is acceptable but blunt. Recommendation: tag the top ~30 Providers by traffic before alerts dispatch ships, so the texture moat actually fires.

**Lands before:**

- **Chat polish phase / launch** — the conditions preamble in tier 3 is one of the highest-leverage chat changes available; it transforms answer quality on activity-shaped queries. Landing this before launch is worth one full sprint slip if needed.
- **Any further alert types** — V1.5 alert ideas (event reminders, snowbird-return greeter, sponsor-specific alerts) extend the `alert_type` enum and the dispatch script; the framework here is the foundation.

If schema migrations are batched into a single "Phase 2 schema landing" PR (Place model + account-lite + image storage + this lane), the four can ship as one Alembic migration with independent ORM additions. Coordinate with the Place model and account-lite implementation-lane authors before splitting or batching.

---

## §13 What we explicitly DON'T build in V1

Calling these out so the implementation lane doesn't over-scope.

- **SMS alerts.** Email-only in V1. Twilio integration + per-message cost + phone-number-verification UI + opt-in compliance is V1.5 scope. The schema already accommodates SMS via the `delivery_channel` enum — flipping it on is a code lane, not a migration.
- **User-defined alert thresholds.** No "alert me when temperature exceeds X" UI. V1 uses operator-set defaults (NWS-issued heat advisory, AirNow non-Good/Moderate). Personalized thresholds are V2 once we see whether anyone asks.
- **Push notifications.** No mobile app, no browser push.
- **Webhooks for third-party integrations.** No outbound webhook to Slack/Discord/Zapier when a condition fires. The audience for this is engineers, not the directory's actual users.
- **Historical conditions data.** Only current state matters for V1. We do not store yesterday's AQI or last week's lake temp. The `external_conditions_cache` table is single-row-per-source by design; no time-series accumulation. Future analytics on historical conditions is a separate data-warehouse lane if it ever becomes interesting.
- **Forecast-based alerts.** Only current-state triggers fire alerts. "Tomorrow will be 115°F — heat advisory likely" is not a V1 alert. Reduces false-positive risk and keeps the alert tone honest ("right now" not "we predict").
- **Conditions-driven category-page banners.** The homepage panel is the only display surface in V1. Putting "Heat advisory in effect — these category-page listings have been re-ranked" banners on the category pages is V1.5.
- **Per-favorite alerts.** "Alert me if this specific business's outdoor seating is unwise" is not a V1 surface. Alerts are city-wide, with favorites used only to populate the alternatives list in the body.
- **Operator-side alert preview / approval flow.** No "Casey reviews and approves each alert before send" workflow. The 15-min dispatch cadence + dedupe + dry-run flag (§5) are the operator safety surfaces. If false-positives become a problem in practice, V1.5 adds approval gating.
- **Multi-language alert bodies.** English only.

---

## §14 Summary

Two compounding features that together capture the conditions axis of the hyperlocal-context-depth strategic bet. Conditions panel (Opus #1) is a homepage strip + chat-tier-2/3 awareness layer that bundles AirNow + NWS + USGS into Havasu-specific decisions; protective alerts (Opus #8) ride on the same fetched data to send calm, venue-aware emails when heat / AQI / lake / event-traffic thresholds cross. Three new tables (`external_conditions_cache`, `alert_subscriptions`, `alerts_dispatched`); one new Railway scheduled-job service for fetching; one new Railway scheduled-job script for dispatch; reuses the `SourceLimiter` rate-limiter, the `BackgroundTasks` + retry wrapper, and the Resend integration from account-lite. Total effort 7-9 engineering days dispatchable as 2 parallel lanes. Ten open questions for operator decision — most are minor / can be deferred to a follow-up taxonomy lock; the load-bearing ones are USGS gauge IDs (§10 Q1), lake temp source (§10 Q2), the city emergency-feed shape (§10 Q4), and SMS-in-V1-or-V1.5 (§10 Q6, recommendation V1.5).

**Next step after this memo is reviewed:** lock the ten open questions, then file Cursor or CC dispatch briefs for Lane A (external-conditions infrastructure + panel + chat wiring) and Lane B (alerts dispatch + subscription UI + venue-context mapping). Lane A unblocks Lane B once its schema is merged.
