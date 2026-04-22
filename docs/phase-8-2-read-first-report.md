# Phase 8.2 — Load testing (read-first report)

**Date:** 2026-04-22  
**HEAD:** `d171c83` (Phase 8.4)  
**Approach:** **Flavor C** (bottleneck inventory) + **light B** (smoke-test design only — **no load run** in this pass).  
**Out of scope:** synthetic 50-user stress tests, k6/Locust, any code or commits.

---

## Pre-flight

| Check | Result |
| --- | --- |
| `git log` / HEAD | **`d171c83`** |
| `git status` | Clean; **untracked** `docs/phase-9-scoping-notes-2026-04-22.md` only |
| `pytest -q` | **792 passed** |

**STOP triggers:** **None** (no broken-behavior finding that blocks planning; no “must use prod” smoke design; 8.2-implement scope fits a single sub-phase with optional deferrals).

---

## 1. DB-layer bottleneck inventory

### 1.1 Connection pool (`app/db/database.py`)

- **`create_engine(DATABASE_URL, pool_pre_ping=True)`** for non-SQLite; **no** explicit `pool_size`, `max_overflow`, `pool_recycle`, or `pool_timeout`.
- **Behavior:** SQLAlchemy **2.x** defaults for `QueuePool` are typically **`pool_size=5`**, **`max_overflow=10`** (up to **15** checked-out connections). `pool_pre_ping` avoids handing out stale connections after idle disconnects.
- **Railway Postgres:** free/starter tiers cap **max connections** (often ~20–25 for the instance). One app process with default pool is **usually fine**; **multiple** replicas or other services sharing the same DB would require **pool math** (sum of all clients ≤ Postgres `max_connections`).
- **Severity:** **MEDIUM** at scale (multiple workers/replicas or many sidecar jobs); **LOW** for current single-service soft launch.
- **Note:** `SessionLocal` + **`get_db()`** uses `try`/`finally` / `yield` — **no** obvious leak pattern. Each request gets one session and it **closes** in `finally`.

### 1.2 Extra sessions per request (Tier 2 path)

- **`app/chat/tier2_db_query.py` `query()`** uses **`with SessionLocal() as db:`** — its own short-lived session **in addition to** the request’s `get_db()` session used by `unified_router.route()`.
- **Impact:** Tier 2 path holds **one** request session and opens **another** sequentially for the catalog query. Connections are **returned** when the `with` block exits. Not a leak, but **doubles** pool churn for Tier 2 traffic vs Tier 1/Tier 3-only paths.
- **Severity:** **LOW**–**MEDIUM** under concurrent Tier 2 load.

### 1.3 Indexes (models + Alembic)

| Area | Indexes found | Gap |
| --- | --- | --- |
| **`chat_logs`** | `ix_chat_logs_session_id` on `session_id` (Alembic `b2f8c1a9d0e1`) | **No** index on **`created_at`**, **`tier_used`**, or **`query_text_hashed`**. Admin / analytics / runbook SQL that filter on **time windows** can **sequentially scan** as `chat_logs` grows. |
| **`contributions`** | `status`, `source`, `submitted_at` | **No** index on **`submitter_ip_hash`**. `count_submissions_since_by_ip_hash` filters `submitter_ip_hash` + `submitted_at` — small table at soft launch; **O(n)** table growth makes rate-limit check costlier. |
| **`events`** | **None** declared in `app/db/models.py` | Listing by **`status`**, **`date`**, sort by **`created_at`** (admin) relies on table size; at **hundreds of thousands** of rows, **composite** indexes may help. **Current seed scale: LOW.** |

### 1.4 N+1 and heavy query patterns

- **`app/chat/context_builder.py` `build_context_for_tier3`:** Fetches up to **10** providers, then for **each** calls `_programs_for` and `_events_future_for` — **~1 + 2N** ORM round-trips in the worst case (N≤10). Documented scale assumption: “catalog snapshot.” **Tier 3 latency** scales with this + LLM, not a correctness bug.
- **Severity:** **MEDIUM** (latency under load, not a leak).
- **`app/chat/entity_matcher.py` `extract_catalog_entities_from_text`:** In-memory **`_rows`** index, but **`_provider_id_for_name` per matched provider** can add **1 query per match** in the loop. Unusually chatty only when many providers score >75. **MEDIUM/LOW.**
- **`app/contrib/mention_scanner.py` (background):** Not profiled in read-first; uses `SessionLocal` in a **BackgroundTask** after response — second-order pool use.

### 1.5 Summary table (DB)

