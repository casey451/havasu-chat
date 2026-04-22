# Phase 8.4 — Admin runbook (read-first report)

**Date:** 2026-04-22  
**HEAD:** `4509d7b` (Phase 8.7)  
**Scope:** Inventory and proposed outline only — no `docs/runbook.md` drafted, no code changes, no commit.

**Structural decision (owner):** Single file `docs/runbook.md` (Option A) — quick reference at top, operational context below, TOC for navigation. Agreed: appropriate at current scale; split only if the doc grows past easy navigation (~200+ lines of *effective* content is still fine with a TOC; revisit if it balloons past ~1500 lines or audience splits).

---

## 1. Operational surfaces inventory

### 1.1 Admin routes — HTML (`app/admin/`, prefix `/admin`)

| URL pattern | Method | Purpose | Who / when |
| --- | --- | --- | --- |
| `/admin/login` | GET | Admin password login form. | Operator first visit or after cookie expiry. |
| `/admin/login` | POST | Submits password; sets HTTP-only session cookie. | Same. |
| `/admin`, `/admin/` | GET | Main dashboard: tabs `pending` / `live` / `programs` / `queue` (query `tab`, `sort`). Pending & live event lists; programs tab; queue tab (pending user events + inactive parent-sourced programs). | Daily moderation. |
| `/admin/analytics` | GET | Usage analytics: top user queries (7d), zero-result heuristic pairs (7d), daily active sessions (30d), event funnel (30d). | Spot-check traffic and pain points. |
| `/admin/feedback` | GET | Thumbs feedback aggregates (time windows). | Quality monitoring. |
| `/admin/categories` | GET | Category frequency tables (active providers, active programs) + pending contribution category hints. | Taxonomy / intake planning. |
| `/admin/contributions` | GET | Paginated list of `contributions` with filters. | Contribution queue. |
| `/admin/contributions/{id}` | GET | Contribution detail: submission, URL fetch block, Google Places enrichment, actions. | Review one submission. |
| `/admin/contributions/{id}/approve` | GET, POST | Approve flow (GET shows form, POST runs approval). | Publishing to catalog. |
| `/admin/contributions/{id}/reject` | GET, POST | Reject flow. | Spam / bad data. |
| `/admin/contributions/{id}/needs-info` | GET, POST | Request more info. | Stuck items. |
| `/admin/mentioned-entities` | GET | List LLM-mention rows (Tier 3 title-case candidates). | 5.5 review. |
| `/admin/mentioned-entities/{id}` | GET | Mention detail. | |
| `/admin/mentioned-entities/{id}/promote` | GET, POST | Promote to a new `contributions` row. | |
| `/admin/mentioned-entities/{id}/dismiss` | GET, POST | Dismiss mention. | |
| `/admin/programs/new` | GET | Create program form. | Catalog edit. |
| `/admin/programs` | POST | Create program. | |
| `/admin/programs/{id}/edit` | GET | Edit program form. | |
| `/admin/programs/{id}/update` | POST | Save program. | |
| `/admin/programs/{id}/deactivate` | POST | Soft-deactivate program. | |
| `/admin/programs/{id}/activate` | POST | Reactivate. | |
| `/admin/event/{id}/approve` | POST | Set user-submitted `events` row to `live` (from dashboard cards). | Event moderation. |
| `/admin/event/{id}/reject` | POST | Set to `deleted`. | |
| `/admin/event/{id}/delete` | POST | Delete from live tab. | |
| `/admin/review/{event_id}` | POST | **JSON** approve/reject (`AdminReviewBody`) for tests/integrations. | API-style moderation (cookie auth). |
| `/admin/reseed` | POST | Deletes seed-origin events and re-runs seed (embeddings). | **Destructive** — rare ops. |
| `/admin/reembed-all` | POST | Regenerate embeddings for **all** events (OpenAI). | Cost + time; ops only. |
| `/admin/programs-reseed` | POST | Import from `docs/HAVASU_CHAT_SEED_INSTRUCTIONS.md` (`?dry_run=true` supported). | Seeding / refresh from instructions file. |
| `/admin/retag-all` | POST | Regenerate tags for all events (OpenAI). | |
| `/admin/debug-pw` | GET | **Non-secret** debug: whether `ADMIN_PASSWORD` is visible to the process. | Railway env sanity (temporary endpoint per code comment). |

