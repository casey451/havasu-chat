# Phase 2.5 Rate-Limiter — §8 Decisions Memo

**Status:** decision-input only; no implementation.
**Source design:** `docs/maintainability/phase2_5_rate_limiter_design.md`
**Author:** Cowork sub-agent (read-only investigation lane, 2026-05-13)
**Audience:** Cowork primary running a decision round with the operator (Casey).

This memo grounds every recommendation in `path:line` citations from the
working tree so the primary can answer the operator without re-reading the
design doc. The design's Option A / Option B / Option C choice for the
limiter shape itself is fixed; only the 7 §8 open questions are in scope.

A note on urgency framing: the 2026-05-12 strategic pivot reshaped this lane.
The pre-pivot "Phase 2.5 Premier inventory refresh" justification (design doc
§2.1) is partly obsolete; the new load comes from the directory surface
(category pages, map geocoding, address validation). Where this changes a
recommendation it is called out explicitly. The rate-limiter is in the
"load-bearing under either vision (KEEP)" bucket per the
`docs/SESSION_HANDOFF_2026-05-12.md:3` pointer to `STRATEGY_PIVOT_2026-05-12.md`
§6 — directory-first pivot makes it **more** urgent, not less, because the
directory hits Google Places more than chat ever did.

---

## §1 Summary recommendations

| # | Question | Recommended answer | Confidence | Blocks impl? |
|---|---|---|---|---|
| 1 | Scope framing ("third-party-source" vs "enrichment-ingest") | Confirm retitle; "third-party-source" is correct | High | No |
| 2 | Default QPS for unified limiter | 4 QPS default; expose `qps=` constructor arg so enrichment can keep its 6.5 QPS | Medium | No |
| 3 | 429-after-retry-exhaustion policy | Keep `PlacesLookupResult(status="error", error_message="http_429_retry_exhausted")`; defer queue/alert to P2 | High | No |
| 4 | Observability surface | (c) structured logs in P1; reuse Option-B's `provider_api_quota` table for telemetry when P2 lands | Medium | No |
| 5 | Phase 2.5 launch concurrency | Single-process is sufficient; ship Option A only; schedule Option B as follow-up | Medium-High | Yes (sizing) |
| 6 | `url_fetcher.py` inclusion | Defer — per-host throttling is a different shape; file follow-up | High | No |
| 7 | OpenAI as future source | Eventually wrap via same interface (with `retry-after` handling); not in P1 | Medium | No |

Q5 is the only question that materially changes lane sizing. Q3–Q4 have
defensible alternatives; Q1, Q6, Q7 are near-uncontested.

---

## §2 Per-question detail

### §2.1 — Q1 (scope framing)

**Question (verbatim from §8):** "Confirm the §0 scope correction. Is
'third-party-source rate-limiter' the right framing, or did the brief mean
something specific by 'enrichment-ingest' that I missed?"

**Evidence:**

- `phase2_5_rate_limiter_design.md:13` — design doc found
  `scripts/ingest/{validate,ingest}_enrichment_csv.py` makes zero external
  API calls. Independently confirmed: searches for `requests` / `httpx` /
  `urllib` in the ingest path return no matches.
- `phase2_5_rate_limiter_design.md:17-24` — table of the actual rate-limit
  surface: `places_client.py::lookup_provider`,
  `places_discovery.py::request_text_search`,
  `places_enrichment.py::request_place_details`,
  `url_fetcher.py::fetch_url_metadata`, `river_scene.py::_sleep_polite`.
- `app/contrib/places_client.py:95-126` — the runtime gap: bare
  `httpx.Client.post` with no backoff, error envelope returns
  `status="error", error_message="http_{status}"` on non-2xx.

**Options:**

- (a) Confirm the §0 retitle. Implementation lane targets the third-party
  HTTP-call surface; CSV ingest stays untouched.
  Pros: factually correct; matches the load profile of the directory-first
  pivot. Cons: none material.
- (b) Push back on the retitle. Brief literally said "enrichment-ingest";
  perhaps a future revision will add a Places call inside the CSV ingest
  for pre-fill.
  Pros: keeps optionality. Cons: speculative; if the future change ships,
  it'll route through the same `SourceLimiter` instance by design (per
  `phase2_5_rate_limiter_design.md:154`), so confirming the retitle does
  not foreclose this.

