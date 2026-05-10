# Phase 2.5 — Third-Party-Source Rate-Limiter Design

**Status:** OPEN — design only; no implementation, no tests, no production code change.
**Source of truth for:** how `havasu-chat` should throttle outbound calls to third-party data sources (Google Places API today; sponsor-onboarding refresh + Phase 2.5 Premier inventory in the future) once concurrent operator workflows + a future API endpoint make per-source contention real.
**Audience:** any agent (Cowork / Claude Code / Cursor) executing the implementation lane that follows this design.
**Companion docs:** `docs/components/places_client.md` (the runtime Places-touching path that has the rate-limit gap), `docs/components/enrichment.md` (background contribution enrichment), `docs/sponsor_outreach/enrichment_sprint_runbook.md` (operator workflow that drives current usage), `docs/maintainability/llm_mock_pattern.md` (the test-pattern doc this lane mirrors in shape: design-first, ship-when-load-bearing).
**Forward-looking premise:** this lane authors the design now so the implementation can follow when the rate-limiter actually becomes load-bearing — currently it is **not** load-bearing for the operator-driven 50-business enrichment sprint (§1.0). The doc is a tool for that future implementation lane.

---

## 0. Scope correction (operator: please confirm or push back)

The dispatch brief framed this as *"enrichment-ingest rate-limiter"* and pointed at `scripts/ingest/{validate,ingest}_enrichment_csv.py`. **Investigation found that script makes zero external API calls** — it is a pure local CSV → SQLite upsert. ENRICHMENT_FIELDS (`scripts/ingest/ingest_enrichment_csv.py:75–82`: address, phone, email, website, hours, description) are operator-typed from a spreadsheet; the script never touches Google Places, Yelp, OpenAI, or any other third-party HTTP surface. The validator is also network-free.

The actual rate-limit surface in this codebase is upstream of that script:

| Path | What it hits | Has rate-limit today? |
|---|---|---|
| `app/contrib/places_client.py::lookup_provider` (~192 LOC) | Google Places (New) Text Search | **No** — documented limitation in `docs/components/places_client.md:55` |
| `scripts/places_discovery.py::request_text_search` | Google Places Text Search (sweep) | Yes — DIY: 0.25s inter-request, 2.0s pagination, 5×exponential-backoff retry on 429/5xx |
| `scripts/places_enrichment.py::request_place_details` | Google Places Place Details | Yes — DIY: same shape as discovery (lines 109–136) |
| `app/contrib/url_fetcher.py::fetch_url_metadata` | Arbitrary contributor URLs | SSRF block; **no** request-rate throttle |
| `app/contrib/river_scene.py::_sleep_polite` | River Scene scrape | DIY: 1.0s polite-sleep + per-attempt backoff |

The forward-looking targets called out in the brief (Phase 2.5 Premier inventory verification refresh, future sponsor-onboarding API endpoint, concurrent operator workflows sharing API quota) all wire into one or more of those paths — not into the CSV ingest path. **This design therefore retitles the subject from "enrichment-ingest rate-limiter" to "third-party-source rate-limiter."**

The CSV ingest path stays in scope only as a *non*-target — confirming it does not need throttling forecloses a category of "should we?" questions for the implementation lane. If the operator wanted the literal "enrichment-ingest" framing for a different reason (e.g., anticipating that a future revision of the CSV ingest will pull from Places to pre-fill rows), say so and I'll re-scope.

---

## 1. Current state inventory

### 1.0 Why the rate-limiter is not load-bearing today

- The 50-business enrichment sprint is operator-driven: Casey hand-fills CSVs from phone calls and site visits, validates, dry-runs, then applies. One CSV at a time, hand-paced.
- The Places-touching scripts (`places_discovery.py`, `places_enrichment.py`) already throttle themselves and are run on Casey's schedule, never concurrently.
- The runtime path (`places_client.py::lookup_provider`) is invoked from `app/contrib/enrichment.py::enrich_contribution`, which fires from contribution-submission webhooks (rate-limited at the inbound side: 1/hour/IP via `app/api/routes/contribute.py::_rate_limited`). Effective outbound QPS today is well under 1.

### 1.1 Existing throttle patterns (the "don't reinvent" reference)

**`scripts/places_discovery.py:71–80, 95–129`** — the canonical script-side pattern:

- `INTER_REQUEST_SLEEP_S = 0.25` (≈4 QPS, well under Google's 600 QPM default)
- `PAGINATION_SLEEP_S = 2.0` (Google's `nextPageToken` takes ~seconds to become valid)
- `RETRY_STATUSES = {429, 500, 502, 503, 504}`, `MAX_RETRIES = 5`, `delay = 1.0` doubled to a 16.0s cap.

**`scripts/places_enrichment.py:108–136`** — copy-pasted from the above, same constants. **Code duplication is a real artifact, not a hypothetical concern.**

**`app/api/routes/contribute.py:48–58, 228`** (`_rate_limited`) — the on-tree DB-backed precedent: hashes client IP into a 24h window via a DB-tracked submission table, returns boolean "would this submission exceed 1/hour for this IP." Notable for being process-independent (multiple FastAPI workers see the same window via the DB).

**`app/core/rate_limit.py`** — `slowapi.Limiter` instance for *inbound* HTTP rate limits (chat: 120/min, programs: 5/min). Not applicable to outbound calls but worth noting as the "we already depend on slowapi" anchor.

### 1.2 The gap

Two concrete gaps the design must close:

- **Gap A — Runtime path (`places_client.py`) has no backoff.** A burst of contribution submissions, OR a future sponsor-onboarding endpoint that triggers refresh, would slam the API. Mitigated today only by inbound rate-limits making the burst small.
- **Gap B — Script-side duplication.** Discovery and enrichment scripts each carry their own retry logic. A new Phase 2.5 Premier-inventory script would either reimplement the pattern again or borrow informally; either way, drift is the eventual outcome (one script tightens, another doesn't, operator can't predict throttle behavior across the toolchain).

A latent **Gap C — cross-process contention** exists in theory (Casey runs `places_enrichment.py` while a contribution comes in and `enrich_contribution` fires) but has no concrete failure case today. The design covers it as an Open Question (§8) rather than a P1 requirement.

---

## 2. Problem statement

A future-state where the rate-limiter becomes load-bearing has three characteristics, any one of which is sufficient on its own:

1. **Phase 2.5 Premier inventory verification refresh.** The Premier sponsor tier (when it ships) likely needs periodic re-verification of stored Provider data — re-pulling Place Details for any sponsor whose `last_verified_at` falls behind a freshness threshold. A nightly job over hundreds of providers will issue a sustained burst of Place Details calls.
2. **Concurrent operator workflows.** Once a second operator (or an automated script triggered by sponsor onboarding) shares Casey's API quota, sleep-based pacing in one process gives no guarantee about aggregate QPS. Two scripts at 4 QPS each = 8 QPS — still under Google's 600 QPM limit, but the principle (no shared-state guarantee) breaks.
3. **Inbound API endpoint for sponsor verification.** A planned-but-not-shipped POST endpoint that triggers a Places refresh inline would invoke `lookup_provider` from a request handler — the burst-shape becomes "however many requests slowapi's inbound limit lets through per minute" and the runtime gap (1.2.A) becomes acute.

The failure modes if the rate-limiter is *missing* in any of those scenarios:

- **Quiet failure (no throttle):** Google Places returns 429s; current script-side retry handles them; current runtime-side path (`places_client.py`) does *not* — it returns `status="error"`, `error_message="http_429"` (`places_client.py:120–126`), and the contribution row keeps the prior un-enriched state. The contribution surface has no operator alert for "enrichment failed because of a quota error."
- **Cost failure (overruns):** A loop bug in any future caller that doesn't observe the script-side sleeps would hit the 600 QPM limit and rack up Places billing fast. Defensive design pushes the throttle below the call site, not above.
- **Operator-confusion failure:** Casey runs `places_enrichment.py` and a contribution arrives mid-run. Both paths hit Places concurrently. Aggregate throttle is invisible — neither path can see the other's pacing.

---

## 3. Requirements

The design must:

1. **Per-source-domain granularity.** A single throttle per *source* (initially: Google Places). New sources (Yelp, openTable, OpenAI for embedding refresh, etc.) plug in without changing the core. The ratelimiter for `places.googleapis.com` is independent of the ratelimiter for `api.openai.com`.
2. **Idempotency-preserving.** The CSV-ingest pattern (`(provider_name, category)` natural key, single transaction with rollback on per-row error — `ingest_enrichment_csv.py:178–252`) must not be broken by retry logic. This is straightforward because the throttle lives below the upsert layer; the implementation lane MUST verify it stays straightforward.
3. **Operator-observability.** Casey can run a script and see: which source is throttled, how long until next slot opens, how many retries fired in the current run. Currently `places_discovery.py` prints "[label] N new unique" but says nothing about backoff; that is a tolerable status quo for a single sequential script and an unacceptable status quo for a concurrent one.
4. **Concurrent-safe (forward-looking).** The design must support multi-process / multi-worker correctness *eventually*. P1 ship can be in-process if the Open Questions below confirm Phase 2.5 launches single-process; P2 must be a known migration path, not a rewrite.
5. **Defensible failure modes.** If the rate-limit-state store goes down (DB unreachable, Redis missing), the call must fail-loud (refuse the call) not fail-silent (assume no throttle and proceed). Catch-22 acceptable: better to surface "rate-limit subsystem unavailable, enrichment paused" than to silently overrun quota.
6. **No infrastructure additions in P1.** Adding Redis is a real ops cost (Railway plan, deploy config, secrets, monitoring). The design must stand without it for P1; introducing Redis is a P2 question that gets its own decision.
7. **Cleanly testable.** Mock-friendly. Mirror the `llm_mock_pattern.md` policy: `@patch` the HTTP boundary, not the rate-limiter logic. The throttle's own unit tests should not require sleeping in the test process (use injectable clock).

---

## 4. Design alternatives

Four credible options, evaluated against the §3 requirements.

| # | Option | Granularity | Concurrent-safe | Infra? | Migration cost | Fit |
|---|---|---|---|---|---|---|
| **A** | In-process per-source semaphore (sleep-based) consolidated in a new `app/contrib/rate_limiter.py` | Per source | **No** (per-process only) | None | Low | Good for P1 single-process; clean P2 migration if interface is stable |
| **B** | DB-backed token-bucket in a new `provider_api_quota` table; mirror the `_rate_limited` IP-hash precedent | Per source | **Yes** | New schema migration | Medium | Best long-term fit; over-built for P1 single-process state |
| **C** | External rate-limiter (Redis token bucket, e.g. `aiolimiter` against a Redis backend) | Per source | **Yes** | Redis infra | High | Right for high-QPS multi-process; out of scale for our load profile |
| **D** | Application-layer pre-check (call source's quota endpoint before each request) | Per source | Indirect (via source) | None | Low | Wrong shape — Places New does not expose a quota-remaining endpoint; latency-doubling for no benefit |

**A in detail.** A new module `app/contrib/rate_limiter.py` exposes:

```python
class SourceLimiter:
    def __init__(self, source: str, qps: float, *, max_retries: int = 5,
                 backoff_initial_s: float = 1.0, backoff_cap_s: float = 16.0,
                 retry_statuses: frozenset[int] = frozenset({429, 500, 502, 503, 504}),
                 clock: Callable[[], float] = time.monotonic): ...

    def acquire(self) -> None: ...  # blocks (sleeps) until next slot

    def call_with_retry(self, fn: Callable[[], httpx.Response]) -> httpx.Response: ...
        # combines acquire() + the existing retry/backoff shape, returns response or raises

GOOGLE_PLACES_LIMITER = SourceLimiter("google_places", qps=4.0)  # default tuned to existing scripts
```

`places_client.py::lookup_provider` swaps its raw `httpx.Client.post` for `GOOGLE_PLACES_LIMITER.call_with_retry(lambda: client.post(...))`. `scripts/places_discovery.py::request_text_search` and `scripts/places_enrichment.py::request_place_details` both delete their inline retry logic and route through the same limiter. `INTER_REQUEST_SLEEP_S` and `MAX_RETRIES` move from script-local constants into the `SourceLimiter` constructor — overridable per-script if a future operator-driven sweep needs a different cadence.

**B in detail.** A `provider_api_quota` table with `(source, window_start, request_count)` rows; pre-check + post-record around every call. Migration adds the table; helper module reads and writes inside a single transaction. Two operators / workers / scripts running concurrently see the same window and back off identically. Cost: the migration, the helper's commit-per-call overhead (negligible at 4 QPS, real at 400 QPS), and the operator-mental-model load of "rate limit state lives in the DB now."

**C in detail.** Redis token bucket via `aiolimiter` or similar. Solves multi-worker correctness elegantly. Cost is real: a new Redis dependency on Railway (additional plan tier or sidecar), a new env var, a new outage class ("Redis is down, enrichment is paused"). Disproportionate to the load.

**D in detail.** Skip — Places New does not expose a quota-remaining endpoint. Even if it did, doubling the latency of every call to ask "may I call you?" is wrong shape.

---

## 5. Recommended approach

**Ship Option A in P1; design the `SourceLimiter` interface so Option B is a drop-in replacement when needed.**

Reasoning:

- **Option A solves the actual P1 gaps.** Gap A (runtime path missing backoff) is closed by routing `places_client.py` through `SourceLimiter`. Gap B (script duplication) is closed by routing both `places_*.py` scripts through the same module. Single-process is sufficient because Phase 2.5 ships single-process by default (verify in §8).
- **Option B is the correct long-term fit but over-built today.** The DB migration, the per-call commit overhead, and the operator-mental-model cost are not earned by current load. When a second worker or a sponsor-onboarding endpoint enters the picture, swap the `SourceLimiter` implementation behind the same interface — caller code does not change.
- **Option C is structurally wrong for this product.** We are not a high-QPS API service; we are a concierge tool with operator-driven enrichment bursts. Adding Redis is a deployment-complexity tax with no proportionate operational return.

**Anti-pattern checklist for the implementation lane:**

- DON'T let `SourceLimiter` become a global singleton hidden in module state. Construct named instances at module top-level (`GOOGLE_PLACES_LIMITER`, future `OPENAI_EMBEDDING_LIMITER`); inject for tests.
- DON'T merge the retry-statuses constant across sources. Google Places' retry-on-429 is *not* the same policy as OpenAI's retry-on-429 (OpenAI returns rate-limit-relevant headers like `retry-after` that the limiter should respect). Per-source policy lives in the per-source instance.
- DON'T add a "global throttle" abstraction that caps total outbound QPS across all sources. That is YAGNI today and the wrong shape — sources are independent and should be limited independently.
- DON'T call `time.sleep` inside `places_client.py` directly. The whole reason to extract `SourceLimiter` is that the call site stops caring how the throttle is enforced.
- DON'T silently swallow rate-limit-state-store failures (when Option B lands). Fail loud, refuse the call, surface to caller.

---

## 6. Integration points

**`app/contrib/places_client.py`** — primary change. `lookup_provider` swaps the bare `httpx.Client.post` (line 96–97) for `GOOGLE_PLACES_LIMITER.call_with_retry(...)`. Behavior on success unchanged; the existing error envelope (`PlacesLookupResult(status="error", error_message=...)`) absorbs new retry-exhausted cases the same way it absorbs current network errors. No new failure modes surface to callers.

**`scripts/places_discovery.py`** and **`scripts/places_enrichment.py`** — secondary change. Replace `request_text_search` / `request_place_details` retry blocks with `GOOGLE_PLACES_LIMITER.call_with_retry`. Delete `INTER_REQUEST_SLEEP_S` / `PAGINATION_SLEEP_S` / `RETRY_STATUSES` / `MAX_RETRIES` constants (now lived in the limiter); keep `PAGINATION_SLEEP_S` semantically (it's not retry, it's "wait for token to validate" — needs its own helper or stays inline).

**`scripts/ingest/ingest_enrichment_csv.py`** — **no change.** The script makes no external calls. The validator (`validate_enrichment_csv.py`) is also untouched.

**`app/contrib/url_fetcher.py`** — out of scope for P1. URL fetching is a different concern (per-host throttling against unknown public sites, not against a known third-party API). File a follow-up if the implementation lane finds a reason to fold it in.

**`app/api/routes/contribute.py`** — no change. Inbound rate-limiting (`_rate_limited`) is separate from outbound; both will exist post-ship.

**Tests:**

- `tests/test_rate_limiter.py` (new) — unit tests for `SourceLimiter` using an injectable `clock`. Pin `acquire()` blocks for the right duration; pin `call_with_retry` retries the correct status set; pin retry-exhaustion raises with diagnostic message.
- `tests/test_places_client.py` (existing) — extend with one regression test pinning that `lookup_provider` honors the `GOOGLE_PLACES_LIMITER` throttle (mock the limiter, assert it was called).
- `tests/test_enrichment.py` (existing) — no change expected; existing mocking should continue to work since `lookup_provider`'s public surface is unchanged.

---

## 7. Rollout plan

This ship is *purely additive* — no behavior change for current load. Suggested phases:

1. **P1.1 — extract `SourceLimiter` + ship the runtime gap close.** New `app/contrib/rate_limiter.py`; new `tests/test_rate_limiter.py`; `places_client.py` routes through the new limiter. **Acceptance:** all existing tests pass + new rate-limiter tests + manual smoke (set `qps=1.0`, fire 5 lookups in a tight loop, observe ≥4s elapsed).
2. **P1.2 — collapse the script duplication.** `places_discovery.py` + `places_enrichment.py` route through `GOOGLE_PLACES_LIMITER`. Delete the duplicated constants. **Acceptance:** dry-run discovery against a 5-category sample returns same place count + same per-category breakdown as pre-refactor; enrichment dry-run resumes correctly from `enrichment_enriched.jsonl`.
3. **P2 (deferred until load-bearing) — Option B migration.** When the second concurrent worker / sponsor-onboarding endpoint / Phase 2.5 Premier refresh job ships, swap `SourceLimiter`'s implementation to the DB-backed token bucket. Add the migration; the public interface (`acquire`, `call_with_retry`) stays. Caller code unchanged.

**Feature-flag strategy:** none needed. The change is behavior-preserving by construction (same QPS pacing, same retry shape, same error envelope). If a regression slips through, the rollback is `git revert` of the script-routing commit (keeps the new module in place but reverts callers to the inline pattern).

---

## 8. Open questions for the operator

These are decisions the implementation lane needs answers to before P1 ships. Listed in order of blocking-ness.

1. **Confirm the §0 scope correction.** Is "third-party-source rate-limiter" the right framing, or did the brief mean something specific by "enrichment-ingest" that I missed?
2. **Per-source default QPS.** `places_discovery.py` uses 4 QPS (line 74); `places_enrichment.py` uses the same. Is that the operator-tuned right value, or a guess that Casey wants revisited? The implementation lane will set the limiter default to whatever is approved here.
3. **Failure-mode policy.** When Google Places returns 429 after retry exhaustion, today the script raises `RuntimeError`. Should the runtime path (`places_client.py`) continue returning `PlacesLookupResult(status="error")` (current behavior), or escalate to a louder signal (background-task retry queue, operator-visible alert)? The first ships with §6 unchanged; the second is a P2 design.
4. **Observability surface.** Where does throttle telemetry land? Options: (a) script stdout only (current state); (b) a new `chat_logs`-style table for outbound-API events; (c) structured logs to whatever Railway log destination Casey already uses. Pick one; the implementation lane wires it accordingly.
5. **Phase 2.5 launch concurrency.** Will Phase 2.5 Premier inventory refresh ship as a single-process scheduled job, or as multiple concurrent workers? Answer determines whether P1 is sufficient or whether P2 (DB-backed) needs to ship in the same lane.
6. **`url_fetcher.py` inclusion.** Should arbitrary contributor-URL fetching get throttled in this lane (per-host rate limiting against unknown sites), or stay separate? The current design defers it; flag if that's wrong.
7. **OpenAI as a future source.** The brief mentions OpenAI quota. Today, `app/core/llm_messages.py::call_anthropic_messages` makes OpenAI calls for chat handlers — those are inbound-rate-limited (slowapi). Should the same `SourceLimiter` interface eventually wrap them (with OpenAI-specific `retry-after` header handling), or do LLM calls live in a separate abstraction? Design doc takes no position; flag for the implementation lane.

---

## 9. Out of scope for this design

Listed explicitly so the implementation lane does not over-deliver:

- The CSV ingest path (`scripts/ingest/{validate,ingest}_enrichment_csv.py`) — no external calls, nothing to throttle.
- Inbound rate-limiting (`slowapi.Limiter`, `_rate_limited` IP-hash) — different concern, working today.
- River Scene scraping (`app/contrib/river_scene.py::_sleep_polite`) — different source, different cadence (1.0s polite sleep), no concrete pain point. File a follow-up if cleanup matters.
- Caching of Places responses (mentioned in `docs/components/places_client.md:55` as the same-line limitation as rate-limiting). Caching is its own design — a `place_id`-keyed cache with TTL would reduce calls but introduce staleness; that is a verification-freshness conversation, not a rate-limit conversation. Separate ticket.
- Cost-based throttling (cap at $X/day per source). Real concern; out of scope for the rate-limiter shape, belongs in a separate "Places cost ceiling" design.