**Nav consistency:** Phase 5 HTML pages (`contributions`, `mentioned-entities`, `categories`, `analytics`, `feedback`) use `app/admin/nav_html.py` — six links including Admin home, Contributions, Mentioned entities, Categories, Analytics, Feedback. The legacy event/program dashboard uses its own inline nav (does not list every Phase 5 page on all tabs — known pattern; 8.0.6 improved cross-links; runbook should not promise identical nav on every screen).

**Authentication:** All guarded routes use shared admin cookie (`app/admin/auth.py`); JSON APIs under `/admin/api` use the same cookie and return 401 without it.

### 1.2 Admin routes — JSON API (`/admin/api`, `app/api/routes/admin_contributions.py`, `admin_mentions.py`)

| URL pattern | Method | Purpose | Who / when |
| --- | --- | --- | --- |
| `/admin/api/contributions` | POST | Create contribution (admin — triggers enrichment `BackgroundTask`). | Operator/API backfill. |
| `/admin/api/contributions` | GET | List with `status`, `entity_type`, `source`, `limit`, `offset`. | Integration / scripting. |
| `/admin/api/contributions/{id}` | GET | Single row. | |
| `/admin/api/contributions/{id}/status` | PATCH | Update status + notes. | |
| `/admin/api/contributions/{id}/enrich` | POST | 202 + schedule re-enrichment (URL fetch + Places for providers). | When enrichment failed or data stale. **Also** linked from HTML contribution detail as a form post. |
| `/admin/api/mentioned-entities` | GET | List with filters + date bounds. | |
| `/admin/api/mentioned-entities/{id}` | GET | Single mention. | |
| `/admin/api/mentioned-entities/{id}/dismiss` | POST | Dismiss. | |
| `/admin/api/mentioned-entities/{id}/promote` | POST | Promote to contribution (+ enrichment). | |

### 1.3 Non-admin operational routes (context for “app down”)

| Route | Notes |
| --- | --- |
| `GET /health` | Liveness for Railway / probes. |
| `GET /` | Main chat UI (`app/static/index.html` — uses **`POST /api/chat`**, not legacy `/chat`). |
| `GET /privacy` | Privacy static page (Phase 8.7). |
| `POST /api/chat` | Unified concierge (120/min rate limit, `slowapi`). |
| `POST /chat` | **Legacy Track A** still in codebase; `chat_logs` uses `tier_used='track_a'` for these rows. Battery script uses production `POST /chat` per `scripts/README.md`. |

### 1.4 Scripts (`scripts/`) — operator-relevant

| Script | Role | Example invocation | Output |
| --- | --- | --- | --- |
| `analyze_chat_costs.py` | Read-only `chat_logs` cost/tier/mode stats (30d window; uses `DATABASE_URL` / local DB). | `.\.venv\Scripts\python.exe scripts\analyze_chat_costs.py` | **stdout** (no query text) |
| `run_query_battery.py` | 120-query regression against **live** `POST /chat` (per README). | (see script / README; needs network) | **stdout** JSON |
| `verify_queries.py` | Short live spot-check. | venv `python` | stdout |
| `diagnose_search.py` | Batch search against live app; may write `diagnose_output.txt` in `scripts/`. | venv `python` | file + stdout |
| `run_voice_audit.py` | Voice audit batch (paid / structured). | venv `python` | JSON / reports per repo |
| `run_voice_spotcheck.py` | Smaller voice checks. | venv `python` | stdout |
| `extract_tier3_queries.py` | Ad hoc extraction of Tier 3–style queries. | venv `python` | stdout / files |
| `measure_hint_extractor_tokens.py` | Token measurement for hint extractor. | venv `python` | stdout |
| `run_manual_phase64_verify.py` | Session-memory manual verification helper. | venv `python` | stdout |
| `activate_scraped_programs.py` | One-off program activation utility (legacy / data ops). | venv `python` | DB |
| `smoke_phase52_contributions.py` | Phase 5.2 smoke path. | venv `python` | stdout |
| `seed_from_havasu_instructions.py` | Imported by **`POST /admin/programs-reseed`**, not only CLI. | via admin or direct | DB + stats |
| `build_complete_handoff.py` | Doc assembly helper — dev / doc maintainers, not production ops. | venv `python` | docs output |