**Recommendation:** (a) Confirm the §0 retitle. "Third-party-source
rate-limiter" is correct.

**Rationale:** The design author's read of the code is verifiable. The CSV
ingest path remains a non-target; if Casey later wants Places pre-fill
inside CSV ingest, that's a separate ticket whose new call site routes
through the same module by design.

**Dependencies:** None. Independent of Q2–Q7.

**Risks / surprises:** None.

---

### §2.2 — Q2 (default QPS)

**Question (verbatim from §8):** "Per-source default QPS.
`places_discovery.py` uses 4 QPS (line 74); `places_enrichment.py` uses the
same. Is that the operator-tuned right value, or a guess that Casey wants
revisited?"

**Evidence:**

- `scripts/places_discovery.py:74` — `INTER_REQUEST_SLEEP_S = 0.25` (4 QPS).
- `scripts/places_discovery.py:71-73` — comment: "Conservative pacing — well
  under the 600 QPM default Places API quota. 0.25s ≈ 4 QPS."
- `scripts/places_enrichment.py:75` — `INTER_REQUEST_SLEEP_S = 0.15`
  (~6.5 QPS). Comment: "~6.5 QPS — comfortable under 600 QPM default."
- `phase2_5_rate_limiter_design.md:21` — design doc claims enrichment
  uses "same shape as discovery" but this is true only for retry constants
  (`RETRY_STATUSES`, `MAX_RETRIES = 5`, delay 1.0s→16.0s cap). The
  inter-request sleep is **different**.
- Google Places (New) documented default: 600 QPM = 10 QPS. 4 QPS = 40%
  utilization; 6.5 QPS = 65% utilization.

**Options:**

- (a) 4 QPS default; enrichment script overrides to 6.5 QPS at construction.
  Pros: defensive default for the runtime path (`lookup_provider`); preserves
  the existing operator-tuned enrichment cadence. Cons: requires the
  `SourceLimiter` constructor to expose a `qps=` override (the design
  signature already does — `phase2_5_rate_limiter_design.md:107-119`).
- (b) 6.5 QPS default everywhere. Pros: simpler. Cons: applies the higher
  rate to the runtime path with no operator decision; consumes more of the
  quota headroom that would otherwise absorb burst from the directory.
- (c) Single 4 QPS everywhere. Pros: simplest. Cons: slows full enrichment
  (~2,525 places) from ~6.5 min to ~10.5 min — a regression that has no
  benefit unless the runtime path is the bottleneck (it isn't today).

**Recommendation:** (a) 4 QPS default with per-instance `qps=` override.

**Rationale:** This is the only option that preserves both existing
operator-tuned values without picking one over the other. 4 QPS is the
conservative-default policy for the lookup path that absorbs unpredictable
contribution-webhook bursts; 6.5 QPS is the operator-paced sweep cadence
that Casey already runs. The `SourceLimiter` interface in
`phase2_5_rate_limiter_design.md:107-119` already accommodates per-instance
overrides.

**Dependencies:** None. The override mechanism is part of the limiter's
designed interface.

**Risks / surprises:** **The design doc's "same constants" claim is wrong.**
The two scripts do not in fact use the same QPS — design §1.1 conflates
retry-constants similarity with pacing-constants similarity. The
implementation lane should not silently round one to the other; the §8 Q2
answer should be explicit that they are preserved independently.

---

### §2.3 — Q3 (failure-mode policy)

**Question (verbatim from §8):** "Failure-mode policy. When Google Places
returns 429 after retry exhaustion, today the script raises `RuntimeError`.
Should the runtime path (`places_client.py`) continue returning
`PlacesLookupResult(status="error")` (current behavior), or escalate to a
louder signal (background-task retry queue, operator-visible alert)?"

**Evidence:**

- `app/contrib/places_client.py:33-47` — `PlacesLookupResult` envelope: the
  `status` field already has a designated `"error"` value, and
  `error_message` is a free-form diagnostic.
- `app/contrib/places_client.py:120-126` — the existing non-2xx handler
  returns `status="error", error_message=f"http_{r.status_code}"` and
  preserves the raw response for audit. A retry-exhausted 429 fits this
  envelope cleanly with `error_message="http_429_retry_exhausted"`.
- `scripts/places_discovery.py:125-129` — script-side retry exhaustion
  raises `RuntimeError(...)`. That's appropriate for a script (process
  exits, operator sees a stack trace) but inappropriate for the runtime
  path (request handler would 500 instead of returning a structured
  no-enrichment result).
