# Phase 8 Architecture Design — Conditions Panel + Alerts + Cat-13 Expansion

> **What this is:** architectural-decision-record-level design doc for Phase 8 of the havasu-chat build, per master plan §4 Phase 8 (lines 401-419). Input to the future Cursor dispatch wrapper; the wrapper itself comes later and chains off Phase 7's HEAD SHA + alembic head + the operator prereq findings from `outputs/phase_8_operator_prereq_checklist.md`.
>
> **Author:** Cowork plan-agent, post-`4b159df` (2026-05-20).
>
> **Companion docs:**
> - `docs/maintainability/master_build_plan.md` §4 Phase 8 (scope canon), §7 (risk register #10 heat_exposure dep), §8 OQ #13 (SMS V1.5 deferral)
> - `docs/maintainability/conditions_panel_and_alerts_design.md` (Opus #1 + #8 design memo — this Phase 8 design is the implementation-time refinement of that memo against the actual Phase 3.1 schema + Phase 4.1/4.4 background-jobs infra that have since shipped)
> - `outputs/phase_8_operator_prereq_checklist.md` (operator-side prereqs — AirNow key, USGS gauge 09427500)
> - `outputs/phase_8a_prereq_verification_report.md` (**AMENDMENT AUTHORITY 2026-05-19** — narrowed USGS to single site `09427500` params `00065`+`00054`; dropped Nixle; reframed `lake_hazard` triggers)
> - `outputs/cursor_dispatch_prompt_phase_6_5.md` (the conditions-strip placeholder ships here)
> - `outputs/phase7_handoff_note.md` (chat-conditions-awareness uses `STUB_CURRENT_TEMPERATURE_F` swap surface)
> - `docs/operations/railway_scheduled_jobs_runbook.md` (operator-side spin-up of new scheduled services)

---

## §1 Scope summary + Phase 8 split

Per master plan §4 Phase 8, the canonical scope is *two compounding lanes plus a trust-layer category expansion*:

**Lane A — Conditions infrastructure + display + chat hookup**
- Conditions data fetching: AirNow + NWS + USGS on Railway scheduled jobs (cadence covered in §3)
- `external_conditions_cache` writes from fetchers (table already exists from Phase 3.1; §2 covers what — if anything — needs to evolve)
- `/api/conditions` endpoint reads from cache (§4)
- "Today in Havasu" conditions strip on `home.html` becomes populated — the Phase 6.5 anchored placeholder gets filled in (§4)
- Chat ranking + tier-3 preamble swap: `STUB_CURRENT_TEMPERATURE_F` in `app/core/ranking.py` becomes `read_current_temperature_f()` reading from cache (§4.5)

**Lane B — Alert dispatch + subscription UI + venue-context mapping**
- Alert evaluation job every 15 min: reads cache, evaluates per-`alert_type` thresholds, queries `alert_subscriptions`, dispatches email via Resend (§5)
- Per-alert-type threshold definitions (heat_advisory / aqi_alert / lake_hazard / event_traffic) — §6
- Per-alert dedup via `alerts_dispatched` table (already exists Phase 3.1) — §8
- `/account/alerts` subscription UI on top of Phase 2A account-lite (§7)
- Alert email templates with venue-context mapping from `UserFavorite` (§9)

**Lane C — Cat-13 (Public & Civic Resources) expansion**
- Layer 3 (city open data) primary populator + Layer 5 operator-typed entries
- Library hours / transit / utilities / airport / civic orgs as ENTITY records (§10)

**Recommended sub-phase split:** Phase 8a = Lane A + Lane B; Phase 8b = Lane C. The two phases are independent (Lane C doesn't read from `external_conditions_cache`; Lanes A/B don't read from cat-13 entities). 8b is also smaller — Layer 3 ingest + sub-30-entity Layer 5 entry — and could even fold into a Phase 8.5 micro-dispatch after the conditions/alerts work ships. Master plan §4 calls Phase 8 "2-3 weeks" already; splitting 8a/8b keeps each Cursor session focused.

---

## §2 `external_conditions_cache` table schema

**Phase 3.1 already shipped this table.** Reference `app/db/models.py:1417-1431`:

```python
class ExternalConditionsCache(Base):
    __tablename__ = "external_conditions_cache"
    __table_args__ = (Index("ix_external_conditions_cache_fetched_at", "fetched_at"),)
    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
```

This shape is sufficient for V1, but Phase 8 needs **two additive column extensions** to fulfill the design memo's commitments and the "honest staleness" requirement. These ship as one tiny additive Alembic migration alongside the Phase 8 fetcher code.

### §2.1 Column additions (additive migration)

| Column | Type | Nullable | Why |
|---|---|---|---|
| `last_attempt_at` | `DateTime` (naive UTC) | Yes | Distinguishes "we just tried and failed" from "we last succeeded N minutes ago". The conditions design memo §3.1 specifies this column; Phase 3.1 shipped without it. The conditions strip uses `fetched_at` for the user-visible "Updated 12 min ago" badge; the fetcher + circuit-breaker logic (§3.5) uses `last_attempt_at` for "should we retry on this tick?". |
| `next_attempt_after` | `DateTime` (naive UTC) | Yes | Drives circuit-breaker skip-ahead. When `error_count >= 3`, the fetcher sets `next_attempt_after = now + min(error_count * 1h, 6h)`. On the next scheduled tick, the fetcher checks this column and short-circuits without an HTTP call if `now < next_attempt_after`. Cleaner than re-deriving from `error_count + last_attempt_at` on every read. |

### §2.2 Source key convention

`source` column values (string PK; one row per logical source):

| `source` value | Cadence | TTL seconds | Used by |
|---|---|---|---|
| `airnow_86403` | 30 min | 1800 | conditions strip (AQI tile + source-station attribution chip per §12) + `aqi_alert` evaluator. Data shape: 0..N parameter rows from AirNow (LHC currently single-row O3 from Blythe CA at ~60mi south per `phase_8a_prereq_verification_report.md §12`); store all rows + source-station attribution (`aqi_source_station_name`, `aqi_source_state_code`, `aqi_source_distance_mi`). |
| `nws_current` | 30 min | 1800 | conditions strip (temp + wind + heat-index tiles) + chat `STUB_CURRENT_TEMPERATURE_F` swap |
| `nws_alerts_lhc_zone` | 15 min | 900 | conditions strip (advisory tile, only renders when active) + `heat_advisory` + `lake_hazard` evaluators (AZZ002-zone-scoped per `phase_8a_prereq_verification_report.md §11`; marine surface dropped) |
| `nws_forecast_daily` | daily 04:00 local | 86400 | not displayed in V1; reserved for V1.5 forecast-tile expansion (cheap to populate now since we're already polling NWS) |
| `nws_sunset` | daily 03:00 local | 86400 | conditions strip (sunset tile) |
| `usgs_09427500` | 60 min | 3600 | conditions strip (lake gauge height ft + reservoir storage ac-ft tiles) + `lake_hazard` gauge-drop evaluator |
| ~~`lhc_emergency`~~ | — | — | **DROPPED FROM V1** — Nixle agency 3726 RSS silent since 2021-09-01 per `phase_8a_prereq_verification_report.md` §4 |
| ~~`lake_temp_operator`~~ | — | — | **DEFERRED** — site 09427500 does not report `00010`; water-temp is V1.5 carry (alternate source TBD) |

The single-row-per-source `(source PK)` model means an UPSERT semantics; SQLAlchemy `merge()` plus an explicit `session.commit()` is the cleanest implementation (use `dialect.dialect_specific` `INSERT ... ON CONFLICT` only if profiling shows merge is slow, which it won't at <10 sources).

### §2.3 Indexes + constraints

Existing: `Index("ix_external_conditions_cache_fetched_at", "fetched_at")` — sufficient for read-by-recency.

Phase 8 adds:
- `Index("ix_external_conditions_cache_next_attempt_after", "next_attempt_after")` — fetcher's per-tick skip-check.
- No new CHECK constraints needed; `source` is operator-curated (constant-set seeded at fetcher-module level, not user input).

### §2.4 Read access pattern

Two-tier cache per design memo §3.1: process-local `dict` (5-min TTL, `functools.lru_cache` doesn't fit because we want explicit invalidation; use a simple `_LOCAL_CACHE: dict[str, tuple[datetime, dict]]` with a thread lock). The DB row is canonical; the in-process cache exists only to avoid DB hits for the `/api/conditions` endpoint and the chat hot-path.

```python
# app/conditions/cache.py
def read_source(source: str) -> tuple[dict, datetime, bool] | None:
    """Returns (data, fetched_at, is_stale) or None if source not in cache.

    is_stale = (now - fetched_at) > ttl_seconds. Caller decides what to do
    with stale data — conditions strip renders with muted badge; alert
    evaluator suppresses on stale (per design memo §2.1 fallback rule).
    """
```

### §2.5 Why not extend the schema further?

Considered + rejected:
- **Time-series accumulation** (store every 15-min snapshot). Design memo §13 explicitly excludes this — V1 is current-state only. A future `external_conditions_history` table is a separate data-warehouse lane.
- **Per-zip-code multiple AirNow rows.** Design memo §10 Q8 recommends single zip `86403` for V1 since AirNow doesn't vary meaningfully across LHC zips at EPA monitor resolution. V1.5 may add `airnow_86404` / `airnow_86406` if the panel grows a "neighborhood air quality" surface.
- **Per-source `success_count` for monitoring.** Sentry breadcrumbs (Phase 4.1) carry this; adding a column duplicates monitoring infrastructure.

---

## §3 Conditions fetcher subsystem

### §3.1 File layout

New module tree:

```
app/conditions/
  __init__.py
  cache.py           # read_source() + in-memory wrapper (§2.4)
  sources.py         # SourceLimiter instances + per-source HTTP client functions
  fetcher.py         # orchestrator: fetch_all_sources() called by scripts/fetch_external_conditions.py
  airnow.py          # AirNow API client (HTTP + response parser)
  nws.py             # NWS API client (gridpoint resolution + current + alerts + sunset)
  usgs.py            # USGS OGC client — site 09427500 only; params 00065 + 00054
  # NO lhc_emergency.py / nixle.py in V1 (Nixle dropped per phase_8a_prereq_verification_report.md)

scripts/
  fetch_external_conditions.py  # Railway scheduled-job entry point
  evaluate_and_dispatch_alerts.py  # see §5
```

The `app/conditions/` location matches the convention set by `app/auth/` (Phase 2A), `app/groups/themed_groups.py` (Phase 6.4), `app/home/` (Phase 6.5) — feature-scoped packages rather than dumping into `app/core/`. Reject the `app/background/conditions_fetcher.py` placement option (the question's parenthetical alternative) because there is no `app/background/` package in this codebase — the Phase 4 background-jobs scaffold lives at `app/core/background.py` and is a *helpers* module (with_retry, Outbox state machine) not a *feature* module. Phase 8 conditions get their own feature scope.

### §3.2 Per-source cadence + retry policy

| Source | Cadence (Railway cron) | TTL (DB cache) | HTTP timeout | `SourceLimiter` qps | Retry policy |
|---|---|---|---|---|---|
| AirNow | every 30 min (`*/30 * * * *`) | 1800s | 10s | 0.5 | 3 retries, exponential 1→2→4s |
| NWS current + sunset | every 30 min (offset +5; `5,35 * * * *` to spread Railway load) | 1800s | 10s | 1.0 | 3 retries, 1→2→4s |
| NWS alerts | every 15 min (`*/15 * * * *`, offset +2) | 900s | 10s | 1.0 | 3 retries, 1→2→4s |
| NWS forecast (daily) | once daily at 04:00 local (Phoenix) | 86400s | 15s | 1.0 | 3 retries |
| USGS | every 60 min (`30 * * * *`) | 3600s | 10s | 0.5 | 2 retries, 1→3s (USGS is slow; longer backoff) |
| ~~LHC emergency / Nixle~~ | — | — | — | — | **Dropped from V1** |

**Why different cadences per source rather than uniform 15-min:** the question's prompt asks specifically about this. Three reasons:

1. **Source freshness reality.** AirNow updates AQI on a ~1-hour cadence at the EPA monitor level; polling every 15 min produces 4x duplicate-write churn for no fresher data. USGS updates lake gauge readings on a 15-min instrument cadence but the data USGS itself ingests + republishes runs on a slower beat — hourly polling captures all meaningful change. NWS `/alerts/active` is the one source where 15-min latency matters (heat advisory issuance is the alert-trigger surface; lag-to-dispatch shows up directly in user experience).

2. **Failure isolation.** If the AirNow API rate-limits us, we don't want it to cascade into delayed NWS polls. Per-source cron schedules in Railway means each source's failure mode is bounded — AirNow downtime doesn't push other sources' next-tick deadlines back.

3. **Cost of polling.** AirNow's free tier is 500 req/hr per key; we're at 2/hr per zip code. USGS has no published cap but politeness norms suggest hourly is the right floor. NWS is open but they ask you to be reasonable.

The wide-service alternative from design memo §4.1 (one script tick every 15 min that internally checks per-source TTL) is rejected for Phase 8 in favor of per-source Railway services because:
- Railway scheduled-job services are cheap to spin up + give clearer per-source observability (each service has its own logs + last-run-time dashboard).
- Per-source failure isolation is built-in at the orchestration layer rather than in the script.
- Operator's `docs/operations/railway_scheduled_jobs_runbook.md` already documents the per-service spin-up pattern; multiple-service pattern is well-trodden ground.

**Trade-off accepted:** 6 Railway services (one per logical source) means 6 bill lines. At Railway's per-service free-tier headroom this is negligible; the observability win is worth it.

### §3.3 Script entry-point shape

```python
# scripts/fetch_external_conditions.py
# Usage:
#   python -m scripts.fetch_external_conditions --source airnow_86403
#   python -m scripts.fetch_external_conditions --source nws_alerts_lhc_zone
#   python -m scripts.fetch_external_conditions --all   # for local dev / smoke

# Railway config (one service per source):
#   - Service "havasu-conditions-airnow": start = python -m scripts.fetch_external_conditions --source airnow_86403; cron = */30 * * * *
#   - Service "havasu-conditions-nws-alerts": start = python -m scripts.fetch_external_conditions --source nws_alerts_lhc_zone; cron = */15 * * * *
#   - ...
```

Script main function:

```python
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    sources = _resolve_source_list(args)
    for source in sources:
        # Per-source try/except; one source's failure does NOT abort the loop
        try:
            fetched = fetch_one_source(source)
            logger.info("conditions.fetch_succeeded", extra={"source": source, "rows_written": 1})
        except Exception as exc:
            logger.exception("conditions.fetch_failed", extra={"source": source, "exc": str(exc)})
            # _record_fetch_failure(source, exc) wrote last_error + error_count
    return 0
```

`fetch_one_source(source)` reads the `external_conditions_cache` row (if any), checks `next_attempt_after`, short-circuits if circuit-breaker is open, otherwise dispatches to per-source HTTP client wrapped in `app.core.background.with_retry` per the established Phase 4.1 pattern.

### §3.4 Source-by-source failure isolation

Three layers of isolation per source:

1. **Per-source Railway service.** AirNow rate-limit-induced 429s don't delay NWS polls (different cron schedules; different service processes).
2. **Per-source `SourceLimiter`** in `app/conditions/sources.py` per the existing `app/contrib/rate_limiter.py:39` pattern. `SourceLimiter.call_with_retry` already handles 429 backoff + does NOT raise on exhaustion (locked decision at `app/contrib/rate_limiter.py:11-14`); caller decides envelope.
3. **Per-source try/except in `fetch_one_source`.** Even if `SourceLimiter` retries are exhausted, the exception is caught + logged + recorded in `last_error` + `error_count`; the next source in the script's loop continues. (In the per-source-Railway-service model, there's typically only one source per script invocation, but this defends against the local `--all` smoke path + against operator running multiple sources in one service if they consolidate later.)

### §3.5 Circuit breaker

When `error_count >= 3`:
- Set `next_attempt_after = now + timedelta(hours=min(error_count, 6))`.
- Log structured `conditions.circuit_open` with the standard Sentry breadcrumb from `app.core.background.with_retry`'s helpers.
- Subsequent fetch attempts within the window short-circuit immediately (no HTTP call, just a `logger.info("conditions.circuit_skipped")`).

On recovery (next successful fetch after window expires):
- `error_count = 0`, `last_error = None`, `next_attempt_after = None`.
- The conditions strip's "Updated 12 min ago" badge starts counting from the recovered fetched_at, transparently.

### §3.6 Where `with_retry` fits

`app.core.background.with_retry` (Phase 4.1) wraps the inner HTTP call inside each per-source fetcher:

```python
# Inside fetch_one_source for AirNow
response = with_retry(
    _airnow_fetch_inner,
    source_zip,
    max_attempts=3,
    backoff_initial_s=1.0,
    backoff_multiplier=2.0,
    retry_on=(httpx.HTTPError, httpx.TimeoutException),
    fatal_on=(),  # AirNow auth errors are 401 — non-retryable; SourceLimiter handles via response inspection
)
```

This stacks on top of `SourceLimiter.call_with_retry` (which retries within the HTTP-status layer for 429/5xx) — `with_retry` retries transport errors that escape `SourceLimiter`. Two-layer retry is intentional: `SourceLimiter` knows about HTTP status codes; `with_retry` knows about transport-level transients.

---

## §4 Conditions strip data flow

### §4.1 End-to-end path

```
Railway scheduled job (per source)
  → scripts/fetch_external_conditions.py
    → app/conditions/{airnow|nws|usgs}.py (HTTP via SourceLimiter+with_retry)
      → external_conditions_cache UPSERT keyed on source
                                       ↓
   (cache row sits in Postgres until read)
                                       ↓
User loads /home OR /api/conditions
  → app/api/routes/conditions.py (NEW Phase 8 endpoint)
    → app/conditions/cache.py read_source() — with 5-min in-memory wrap
      → returns {data, fetched_at, is_stale} per source
  → app/conditions/view_model.py (NEW; mirrors app/providers/view_models.py shape)
    → assembles tile-by-tile structure: ConditionsStripViewModel
                                       ↓
home.html template — fills <!-- conditions-strip-anchor --> placeholder (from Phase 6.5)
  with {% include 'components/conditions_strip.html' %}
```

### §4.2 The Phase 6.5 placeholder

Per `outputs/cursor_dispatch_prompt_phase_6_5.md` lines 159-163, Phase 6.5 adds two anchor comments to `home.html`:

```html
<!-- themed-tiles-anchor -->
<!-- conditions-strip-anchor -->
```

Phase 6.5 also adds an empty/placeholder rendered shape — "Conditions data coming soon" text per the operator-locked decision (option a). Phase 8 replaces this content via an anchored edit:

```html
<!-- conditions-strip-anchor -->
{% include 'components/conditions_strip.html' %}
```

The `components/conditions_strip.html` partial is new in Phase 8. The home.py route handler (anchored edit) populates the `conditions_view_model` context variable from `read_source()` calls, exactly the way Phase 6.5 populated the themed-tile data.

### §4.3 Conditions strip view-model + tile shape

```python
# app/conditions/view_model.py
@dataclass(frozen=True)
class ConditionsTile:
    kind: str          # 'temp' | 'aqi' | 'wind' | 'sunset' | 'advisory' | 'lake_level' | 'lake_storage'
    # 'lake_temp' deferred V1.5 (USGS 09427500 has no 00010)
    primary_value: str # "108°F", "Moderate", "12 mph SW", "7:42 PM"
    secondary_value: str | None  # heat index, dominant pollutant ("O3"), etc.
    attribution_chip: str | None  # AQI tile: "from Blythe, CA ~60mi south" per §12
                                  # of phase_8a_prereq_verification_report.md. Other
                                  # tiles: typically None.
    severity: str      # 'good' | 'moderate' | 'warning' | 'severe' | 'neutral'
    staleness_label: str  # "Updated 12 min ago" / "Updated >1h ago" / "Updated yesterday by operator"
    is_stale: bool     # drives muted styling
    detail_text: str | None  # tap/hover expansion (full forecast, NWS alert text)
    visible: bool      # if False, tile doesn't render at all (e.g., no active advisory)

@dataclass(frozen=True)
class ConditionsStripViewModel:
    tiles: list[ConditionsTile]
    any_source_stale: bool       # drives a single subtle indicator at strip level
    rendered_at: datetime         # used for "as of HH:MM" caption
```

The view-model is constructed once per request in the home route. Empty / all-stale state still renders the strip (Phase 6.5 ships the placeholder slot; Phase 8 keeps it visible with degraded indicators rather than hiding entirely).

### §4.4 Mobile vs desktop shapes

| Viewport | Layout | Tile count | Per-tile content |
|---|---|---|---|
| Mobile <768px | Vertical stack, full width OR 2-col grid | 4-5 tiles max (drop sunset, drop wind detail) | Primary value + severity color + staleness in microcopy |
| Tablet 768-1024px | Horizontal row, 4-col | 4-6 tiles | Primary + secondary value + staleness |
| Desktop >=1024px | Horizontal row, 6-7 tiles | Up to 7 (temp, AQI, wind, lake-level, lake-storage, sunset, advisory) | Full tile content + hover popover with detail_text |

CSS lives at `app/static/styles/components/conditions_strip.css` (the file Phase 6.5 already creates). Phase 8 amends rather than replaces — Phase 6.5 ships the placeholder styles; Phase 8 adds severity color classes (`.cond-tile--good`, `.cond-tile--severe`, etc.) + the stale-state muted variants.

### §4.5 Staleness indicator rendering

```python
def staleness_label(fetched_at: datetime, now: datetime) -> tuple[str, bool]:
    delta = now - fetched_at
    minutes = int(delta.total_seconds() / 60)
    if minutes < 60:
        return f"Updated {minutes} min ago", False
    hours = minutes // 60
    if hours < 24:
        is_stale = hours >= 2  # 2x typical TTL = stale
        return f"Updated >{hours}h ago", is_stale
    return f"Updated {delta.days}d ago", True
```

Lake-temp operator fallback deferred to V1.5 (no `00010` at site 09427500). Storage tile label: e.g. `"589k ac-ft"` with optional capacity context in V1.5.

### §4.6 `/api/conditions` endpoint

Optional but recommended even for V1: a JSON read endpoint at `/api/conditions` that returns the same view-model shape as JSON. Uses:
- Mobile PWA shell (V1.5) could long-poll this endpoint.
- Chat tier-3 preamble can call this internally rather than going through `read_source()` directly (one less import surface for the chat module).
- Operator can curl it for monitoring.

Lives at `app/api/routes/conditions.py`. Simple FastAPI route returning the dataclass via `dataclasses.asdict()` + JSONResponse.

### §4.7 Swapping `STUB_CURRENT_TEMPERATURE_F`

Phase 6.3 introduced `STUB_CURRENT_TEMPERATURE_F = 105.0` at `app/core/ranking.py:12`. Phase 7 reused it in `app/chat/chat_request_context.py:8`. Both call sites read the constant directly.

Phase 8 swap pattern (recommended):
1. Leave `STUB_CURRENT_TEMPERATURE_F` in place as a fallback constant — when conditions cache has no data (cold start, all sources failing), readers fall back to the stub rather than to `None` which would break the existing heat-bias logic.
2. Add `app/core/ranking.py: def current_temperature_f() -> float:` that:
   - Calls `app.conditions.cache.read_source("nws_current")`.
   - If row exists and `not is_stale`, returns `data["temperature_f"]`.
   - Otherwise returns `STUB_CURRENT_TEMPERATURE_F` (stub) + logs `conditions.fallback_to_stub` warning.
3. Replace call sites at `app/api/routes/category_pages.py:602` and `app/api/routes/map_data.py:111` with `current_temperature_f()`.
4. Replace `app/chat/chat_request_context.py:37` `STUB_CURRENT_TEMPERATURE_F` with `current_temperature_f()`.

**Why not just delete the stub:** Tests in `tests/test_phase7_chat_conditions.py` exercise the heat-bias logic deterministically against the stub. Keeping the constant as the cold-start fallback means those tests stay green AND fresh-install-no-cache-row environments still rank correctly (assumption: 105°F summer-default is a closer truth for Havasu than 70°F dev-machine-temperature).

---

## §5 Alert dispatch evaluation job

### §5.1 Script entry-point

`scripts/evaluate_and_dispatch_alerts.py` — Railway scheduled job, cron `*/15 * * * *` (offset +7 to avoid clashing with conditions fetcher ticks; e.g., `7,22,37,52 * * * *`).

```python
# Usage:
#   python -m scripts.evaluate_and_dispatch_alerts                  # production
#   python -m scripts.evaluate_and_dispatch_alerts --dry-run        # log + write nothing
#   python -m scripts.evaluate_and_dispatch_alerts --alert-type heat_advisory
#   python -m scripts.evaluate_and_dispatch_alerts --user-id <id>   # single-user test
```

### §5.2 Pipeline

```
1. Read cache rows for all relevant sources
   (airnow_86403, nws_alerts_lhc_zone, usgs_09427500)
2. For each alert_type in ('heat_advisory', 'aqi_alert', 'lake_hazard', 'event_traffic'):
     a. Evaluate threshold (§6) → fired: bool, trigger_data: dict
     b. If not fired, skip
     c. Query: SELECT * FROM alert_subscriptions
                WHERE alert_type = :alert_type
                  AND delivery_channel = 'email'
                  AND (paused_until IS NULL OR paused_until < :now)
                JOIN users ON users.id = subscription.user_id
                WHERE users.is_active = true
     d. For each candidate subscription:
        i. Dedup check (§8): is there a row in alerts_dispatched
           WHERE subscription_id = X AND alert_type = Y
             AND delivery_status = 'sent'
             AND dispatched_at > now - INTERVAL '6 hours'?
           If yes → INSERT a 'suppressed_dedupe' row, skip dispatch.
        ii. Build venue-context (§9) from user's UserFavorite rows
        iii. Render email template (§9) with venue-context substitutions
        iv. Enqueue Outbox row (kind='alert_email') OR direct Resend POST?
            → Decision: direct Resend POST inside the job (NOT Outbox-wrapped).
              Rationale: the 15-min cadence is itself the retry mechanism.
              If the Resend POST fails transiently, the next-tick re-evaluation
              + dedupe-check-misses-because-no-'sent'-row-exists means it
              naturally retries. Outbox is overhead for must-not-lose; alerts
              tolerate a missed send if the underlying condition has cleared
              by next tick.
        v. INSERT alerts_dispatched row with delivery_status = 'sent' or 'failed'
3. Exit 0.
```

### §5.3 Why a separate script + not in the fetcher

Three reasons:
- **Clean separation of read-from-source vs read-from-cache.** Fetchers are I/O-bound on external APIs; dispatcher is I/O-bound on Resend. Different failure modes; different observability surfaces.
- **Disable-in-emergency.** Casey can toggle the Railway cron for `havasu-alerts-dispatch` to off without affecting the conditions strip on the homepage. Important for "we're sending false-positive heat alerts in shoulder season" panic-recovery.
- **Dry-run is meaningful.** A dry-run flag on the dispatcher walks the entire pipeline + logs the rendered bodies WITHOUT calling Resend; this is the operator's primary safety surface for testing template changes pre-deploy.

### §5.4 Direct-Resend vs Outbox decision

Per master plan §4 Phase 8 + design memo §5 step 6, V1 ships direct-Resend (no Outbox). The trade-off:

| Approach | Pros | Cons |
|---|---|---|
| **Direct Resend in dispatcher** (V1) | Simpler; one fewer table read; 15-min cadence is natural retry; explicit `delivery_status='failed'` audit row | A Resend transient outage at the exact moment a heat advisory fires means that user misses that send + waits 6h dedupe window. Risk acceptable for V1. |
| Outbox-wrapped (V1.5) | Survives transient Resend outage cleanly; retries via existing `scripts/outbox_redrive.py` infra | Adds Outbox row per dispatched alert; need new `OUTBOX_KIND_ALERT_EMAIL` (`app/core/background.py:328-338` would extend); risk of double-send if redrive fires AFTER dedupe-window-clearing |

Recommendation: ship V1 with direct-Resend. If post-launch monitoring shows >5% dispatch failure rate, V1.5 promotes to Outbox.

### §5.5 BackgroundTasks vs script-only

Master plan §4 Phase 8 says "dispatches email via Resend BackgroundTasks (Phase 4 infrastructure)". This phrasing is slightly imprecise: `BackgroundTasks` is FastAPI's request-scoped helper for fire-and-forget work after returning a response. The alert dispatcher is a *scheduled* job, not a request-scoped one — it runs in a Railway container with no FastAPI request context.

Within the dispatcher script, `httpx.Client.post()` to Resend is just a synchronous HTTP call. The "background" framing is correct in spirit (it's not in a user-request hot path) but the literal FastAPI `BackgroundTasks` class isn't used. The script imports `app.auth.email_sender` and a new sibling `send_alert_email(user, alert_type, body)` function — exact pattern from design memo §9.

---

## §6 Alert trigger threshold definitions

### §6.1 Per-`alert_type` thresholds

| `alert_type` | Trigger predicate | Source row read | Operator-tunable? |
|---|---|---|---|
| `heat_advisory` | `nws_alerts_lhc_zone` row contains item where `event` matches `"Heat Advisory" OR "Excessive Heat Warning" OR "Heat Watch"` | `nws_alerts_lhc_zone` | Threshold not tunable (NWS-issued is the signal). Bare heat-index threshold (e.g. >=110°F) explicitly excluded per design memo §10 Q3 — reduces false positives. |
| `aqi_alert` | ANY row in `airnow_86403.data["rows"]` has `category_name` NOT IN `{"Good", "Moderate"}` (i.e. "Unhealthy for Sensitive Groups" or worse). Evaluator iterates the rows array; LHC currently has single O3 row from Blythe per §12, but evaluator must be multi-row tolerant. Absence of PM2.5/PM10 rows is data-not-available, NOT safe-condition zero. | `airnow_86403` | Threshold operator-tunable via `AQI_ALERT_CATEGORY_THRESHOLD` env var (default: `unhealthy_for_sensitive_groups`). **Amended 2026-05-19 (§12):** evaluator multi-row tolerant; source-station distance available on the row for honest UX. |
| `lake_hazard` | `nws_alerts_lhc_zone` matches inland-LHC keyword set `LAKE_HAZARD_NWS_KEYWORDS` (flash flood / flood warning / flood advisory / lake wind / high wind / wind advisory / blowing dust / dust storm / severe thunderstorm) **OR** `usgs_09427500` gauge height dropped > `LAKE_HAZARD_GAUGE_DROP_FT` (default 2.0) in 24h | `nws_alerts_lhc_zone` + `usgs_09427500` | **Amended 2026-05-19 (§6 + §11 per verification report):** Nixle dropped (silent since 2021); NWS marine surface dropped (doesn't cover inland LHC); collapsed to single AZZ002-zone-scoped land surface + gauge-drop secondary. USGS drop threshold operator-tunable via env; keyword set tunable post-launch if false-pos pattern surfaces. |
| `event_traffic` | TBD — Events table doesn't exist in usable form until Phase 9 | (deferred to V1.5 / Phase 9.5) | — |

### §6.2 Specific recommended values

**Heat advisory threshold:** Master plan §4 Phase 8 says "heat advisory (NWS Excessive Heat Warning OR forecast > X°F — pick a threshold; mention operator-tunable)". My recommendation:

- **Primary:** NWS-issued `Heat Advisory` OR `Excessive Heat Warning` OR `Heat Watch` from `nws_alerts_lhc_zone`. This is what design memo §10 Q3 recommends; NWS authority signal.
- **NOT a bare heat-index threshold.** Design memo §10 Q3 explicitly rejects this for V1 to avoid contradicting NWS (firing alerts they don't endorse). Confirmed recommendation.
- **Operator override env var:** `HEAT_ADVISORY_INDEX_FLOOR_F` (default unset). If set to e.g. `112`, the evaluator ALSO fires when `nws_current.heat_index_f >= 112` regardless of NWS alert status. Off by default; operator opts in if NWS proves too conservative for Havasu.

**AQI threshold:** Per the question — "AirNow AQI > 100 → unhealthy for sensitive groups; > 150 unhealthy; pick a threshold". My recommendation:

- **Default:** fire at AQI category = "Unhealthy for Sensitive Groups" or worse (numeric AQI > 100). Conservative + matches EPA messaging. Same as design memo §10 default.
- **Operator-tunable via env var:** `AQI_ALERT_NUMERIC_FLOOR` (default 101). If operator wants tighter threshold (e.g. only fire at 150+ "Unhealthy"), set to 151.
- **Suppression on stale data:** if `airnow_86403.is_stale = True`, skip evaluation entirely (don't fire alert based on hours-old data).

**Lake hazard threshold (amended 2026-05-19 per `phase_8a_prereq_verification_report.md`):**
- **Primary:** NWS AZZ002-zone alert keyword match against `nws_alerts_lhc_zone` cache row. Inland-LHC keyword set targets the actual products NWS issues for AZZ002 ("Lake Havasu and Fort Mohave", served by KVEF Las Vegas): Lake Wind Advisory, High Wind Warning, Wind Advisory, Flash Flood Warning, Flood Warning, Flood Advisory, Blowing Dust / Dust Storm Advisory, Severe Thunderstorm. (Marine surface dropped: NWS marine zones cover Coastal + Great Lakes only; inland reservoirs are not in scope. Verified at weather.gov/marine/usamz.)
- **Secondary:** USGS gauge-height drop at site `09427500` — fire when `00065` drops more than `LAKE_HAZARD_GAUGE_DROP_FT` (default 2.0 ft) over 24h. Reservoir drawdowns during normal ops may false-positive; operator tunes threshold.
- **Dropped:** Nixle RSS ingest + `lhc_emergency` cache row. NWS marine forecast + `nws_marine_alerts` cache row also dropped (§11 per verification report). V1.5 carry to research Mohave County SO / ein.az.gov / lhcaz.gov as alternate alert surfaces.

**Event traffic threshold:** Per the question — "TBD; may be V1.5". My recommendation: **defer to V1.5 / Phase 9.5.** Reasoning:
- Events as ENTITY type aren't fully wired until Phase 9 (master plan §4 Phase 9).
- The design memo §10 Q7 proposes an `Event.traffic_impact=true` tag — that column doesn't exist in `events` table today.
- For V1 Phase 8, the `alert_subscriptions.alert_type` CHECK constraint (`'heat_advisory', 'aqi_alert', 'lake_hazard', 'event_traffic'`) already includes `event_traffic`. UI can show the toggle as "Coming with events" disabled state.

### §6.3 Threshold-tuning configuration surface

A small `app/alerts/thresholds.py` module reads env vars + exposes constants:

```python
# app/alerts/thresholds.py
import os

HEAT_ADVISORY_NWS_EVENT_PATTERNS = (
    "Heat Advisory", "Excessive Heat Warning", "Heat Watch",
)
HEAT_ADVISORY_INDEX_FLOOR_F: float | None = (
    float(os.environ["HEAT_ADVISORY_INDEX_FLOOR_F"])
    if os.environ.get("HEAT_ADVISORY_INDEX_FLOOR_F")
    else None
)

AQI_ALERT_NUMERIC_FLOOR: int = int(os.environ.get("AQI_ALERT_NUMERIC_FLOOR", "101"))

AIRNOW_ZIP = "86403"  # Lake Havasu City
AIRNOW_DISTANCE_MI: int = int(os.environ.get("AIRNOW_DISTANCE_MI", "100"))
# §12 verification 2026-05-19: distance=25 + distance=60 both return empty
# for LHC; distance=100 returns Blythe CA (O3 only) as nearest monitor at
# ~60mi south. Operator-tunable down to 75 if tighter scope wanted. Cache
# stores source-station attribution (name + state_code + distance_mi) so
# the conditions strip can render honest "from Blythe, CA ~60mi south"
# subtitle alongside the AQI value.

LAKE_HAZARD_NWS_KEYWORDS = (
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
# Inland-LHC keyword set per phase_8a_prereq_verification_report.md §11.2.
# Dropped marine-only terms ("small craft", "capsize"), non-NWS-vocabulary
# terms ("drowning", "rescue"), and over-broad terms ("advisory" without a
# specific product prefix). Heat-advisory keywords live in their own constant
# HEAT_ADVISORY_NWS_EVENT_PATTERNS above.
LAKE_HAZARD_GAUGE_DROP_FT: float = float(os.environ.get("LAKE_HAZARD_GAUGE_DROP_FT", "2.0"))
LHC_NWS_ZONE_ID = "AZZ002"  # Lake Havasu and Fort Mohave; KVEF Las Vegas. NWS land zone (marine zones don't cover inland LHC).
USGS_LAKE_HAVASU_SITE = "09427500"
USGS_PARAMETER_CODES = ("00065", "00054")

ALERT_DEDUPE_WINDOW_HOURS = int(os.environ.get("ALERT_DEDUPE_WINDOW_HOURS", "6"))
```

Operator can tune via Railway env vars without code changes. Test coverage exercises both default + overridden behavior.

---

## §7 Alert subscription UI on `/account/alerts`

### §7.1 Route + template

New route `/account/alerts` (GET + POST) at `app/api/routes/account_alerts.py`. Auth via existing `app/auth/dependencies.py` `require_current_user` dependency (Phase 2A.1 pattern).

Template `app/templates/account/alerts.html`, included via the existing account-shell layout that Phase 2A.3 ships (mirrors `/account/favorites` shape).

### §7.2 Form shape

Mobile-first vertical stack:

```
┌─────────────────────────────────────────────┐
│ Alerts                                       │
│ We'll email you when conditions matter.      │
│                                              │
│ ☑ Heat advisory                              │
│   When NWS issues a heat advisory for LHC    │
│                                              │
│ ☑ Air quality                                │
│   When AQI reaches unhealthy levels          │
│                                              │
│ ☐ Lake hazard                                │
│   Closures, evacuations, water emergencies   │
│                                              │
│ ☐ Event traffic (coming with events)         │
│   [disabled in V1]                           │
│                                              │
│ Snooze all until:                            │
│   [ date picker ] [Snooze]                   │
│                                              │
│ [ Save changes ]                             │
└─────────────────────────────────────────────┘
```

### §7.3 Form semantics

- Each checkbox = one `AlertSubscription` row keyed by `(user_id, alert_type, delivery_channel='email')`.
- Unchecked = row deleted (per `Unique` constraint on `(user_id, alert_type, delivery_channel)`).
- Checked = row inserted or kept.
- "Snooze all until" sets `paused_until` on all subscription rows for this user. Per-alert-type snoozing is V1.5 (master plan can tolerate it).
- No SMS toggle in V1 per §11 below (SMS deferred to V1.5).
- Email address shown read-only at top ("Sending to your-email@example.com — change in /account").

### §7.4 Empty state

User with no subscriptions sees the form with all checkboxes unchecked + a one-line "You'll only get alerts you opt into. Pick the ones that matter to you." caption.

### §7.5 Form handling

POST handler:
1. Parse form → set of opted-in `alert_type` strings.
2. Query existing subscriptions for this user.
3. Compute diff: `to_insert = opted_in - existing`, `to_delete = existing - opted_in`.
4. Apply diff in single transaction.
5. Optionally parse `snooze_until` field → update `paused_until` on all current subscriptions.
6. Redirect-after-POST to `/account/alerts?saved=1` with a flash banner.

Test coverage: `tests/test_phase8_alert_subscription_ui.py` — form renders, save adds rows, save deletes rows, snooze updates `paused_until`, unauthenticated request 401s, invalid alert_type rejected.

---

## §8 Per-alert dedup pattern

### §8.1 Pattern decision: persistent table

Use the existing `alerts_dispatched` table (Phase 3.1). It already supports this — rows have `subscription_id`, `alert_type`, `dispatched_at`, `delivery_status`.

**Why persistent over in-memory:**
- The dispatcher script restarts every 15 min (each cron tick is a fresh process). In-memory state would reset every run.
- A single Railway redeploy mid-heat-advisory would clear in-memory state and cause double-sends.
- The `alerts_dispatched` table is also the audit log — we want this data anyway for "did the user actually get the alert?" investigation.

### §8.2 Implementation

```python
# app/alerts/dedup.py
from datetime import timedelta
from app.alerts.thresholds import ALERT_DEDUPE_WINDOW_HOURS
from app.db.models import AlertDispatched

def is_duplicate(
    db, subscription_id: str, alert_type: str, now: datetime
) -> bool:
    """Returns True if there's already a 'sent' dispatch for this
    (subscription, alert_type) in the last ALERT_DEDUPE_WINDOW_HOURS hours."""
    cutoff = now - timedelta(hours=ALERT_DEDUPE_WINDOW_HOURS)
    return (
        db.query(AlertDispatched)
        .filter(
            AlertDispatched.subscription_id == subscription_id,
            AlertDispatched.alert_type == alert_type,
            AlertDispatched.delivery_status == "sent",
            AlertDispatched.dispatched_at > cutoff,
        )
        .first()
        is not None
    )
```

### §8.3 Index support

Existing `Index("ix_alerts_dispatched_subscription_id", "subscription_id")` + the implicit query on `dispatched_at` is good enough at V1 scale (<100 dispatches/day). If post-launch profiling shows slow dedupe checks, Phase 8.5 / V1.5 can add a composite `(subscription_id, alert_type, dispatched_at)` index. **Not added preemptively** per "no premature optimization."

### §8.4 Suppressed-dedupe audit row

Per design memo §3.3, even SUPPRESSED dispatches get an `alerts_dispatched` row with `delivery_status='suppressed_dedupe'`. This:
- Lets the operator answer "why didn't this user get the alert?" — answer: dedupe-window-active.
- Gives V1.5 analytics surface for "how often does dedupe fire?" (informs whether 6h is the right window).
- Does NOT count against future dedupe checks (only `'sent'` rows do — see §8.2 query).

The existing `alerts_dispatched.delivery_status` CHECK constraint at `app/db/models.py:1389-1392` is `('queued', 'sent', 'failed', 'bounced')`. Phase 8 needs an additive constraint amendment to include `'suppressed_dedupe'` and `'suppressed_paused'`:

```sql
-- Alembic migration adds:
ALTER TABLE alerts_dispatched DROP CONSTRAINT ck_alerts_dispatched_delivery_status;
ALTER TABLE alerts_dispatched ADD CONSTRAINT ck_alerts_dispatched_delivery_status
  CHECK (delivery_status IN ('queued', 'sent', 'failed', 'bounced', 'suppressed_dedupe', 'suppressed_paused'));
```

This is a tiny migration; rolls into Phase 8's single additive migration alongside the `last_attempt_at` + `next_attempt_after` columns from §2.1.

---

## §9 Alert email templates + venue-context mapping

### §9.1 Template file layout

```
app/alerts/
  __init__.py
  thresholds.py            # §6.3
  dedup.py                 # §8.2
  evaluator.py             # per-alert-type fired/not-fired evaluation
  venue_context.py         # the texture-moat helper
  dispatcher.py            # render + send orchestrator
  templates/
    heat_advisory.html.j2
    heat_advisory.txt.j2
    aqi_alert.html.j2
    aqi_alert.txt.j2
    lake_hazard.html.j2
    lake_hazard.txt.j2
    base_alert.html.j2     # shared header/footer
    base_alert.txt.j2
```

Templates are Jinja2 rendered via a small `app/alerts/render.py` helper. Both HTML + text versions per Resend email best practice.

### §9.2 Heat advisory template (example)

```jinja
{# heat_advisory.txt.j2 #}
Heat advisory in effect through {{ trigger.expires_local }}.

{% if indoor_favorites %}
{{ indoor_favorites|length }} of your favorites are indoor:

{% for fav in indoor_favorites %}
  - {{ fav.name }} — {{ fav.district }}, {{ fav.open_hours_today }}
{% endfor %}
{% else %}
We'll surface indoor options when you favorite a few places at https://havasu-chat.example.com/account/favorites.
{% endif %}

Stay hydrated, and keep an eye on heat-sensitive friends + pets.

—
You're getting this because you opted into heat alerts.
Snooze or unsubscribe: https://havasu-chat.example.com/account/alerts
```

### §9.3 Venue-context mapping helper

```python
# app/alerts/venue_context.py
from sqlalchemy.orm import Session
from app.db.models import Entity, UserFavorite

def indoor_favorites_for_user(
    db: Session, user_id: str, limit: int = 5
) -> list[Entity]:
    """Heat / AQI alert venue-context: user's favorite entities with
    heat_exposure IN ('indoor', 'shaded'). Top N by recency."""
    return (
        db.query(Entity)
        .join(UserFavorite, UserFavorite.entity_id == Entity.id)
        .filter(UserFavorite.user_id == user_id)
        .filter(Entity.heat_exposure.in_(("indoor", "shaded")))
        .order_by(UserFavorite.created_at.desc())
        .limit(limit)
        .all()
    )

def non_water_favorites_for_user(...) -> list[Entity]:
    """Lake hazard alert venue-context: user's favorites NOT
    water-adjacent. Surface alternatives."""

def non_district_favorites_for_user(db, user_id, affected_district, ...):
    """Event traffic alert venue-context: user's favorites NOT
    in the affected district."""
```

### §9.4 Heat_exposure dependency (risk #10)

Per master plan §7 risk #10 + Phase 5/6/7 operator workload: **top ~30 entities by traffic must have `heat_exposure` tagged before alerts fire.** The `Entity.heat_exposure` column exists since Phase 1 (per `app/db/models.py:672`) with values `'indoor' | 'shaded' | 'outdoor' | 'water_adjacent'`. Whether 30+ entities are actually tagged at Phase 8 dispatch time is the critical pre-flight check.

Phase 8 dispatch wrapper should include a pre-flight smoke test:

```powershell
python -c "
from app.db.database import SessionLocal
from app.db.models import Entity
with SessionLocal() as db:
    indoor = db.query(Entity).filter(Entity.heat_exposure == 'indoor').count()
    shaded = db.query(Entity).filter(Entity.heat_exposure == 'shaded').count()
    print(f'indoor: {indoor}, shaded: {shaded}, total: {indoor+shaded}')
"
# Expected: at least 30 combined indoor+shaded entities
# If <30, HALT Phase 8 dispatch + revisit Phase 5/6/7 heat_exposure tagging
```

### §9.5 Cold-start fallback

Per design memo §6, a user with zero favorites or zero qualifying favorites gets the template's `{% else %}` branch — a one-paragraph alert with no venue list, plus a CTA to favorite places. Honest + matches calm-by-construction tone.

### §9.6 Resend integration

Reuse `app/auth/email_sender.py` Resend client. Add sibling function:

```python
def send_alert_email(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> str | None:
    """Send via Resend. Returns Resend message ID on success, None on failure.
    Same env var pattern as send_magic_link (RESEND_API_KEY, RESEND_FROM_ADDRESS).
    Same dev-mode bypass (AUTH_DEV_MODE) — logs instead of sending in dev."""
```

Same Resend API key + from address as magic-link. From address may need a different display name (`"Hava Alerts <alerts@havasu-chat.example.com>"` vs `"Hava <noreply@havasu-chat.example.com>"`) — operator decides at dispatch time. Adds optional `RESEND_ALERTS_FROM_ADDRESS` env var; falls back to `RESEND_FROM_ADDRESS` if unset.

### §9.7 Template authoring as operator-side workload

Per the question's §12 effort estimate ask — **operator authors the alert email copy.** Engineering ships the template skeleton + variable interpolation; operator-tunes the actual wording. Estimate: ~2 hours operator time for 3 email types × 2 formats (HTML + text) = 6 templates × ~20 min each. Operator can iterate post-launch as feedback comes in.

---

## §10 Cat-13 (Public & Civic Resources) expansion

### §10.1 Scope

Per master plan §4 Phase 8 — "Public & Civic Resources category page (library, transit, visitor info, utilities, airport, senior resources, payment/licensing links, civic orgs) — entities populated via Layer 3 (city open data) primarily".

The cat-13 category page itself was already shipped by Phase 6.3 (breadth pass through all 11 remaining Tier 1 slugs). What's missing is **entity population** in that category. Currently cat-13 likely renders an "empty category" state.

### §10.2 What LHC publishes

Inventory needed before Phase 8b dispatch (operator-side, ~1 hour):

| Entity sub-type | Likely source | Layer |
|---|---|---|
| Library (Mohave County Library — LHC branch) | https://www.mohavecountylibrary.us | Layer 3 (web scrape) OR Layer 5 (operator-typed) |
| Public transit (Havasu Hopper bus) | https://www.lhcaz.gov/transit | Layer 5 (likely no API; operator-typed) |
| Utilities (water/sewer = City; trash = Republic; electric = UniSource/Mohave Electric) | City utilities page + commercial providers | Layer 5 |
| Airport (Lake Havasu City Airport KHII) | Federal AirNav / FAA + city airport page | Layer 3 / Layer 5 mix |
| Senior resources (Senior Center, Meals on Wheels chapter) | City + Mohave County aging services | Layer 5 |
| Payment/licensing links (utility bill pay, court records, business license) | City portals | Layer 5 (URLs as entity attributes, not standalone entities) |
| Civic orgs (Chamber, Rotary, Kiwanis, Visitor Bureau) | Direct websites | Layer 5 |

Realistic V1 cat-13 entity count: **~15-25 entities.** Smaller than other categories (Eat & Drink has 100+) but high-trust + high-density-per-entity. Most are Layer 5 (operator-typed in admin form) rather than scraped.

### §10.3 Implementation shape

Phase 8b (or 8.5) ships:
- 1 new Layer 3 scraper: `scripts/ingest/lhc_civic_scrape.py` — pulls library hours + Havasu Hopper schedule + airport info from city + library pages. Modest ~6 entities populated this way.
- ~20 operator-typed entities entered via admin form (existing `app/admin/contributions_html.py` flow OR a Phase 8b-specific seed script).
- Cat-13 specific filter chips on the category page (operator decides at dispatch time — likely "Government services", "Civic groups", "Utilities", "Transit").

### §10.4 Why split 8a from 8b

Phase 8a (conditions + alerts) is the load-bearing infrastructure work. Phase 8b is data + content + a modest scraper. They share:
- Nothing in the schema (cat-13 entities use existing `Entity` table; conditions use `external_conditions_cache`).
- Nothing in routes (cat-13 uses existing `/category/public-civic-resources`; conditions use new endpoints).
- Almost nothing in tests.

Splitting means Phase 8a can dispatch as a focused 4-6 day Cursor session against the post-Phase-7 SHA + the operator prereqs; Phase 8b is a parallel-eligible / sequential-after-8a small dispatch that's mostly operator data entry.

**Operator decision-lock at Phase 8 wrapper authoring time:** ship as one Phase 8 dispatch (4-7 days) OR split 8a + 8b. Recommend the split for tighter Cursor session bounds.

---

## §11 What's NOT in Phase 8

Explicit non-scope list to prevent over-scoping:

| Excluded | Why | When (if ever) |
|---|---|---|
| SMS dispatch | Per master plan §8 OQ #13 — Twilio integration cost + per-message cost + phone-number verification UI is V1 scope creep. Schema already SMS-ready (`alert_subscriptions.delivery_channel` CHECK includes `'sms'`). | V1.5 |
| Push notifications | No mobile app, no service worker push subscriptions | V2+ |
| Webhooks (Slack/Discord/Zapier on condition fire) | Not the audience for this product | V2+ |
| Historical conditions data / time-series | `external_conditions_cache` is single-row-per-source by design | Separate data-warehouse lane if ever needed |
| Forecast-based alerts ("tomorrow will be 115°F") | Current-state only in V1; reduces false-positive risk | V1.5 |
| Per-favorite alerts ("alert me if THIS business's outdoor seating is unwise") | City-wide alerts only in V1 | V1.5 / V2 |
| User-defined custom thresholds ("alert me when temp > X") | Operator-set defaults only in V1 | V2 if anyone asks |
| Operator-approval UI for each alert pre-send | Cron cadence + dedup + dry-run flag are the safety surfaces | V1.5 if false-positives become a problem |
| Multi-language alert bodies | English only | V2 |
| Conditions-driven category-page banners ("Heat advisory active — listings re-ranked") | Homepage strip is the only display surface in V1 | V1.5 |
| Twitter/X API for LHC emergency feed | $100/mo minimum + dev account complexity per prereq checklist §4 | V1.5 if LHC has no other feed |
| `event_traffic` alert fully wired | Events not as ENTITY type until Phase 9 | Phase 9.5 / V1.5 (toggle visible in UI but disabled) |
| Conditions endpoint for V1.5 PWA | `/api/conditions` JSON endpoint exists; consumers TBD | V1.5 |
| Lake-temp Layer 5 admin form | Deferred V1.5 — site 09427500 confirmed no `00010` | Omit from Phase 8a |
| Outbox-wrapped alert dispatch | V1 uses direct Resend + 15-min cron retry | V1.5 if >5% dispatch failure rate post-launch |

---

## §12 Risk register

Top 5 risks for Phase 8, with mitigations:

### Risk 1 — AirNow API rate-limit / approval lag (HIGH severity)

**Threat:** AirNow's free tier is 500 req/hr per key. At 2 req/hr per zip × 1 zip = no risk. BUT: the AirNow approval process takes 1-2 business days historically. If the operator hasn't registered the key by Phase 7's SHIP commit, Phase 8 dispatch idles 1-2 days waiting.

**Mitigation:** Already pre-positioned. `outputs/phase_8_operator_prereq_checklist.md` §2 explicitly tells the operator to register TODAY (2026-05-20) to bake the approval lag during Cursor's Phase 6.4/7 grind. Phase 8 dispatch wrapper has the key ready at dispatch time.

**Residual risk:** AirNow occasionally rotates approval requirements; key registration could fail for "intended use" wording mismatch. Cowork-side mitigation: pre-position acceptable wording in §2 of the prereq checklist + give operator a copy-paste-ready boilerplate.

### Risk 2 — USGS site `09427500` retired or parameter set changes (MEDIUM severity)

**Threat:** USGS occasionally retires gauges with little notice. Site `09427500` is verified live (2026-05-19) for `00065` + `00054` only — no `00010` water temp. Secondary site `09427520` is historic-only since 2006 (do not use).

**Mitigation:**
- Pre-flight smoke check: iv/OGC API for site `09427500` must return non-empty `00065` + `00054` series. If empty, dispatch HALTs.
- `USGS_LAKE_HAVASU_SITE` env var (default `"09427500"`). Water-temp alternate source is V1.5 carry (e.g. Bill Williams River `09426630` — browser-verify pending).
- Gauge-drop `lake_hazard` threshold tunable via `LAKE_HAZARD_GAUGE_DROP_FT` to limit false positives on reservoir operations.

### Risk 3 — Resend deliverability / spam classification on alert emails (MEDIUM severity)

**Threat:** Alert emails are a different cohort from magic-link auth emails. Higher volume per user, more variable content. Risk: gmail/outlook classify them as promotional and they land in spam, defeating the whole alert system.

**Mitigation:**
- Sender authentication: SPF + DKIM + DMARC fully configured on the sending domain (already done for magic-link).
- Send-rate management: stays at <100 alerts/day in V1; far below thresholds that trigger volume-based filters.
- One-click unsubscribe header (`List-Unsubscribe: <https://...alert-snooze>`) per RFC 8058 — improves inbox placement.
- Subject line crafted as informational not promotional ("Heat advisory in Lake Havasu — 3 indoor favorites" not "URGENT - Heat advisory NOW!").
- Operator post-launch: monitor Resend dashboard for bounce/complaint rates; tune copy if needed.

**Residual risk:** Cold-start sending domain reputation. Mitigation: V1 launch traffic is small enough that this isn't immediate; established sender domain accrues reputation organically.

### Risk 4 — NWS `/alerts/active` semantic drift (MEDIUM severity)

**Threat:** NWS occasionally changes `event` field values (e.g. "Heat Advisory" becomes "Heat Watch — Localized" or similar). Our keyword matcher (`("Heat Advisory", "Excessive Heat Warning", "Heat Watch")`) could miss new variants and silently stop firing.

**Mitigation:**
- Test fixture from real NWS response shape; pin against known-good payload.
- Pattern matching uses `in_anywhere_in_event_string` (case-insensitive) not exact-equality.
- Sentry breadcrumb on every fetch logs the alert payload shape; operator-visible if NWS changes structure.
- Phase 8 close-out includes "verify against current NWS response shape" as an acceptance gate.

**Residual risk:** Silent miss for ~24 hours until operator notices. Acceptable; V1 can't fully eliminate this without a per-alert active-conditions monitoring surface (V1.5).

### Risk 5 — `heat_exposure` tagging incomplete at dispatch time (MEDIUM severity)

**Threat:** Per master plan §7 risk #10, Phase 5/6/7 operator workload should tag top-30 entities with `heat_exposure`. If actual tagged count at Phase 8 dispatch is <30, alerts fire with empty venue-context for most users — defeats the texture-moat that's the entire point of the feature.

**Mitigation:**
- Pre-flight smoke check in Phase 8 dispatch wrapper (per §9.4 above).
- If <30 tagged, HALT dispatch + operator does a 1-2 day tagging sprint via admin form before resuming.
- Cold-start template fallback (per §9.5) means users with no qualifying favorites get a usable-but-blunt alert — not a broken experience, just a missed-opportunity one.

**Residual risk:** Pre-flight check passes (30 entities tagged citywide) but specific user's favorites happen to be untagged. Per §9.5, that user gets the fallback template — honest but not magical. Acceptable; tagging continues post-launch.

### Honorable mentions (lower-severity risks not in top 5)

- **LHC emergency feed format changes mid-V1 lifecycle.** Operator's prereq research locks in the format; future drift triggers a small re-author.
- **Time-zone bugs in `paused_until` semantics.** Mitigation: tests cover Phoenix-vs-UTC edge cases.
- **Dedupe window race conditions** if Resend send succeeds but DB write of `'sent'` row fails. Mitigation: write the `'sent'` row INSIDE the same transaction as the send-success acknowledgment; if write fails, next-tick re-evaluates + may double-send — acceptable in V1; logged.
- **Operator decision-lock drift** between prereq research (May 2026) and dispatch (likely June 2026). Mitigation: dispatch wrapper re-prompts operator to re-verify prereq findings before paste.

---

## §13 Success criteria

Per master plan §4 Phase 8: "Conditions panel updates every 15 min. Alerts fire correctly for heat advisory / AQI / lake hazard / event traffic. Alert emails include relevant venue-context recommendations."

Concrete pass/fail criteria for Phase 8 close-out:

### §13.1 Conditions panel acceptance

| # | Criterion | How to verify |
|---|---|---|
| C1 | Conditions strip on `/home` renders 4-8 tiles with real data | Browse to `/` in prod browser; tiles populated (not "Coming soon"); values match current Havasu reality |
| C2 | Each tile shows accurate staleness indicator | Inspect tile microcopy — "Updated N min ago" for N < TTL minutes |
| C3 | Fetcher updates `external_conditions_cache` rows on schedule | `SELECT source, fetched_at, error_count FROM external_conditions_cache` after 1h shows rows with `fetched_at` within last TTL window |
| C4 | Source failure isolation works — one source down ≠ others affected | Manually break AirNow key in Railway env; verify NWS + USGS still update + only AirNow tile shows degraded state |
| C5 | `STUB_CURRENT_TEMPERATURE_F` is swapped — chat ranking reads real temp | `app/chat/chat_request_context.py` calls `current_temperature_f()`; integration test asserts |
| C6 | `/api/conditions` JSON endpoint returns expected shape | `curl /api/conditions` returns valid JSON matching `ConditionsStripViewModel` shape |

### §13.2 Alert dispatch acceptance

| # | Criterion | How to verify |
|---|---|---|
| A1 | Subscription UI at `/account/alerts` renders + saves | Authenticated user can browse, toggle, save; rows appear in `alert_subscriptions` |
| A2 | Heat advisory alert fires when NWS issues one | Dry-run dispatcher against fixture-injected `nws_alerts_lhc_zone` payload; verify rendered email body |
| A3 | AQI alert fires above category threshold | Dry-run dispatcher against fixture-injected `airnow_86403` payload with category="Unhealthy"; verify dispatch |
| A4 | Lake hazard alert fires only on operator-approved LHC payload | Dry-run + verify operator-approval flag check |
| A5 | Per-alert dedup works — same alert_type not fired for same user within 6h | Run dispatcher twice in succession against fired condition; second run inserts `suppressed_dedupe` row + NO duplicate Resend POST |
| A6 | Venue context populates correctly | User with 5 indoor favorites receives alert listing those 5 favorites; user with 0 favorites gets fallback template |
| A7 | Email actually delivers (end-to-end Resend test) | Operator opt-in to all alert types; trigger via dry-run-disabled dispatcher against synthetic payload; verify email arrives in inbox |
| A8 | Snoozed subscription doesn't dispatch | Set `paused_until = now + 1d` for a subscription; trigger condition; verify `suppressed_paused` audit row + no Resend POST |

### §13.3 Cat-13 acceptance (Phase 8b)

| # | Criterion | How to verify |
|---|---|---|
| L1 | Cat-13 category page populated with at least 15 entities | Browse `/category/public-civic-resources`; count rendered cards |
| L2 | Library hours + Havasu Hopper info present | Specific entities for library + transit visible with hours rendered |
| L3 | Cat-13 entities appear in chat results | Ask Hava "where's the library?" — gets library entity |

### §13.4 Operational acceptance

| # | Criterion | How to verify |
|---|---|---|
| O1 | Pytest stays green at +25-40 net-new tests | `python -m pytest` exits 0; count delta within range |
| O2 | Alembic head migrates cleanly (additive migration) | `python -m alembic upgrade head` on staging DB; head moves forward |
| O3 | All Railway scheduled services deploy + run | Railway dashboard shows green status for all 6 conditions services + alerts dispatcher |
| O4 | Sentry breadcrumbs from `background-jobs` category visible | Inspect Sentry for `conditions.fetch_succeeded` + `alerts.dispatched` events |

---

## §14 Effort estimate

Master plan §4 Phase 8 estimates "M (5-8 days dispatch). Plus operator work to register AirNow API key, confirm USGS gauge ID, check City of Lake Havasu emergency-notification feed format."

### §14.1 Engineering-side refinement (Phase 8a only, conditions + alerts)

| Sub-lane | Effort | Notes |
|---|---|---|
| Alembic migration (3-4 column additions + CHECK extension) | 0.5 day | Minimal; pattern from Phase 3.1 + 4.1 |
| `app/conditions/` package (5 modules: cache, sources, fetcher, airnow, nws, usgs) | 2 days | HTTP clients + SourceLimiter wiring + cache reader; mocked-HTTP tests; no Nixle/lhc_emergency in V1 |
| `scripts/fetch_external_conditions.py` + Railway service config | 0.5 day | Pattern from `scripts/outbox_redrive.py` |
| `/api/conditions` endpoint + view-model | 0.5 day | Simple route + dataclass→JSON |
| Conditions strip template + CSS (replaces Phase 6.5 placeholder) | 1 day | Anchored edits to `home.html`, `components/conditions_strip.html` new, CSS amends |
| `STUB_CURRENT_TEMPERATURE_F` swap at 4 call sites + `current_temperature_f()` helper | 0.5 day | Trivial; tests stay green |
| Alert evaluator + threshold config (`app/alerts/`) | 1 day | Per-`alert_type` predicate functions + env-var threshold loading |
| Venue-context helpers (`app/alerts/venue_context.py`) | 0.5 day | 3 functions + shared `top_alternative_venues` |
| Alert dispatcher script + Resend integration | 1 day | `scripts/evaluate_and_dispatch_alerts.py` + `send_alert_email()` |
| Alert email templates (HTML + text, 3 types) | 0.5 day engineering + ~2h operator copy | Skeleton in engineering; operator writes final copy |
| `/account/alerts` route + template | 1 day | Anchored into account-lite shell |
| Tests (~25-35 net-new) | 1.5 days | Fetcher mocked-HTTP, evaluator predicates, dispatcher dedup, template rendering, subscription UI |
| **Total Phase 8a engineering** | **10-11 days dispatch** | Higher than master plan's M (5-8 days) — design memo §11 said 7-9 days; refined here against actual schema discovered (Phase 3.1 already shipped 3 tables, saves ~1 day on schema work but adds back the column-addition + CHECK migration work) |

### §14.2 Phase 8b engineering (cat-13 expansion)

| Sub-lane | Effort | Notes |
|---|---|---|
| `scripts/ingest/lhc_civic_scrape.py` (Layer 3 scraper for library + transit + airport) | 1 day | |
| Cat-13 filter chips on category page | 0.5 day | |
| Tests | 0.5 day | |
| **Total Phase 8b engineering** | **2 days dispatch** | |

### §14.3 Combined Phase 8 (8a + 8b sequential)

**12-13 days dispatch.** Higher than master plan's M (5-8 days). Recommend:
- **Update master plan §4 Phase 8 estimate to M-L (8-12 days).**
- Or formally split: Phase 8a = M (8-10 days), Phase 8b = S (2-3 days).

### §14.4 Operator-side workload

Beyond the prereq checklist (~2-3 hours already documented):

| Activity | Time |
|---|---|
| Author alert email copy (3 types × 2 formats = 6 templates) | ~2 hours |
| Pre-flight: verify ≥30 heat_exposure-tagged entities; tag more if needed | 0-4 hours depending on current state |
| Cat-13 Layer 5 entity data entry (~20 entities via admin form) | ~3-4 hours |
| Post-deploy smoke tests (all 8 acceptance criteria in §13.2) | ~1 hour |
| **Total operator work in Phase 8** | **~6-12 hours** |

This is on top of the §6 master plan estimate of "2-3 hours" for prereqs. **Recommend updating master plan §6 entry to ~8-15 hours total for Phase 8 operator workload.**

---

## §15 Sequencing + dispatch chain

### §15.1 Dependencies that must be true before dispatch

- Phase 2A.1 + 2A.3 shipped (User + UserFavorite tables + Resend integration). Confirmed.
- Phase 3.1 shipped (alert tables + ExternalConditionsCache base shape). Confirmed at `app/db/models.py:1342-1431`.
- Phase 4.1 + 4.4 shipped (background jobs scaffold + with_retry + Outbox infra). Confirmed at `app/core/background.py`.
- Phase 6.5 shipped (home.html has `<!-- conditions-strip-anchor -->` + empty placeholder). PENDING — Phase 6.5 wrapper pre-positioned but not yet dispatched.
- Phase 7 shipped (chat conditions awareness using `STUB_CURRENT_TEMPERATURE_F`). PENDING — Phase 7 currently in flight per the question's context.
- Operator prereqs: AirNow key (pending) + USGS `09427500` live-verified. Nixle dropped per `phase_8a_prereq_verification_report.md`.
- Top-30 entities tagged with `heat_exposure`. PENDING — verify at dispatch time per §9.4 smoke check.

### §15.2 Phase 8 dispatch wrapper SHA-patch slots

The Phase 8 dispatch wrapper (to be authored AFTER Phase 7 ships) needs these patch slots:

- `<<<PHASE_7_HEAD_SHA>>>` — Phase 7's SHIP commit
- `<<<PHASE_7_ALEMBIC_HEAD>>>` — alembic head after Phase 7 (likely unchanged from Phase 6.4; verify)
- `<<<PHASE_6_5_HEAD_SHA>>>` — Phase 6.5's SHIP commit (the conditions-strip placeholder slot)
- `<<<AIRNOW_API_KEY_AVAILABLE>>>` — boolean confirming operator has the key in Railway env
- `<<<USGS_LAKE_HAVASU_SITE>>>` — locked `09427500`; params `00065` + `00054`
- `<<<LHC_EMERGENCY_FEED_DISPOSITION>>>` — **locked: dropped_from_v1_nixle_silent**; V1.5 research replacement

### §15.3 Suggested commit batching

Per the codebase's Rule 8 (operator-reviewed commit batches), Phase 8a likely splits into 3-5 commits:

1. **schema + cache.** Migration + `app/conditions/cache.py` + tests.
2. **fetchers.** `app/conditions/sources.py` + per-source modules + `scripts/fetch_external_conditions.py` + tests.
3. **conditions UI + chat swap.** Strip template + view-model + `/api/conditions` + `current_temperature_f()` helper + ranking.py amend + tests.
4. **alert evaluator + dispatcher.** `app/alerts/` package + `scripts/evaluate_and_dispatch_alerts.py` + `send_alert_email()` + templates + tests.
5. **subscription UI + close-out.** `/account/alerts` route + template + tests + STATE.md update.

Phase 8b is a single follow-up commit.

---

## §16 Summary

Phase 8 is the implementation of the Opus #1 + #8 texture-moat features the design memo named at `docs/maintainability/conditions_panel_and_alerts_design.md`, refined against the actual Phase 3.1 schema (which already shipped the three tables) + the Phase 4.1 background-jobs scaffold (which provides `with_retry` + structured logging + Sentry breadcrumbs) + the Phase 6.5 anchored placeholder slot (which gives the conditions strip a slot ready to fill).

Three lanes, recommended split into 8a (conditions infrastructure + alerts dispatch + subscription UI; ~10-11 engineering days + 6-12 operator hours) and 8b (cat-13 Public & Civic Resources expansion; ~2 engineering days + 3-4 operator data-entry hours). 8a is the load-bearing infrastructure work; 8b is content + a modest Layer 3 scraper that can dispatch in a separate short Cursor session.

The architecture leans on five existing project patterns: feature-scoped packages (`app/conditions/`, `app/alerts/`), additive Alembic migrations (no destructive schema changes), Railway scheduled jobs per `docs/operations/railway_scheduled_jobs_runbook.md`, `SourceLimiter` for per-source rate limiting (`app/contrib/rate_limiter.py:39`), and `with_retry` for transport-level retries (`app/core/background.py:77`). One new infrastructure pattern introduced: per-source-Railway-service for failure isolation (rejecting the design memo's wide-service alternative). Two-tier caching (in-process + DB) keeps homepage strip reads cheap. Direct-Resend dispatch (not Outbox-wrapped) for V1, with 15-min cron retry as natural recovery; V1.5 promotion to Outbox if dispatch failure rate >5% post-launch.

Critical risks: AirNow approval lag (pre-positioned via prereq checklist), USGS gauge retirement (env-var-configurable gauge ID + Layer 5 fallback), Resend deliverability on a new email cohort (SPF/DKIM/DMARC + List-Unsubscribe header), NWS semantic drift (test fixtures + Sentry monitoring), heat_exposure tagging incompleteness (pre-flight smoke check + cold-start template fallback).

What Phase 8 explicitly does NOT ship: SMS (V1.5), push (V2), historical conditions, forecast alerts, per-favorite alerts, custom user thresholds, operator pre-approval UI, multi-language, conditions-driven category-page banners, fully-wired `event_traffic` (deferred to Phase 9.5 since Events as ENTITY type comes in Phase 9).

---

*Authored by Cowork plan-agent at the post-`4b159df` design-pre-position session (2026-05-20). Pre-positioned during Cursor's Phase 6.4 + Phase 7 parallel lane work, against an estimated dispatch window of late June 2026 after Phase 7 ships. Input to the future Phase 8 dispatch wrapper; SHA-patch slots in §15.2 fill at dispatch authoring time.*

---

### Critical Files for Implementation

- `C:\Users\casey\projects\havasu-chat\app\db\models.py` (lines 1342-1431 — `AlertSubscription`, `AlertDispatched`, `ExternalConditionsCache` already exist; Phase 8 adds two columns + CHECK constraint extension)
- `C:\Users\casey\projects\havasu-chat\app\core\ranking.py` (lines 12, 59, 94 — `STUB_CURRENT_TEMPERATURE_F` swap surface; add `current_temperature_f()` helper)
- `C:\Users\casey\projects\havasu-chat\app\core\background.py` (`with_retry` + `OUTBOX_KIND_*` patterns; Phase 8 reuses for fetcher retry envelope)
- `C:\Users\casey\projects\havasu-chat\app\auth\email_sender.py` (Resend integration to extend with `send_alert_email()`)
- `C:\Users\casey\projects\havasu-chat\app\templates\home.html` (lines 80-99 area — anchored edit at `<!-- conditions-strip-anchor -->` to replace Phase 6.5 placeholder)

### One-paragraph summary

I produced a ~900-line Phase 8 architectural design document covering all 13 requested sections — `external_conditions_cache` schema (Phase 3.1 already shipped the base; Phase 8 adds `last_attempt_at` + `next_attempt_after` columns + extends the `delivery_status` CHECK), conditions fetcher subsystem at `app/conditions/` with per-source Railway scheduled jobs (rejecting the design memo's wide-service in favor of per-source failure isolation), `/api/conditions` endpoint + view-model + conditions strip replacing the Phase 6.5 placeholder, alert dispatch evaluator script with persistent dedup via the existing `alerts_dispatched` table, per-`alert_type` threshold definitions (NWS-issued heat advisory; AirNow category "Unhealthy for Sensitive Groups" or worse; operator-approved LHC keyword match; `event_traffic` deferred to Phase 9.5), mobile-first `/account/alerts` subscription UI, three alert email templates with venue-context mapping from `UserFavorite` × `Entity.heat_exposure`, recommended Phase 8a/8b split (conditions+alerts vs cat-13), top-5 risk register (AirNow approval lag, USGS gauge retirement, Resend deliverability, NWS semantic drift, heat_exposure tagging incompleteness), concrete pass/fail acceptance criteria, refined effort estimate of 12-13 dispatch days plus 6-12 operator hours (revises master plan's M up to M-L), and the explicit non-scope list (SMS V1.5, push V2, no historical/forecast/per-favorite alerts). Important note: I was in READ-ONLY planning mode and could not write the file directly to `outputs/phase_8_architecture_design.md` — the document is delivered in the response above for the user to save.