**CI / test-only** scripts: none under `scripts/` are strictly “CI” only, but `battery_results.json` and friends are **baseline artifacts** — treat `run_query_battery` + baseline updates as a deliberate release process, not a daily runbook item.

**`app/db/`:** No separate “backfill” package surfaced beyond Alembic migrations; operational backfills are **admin HTTP actions** (reembed, retag, programs-reseed) or **SQL** (not wrapped in a first-class app UI).

### 1.5 Environment variables (runtime / ops)

| Variable | Default / resolution | What non-default does | When to touch |
| --- | --- | --- | --- |
| `DATABASE_URL` | Unset → local `events.db` SQLite path in `app/db/database.py` | **Required shape on Railway:** Postgres URL. Wrong URL → app fails or wrong DB. | Every deploy; restore drills. |
| `ADMIN_PASSWORD` | None → login fails (must be set in prod) | Bcrypt-checked admin auth | **Secret rotation**; never commit. `main.py` logs `bool(ADMIN_PASSWORD)` on startup (not the value). |
| `ANTHROPIC_API_KEY` | Empty → Tier 2/3 Anthropic calls fail (graceful Tier 3 user copy when applicable). | Required for full Tier 2/3. | Key rotation, outage response. |
| `ANTHROPIC_MODEL` | Default in code if unset (see `tier2_parser.py` / `tier3_handler` — e.g. Haiku per handoff) | Change model = cost/quality tradeoff. | Deliberate experiments only. |
| `OPENAI_API_KEY` | Used by extraction, embeddings, tags, intent tooling | Missing → features fail (search, Tier 2 parser path, etc.) | Key rotation. |
| `OPENAI_MODEL` | Defaults to `gpt-4.1-mini` in `extraction.py` / `hint_extractor.py` | Change model for classifier/parser | Rare. |
| `GOOGLE_PLACES_API_KEY` | `places_client` | Missing → Places enrichment **fails** for provider contributions; non-blocking for queue. | Places quota, billing, key restrict. |
| `SENTRY_DSN` | Unset → Sentry off | **Enables** Sentry; `main.py` uses `scrub_sentry_event` / `scrub_sentry_breadcrumb` (Phase 8.7). | Prod monitoring. |
| `SEARCH_DIAG_VERBOSE` | Falsy (see `is_search_diag_verbose()`) | When `true`/`1`/`yes`: `search_debug.log` file + `[search_diag]` logger at DEBUG (repo root path in `app/core/search_log.py`). | **Short** production investigations only; 8.7 default is off. |
| `RATE_LIMIT_DISABLED` | Falsy | When truthy: **disables** global `slowapi` limiter entirely (`app/core/rate_limit.py`). | **Tests** (conftest) or emergency; never default in prod. |
| `RAILWAY_ENVIRONMENT` | Unset locally | If set, triggers Railway-only behaviors (`main.py`: auto-seed empty DB, Sentry env = production, etc.) | N/A to change manually in prod — platform sets. |

**`.env` loading:** `app/bootstrap_env.py` loads with **`override=False`** so platform env wins.

### 1.6 External dashboards & consoles

| Service | What to check | URL / access |
| --- | --- | --- |
| **Railway** | Deploy status, restarts, **logs** (HTTP 429, 5xx, boot errors), `DATABASE_URL` / env, resource usage, **connectivity to Postgres** | `https://railway.app` (project dashboard) |
| **Sentry** | Exception volume, regressed issues, PII scrubbing still appropriate | `https://sentry.io` (org/project from DSN) — exact path depends on org |
| **Anthropic** | API errors, **rate limits**, usage/cost, key health | `https://console.anthropic.com` |
| **OpenAI** | Embeddings + chat model usage, rate limits, billing for keys used by extraction/classifier | `https://platform.openai.com` |
| **Google Cloud (Places API)** | **Places API (New)** billing, quota, which key, IP/referrer restrictions for production | Google Cloud Console → APIs & Services |
| **DNS / registrar** (if custom domain) | TLS, routing to Railway | Not hardcoded in repo; owner-specific |