- `docs/components/places_client.md:33` — documents the existing failure
  contract: timeouts, transport errors, non-JSON, non-2xx all map into
  `error` with coded `error_message`.
- `phase2_5_rate_limiter_design.md:74` — design doc cites that the
  contribution surface has "no operator alert for 'enrichment failed
  because of a quota error.'" Calling that out as a real failure mode but
  not necessarily one that needs P1 infrastructure.

**Options:**

- (a) Keep the envelope. `lookup_provider` returns
  `PlacesLookupResult(status="error", error_message="http_429_retry_exhausted")`
  on exhaustion. Contribution row stays un-enriched; admin queue surfaces
  it for operator action. Pros: zero new infrastructure, behavior-preserving
  by construction. Cons: silent under operator's view of incoming traffic
  unless Q4's observability answer addresses it.
- (b) Add a retry queue. A new table tracks 429-exhausted enrichments; a
  background job re-runs them after a cool-off window. Pros: guaranteed
  eventual enrichment. Cons: new table, new background job, new operator
  mental model. ~1–2 days of lane work, much of it not designed yet.
- (c) Add an operator alert. Either log-based (paired with Q4's structured
  logs) or push (email/Slack via an existing notification path).
  Pros: lightweight. Cons: needs a destination Casey actually watches.

**Recommendation:** (a) Keep current envelope. Defer queue/alert to P2.

**Rationale:** The current envelope is already structured for this case;
adding a retry queue is a new design lane, not a §8 decision. Whether 429
exhaustion is rare or common at directory-launch scale is something Q4's
observability answer will tell us — if it's frequent, P2 escalates; if
it's rare, the existing "operator notices in admin queue" failure mode is
sufficient. Coupling this decision to Q4 keeps P1 small.

**Dependencies:** **Couples to Q4.** Whatever observability surface Q4
picks must make 429-exhaustion events visible enough that the operator can
decide whether to escalate to P2.

**Risks / surprises:** None. The existing error envelope is already
absorbing the equivalent shape (timeouts, network errors), so adding a
retry-exhausted code is purely additive.

---

### §2.4 — Q4 (observability surface)

**Question (verbatim from §8):** "Observability surface. Where does throttle
telemetry land? Options: (a) script stdout only (current state); (b) a new
`chat_logs`-style table for outbound-API events; (c) structured logs to
whatever Railway log destination Casey already uses. Pick one."

**Evidence:**

- `app/contrib/places_client.py:14, 76` — `logger = logging.getLogger(__name__)`
  and `logger.warning(...)` already in place; structured-log emission is a
  drop-in extension.
- `scripts/places_discovery.py:201-205` — current script stdout: prints
  per-category "N new unique" but nothing about retries or throttle waits.
- `app/api/routes/contribute.py:48-58` — the DB-backed `_rate_limited`
  precedent for option (b): hashes IP into a 24h window, queries a
  submission-tracking table. Note this is *inbound* rate-limiting state,
  not outbound telemetry, but it is the on-tree precedent the design doc
  cites for "rate-limit state lives in the DB" patterns.
- `phase2_5_rate_limiter_design.md:124` — Option B (deferred to P2) adds
  `provider_api_quota` table. If that table ships, it is the natural home
  for both rate-state and rate-telemetry.

**Options:**

- (a) Script stdout only. Pros: zero new code. Cons: invisible for the
  runtime path (no operator console attached to a request handler); blocks
  Q3's "is it rare or frequent?" question.
- (b) New DB table for outbound-API events. Pros: SQL-queryable history,
  per-source/per-hour breakdowns trivial. Cons: new migration; per-call
  commit overhead; over-built for current load; second migration if
  Option B's `provider_api_quota` lands later and overlaps.
- (c) Structured logs to existing destination. Pros: reuses what's already
  wired; both script and runtime path emit through the same `logger`;
  Casey already has Railway log access. Cons: harder to aggregate over
  time without a log-shipping pipeline.