| ID | File / area | Finding | Scaling concern | Severity |
| --- | --- | --- | --- | --- |
| DB-1 | `database.py` | Default **pool 5+10**; `pool_pre_ping` only | Pool exhaustion if many processes or unbounded clients | **MEDIUM** (later) |
| DB-2 | `chat_logs` | **No** `created_at` index | Slow analytics & time-range reports | **MEDIUM** (post-50k+ rows) |
| DB-3 | `contributions` | **No** index on `submitter_ip_hash` + time | Slower rate-limit `COUNT` as table grows | **LOW** |
| DB-4 | `events` | No explicit indexes in model | Admin list scans at very large N | **LOW** now |
| DB-5 | `context_builder.py` | N+1 for programs/events per provider | Tier 3 slow under concurrency | **MEDIUM** |
| DB-6 | `tier2_db_query.py` | Second `SessionLocal` per Tier 2 | Extra pool use | **LOW**–**MEDIUM** |
| DB-7 | `get_db()` | Standard FastAPI `yield` + `close` | Safe | **—** |

---

## 2. LLM provider bottleneck inventory

### 2.1 Anthropic (`tier3_handler`, `tier2_parser`, `tier2_formatter`)

- **Client:** **`anthropic.Anthropic(api_key=...)` created per call** (e.g. `tier3_handler.answer_with_tier3` L166). **No** shared client singleton; no explicit **`timeout=`** on `messages.create` — **SDK default** (environment-dependent, often on the order of **minutes** unless overridden by env).
- **Retries / rate limits:** **No** application-level retry. **`except Exception`** → log + **`FALLBACK_MESSAGE`** (Phase 8.3). **429 / rate limit** is treated as failure → **graceful**, not backoff-and-retry.
- **Account tier / org limits:** **Not** visible in code — **operator** concern (Anthropic console).
- **Severity:** **MEDIUM** — **concurrency** stacks **parallel** in-flight calls; if many users hit **Tier 2+3** at once, the **bottleneck is often Anthropic (and OpenAI) throughput**, not the Python pool alone. **LOW** for projected soft-launch concurrency.

### 2.2 OpenAI (hint extraction, intent/classifier path, tags, embeddings)

- **`OpenAI()` instantiated per use** in `extraction.py`, `hint_extractor.py`, etc. Same pattern: **no** explicit timeout in snippets reviewed; exceptions often swallowed or return `None` / empty.
- **Severity:** **MEDIUM** same as Anthropic for burst traffic; **LOW** at small scale.

### 2.3 Summary table (LLM)

| ID | File | Behavior | Concern | Severity |
| --- | --- | --- | --- | --- |
| LLM-1 | `tier3_handler.py` | New `Anthropic()` per request; no retry | Connection overhead; no backoff on 429 | **MEDIUM** |
| LLM-2 | All | No explicit `timeout` on API calls (defaults) | Workers blocked for long on hung requests | **MEDIUM** |
| LLM-3 | All | Failure → fallback or `None` | **Correct** per §3.11; not a “broken” path | **—** |

**STOP?** **No** — at **realistic** soft-launch **concurrency** (single digits), **org-wide** Anthropic/OpenAI limits are **extremely** unlikely to be the limiter. **Revisit** when traffic is measurable.

---

## 3. In-memory state bottleneck

### 3.1 `app/core/session.py` `sessions: dict[...]`

- **Unbounded growth:** New **`session_id`** → new entry via **`get_session` → `clear_session_state`**; **no** eviction, **no** max size, **no** TTL sweep on the dict (idle reset only clears **hints** / `prior_entity` in **`touch_session`**, not the dict entry).
- **Threading:** **No** `threading.Lock`. FastAPI **sync** route handlers for **`POST /api/chat`** run in a **thread pool**; in theory concurrent writes to the **same** `session_id` could **race** — in practice a single browser tab is usually one **client**; still a **theoretical** concern at high concurrency. **GIL** reduces but does not eliminate races on composite updates.
- **Memory at 10K / 100K keys:** Proportional to (number of distinct `session_id`s) × (small dict). **10K** sessions in RAM is plausible over **months** of distinct IDs; **100K** without restart is a **stale-attack / crawler** risk more than normal users.
- **Severity:** **MEDIUM** (memory + rare races); **not** a soft-launch blocker. **Fix cost:** **high** (Redis, TTL eviction, or periodic sweep + cap).

### 3.2 Other process-local state