---

## 2. Failure mode detection

Handoff **§3.11** and **Phase 8.3** tests define graceful behavior. Below: how an operator *detects* each class in production.

### 2.1 Tier 2 / Tier 1 “fail” (fall-through)

- **User-visible:** Normal answer from a deeper tier; no error copy.
- **Detection:** **Not** an operations alert. Optional: `tier_used` in `chat_logs` shows `2`→`3` only if you compare consecutive turns; not logged as a failure.
- **First step:** N/A for ops; product tuning only.

### 2.2 Tier 3 and upstream failures (graceful user copy)

**Canonical user string** (handoff + tests): the full `FALLBACK_MESSAGE` in `app/chat/tier3_handler.py` (re-exported as `_GRACEFUL` in `unified_router`).

**`chat_logs` behavior (tests: `test_phase2_integration.py`):**
- **Anthropic transport / Tier 3 handler failure (after context build):** `tier_used == '3'`, `message` equals `FALLBACK_MESSAGE`, `llm_tokens_used` may be `None` on failure path.
- **Context build or other pre-classifier failure (some paths):** `tier_used == 'placeholder'`, same user-facing `FALLBACK_MESSAGE` (non-Tier-3 `placeholder` rows *also* exist for contribute/correct flows with **different** user copy — do **not** use `placeholder` alone as a failure filter).

**Recommended SQL patterns (Postgres; adjust for SQLite in dev):**

1. **All assistant rows that are the true graceful string** (broadest “something broke” for user- visible fallback copy):
   - `role = 'assistant' AND message = '<exact FALLBACK_MESSAGE>'`  
   - Use a **param** or paste exact string from source to avoid quote drift.

2. **Narrow: Tier 3 LLM path failures only** (handoff “Tier 3 fails” + integration test for Anthropic):
   - Same as (1) plus `tier_used = '3'`.

3. **Rate of failure:**  
   - `COUNT(*) / NULLIF(COUNT assistant rows in window), 0)` for (1) or (2) vs total assistant `ask` traffic — join or filter on `mode = 'ask'` (unified) when available.

**Reasonable threshold:** **Not in codebase** — owner baseline. Suggested runbook phrasing: track **rolling daily or hourly rate**; alert on **sustained** spike over baseline (e.g. 5–10× moving average) or absolute floor (e.g. >1% of ask-mode assistant replies) — **owner to set** after soft launch. No automated “admin alert” is shipped (§3.11 “alert admin if error rate exceeds threshold” remains **procedural** via Sentry + SQL until a future sub-phase).

**Sentry:** Uncaught exceptions in request path may create issues; many Tier 3 failures are **caught** and return 200 with fallback — **Sentry may not** fire. Do not rely on Sentry alone for fallback-string rate.

### 2.3 `placeholder` rows with *successful* user copy

- Contribute/correct `placeholder` paths are **not** errors. Filter by `message` text, not `tier_used` alone.

### 2.4 Specific tier cost / token “spike”

- **Source:** `chat_logs.llm_input_tokens` / `llm_output_tokens` (split) + legacy `llm_tokens_used` aggregate.
- **Detection:** `scripts/analyze_chat_costs.py` (30d) or ad hoc SQL: `sum`/`avg` by `tier_used` and time bucket.
- **First step:** Distinguish traffic surge vs. bug (e.g. runaway context) via **top `normalized_query`** and time alignment with deploys (Railway release history).

### 2.5 DB connection / slowness

- **App:** `pool_pre_ping` on non-SQLite engines (`app/db/database.py`) — recycles dead connections; users may see 500/timeout on pool exhaustion.
- **Signals:** Railway app logs, Postgres metrics (if enabled), Sentry (if exception surfaces).
- **First step:** Railway restart; check `DATABASE_URL` and Railway Postgres plan limits.

### 2.6 Background enrichment (`contributions`)