**Recommendation:** (c) structured logs in P1, with (b) reserved as the
P2 home that comes for free with the Option B migration.

**Rationale:** Two parts.

1. **P1 needs visibility into the runtime path.** Option (a) leaves the
   runtime path silent, which is exactly what we want to avoid given Q3's
   recommendation that 429-exhausted enrichments be tracked through the
   admin queue rather than a retry mechanism.
2. **Avoid two migrations.** Option B's `provider_api_quota` table is going
   to ship eventually for state. When it does, columns for telemetry come
   along for negligible additional cost. Standing up a separate telemetry
   table in P1 would create two overlapping DB surfaces.

**Dependencies:** Affects Q3 (operator visibility into 429 exhaustion).

**Risks / surprises:** None material. The implementation lane should agree
on a structured `extra=` dict shape (e.g., `{"source": "google_places",
"event": "retry"|"throttled"|"exhausted", "status": 429, "attempt": N,
"elapsed_s": ...}`) and use it consistently across the limiter — this is
implementation detail, not a §8 decision.

---

### §2.5 — Q5 (launch concurrency)

**Question (verbatim from §8):** "Phase 2.5 launch concurrency. Will Phase
2.5 Premier inventory refresh ship as a single-process scheduled job, or
as multiple concurrent workers? Answer determines whether P1 is sufficient
or whether P2 (DB-backed) needs to ship in the same lane."

**Evidence:**

- `phase2_5_rate_limiter_design.md:60` — latent Gap C (cross-process
  contention: Casey runs the enrichment script while a contribution webhook
  fires) is acknowledged as theoretical, no concrete failure case today.
- `phase2_5_rate_limiter_design.md:88` — requirement to support "multi-process
  / multi-worker correctness *eventually*"; P2 must be a known migration
  path, not a rewrite.
- `phase2_5_rate_limiter_design.md:100-101` — Option A is per-process only;
  Option B is concurrent-safe.
- `docs/SESSION_HANDOFF_2026-05-12.md:3` and §0 — the 2026-05-12 pivot is
  the authoritative strategic-priority signal; chat is being deprioritized
  in favor of a directory product.
- The original "Phase 2.5 Premier inventory verification refresh" scenario
  (design doc §2.1, the nightly-job-over-hundreds-of-providers picture)
  was scoped pre-pivot. The directory-first pivot's load profile
  (category-page enrichment, map geocoding, address validation) is
  predominantly single-process at V1 — these are scheduled jobs or
  per-request handler calls, not parallel worker fleets.
- `app/contrib/enrichment.py` is fired from contribution-submission webhooks
  which are inbound-rate-limited at 1/hour/IP (`contribute.py:48-58`),
  capping concurrent in-flight enrichments to a manageable number.

**Options:**

- (a) Single-process P1; ship Option A only; Option B follow-up gated on the
  first concrete multi-process scenario. Pros: smallest P1; cleanly migrates
  via stable interface. Cons: gambles on no surprise concurrent worker in
  the next 90 days.
- (b) Ship Option B (DB-backed token bucket) in this lane. Pros: multi-process
  correctness from day one; sponsor-onboarding endpoint + concurrent
  directory backfill workers Just Work. Cons: ~1–2 extra days for migration
  + helper module + tests; per-call commit overhead (negligible at 4 QPS,
  not invisible at higher rates).
- (c) Ship both as a feature flag. Pros: optionality. Cons: maintenance burden
  of two implementations; YAGNI.

**Recommendation:** (a) Single-process. Ship Option A; defer Option B.

**Rationale:** No concrete multi-process scenario exists today, and the
post-pivot V1 directory workflows don't introduce one. The design's
"stable interface so Option B is a drop-in" approach in
`phase2_5_rate_limiter_design.md:134` is intentional precisely to handle
this case — the migration is not painful when the load arrives.

**Dependencies:** None blocking.

**Risks / surprises:** If the operator answers Q5 as "yes, expect a
concurrent backfill worker within 30 days," the recommendation flips to
(b) immediately — that's the canonical first-concrete-multi-process
scenario. This is the only §8 question where the operator's answer
materially changes lane sizing. **Flag prominently in the decision round.**

---

### §2.6 — Q6 (`url_fetcher.py` inclusion)

