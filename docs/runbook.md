# Havasu Chat — Operational runbook

**Last updated:** 2026-04-22 (Phase 8.4 runbook; Phase 8.2 performance subsection)

This document is for the **operator** running Havasu Chat in production: daily checks, emergency triage, and enough context for a future hire to get oriented. It does not replace the architecture spec — use [`HAVA_CONCIERGE_HANDOFF.md`](../HAVA_CONCIERGE_HANDOFF.md) (repo root) for locked design and deep detail.

**Local tooling (Windows):** the repo is developed with a project venv — `.\.venv\Scripts\python.exe` (plain `python` on Windows can hit the Store stub). The **test** command is `.\.venv\Scripts\python.exe -m pytest -q`. `curl.exe` with JSON bodies should use `--data-binary "@file.json"` in PowerShell (per project conventions).

---

## Table of contents

1. [Quick reference (read in an emergency)](#1-quick-reference-read-in-an-emergency)
2. [Routine operations](#2-routine-operations)
3. [Detailed context](#3-detailed-context) — includes [§3.10](#310-known-performance-characteristics)
4. [Useful queries (copy-paste SQL)](#4-useful-queries-copy-paste-sql)
5. [Companion docs and contacts](#5-companion-docs-and-contacts)

---

## 1. Quick reference (read in an emergency)

Short, scannable steps. Production base URL: `https://havasu-chat-production.up.railway.app` (replace below with your deployment URL if different).

### 1.1 App is down

1. **Health check (CLI):** from any machine with HTTPS access:

   ```bash
   curl.exe -sS -i "https://havasu-chat-production.up.railway.app/health"
   ```

   Expect **HTTP 200** and JSON like:

   `{"status":"ok","db_connected":true,"event_count":<n>}`

   (`app/main.py` — the handler runs a **cheap** `Event` count; if the DB is unreachable, you may still get `200` with `"db_connected": false` and `"event_count": 0`.) Use `-i` to see the status line if the body is empty.

2. **Railway:** project → service → **Deployments** (last deploy green?) and **Observability → Logs** (boot errors, crash loops, OOM).
3. **Root page:** `curl.exe -sS -o NUL -w "%{http_code}" "https://havasu-chat-production.up.railway.app/"` — expect **200** for the main UI.
4. **Sentry** (if `SENTRY_DSN` is set): new issues spike around the outage window.
5. **Postgres (Railway):** database service → **Metrics** / connection count; ensure the `DATABASE_URL` for the app points at the live instance and the DB is not paused.

**If health fails but Railway shows the process up:** check recent **deploy**, **migrations** (schema mismatch in logs), or **env** (missing `ADMIN_PASSWORD` does not take down `/health`, but missing `DATABASE_URL` on misconfig can break DB paths).

### 1.2 Response quality is way off

1. **Recent deploy?** Rollback in Railway if a bad release is obvious.
2. **Short diagnostic window:** set `SEARCH_DIAG_VERBOSE=true` in Railway env, redeploy or restart, reproduce one query, read `search_debug.log` and logs — then **turn it off** (see [§2.5](#25-toggling-diagnostics)). See [`docs/privacy.md`](privacy.md) for what may be written when diagnostics are on.
3. **Traffic patterns:** open `/admin/analytics` (top queries, zero-result heuristics, daily sessions).
4. **Tier mix / cost:** run `.\.venv\Scripts\python.exe scripts\analyze_chat_costs.py` against a copy of production data or with `DATABASE_URL` pointed at read-only access (see [§3.5](#35-scripts)).

### 1.3 Error rate is spiking (graceful “Something went sideways…” copy)

1. There is **no** automated in-app alert for Tier 3 fallback rate (see [§3.7](#37-failure-modes-and-monitoring)). Run the SQL in [§4](#4-useful-queries-copy-paste-sql) (**Tier 3 fallback rate, last hour / 24 hours**) and compare to your **baseline** (after soft launch, owner defines “normal” from 1–2 weeks of traffic).
2. **Railway logs:** 5xx, stack traces, worker deaths.
3. **Sentry:** error volume and new issues (some caught fallbacks return HTTP 200 with no Sentry event — do not rely on Sentry alone).
4. **Upstream APIs:** Anthropic / OpenAI status; check API keys and quota in provider consoles.

### 1.4 DB is slow or unreachable

1. **Railway:** app logs for connection errors, `pool` / timeout messages; Postgres plugin CPU / connections.
2. **App:** production uses **SQLAlchemy** with `pool_pre_ping` on non-SQLite (`app/db/database.py`) — flaky networks often surface as occasional 500s.
3. **Last resort:** **Restart** the Railway service (clears in-memory session state; see [§3.8](#38-session-state)).

### 1.5 Contribution queue is piling up

1. Open **`/admin/contributions`** and review **count** and oldest rows.
2. On a submission **detail** page, check **URL fetch** and **Google Places** enrichment: failed enrichment is **visible** in the row (`url_fetch_status`, `google_enriched_data`, etc.) and can be retried with **Re-enrich** (see [§3.2](#32-admin-ui-guide)).
3. If **many** Places failures: verify **`GOOGLE_PLACES_API_KEY`**, Google Cloud **billing** and **Places API (New)** enablement, and **quota**.

### 1.6 Users are hitting rate limits (HTTP 429)

| Path | Limit | What users see | Where to look |
| --- | --- | --- | --- |
| `POST /api/chat` | 120/min per IP (slowapi) | JSON with “Slow down a sec! Try again in a minute 😅” | **Railway HTTP / app logs** for 429; not stored in `chat_logs` for failed requests |
| `POST` to public **`/contribute`** | 1/hour per IP **hash** (DB) | HTML rate message on the form | Same; optional SQL on `contributions` by time + IP hash for abuse analysis |

**`RATE_LIMIT_DISABLED`:** when set to a truthy value (`1`, `true`, `yes`, `on`), disables the **global** slowapi limiter for the process (`app/core/rate_limit.py`). **Emergency-only** — do not run permanently in production.

### 1.7 Where to look first

| Symptom | First place to look |
| --- | --- |
| Blank 502/503 | Railway deploy + app logs |
| 200 but wrong or empty answers | Recent deploy, `/admin/analytics`, `SEARCH_DIAG_VERBOSE` (briefly) |
| “Something went sideways” everywhere | [§4](#4-useful-queries-copy-paste-sql) fallback SQL, Anthropic key, Sentry, Railway |
| 429 to users | Railway 429 count; distinguish `/api/chat` vs contribute |
| Admin login fails | `ADMIN_PASSWORD` env, cookie domain, `/admin/login` 401 |
| Enrichment all failing | `GOOGLE_PLACES_API_KEY`, Google billing |
| Stuck “conversation” in browser | [§3.8](#38-session-state) (new session / restart) |

---

## 2. Routine operations

### 2.1 Daily check-in (5–10 minutes)

- **`GET /health`** (or open the app in a browser). Confirm `db_connected` in JSON when the DB is critical; if the UI loads but `db_connected` is false, open Railway DB status before chasing app-only bugs.
- **Sentry:** new issues, regressions. Snooze or resolve noise so new problems surface in **New**.
- **Railway:** one glance at the active deployment (green) and that no autoscaling/restart storm is in progress.
- **`/admin/analytics`:** same-day traffic not zero (unless you expect a quiet day); look for a sudden new topic in the **top user queries** list.
- **`/admin/contributions`:** queue depth; skim oldest **pending** age; open one row to confirm **enrichment** is not systemically failing.
- **`/admin/mentioned-entities`:** if the **unreviewed** backlog is growing, schedule focus time; promotion creates real catalog work.
- **`/admin/feedback`:** thumbs-down not spiking vs recent volume (or run [§4](#4-useful-queries-copy-paste-sql) query 10 for a count).
- **Disk / logs (if you enabled `SEARCH_DIAG_VERBOSE` yesterday):** confirm it is **off** again so you do not accumulate PII-laden `search_debug.log` files in production.

### 2.2 Weekly

- Sentry **triage** (resolve, assign, mute noise).
- Run **`scripts/analyze_chat_costs.py`** (default **30d** window in script) — tier distribution and token/cost ballpark; shorten window in SQL if you need 7d only.
- **Contribution SLA:** how long are rows **`pending`**? (SQL in [§4](#4-useful-queries-copy-paste-sql).)
- **`/admin/mentioned-entities`:** unreviewed mention backlog.

### 2.3 Monthly / as needed

- **`/admin/categories`:** category / hint drift; informs intake.
- Re-read **`docs/pre-launch-checklist.md`** for stale open items.
- **Cost review:** OpenAI, Anthropic, Google Places billing vs traffic.
- **Backup / restore:** Railway Postgres **backups** (if enabled on your plan) are the primary **point-in-time** safety net. Before **destructive** `POST` actions ([§2.4](#24-running-backfills-and-bulk-admin-actions)) or a **schema** migration, confirm a **recent backup** or take a one-off **dump** (`pg_dump`) when you are about to do something you cannot easily undo. Restoring a dump is a **procedure** for the owner — not covered step-by-step here; keep a link to Railway’s “restore from backup” doc in your own notes.
- **Dependency / license audit (light):** once a quarter, confirm API **keys** and **Google Cloud** project still belong to the right billing account; rotate **secrets** that have been in email or old tickets.

### 2.4 Running backfills and bulk admin actions

All of these require an **admin session cookie** (use browser after `POST /admin/login`, or tools that send the cookie). Prefer **maintenance windows** for expensive calls.

| `POST` endpoint | What it does | Cost / risk |
| --- | --- | --- |
| `/admin/reembed-all` | Recomputes **embeddings** for every **event** (OpenAI) | **$$** + time; every row |
| `/admin/retag-all` | Regenerates **tags** for every event (OpenAI) | **$$** + time |
| `/admin/programs-reseed` | Imports from `docs/HAVASU_CHAT_SEED_INSTRUCTIONS.md` (supports `?dry_run=true`) | **Writes**; idempotent design but review output |
| `/admin/reseed` | **Destructive:** deletes **seed-origin** events and re-runs seed | **Data loss** for those rows; backup first |

**Do not** run destructive endpoints against production without a **backup** and a clear **reason**.

### 2.5 Toggling diagnostics

1. In Railway, set **`SEARCH_DIAG_VERBOSE=true`** (or `1` / `yes`, case-insensitive per `app/core/search_log.py`).
2. **Redeploy** or **restart** so the worker picks up env.
3. **Output:** (a) `search_debug.log` at the **project repo root path** resolved from `app/core/search_log.py` in the container’s filesystem, and (b) logger **`search_diag`** to stdout at DEBUG.
4. **Turn off** by unsetting or setting to false, then restart again.

**Privacy:** verbose diagnostics can log **raw query text and pipeline detail**. Treat log files and stdout as **sensitive**; see [`docs/privacy.md`](privacy.md) and external surface scrubbing (Sentry) vs internal DB retention.

### 2.6 Before you change production environment variables

1. **Confirm** the key name in `app/` (or this runbook [§3.4](#34-environment-variables)) — typos are silent failures.
2. **Prefer** platform-injected secrets (Railway) over pasting into chat; **rotate** if a key ever appears in a log ticket.
3. **Redeploy or restart** after changes so workers pick up new values (and `bootstrap_env` / `override=False` behavior still lets platform win over `.env` on disk if both exist in dev).
4. **Document** the change in your personal ops log (date, what, why) — the **git** history does not track Railway.
5. **Test** a single `GET /health` and one `/api/chat` turn in staging or production after **risky** changes (e.g. wrong `ANTHROPIC_API_KEY`).

---

## 3. Detailed context

### 3.1 Architecture in one page

- **User-facing** chat UIs use **`POST /api/chat`** (unified router): classifier → **Tier 1** templates (deterministic) → **Tier 2** retrieve-then-generate (OpenAI/Anthropic stack per path) → **Tier 3** Haiku synthesis, plus **gap_template** and **chat** modes.
- **Community growth:** contribute flow, enrichment (URL fetch + **Google Places** for providers), operator **approval** into `providers` / `programs` / `events`. Mention scanner (Tier 3) → **`llm_mentioned_entities`** review queue.
- **Legacy `POST /chat` (Track A)** was **removed** on **2026-04-29** (H1 deletion ship, `61387e4..23a39a5`). The only live chat endpoint is **`POST /api/chat`** (unified concierge). Historical **`chat_logs`** rows may still show **`tier_used = 'track_a'`** from before that date; **no current code path emits `track_a`**.

Full routing, voice, and locked decisions: [`HAVA_CONCIERGE_HANDOFF.md`](../HAVA_CONCIERGE_HANDOFF.md) **§1b–1d**.

### 3.2 Admin UI guide

**Auth:** Password login at **`/admin/login`** sets an HTTP-only cookie; same cookie gates **`/admin/api/...` JSON** routes.

#### Dashboard and events

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/admin/`, `/admin?tab=…` | Tabs: `pending` / `live` / `programs` / `queue` — list and moderate **user-submitted events**; program list when `tab=programs` |

**`tab=queue`:** a combined “operator queue” of **user events** in `pending_review` (newest/oldest sort same as other tabs) plus **inactive programs** submitted with `source == "parent"` (parent-submitted program activation flow). Cards use the same **approve/reject/activate** patterns as `pending` events and the program list; use the card actions or links to **Edit** a program for detail changes before activation.
| POST | `/admin/event/{id}/approve` | Set event **live** |
| POST | `/admin/event/{id}/reject` | Set event **deleted** |
| POST | `/admin/event/{id}/delete` | Delete from **live** tab |
| POST | `/admin/review/{id}` | JSON body `{ "action": "approve" \| "reject" }` for **tests/API** (cookie auth) |

#### Programs (CRUD + activation)

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/admin/programs/new` | Create form |
| POST | `/admin/programs` | Create program |
| GET | `/admin/programs/{id}/edit` | Edit form |
| POST | `/admin/programs/{id}/update` | Save |
| POST | `/admin/programs/{id}/deactivate` | Soft-deactivate |
| POST | `/admin/programs/{id}/activate` | Reactivate |

#### Analytics and feedback

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/admin/analytics` | 7d top queries, zero-result heuristics, 30d daily active sessions, 30d event funnel |
| GET | `/admin/feedback` | Thumbs up/down aggregated + sample rows (Tier 3 **negative** samples listed) — `?window=7d` (default), `30d`, or `all` |

#### Phase 5 admin modules (nav in `app/admin/nav_html.py`)

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/admin/contributions` | Paginated **contributions** queue |
| GET | `/admin/contributions/{id}` | Detail + **Re-enrich** to `POST /admin/api/contributions/{id}/enrich` |
| GET/POST | `/admin/contributions/{id}/approve` | Approve flow |
| GET/POST | `/admin/contributions/{id}/reject` | Reject |
| GET/POST | `/admin/contributions/{id}/needs-info` | Needs info |
| GET | `/admin/mentioned-entities` | LLM-mention list |
| GET/POST | `…/promote`, `…/dismiss` | Promote to contribution or dismiss |
| GET | `/admin/categories` | Category frequency + pending **category hints** |

**Contributions** rows use **`status`**: `pending` (in queue), `approved`, `rejected`, `needs_info` — and link to `created_provider_id` / `created_program_id` / `created_event_id` after approval when applicable. **Mentioned entities** use **`status`**: `unreviewed` (default), `dismissed`, or `promoted`. The **promote** flow creates a **`contributions`** row and enqueues **enrichment** the same way as a public form submit.

#### Bulk / maintenance `POST` (see [§2.4](#24-running-backfills-and-bulk-admin-actions))

- `/admin/reseed`, `/admin/reembed-all`, `/admin/programs-reseed`, `/admin/retag-all`

#### Debug (non-secret)

- **`GET /admin/debug-pw`** — returns whether **`ADMIN_PASSWORD`** is visible to the process (booleans only; no secret in response).

#### JSON: `/admin/api` (cookie same as HTML)

| Method | Path | Summary |
| --- | --- | --- |
| POST | `/admin/api/contributions` | Create row + background enrichment |
| GET | `/admin/api/contributions` | List (`status`, `entity_type`, `source`, pagination) |
| GET | `/admin/api/contributions/{id}` | Get one |
| PATCH | `/admin/api/contributions/{id}/status` | Status update + notes |
| POST | `/admin/api/contributions/{id}/enrich` | 202, schedule enrichment again |
| GET | `/admin/api/mentioned-entities` | List mentions (filters) |
| GET/POST | `/admin/api/mentioned-entities/.../dismiss` and `.../promote` | Dismiss or promote to contribution |

### 3.3 `chat_logs` for operators

Columns (see handoff **§3.10**; names match `app/db/models.py` `ChatLog`):

- **`session_id`**, **`role`** (`user` / `assistant`), **`message`**, **`intent`**, **`created_at`**
- **Unified path:** `query_text_hashed`, `normalized_query`, `mode` (`ask` / `contribute` / `correct` / `chat` …), `sub_intent`, `entity_matched`, **`tier_used`**, `latency_ms`, `llm_tokens_used` (legacy total), `llm_input_tokens`, `llm_output_tokens`, **`feedback_signal`**

**`tier_used` (common values):** `1`, `2`, `3`, `gap_template`, `chat`, `placeholder`, `intake`, `correction`, `track_a`, or **NULL** on old rows. **`track_a`:** appears **only on historical rows** written **before** **`POST /chat`** was removed (**2026-04-29**, H1); **no emitter today**. **NULL `tier_used`:** small fraction of **historical** pre-sentinel rows (handoff: ~legacy reconciliation — treat as “unknown / old pipeline” in analytics, not as a bug by itself).

**`feedback_signal`:** strings **`positive`** / **`negative`** (thumbs) set via **`POST /api/chat/feedback`** for a **prior assistant turn**; see [`admin/feedback_html.py`](../app/admin/feedback_html.py) for how aggregates are computed.

**`tier_used` quick reference (not exhaustive for every edge case, but what you will see in SQL):**

| Value | Meaning (operator view) |
| --- | --- |
| `1` | Tier 1 template hit (deterministic) |
| `2` | Tier 2 retrieve-then-generate |
| `3` | Tier 3 Haiku synthesis (normal path) |
| `gap_template` | No entity match; gap acknowledgment |
| `chat` | Out-of-scope / chat-style handling (classifier) |
| `placeholder` | Contribute/correct/short-circuit rows **or** some **error** paths that return fallback **before** a Tier 3 call — **do not** treat as “all errors” by itself |
| `intake` / `correction` | Contribute or correction flow (if present in your window) |
| `track_a` | **Historical only** — rows tagged when legacy **`POST /chat`** (Track A) still existed (**before 2026-04-29**); **not written by current code** |
| `NULL` | **Legacy** pre-sentinel rows or rare gaps — do not conflate with “unified” rows |

**PII & retention:** Plaintext messages exist in your DB for operations and analytics; external logging is scrubbed per [`docs/privacy.md`](privacy.md). Do not copy production `message` into untrusted systems.

### 3.4 Environment variables

| Variable | Default / resolution | Effect if wrong | When to change |
| --- | --- | --- | --- |
| `DATABASE_URL` | If unset, local SQLite `events.db` in repo (`app/db/database.py`) | Wrong URL → wrong DB or connection failure | Railway Postgres URL; rotate on compromise |
| `ADMIN_PASSWORD` | None → admin login **fails** | No admin | Set in Railway; rotate by changing env + re-login |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Key required for Tier 2/3 LLM; model defaults in code (Haiku) | Degraded or empty responses; graceful string on some failures | Key rotation, model experiments |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Key for parsing, embeddings, tags; `OPENAI_MODEL` e.g. `gpt-4.1-mini` | Search / Tier 2 / features fail | Key rotation |
| `GOOGLE_PLACES_API_KEY` | Places **New** client | Enrichment **fails**; queue still works | Quota, billing, key restrict |
| `SENTRY_DSN` | If unset, Sentry **off** | No crash aggregation | Set in prod; alerts configured in Sentry **UI** (see checklist) |
| `SEARCH_DIAG_VERBOSE` | Off | When **on**: `search_debug.log` + `search_diag` **DEBUG** | Short incidents only; see [§2.5](#25-toggling-diagnostics) |
| `RATE_LIMIT_DISABLED` | Off | If **on**, **all** slowapi limits disabled (tests or emergency) | **Never** default in prod |
| `RAILWAY_ENVIRONMENT` | Unset locally | If set, production-flavored init (e.g. auto-seed if empty) | **Platform** — not hand-edited |

`app/bootstrap_env.py` loads **`.env`** with **`override=False`** (platform env wins over file).

### 3.5 Scripts

Run from repo root; use `.\.venv\Scripts\python.exe` on Windows. Set **`DATABASE_URL`** in env when pointing at Railway (read-only user recommended for reporting).

| Script | Purpose | Example | Notes |
| --- | --- | --- | --- |
| `scripts/analyze_chat_costs.py` | Tier/mode/cost rollups, **30d** window | `.\.venv\Scripts\python.exe scripts\analyze_chat_costs.py` | **stdout only**; no full query text in output |
| `scripts/run_query_battery.py` | Regression battery (HTTP client still POSTs to **`/chat`**) | See `scripts/README.md` | **Post-H1:** **`/chat`** returns **404** until the script is updated to **`POST /api/chat`** with the concierge payload — **do not** assume results until then; **Production traffic** / costs if fixed |
| `scripts/verify_queries.py` | Short live spot check | venv `python` | |
| `scripts/diagnose_search.py` | Batch search; may write `diagnose_output.txt` | venv | |
| `scripts/run_voice_audit.py` / `run_voice_spotcheck.py` | Voice QA | venv | Paid/structured; see `prompts/` |
| `scripts/seed_from_havasu_instructions.py` | Seeding | also invoked by `POST /admin/programs-reseed` | |
| `scripts/activate_scraped_programs.py` | One-off data ops | use rarely | can **mutate** DB |
| `scripts/build_complete_handoff.py` | Doc build | not prod ops | |
| `scripts/extract_tier3_queries.py` | Ad hoc Tier-3–style query extraction | venv | dev / tuning |
| `scripts/measure_hint_extractor_tokens.py` | Token use for session **hint** extraction | venv | dev |
| `scripts/run_manual_phase64_verify.py` | Session-memory spot verification | venv | post-change QA |
| `scripts/smoke_phase52_contributions.py` | Phase-5.2 contribute path smoke | venv | after deploy touching contribute |

**Results / baselines in `scripts/`** (e.g. `battery_results.json`, JSON audit exports) are **not** auto-applied; treat rewrites as a **deliberate** baseline move per `scripts/README.md`.

### 3.6 External dashboards

- **Railway** — deploys, logs, metrics, DB plugin, **restart** / env.
- **Sentry** — issues, **alert rules** (set per org; not in this repo) — see [`pre-launch-checklist.md`](pre-launch-checklist.md).
- **Anthropic** — API keys, rate limits, usage, Haiku model availability.
- **OpenAI** — keys, usage for **embeddings** and chat models used in extraction/classifier.
- **Google Cloud** — **Places API (New)** product enabled, **billing**, **key** restrictions, quota.
- Exact URLs depend on your accounts (do not hardcode a single org’s console path in a shared doc; start from the vendor home pages).

### 3.7 Failure modes and monitoring

- **Handoff §3.11** defines graceful copy when Tier 3 and some upstream paths fail; in-app **automated** “admin alert if error rate exceeds threshold” is **not** shipped — **manually** check **Sentry** + **SQL** in [§4](#4-useful-queries-copy-paste-sql).
- **Soft-launch baseline:** for the first **~2 weeks**, log rough **hourly/daily** fallback rate and adjust expectations; **numeric threshold = operator judgment** until you have a stable baseline, then you can set **Sentry** and/or a calendar reminder. **Tier 3 LLM failure** often logs **`tier_used = '3'`** with the fallback **exact string**; **context-build failure before the Tier 3 call** may log **`tier_used = 'placeholder'`** *with the same user-visible string* — do not use `placeholder` as the only error filter.
- **Tier 1 / 2** internal fall through does **not** log as an “error” row — no ops alert.
- **Manual severity ladder (solo soft launch, not a substitute for Sentry after you configure it):** (1) *Monitor* — a single Sentry blip, one grumpy feedback row, a quiet traffic day. (2) *Triage same day* — stack-trace in Sentry, **Railway** crash loop, or a rough **>5%** of `assistant` rows in a **one-hour** window being the **exact** fallback string without a deploy. (3) *Drop everything* — “almost all queries return fallback” (check Anthropic/DB), **no DB writes** for approval, or **suspected PII** in an **external** log; follow `docs/privacy.md` and vendor incident playbooks. After Sentry **alert rules** and synthetics are set up (checklist), treat those alerts as first signal but **still** skim *New* issues daily at low scale.

### 3.8 Session state

- In-memory **global** `sessions` dict in `app/core/session.py` (not in Postgres). **No** admin endpoint to delete one `session_id`.
- **Workarounds:** have the user open a **fresh** session (new `session_id` in client), hard-refresh / clear site data, or **restart** the web service to wipe **all** in-memory state.

### 3.9 Logging and diagnostics

- **Sentry** uses **event/breadcrumb scrubbing** (Phase 8.7) in `app/main.py` for external observability; internal **`chat_logs`** still hold text per privacy doc.
- **`scripts/analyze_chat_costs.py`** is designed to print **aggregates** without full query text.
- **`SEARCH_DIAG_VERBOSE`** — see [§2.5](#25-toggling-diagnostics); keep **off** in default prod.
- **Background maintenance:** `main.py` runs an **hourly** loop that marks **expired** `pending_review` **events** (where `admin_review_by` is in the past) as **`deleted`**. If you rely on long review windows, check that `admin_review_by` is set as you expect when events enter the queue; otherwise rows can **disappear** from “pending” on the hour boundary.

### 3.10 Known performance characteristics

At the current scale and configuration, several behaviors are **deliberate trade-offs**, not bugs. This section records what to expect and what may need work as traffic grows.

**Single uvicorn worker.** The `Procfile` runs **one** process (`uvicorn` with no `--workers` flag). **Blocking** `POST /api/chat` handlers (Tier 3 can take **1–5+** seconds) run in the thread pool; under **concurrent** load, requests **queue** behind each other. For **soft-launch** single-digit concurrency this is acceptable. **Multi-worker** deployment is **not** enabled: session state lives in a **process-local** Python dict (`app/core/session.py`), so a second worker could serve **message 2** on a different process than **message 1** and **break** session memory. A **shared** store (e.g. Redis) or **sticky** routing is a **post-launch** prerequisite for multiple workers.

**Default database connection pool.** SQLAlchemy uses the default **QueuePool** for Postgres: typically **`pool_size=5`**, **`max_overflow=10`**, up to **~15** checked-out connections, with **`pool_pre_ping=True`** in `app/db/database.py` to drop dead connections. **One** app process fits **Railway** starter Postgres **max_connections** budgets. **Sum** pool sizes if you add **replicas** or other services against the same DB.

**In-memory session dict growth.** `sessions` has **no** TTL or max size; **new** `session_id` values add entries. **Railway** deploys and **restarts** clear the dict. If a process ran for **weeks** without restart, memory would grow with **distinct** session IDs (including abandoned clients). **Mitigation today:** deploy/restart cadence. **Post-launch:** optional eviction if this becomes measurable.

**Tier 3 context builder query pattern.** `build_context_for_tier3` loads providers, then issues **programs** and **events** queries **per provider** (N+1 style, capped at **~10** providers). At current catalog size this is **fast**; at much larger scale it can dominate **Tier 3** latency. **Post-launch:** batch or measure before changing.

**LLM client timeouts (Phase 8.2).** Anthropic and OpenAI Python clients are constructed with a **45-second** read timeout (`app/core/llm_http.py`). Hung upstream calls **fail** into existing **§3.11** graceful paths instead of holding a worker for the SDK’s **default** (often much longer).

**Concurrent smoke script.** `scripts/smoke_concurrent_chat.py` runs a **local** **8-thread** × **~3 minute** smoke (mixed Tier 1/2/3-style queries) against `POST /api/chat`. Use after performance-related changes; see the script **docstring**. It is **not** a 50-user stress test.

---

## 4. Useful queries (copy-paste SQL)

**Postgres (production on Railway) assumed below.** `chat_logs` table name matches `ChatLog.__tablename__` (`chat_logs`).

**Running these:** from your laptop, use the **Railway Postgres** “Connect” string (or `psql` with `DATABASE_URL` in env). Prefer a **read-only** user or a **replica** if you add one later. For one-off analysis, you can set `DATABASE_URL` in a local shell to the production URL, run `psql` or `scripts/analyze_chat_costs.py`, then **unset** the var — do not log the URL. Never point a **write** test script at prod.

**Exact fallback string (must match `app/chat/tier3_handler.py` `FALLBACK_MESSAGE` — if code changes, update this section):**

```text
Something went sideways on my end — try that again in a sec, or call the business directly if you're in a hurry.
```

In PostgreSQL, the examples use **dollar-quoting** `$msg$...$msg$` so you do not have to escape apostrophes in `you're`.

**SQLite (local `events.db`):** use `date(created_at)` and `datetime('now', '-1 hour')` where noted; `CURRENT_TIMESTAMP` is acceptable for simple tests. Types may be stored as strings — cast if needed.

---

### 4.1 Today’s chat volume (UTC day), by `tier_used` — Postgres

Counts **all** rows in `chat_logs` in the current **UTC** calendar day.

```sql
SELECT
  COALESCE(tier_used, '(null)') AS tier_used,
  COUNT(*)                    AS n
FROM chat_logs
WHERE created_at >= date_trunc('day', (now() AT TIME ZONE 'UTC'))
  AND created_at <  date_trunc('day', (now() AT TIME ZONE 'UTC')) + interval '1 day'
GROUP BY ROLLUP (tier_used)
ORDER BY tier_used NULLS FIRST;
```

The `ROLLUP` adds a **grand total** row (the row where `tier_used` is NULL in the grouping output). For only per-tier counts, use `GROUP BY tier_used` instead.

**SQLite (local) sketch:**

```sql
SELECT
  IFNULL(tier_used, '(null)') AS tier_used,
  COUNT(*)                   AS n
FROM chat_logs
WHERE date(created_at) = date('now')
GROUP BY tier_used;
```

---

### 4.2 Tier 3 fallback rate, **last hour** — Postgres

**Numerator:** assistant rows whose `message` equals the canonical fallback. **Denominator:** all assistant rows in the window. Adjust the interval for other windows.

```sql
WITH w AS (
  SELECT *
  FROM chat_logs
  WHERE role = 'assistant'
    AND created_at >= (now() AT TIME ZONE 'UTC') - interval '1 hour'
)
SELECT
  COUNT(*) FILTER (WHERE message = $msg$Something went sideways on my end — try that again in a sec, or call the business directly if you're in a hurry.$msg$) AS fallback_rows,
  COUNT(*) AS assistant_rows,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE message = $msg$Something went sideways on my end — try that again in a sec, or call the business directly if you're in a hurry.$msg$) / NULLIF(COUNT(*), 0),
    2
  ) AS fallback_pct
FROM w;
```

**If you see drift** (e.g. invisible Unicode differences), a looser check is:

```sql
-- Fallback only: use if exact match undercounts
SELECT COUNT(*) FROM chat_logs
WHERE role = 'assistant'
  AND created_at >= (now() AT TIME ZONE 'UTC') - interval '1 hour'
  AND message ILIKE 'Something went sideways on my end%in a hurry.%';
```

**What to look for:** sustained **higher** `fallback_pct` than your baseline, or an absolute **spike** in `fallback_rows` after a deploy or upstream outage.

---

### 4.3 Tier 3 fallback rate, **last 24 hours** — Postgres

```sql
WITH w AS (
  SELECT *
  FROM chat_logs
  WHERE role = 'assistant'
    AND created_at >= (now() AT TIME ZONE 'UTC') - interval '24 hours'
)
SELECT
  COUNT(*) FILTER (WHERE message = $msg$Something went sideways on my end — try that again in a sec, or call the business directly if you're in a hurry.$msg$) AS fallback_rows,
  COUNT(*) AS assistant_rows,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE message = $msg$Something went sideways on my end — try that again in a sec, or call the business directly if you're in a hurry.$msg$) / NULLIF(COUNT(*), 0),
    2
  ) AS fallback_pct
FROM w;
```

---

### 4.4 Pending contributions count

```sql
SELECT COUNT(*) AS pending_contributions
FROM contributions
WHERE status = 'pending';
```

---

### 4.5 Pending contributions, oldest first

```sql
SELECT id, submission_name, submitter_email, submitted_at, status, source
FROM contributions
WHERE status = 'pending'
ORDER BY submitted_at ASC
LIMIT 200;
```

---

### 4.6 Mentioned-entities queue depth (by `status`)

```sql
SELECT status, COUNT(*) AS n
FROM llm_mentioned_entities
GROUP BY status
ORDER BY n DESC;
```

---

### 4.7 Tier distribution, last 24 hours — assistant rows — Postgres

```sql
SELECT
  COALESCE(tier_used, '(null)') AS tier_used,
  COUNT(*)                      AS n
FROM chat_logs
WHERE role = 'assistant'
  AND created_at >= (now() AT TIME ZONE 'UTC') - interval '24 hours'
GROUP BY tier_used
ORDER BY n DESC;
```

---

### 4.8 Token cost — sum `llm_tokens_used` by `tier_used` and **day** (last 7 days) — Postgres

`llm_tokens_used` is a **single aggregate** on older rows; per-tier **input/output** split is more accurate when `llm_input_tokens` / `llm_output_tokens` are set (see `scripts/analyze_chat_costs.py` for cost math). This query gives a **rough** 7d trend.

```sql
SELECT
  (created_at AT TIME ZONE 'UTC')::date AS day_utc,
  COALESCE(tier_used, '(null)') AS tier_used,
  SUM(COALESCE(llm_tokens_used, 0)) AS total_llm_tokens
FROM chat_logs
WHERE created_at >= (now() AT TIME ZONE 'UTC') - interval '7 days'
  AND llm_tokens_used IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2;
```

**If** your column is `timestamp without time zone` and you store UTC, use `created_at::date` (or `date(created_at)`) for `day_utc` instead of the `AT TIME ZONE` expression.

**What to look for:** a tier’s **sudden jump** in `total_llm_tokens` vs prior weeks.

---

### 4.9 Track A vs unified (last 7 days) — Postgres

**Unified** approximated as **“not `track_a`”**; refine with `query_text_hashed` / `mode` if you need stricter definition.

```sql
SELECT
  CASE WHEN tier_used = 'track_a' THEN 'track_a' ELSE 'unified_or_other' END AS bucket,
  COUNT(*) AS n
FROM chat_logs
WHERE created_at >= (now() AT TIME ZONE 'UTC') - interval '7 days'
GROUP BY 1
ORDER BY n DESC;
```

---

### 4.10 Thumbs-down (negative feedback) on assistant rows, last 7 days

Schema uses the string **`negative`**, not numeric comparisons.

```sql
SELECT
  id,
  created_at,
  tier_used,
  LEFT(message, 200) AS message_preview
FROM chat_logs
WHERE role = 'assistant'
  AND feedback_signal = 'negative'
  AND created_at >= (now() AT TIME ZONE 'UTC') - interval '7 days'
ORDER BY created_at DESC
LIMIT 100;
```

**Privacy:** this returns **message** fragments — use read-only DB roles and do not re-post publicly.

---

### 4.11 `mode` distribution, last 24 hours (unified path) — Postgres

`mode` is set on **unified** `chat_logs` rows (see handoff **§3.10**). Handoff / code use values like `ask`, `contribute`, `correct`, `chat`.

```sql
SELECT
  COALESCE(mode, '(null)') AS mode,
  COUNT(*) AS n
FROM chat_logs
WHERE created_at >= (now() AT TIME ZONE 'UTC') - interval '24 hours'
GROUP BY mode
ORDER BY n DESC;
```

**What to look for:** sudden jumps in `contribute` or `chat` that might indicate **abuse** or a **bug** in intent routing; compare to **§4.7** tier mix.

---

### 4.12 Ask-mode volume only, last 24 hours — Postgres

Useful when you want “concierge Q&A” traffic without contribute/correct noise.

```sql
SELECT
  COALESCE(tier_used, '(null)') AS tier_used,
  COUNT(*) AS n
FROM chat_logs
WHERE role = 'assistant'
  AND mode = 'ask'
  AND created_at >= (now() AT TIME ZONE 'UTC') - interval '24 hours'
GROUP BY tier_used
ORDER BY n DESC;
```

If `mode` is often NULL in your window (older clients), this query will undercount — fall back to **§4.7** without the `mode` filter.

---

### 4.13 Median / p95 `latency_ms` by `tier_used`, last 7 days — Postgres

Requires **non-NULL** `latency_ms` on rows (unified path). Uses `percentile_cont` (Postgres **aggregate** in recent versions; if your PG is older, use a subquery or `pg_stats` + rough eyeballing instead).

```sql
SELECT
  COALESCE(tier_used, '(null)') AS tier_used,
  COUNT(*) AS n,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms
FROM chat_logs
WHERE created_at >= (now() AT TIME ZONE 'UTC') - interval '7 days'
  AND latency_ms IS NOT NULL
GROUP BY tier_used
ORDER BY n DESC;
```

**What to look for:** a tier’s **p95** doubling after a **deploy** (regression) or during an **upstream** slowdown.

---

### 4.14 DRY variant — define fallback text once in a CTE (Postgres)

If you prefer not to paste the long string three times in ad hoc analysis:

```sql
WITH fb AS (
  SELECT $msg$Something went sideways on my end — try that again in a sec, or call the business directly if you're in a hurry.$msg$ AS text
)
SELECT
  COUNT(*) FILTER (WHERE c.message = fb.text) AS fallback_rows,
  COUNT(*) AS assistant_rows
FROM chat_logs c
CROSS JOIN fb
WHERE c.role = 'assistant'
  AND c.created_at >= (now() AT TIME ZONE 'UTC') - interval '1 hour';
```

You can change the `interval` and add `c.tier_used` filters as needed.

---

### 4.15 User messages (turns) in the last 24 hours — Postgres

**Rough “how many user questions”** in a day (one row per user message, not de-duplicated by `session_id`).

```sql
SELECT COUNT(*) AS user_messages_24h
FROM chat_logs
WHERE role = 'user'
  AND created_at >= (now() AT TIME ZONE 'UTC') - interval '24 hours';
```

For **unique sessions** in 24h:

```sql
SELECT COUNT(DISTINCT session_id) AS active_sessions_24h
FROM chat_logs
WHERE created_at >= (now() AT TIME ZONE 'UTC') - interval '24 hours';
```

---

## 5. Companion docs and contacts

### 5.1 Companion docs

- **[`HAVA_CONCIERGE_HANDOFF.md`](../HAVA_CONCIERGE_HANDOFF.md)** — **Architecture spec** (tiers, voice, locked decisions, data model). Reach for this when changing behavior, onboarding an engineer, or reconciling “why is it built this way?”
- **[`docs/privacy.md`](privacy.md)** — **Data handling, retention, external scrubbing** — when touching logs, diagnostics, or user data questions
- **[`docs/pre-launch-checklist.md`](pre-launch-checklist.md)** — **Launch-gate and pre-public tasks** (Sentry alert rules, inbox, retention review, etc.)

### 5.2 Who to call

- **Owner (primary):** Casey — primary on-call for the product during soft launch; **no** dedicated Havasu Chat support inbox is guaranteed yet (see **Replace privacy page contact email** in the checklist). **Contact paths:** the in-app feedback flows and personal/owner email as you’ve published on the **privacy** page and site.
- **Vendors (support / status):** **Railway** (hosting, Postgres, deploys, HTTP logs), **Sentry** (crashes, performance, *after* you add alert rules per checklist), **Anthropic** (Tier 2/3 LLM and rate limits), **OpenAI** (classifier, embeddings, tags, tools), **Google Cloud** (Places API billing, **Maps Platform** / API enablement, key restrictions). For each, keep **one** saved URL to your org’s **support** or **status** page; update when vendors change console navigation.
- **Escalation:** For now, **escalation = owner** — there is no separate 24/7 operations team. Post-launch, if you add a second operator, add their contact and rotation here.

**Emergency triage order (short):** (1) `GET /health` + Railway, (2) Sentry for new fatals, (3) `docs/pre-launch-checklist.md` for any **open** item that blocks safe operation (e.g. Sentry not configured at all on first public day), (4) owner. **Do not** post database extracts or Sentry event bodies in a public channel without checking `docs/privacy.md` first.

---

*Phase 8.4 — `docs/runbook.md`. Eight capability gaps from the read-first pass are addressed as **documentation and process** in this file and the checklist, not as new app code in 8.4.*