- **Where:** `contributions.url_fetch_status`, `url_fetched_at`, `url_title` / `url_description`, `google_place_id`, `google_enriched_data` (see `app/db/models.py`); **displayed** on **HTML** detail (`_url_fetch_display` and similar in `contributions_html.py`).
- **“Failure”** is **non-blocking** for queue — operator sees “failed” / empty enrichment on the row, not a separate alert.
- **Retry:** `POST` `/admin/api/contributions/{id}/enrich` (or form on detail page).

### 2.7 Rate limit — `/api/chat` (120/min per IP)

- **User:** HTTP **429** with `RATE_LIMIT_MESSAGE` = `"Slow down a sec! Try again in a minute 😅"` (`app/core/rate_limit.py`).
- **Operator visibility:** **Not** stored in `chat_logs` for failed pre-chat requests. Check **Railway HTTP logs** or Sentry (if 429 is instrumented — may be sparse).
- **Override:** `RATE_LIMIT_DISABLED` **not** recommended in prod; use only in controlled incident response.

### 2.8 Rate limit — `/contribute` (1/hour per IP hash, DB)

- **User:** Friendly HTML message (rate message constant in `contribute.py` — not the chat limiter).
- **Logs:** Not the same as `slowapi`. **Detection:** support reports, reproduce from IP, optional SQL on `contributions` by `submitter_ip_hash` and `submitted_at` if abusing.

### 2.9 Session state “weirdness” (`app/core/session.py` global `sessions` dict)

- **Inspect:** **No** admin API to list or clear a single `session_id`. Code supports **`clear_session_state`**, `get_session`, and **user-phrase hard reset** in legacy Track A (`app/chat/router.py` — e.g. hard/soft reset flows).
- **Unified `/api/chat`:** In-memory state still applies to the **same** `session_id` the frontend sends — stuck state **may** be cleared by **new session_id** in the client or **app redeploy** (in-memory store lost).
- **Finding for runbook:** **“Reset one stuck session”** in production = **use a new session (browser tab / clear site data)** or **wait for natural expiry** of blocking flows, or **restart the Railway service** to wipe all in-memory sessions. **Not** a DB table.

### 2.10 Hourly `pending_review` event cleanup

- `run_expired_review_cleanup` in `main.py` lifespan: marks `pending_review` with past `admin_review_by` as `deleted`.
- **If broken:** Stale “pending” rows accumulate — detect via **admin** live/pending views or `events` SQL.

---

## 3. Routine operational tasks

| Task | How today |
| --- | --- |
| **Daily “health”** | `GET /health`; Railway “running”; spot-check `GET /`; Sentry 0 new critical (if Sentry on). |
| **Traffic / quality** | `/admin/analytics` (7d/30d); `scripts/analyze_chat_costs.py` for **tier and cost** (30d, local DB with prod URL). |
| **User feedback** | `/admin/feedback`. |
| **Contribution & mention queues** | `/admin/contributions`, `/admin/mentioned-entities` (+ JSON APIs for bulk). |
| **Category discovery** | `/admin/categories`. |
| **Events / programs** | `/admin?tab=…` (pending/live/queue) + program CRUD under `/admin/programs/…`. |
| **Search diagnostics** | Set `SEARCH_DIAG_VERBOSE` temporarily; inspect `search_debug.log` + stdout; **turn off** after. |
| **Re-embed / re-tag / seed from MD** | Authenticated `POST` to `/admin/reembed-all`, `/admin/retag-all`, `/admin/programs-reseed` (and destructive `/admin/reseed` only with understanding). |
| **Pending contributions count** | **UI list** + `COUNT` SQL on `contributions` where `status='pending'`; **no** dedicated threshold alert in app. |
| **“Today’s chat volume”** | **SQL** on `chat_logs` (no dedicated admin view): `date_trunc` / `cast` on `created_at` by `role` or by counting user rows. |
| **Tier distribution / `track_a` vs unified** | **SQL** or `analyze_chat_costs.py` output — `track_a` = legacy `POST /chat` only; unified rows have `query_text_hashed` / `mode` / `sub_intent` populated per handoff **§3.10**. |
| **Redeploy** | Railway: deploy from `main` (auto), or **“Restart”** in dashboard — clears **in-memory** session store. |
| **DB inspection** | Direct DB client to Railway Postgres (credentials from Railway) — **no** in-app query console. |

---