**Question (verbatim from §8):** "`url_fetcher.py` inclusion. Should arbitrary
contributor-URL fetching get throttled in this lane (per-host rate limiting
against unknown sites), or stay separate? The current design defers it;
flag if that's wrong."

**Evidence:**

- `app/contrib/url_fetcher.py:124-249` — `fetch_url_metadata` does single
  fetch with redirect-following and SSRF block; no rate-limit logic.
- `app/contrib/url_fetcher.py:38-82` — `_is_blocked_target` is the only
  defense in the path: blocks private/reserved/loopback IPs. Public-host
  request-rate is unbounded.
- `app/api/routes/contribute.py:48-58, 228` — inbound rate-limit at
  1/hour/IP caps URL-fetch bursts to 1 per hour per source IP. This is
  the de facto outbound URL-fetch rate-limit today.
- `phase2_5_rate_limiter_design.md:160` — design explicitly defers url_fetcher
  as a different concern.

**Options:**

- (a) Defer (current design position). Pros: keeps lane scope tight; the
  inbound rate-limit already provides de facto protection. Cons: leaves
  a known gap that may matter later (admin re-fetches, future bulk
  contributor-URL refresh).
- (b) Include in P1. Pros: closes the gap now. Cons: per-host throttling
  is a fundamentally different data structure (keyed-by-host LRU/TTL map,
  not a per-source fixed instance); folding it into `SourceLimiter`
  conflates two designs; adds ~1 day of lane work.

**Recommendation:** (a) Defer. The design doc's current position is correct.

**Rationale:** `SourceLimiter` is keyed on a known stable source name and
QPS budget. Per-host throttling against an unknown set of public sites needs
a different shape (LRU + TTL to bound memory, host-extraction logic, no
fixed QPS budget per host because each host is different). The two designs
share approximately zero code. The inbound 1/hour/IP limit at
`contribute.py:48-58` provides the de facto outbound rate-limit for the
only call site that exists today.

**Dependencies:** None. Independent of all other §8 questions.

**Risks / surprises:** None. Worth noting that the implementation lane
should leave a `# TODO(rate-limit): see follow-up #XX for per-host
throttling` comment near `fetch_url_metadata` to make the deferral
discoverable.

---

### §2.7 — Q7 (OpenAI as future source)

**Question (verbatim from §8):** "OpenAI as a future source. The brief
mentions OpenAI quota. Today, `app/core/llm_messages.py::call_anthropic_messages`
makes OpenAI calls for chat handlers — those are inbound-rate-limited
(slowapi). Should the same `SourceLimiter` interface eventually wrap them
(with OpenAI-specific `retry-after` header handling), or do LLM calls live
in a separate abstraction?"

**Evidence:**

- `app/core/llm_messages.py:1-17` — file header: "Provider swap (2026-05-07):
  every Anthropic call site was migrated to OpenAI `gpt-4o-mini`." The
  function `call_anthropic_messages` is intentionally retained for
  call-site stability.
- `app/core/llm_messages.py:96-157` — actual implementation: instantiates
  `OpenAI` client, calls `chat.completions.create`, catches `Exception`,
  returns `None` on failure.
- `app/core/llm_messages.py:130-143` — no retry, no rate-limit awareness:
  a single try/except wrapping the SDK call; any exception (including
  rate-limit) returns `None`.
- `phase2_5_rate_limiter_design.md:145` — anti-pattern checklist: "DON'T
  merge the retry-statuses constant across sources. Google Places'
  retry-on-429 is **not** the same policy as OpenAI's retry-on-429 (OpenAI
  returns rate-limit-relevant headers like `retry-after` that the limiter
  should respect)."
- `app/core/rate_limit.py:14-22` — slowapi inbound limiter caps chat at
  120/min; that's the implicit outbound rate-limit on OpenAI today.

**Options:**

- (a) Eventually wrap; not in P1. Use the same `SourceLimiter` interface
  with an OpenAI-specific instance that subclasses or configures
  `retry-after` header handling. Pros: keeps the interface generalized;
  defers a real call-site change until there's a concrete pain point.
  Cons: needs explicit confirmation that the interface accommodates header
  parsing — it does, via `call_with_retry`'s `Callable[[], httpx.Response]`
  signature, which exposes response headers.