- **`app/chat/entity_matcher.py` `_rows`:** Global list of program provider names; **`refresh_entity_matcher(db)`** reloads from DB. **Read-mostly** after first load. **MEDIUM/LOW** — must **refresh** after bulk import (documented in docstrings). Stale name list until refresh — **ops** not **throughput** bug.
- **No** large in-process ML model cache beyond that.

| ID | Area | Concern | Severity |
| --- | --- | --- | --- |
| MEM-1 | `session.py` | Unbounded `sessions` dict | **MEDIUM** (long-uptime) |
| MEM-2 | `entity_matcher` | Stale `_rows` until refresh | **LOW** (correctness/ops) |

---

## 4. Rate limiting vs. real load (reasoning check)

- **`POST /api/chat`:** **`120/minute` per IP** (`slowapi`, `app/api/routes/chat.py`).  
- **Example:** 10 real users, **~1 message every 30s** each → **10 × 2 = 20 req/min** to the app from **10 IPs** (each under **120**). **Comfortable.**
- **Stressed single user:** **burst** of >120 req/min to **one** IP (scripts, bug, abuse) **hits 429** before the LLM — **intended.**
- **Conclusion:** For soft launch, the **practical** ceiling is **not** the app rate limit; it is **downstream (Anthropic/OpenAI token rate + latency)** and **DB connection** count if **concurrency** spikes. **This matches** the Part C focus.

---

## 5. FastAPI / uvicorn worker configuration

- **`Procfile`:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT` — **single** worker process, **default** (often **1** event loop; sync views run in **thread pool**).
- **No** `Dockerfile` / `railway.toml` in repo — **Rail** uses Nix/Procfile.
- **`POST /api/chat` handler:** **sync** `def`; **`unified.route`** and LLM/DB are **blocking** for the full **Tier 1 + Tier 2 + Tier 3** path (up to many **seconds** for **Tier 3**).
- **Implication:** Under **concurrent** users, the **thread pool** queues; **p95** latency **rises** with concurrency even if **upstream** is fine. **MEDIUM** — not fixed by a **single** small pool tweak; **mitigations** = more workers (× session affinity problem for in-memory `sessions` **without** shared store), or **async** refactors (large).

| ID | Finding | Severity |
| --- | --- | --- |
| SRV-1 | Single uvicorn process, **blocking** `POST /api/chat` | **MEDIUM** (queueing under load) |
| SRV-2 | In-memory sessions **tied to process** | **High cost** to multi-worker | **N/A** until shared session store |

---

## 6. Part B — Proposed smoke test (8.2-implement, not run now)

**Goal:** **5–10** concurrent “users” (distinct `session_id`s or threads), **2–5** minutes, against **`http://127.0.0.1:8000`** (or `localhost`) with a **pre-started** `uvicorn` using **project venv** and local **SQLite** or dev DB — **not** production.

| Aspect | Proposal |
| --- | --- |
| **Mechanism** | **`concurrent.futures.ThreadPoolExecutor`** (sync `httpx` or stdlib `urllib.request`) or **`httpx` client** in each worker — **stdlib + `httpx`** (already a common test dep; if absent, use **`requests`** in venv or pure **urllib**). **Avoid** k6/Locust. |
| **Script** | **New** `scripts/smoke_concurrent_chat.py` (or `scripts/phase8_2_smoke_chat.py`) to avoid overloading `run_query_battery.py` (that targets **production** `POST /chat` and 120+ queries — wrong shape). |
| **Load shape** | **8** threads (middle of 5–10) × each sends **1 req every ~20–30s** for **3 min** → **~6–8 requests per thread**; **or** a short **burst** (all threads start within a second) with a **dozen** total requests. Mix **fixed queries** that tend to land **Tier 1** (e.g. hours for known provider), **Tier 2** (open-ended with filters if stable), **Tier 3** (broad). |
| **Metrics** | Per request: **HTTP status**, **elapsed** `time.perf_counter` ms, **optional** `tier_used` and `latency_ms` from JSON. Aggregate **p50/p95**, **error count** (5xx, timeout), **% fallback** (`response` text equals `FALLBACK_MESSAGE` or contains “Something went sideways”) — treat high fallback as **degraded** in smoke, not just “error.” |
| **Pass criteria (draft)** | **Zero** 5xx; **zero** unhandled client exceptions; **p95** end-to-end **&lt; 20s** for **Tier 3**-heavy cases on **local** (cold JIT + SQLite + one machine — owner may tighten to **15s** on a fast dev box). **% fallback &lt; 5%** unless keys missing (if **no** API keys in test env, skip Tier 3 assertions or `pytest.skip`). |
| **Time** | **&lt; 10 min** wall clock including one server start, per prompt. |
| **Deps** | Prefer **existing** stack; if adding **`httpx`**, one line in **`requirements.txt`** in **8.2-implement** — not in read-first. **No** new **distributed** test infra. |