## 4. Proposed `docs/runbook.md` outline (8.4-implement)

**Expected size:** **Medium** (~500–1200 lines) if we use **links** to `HAVASU_CHAT_CONCIERGE_HANDOFF.md` for architecture deep dives, `docs/privacy.md` for retention, and keep SQL/appendix blocks tight. **>1500 lines** only if we inline full handoff subsections (should **not** — flag as scope creep).

### 4.1 Document header & TOC (1–2 screens)

- Title, audience (11pm you vs new hire), last-updated, **link to handoff** as canonical architecture.

### 4.2 Quick reference — emergency (1–2 pages, scannable bullets)

- **App down** — `GET /health`, Railway status, `GET /`, Sentry, recent deploy, Postgres up.
- **Response quality off** — recent deploy? `SEARCH_DIAG_VERBOSE` short probe? Sentry, `/admin/analytics` top queries, `analyze_chat_costs` tier mix.
- **“Error” rate (graceful copy)** — SQL for `FALLBACK_MESSAGE` + optional `tier_used='3'`; spike vs baseline; **no magic threshold** (owner).
- **DB issues** — connection errors in logs, pool, restart, `DATABASE_URL`.
- **Contribution queue piling up** — `/admin/contributions`, `COUNT` pending, enrichment column interpretation.
- **Users blocked (429)** — distinguish `/api/chat` vs `/contribute`; check abuse vs misconfigured shared IP; **no** in-app per-IP log tail — Railway logs.
- **Where to look first** table (Railway / Sentry / admin page / script).

*Length:* ~1–1.5 pages. *Source:* this report + `tier3_handler` + handoff **§3.10–3.11**.

### 4.3 Routine operations (2–4 pages)

- **Daily** — same as §3 table; 5–10 min checklist.
- **Weekly** — Sentry triage, cost script, contribution SLA (informal), mention queue depth.
- **Backfills** — `POST` admin backfill matrix with **“destructive / $$ / one-off”** callouts; **no** new prose for what code already says — link to endpoint list from **§1.1** (this report).
- **Diagnostics toggle** — `SEARCH_DIAG_VERBOSE` + log path; redaction / privacy cross-ref **§1.1 `docs/privacy.md`**.

*Source:* admin router docstrings, `search_log.py`, 8.7 privacy doc.

### 4.4 Detailed context (bulk of file; rest split by H2s)

- **4.4.1 Architecture in one page** — Four-tier + contribute path; **link to handoff §1b–1d** (do not copy).
- **4.4.2 Admin UI guide** — **One subsection per** primary area: dashboard tabs, events/programs, analytics, feedback, contributions (HTML + re-enrich), mentioned entities, categories; **include JSON** endpoints in a compact table.
- **4.4.3 `chat_logs` for operators** — Columns per **§3.10**; **`track_a`** meaning; `tier_used` values; **feedback** via `/api/chat/feedback` and `feedback_signal`.
- **4.4.4 Environment** — table from **§1.5** (this report).
- **4.4.5 Scripts** — table from **§1.4** with **“when to run / never in prod”** for destructive scripts.
- **4.4.6 External services** — **§1.6** with no fabricated URLs; note Places SKU handoff has cost notes.
- **4.4.7 Failure modes** — synthesis of **§2**; explicit **“manual alert”** = SQL + Sentry + **Calendar owner review** until automated.
- **4.4.8 Session model** — in-memory; **new session_id** vs restart; link `session.py` behavior in prose.
- **4.4.9 Logging** — Sentry scrub (8.7), search diag gate, no query text in `analyze_chat_costs` (already).

*Length:* majority of file; *Source:* code + handoff + 8.7 + this inventory.

### 4.5 `docs/pre-launch-checklist.md`

- **Link only** in runbook: “Launch gate tasks live in …” + one line on relationship (runbook = day-2-day; checklist = gate). **No** copy of open items in runbook (duplication risk) — or one-line stub.

### 4.6 Who to call (≤ half page pre-launch)

- **Owner** primary contact; **Vendors** as links (support portals); **“Post-launch”** placeholder for dedicated inbox when exists.