- (b) Wrap in P1. Pros: one lane, done. Cons: expands scope by ~1 day
  (new instance + tests in `tests/test_llm_messages.py`); chat is being
  deprioritized per the pivot; no current pain point.
- (c) Keep LLM calls in a separate abstraction. Pros: respects that LLM
  calls have semantics (token budget, model selection, prompt caching)
  that don't apply to Google Places. Cons: duplicates retry + backoff logic;
  exactly the kind of drift the design doc is trying to avoid.

**Recommendation:** (a) Eventually wrap via the same interface; not in P1.

**Rationale:** The `SourceLimiter` interface as specified in
`phase2_5_rate_limiter_design.md:107-119` accommodates per-source
retry-status sets and presumably per-source backoff strategies — a future
OpenAI instance can override these. Wiring it in P1 expands scope without
a corresponding pain point: chat is deprioritized per the pivot, and
slowapi's inbound 120/min cap is the current de facto outbound limit.
**Do not rename `call_anthropic_messages`** — `llm_messages.py:96` header
explicitly retains the name for call-site stability.

**Dependencies:** None blocking P1. The Q4 observability decision applies
to OpenAI's eventual instance too — structured logs and the future
`provider_api_quota` table both generalize.

**Risks / surprises:** The function name `call_anthropic_messages` is
deeply misleading and worth flagging once for the implementation lane:
when the OpenAI limiter wraps it, the wrapping should be by function
identity (the existing import path), not by name pattern matching.

---

## §3 Decisions surfaced during investigation (not §8 questions, but worth flagging)

These came up while grounding the §8 questions and probably belong in the
decision round even though they aren't on the official list.

- **HTTP library mismatch.** `places_client.py:11, 96-97` uses `httpx`.
  `places_discovery.py:39, 110` and `places_enrichment.py:40, 118` use
  `requests`. The design's `call_with_retry` signature in
  `phase2_5_rate_limiter_design.md:116` types the return as
  `httpx.Response`, but the script callers produce `requests.Response`. The
  implementation lane needs to either standardize on `httpx` (recommended;
  it's already in the runtime path) or make `call_with_retry`
  library-agnostic. This is implementation-shape, not a §8 question, but it
  shows up if the operator asks "what changes in the scripts?"
- **Inter-request pacing mismatch (re-flag from Q2).** The design doc's
  §1.1 claim of "same constants" between the two scripts is wrong —
  discovery is 4 QPS, enrichment is 6.5 QPS. Q2 above addresses the
  user-facing decision; flagging here for the implementation lane to not
  silently round one to the other.
- **`PAGINATION_SLEEP_S` is not rate-limit logic.** `places_discovery.py:75`
  exists because Google's `nextPageToken` takes a couple seconds to become
  valid. It is not a retry or a QPS cap. Design §6 mentions deleting it
  along with the other constants but then notes it has different semantics.
  Recommend keeping it inline in the script as a paginate-helper; folding
  it into `SourceLimiter` would muddy the limiter's contract.
- **`river_scene.py::_sleep_polite`** is in design doc §1 table but **out
  of scope** for this lane per §9. Worth confirming with the operator that
  they don't want it folded in for symmetry.

---

## §4 Open meta-questions for the primary

Things I could not resolve from the doc + code alone:

1. **Q5 hinges entirely on the operator's near-term roadmap.** "Will there
   be a concurrent backfill worker within 90 days?" is the operator-only
   answer; my recommendation defaults to "no" based on a pivot doc I could
   not directly access (it is referenced from
   `docs/SESSION_HANDOFF_2026-05-12.md:3` but the file
   `docs/STRATEGY_PIVOT_2026-05-12.md` is not present in the working tree
   I read). The primary should confirm the pivot doc says what the
   sub-agent assumes (directory V1 is single-process).
2. **Q3 + Q4 coupling.** If the operator answers Q4 = (b) DB table, that
   shifts Q3's calculus — once 429-exhaustion is queryable, the case for
   adding an explicit retry queue weakens further. Worth presenting Q3
   and Q4 together rather than independently.
3. **Whether the operator wants river_scene folded in.** Design doc §9
   excludes it; I default to respecting that, but if the operator wants
   one rate-limiter to rule them all, file a question.