**STOP?** This design is **in-process HTTP** + **no** production URL — **no** k6/Locust scope creep.

---

## 7. Recommended 8.2-implement scope

### 7.1 Include (prioritized, cheap first)

| # | Change | Bottleneck | Cost | Notes |
| --- | --- | --- | --- | --- |
| 1 | **Add smoke script** + `README` blurb (how to run `uvicorn` + script) | Part B verification | **Small** | Owner lean: **include**; reusable in dogfooding. |
| 2 | **Optional** Alembic migration: **`chat_logs(created_at)`** index (and optionally **`(created_at, tier_used)`** if queries justify) | **DB-2** analytics | **Small**–**medium** | **Migration** = owner says “go” on schema change; add **tests** if migration harness requires. |
| 3 | **Document** pool / worker limits in `docs/runbook.md` or a short `docs/perf-notes-8-2.md` (no handoff edit unless desired) | **DB-1**, **SRV-1** | **Trivial** |
| 4 | **Set explicit** `httpx`/`anthropic` **timeouts** in code (e.g. **60s** read for Haiku) | **LLM-2** stuck workers | **Small** | Behavior change: needs **8.3-style** test that timeout → graceful path still holds. |
| 5 | **Context builder** batch: batch-fetch programs/events for multiple **provider_id**s in fewer queries | **DB-5** | **Medium** | Most **impact**; **highest** code surface — can **defer** to post-8.2 if timeboxed. |
| 6 | **Entity matcher** coalesce `provider` lookups into one `WHERE IN` in **extract** path | **N+1** in matcher | **Small**–**medium** | Defer if tests heavy. |

### 7.2 Defer post-launch (and trigger signals)

| Item | Why defer | Revisit when |
| --- | --- | --- |
| **Redis + shared session** (multi-worker) | **Expensive**; in-memory **OK** for single process | **Horizontal** scale or need **&gt;1** uvicorn worker without sticky sessions |
| **Session dict TTL / eviction** | **Medium** code; edge abuse | `sessions` **memory** report or OOM; abuse pattern |
| **Per-request Anthropic singleton** (HTTP/2 pool) | **Medium**; **measure** first | p95 LLM time dominated by **client connect** in profiling |
| **Composite** **events** / **submitter_ip_hash** indexes | **Low** benefit at current N | `EXPLAIN` shows seq scans in prod |

### 7.3 Scope size estimate

- **Small:** smoke script + docs only.  
- **Medium (expected):** smoke **+** (index migration **or** small timeout PR **or** one N+1 batch fix) **— pick 1–2** to stay contained.  
- **Large:** smoke + **context_builder** batch rewrite + **timeouts** + **index** + entity matcher — **split** to **8.2.1/8.2.2** if owner wants all.

**Recommendation:** **Medium** — **include** the **smoke script** (owner), add **`created_at` index** if **1 migration** is acceptable, add **LLM read timeouts** with **tests** if time allows; **batch context_builder** as **“stretch or 8.2.1”** to avoid a **large** monolithic 8.2.

---

## 8. Severity roll-up (for one-paragraph summary)

- **Counts (approx.):** **HIGH** 0, **MEDIUM** ~7 (DB pool/created_at, Tier3 N+1, LLM no-timeout + no-retry, sessions growth, single-worker blocking, Tier2 second session, entity_matcher N+1), **LOW** several (events index, **submitter** index, **entity_matcher** cache staleness).
- **8.2-implement (draft):** smoke test script (**small**); optional **index** + **timeout** + **one** query batch = **medium** cost mix.
- **Part B in one line:** *New local-only concurrent **POST /api/chat** script (~8 workers × ~3 min) recording **p50/p95**, **5xx=0**, **fallback%**, and **no** 5xx — **httpx** + **ThreadPoolExecutor**, **no** prod, **&lt;10 min** wall clock.*

---

## 9. Acceptance (read-first)

- [x] Items **1–7** in this file  
- [x] `docs/phase-8-2-read-first-report.md` created **uncommitted**  
- [x] No code / tests / load executed / no commit  

**Path to report:** `docs/phase-8-2-read-first-report.md`

---

*Handback: this message + file. No `phase-8-2-handback-*.md` generated to avoid extra untracked files.*