**Structural note:** The sketch in the **prompt** maps cleanly. Optional **appendix** if SQL snippets push past ~60 lines: “Appendix A: Example SQL (Postgres)”. If we add *second* app (not planned), *then* split by audience; **not** a STOP for read-first.

---

## 5. Capability gaps (classification)

| Gap | Class |
| --- | --- |
| **Automated “admin alert” when `FALLBACK_MESSAGE` rate exceeds X** (handoff **§3.11**) | **Document** manual SQL + Sentry review; **build** = future sub-phase (Sentry metric alert or internal cron) if owner wants automation. |
| **Single-session reset without restart** (in-memory `sessions`) | **Document** new `session_id` + redeploy for global wipe; **not needed** as product feature for launch. |
| **In-app `chat_logs` query UI** | **Document** SQL + `analyze_chat_costs.py`; **build** optional (post-launch) if pain is high. |
| **Sentry alert rules for fallback rate** | **Document** that rules may be unconfigured; **build** = owner sets in Sentry UI (not code) or defers. |
| **Queue depth notification (contributions / mentions)** | **Document** periodic check; **build** deferred. |
| **Per-IP rate limit audit trail** | **Document** Railway access logs; **build** optional. |
| **Postgres read replica / manual reporting DB** | **N/A** at current scale; **not needed** in runbook beyond “use read-only user if you add one”. |
| **Explicit diff between “Tier 3 LLM error” and “context build error” in logs** (both can show same user string) | **Document** `tier_used` = `3` vs `placeholder` for investigation; may still need Sentry/exception **if** attached in future. |

**STOP trigger check:** *Inventory turns up more than one runbook can cover?* **No** — one medium file + links to handoff/privacy/checklist is sufficient. No escalation needed.

**Handoff §5 Phase 8.4 “backfills / reset sessions / who to call”:** All mappable: backfills and DB checks exist; “reset session” = **workaround** (new session or restart) — not absent capability to **document**.

---

## 6. Proposed 8.4-implement scope

- **File to create:** `docs/runbook.md` (single; Option A).
- **Files to update (optional, small):**  
  - `docs/pre-launch-checklist.md` — one bullet under **Open** *or* short note in header: “Operational runbook: `docs/runbook.md` (Phase 8.4).” **Owner choice** — not required for acceptance if we want checklist edits in a **separate** commit per repo discipline.  
  - `HAVASU_CHAT_CONCIERGE_HANDOFF.md` — **no** update required if runbook links *to* it (avoid churn in locked spec doc unless owner wants a one-line “see also”).
- **Sections to write (approximate length):**
  - **TOC** — 20–40 lines
  - **Quick reference** — 80–150 lines (bullets + one SQL appendix pointer)
  - **Routine ops** — 100–200 lines
  - **Admin guide + tables** — 200–500 lines (tables are dense, not wordy)
  - **Env + scripts + external** — 150–300 lines
  - **Failure modes + monitoring** — 150–300 lines
  - **Pre-launch checklist link** — 10–20 lines
  - **Who to call** — 20–50 lines
- **Link vs new prose:** **New prose** = operational “how to open Railway”, “how to run SQL with psql”, “what the fallback string means for metrics”. **Links** = handoff architecture, `docs/privacy.md` data handling, `docs/pre-launch-checklist.md` gates, in-repo path references to `app/...` for maintainers.
- **Size estimate:** **Medium (500–1200 lines)** in Markdown with tables; **not** >1500 unless we wrongly duplicate handoff.

---

## 7. Acceptance (read-first self-check)

| Criterion | Status |
| --- | --- |
| Items 1–6 in this file | **Yes** |
| No `docs/runbook.md` yet | **N/A (correct)** |
| No code / tracked doc edits in this pass | **Report file only; see below** |
| Working tree: only new untracked report (+ optional owner `phase-9` file) | **To verify after save** |
| 792 tests | **792 passed** (7m26s) |
| No commit | **Yes** |

After writing this file, **expected** `git status`: **untracked** `docs/phase-8-4-read-first-report.md` and any pre-existing `docs/phase-9-scoping-notes-2026-04-22.md`; no modified tracked files.

---

## 8. STOP-and-ask triggers (this read-first pass)

- **Pre-flight:** All passed. **No STOP.**
