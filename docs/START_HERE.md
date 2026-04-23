# Start here — Hava (Lake Havasu concierge)

This document is an **onboarding map**: what the product is, how the repo is laid out, where the authoritative specs live, and how to resume work after a gap. It does **not** replace setup steps (`HAVA_CONCIERGE_HANDOFF.md`, `docs/runbook.md`) or the persona/voice deep dives (`docs/persona-brief.md`, handoff §8).

---

## 1. What is Hava?

**Hava is the AI local of Lake Havasu** — a single-chat web app that answers questions about things to do, places, and services in Lake Havasu City, Arizona, in a local voice. The system routes questions through a **four-tier** pipeline: template lookups, structured catalog retrieval, LLM synthesis when needed, plus deterministic “gap” and out-of-scope handling. The catalog is **community-grown**: seed data is a starting point; residents and visitors add and correct information through the same interface (URL-backed contribution and operator review). One text box; modes include default **ask**, **contribute** (intake), **correct** (contested fields), and light **chat** (greetings / off-topic) per the handoff.

---

## 2. Current state — one-minute snapshot

*Figures below are from `HAVA_CONCIERGE_HANDOFF.md` §1d and recent git history. Update this section when a phase ships.*

- **Last closed major hardening pass:** **Phase 8.6** full regression — commit **`0d01d40`** (*Phase 8.6: full regression pass — voice baseline, smoke, endpoints*). See `docs/phase-8-6-implement-report.md` for pass/fail narrative; launch framing there: **GO for dogfooding week** with pre-launch checklist items still open.
- **Doc/persona track (8.8.x):** **8.8.1a** closed at **`3d4680b`** (*handoff rewrite for Hava persona/identity*). Follow-up doc-only commits may appear after that hash (e.g. §1d hash fix, completion report) — see `git log` for **tip of `main`**.
- **In flight:** **Phase 8.8.1b** — code alignment with `docs/persona-brief.md` and handoff §2.1 / §8 (system prompt, templates, known-issues cross-references as scoped in the brief). **8.8.2** (voice regression with new acceptance bar) is **pending** after 8.8.1b. **8.9** (event ranking: one-time vs recurring) is a **pre-launch addendum** — scope in `docs/persona-brief.md` §9.6; not in 8.8.1b.
- **Launch readiness:** **Soft-launch / dogfooding — GO** per Phase 8.6 report; **wider public launch — not fully GO** while `docs/pre-launch-checklist.md` has open items (Sentry rules, lawyer review, contact email, etc.). Treat **TBD** for a single “public flip” date — owner decision.
- **Next in queue (typical order):** Finish **8.8.1b** → **8.8.2** voice verification → **8.9** as scheduled → clear **pre-launch checklist** before broad marketing.

**Condensed phase map (not a substitute for §1d):** Core build **Phases 1–5.6** are closed (seed, chat API, tiers, contribute stack). **Phase 6** is closed (`7a12022` — voice, feedback, onboarding, session memory, 6.4.1, 6.5-lite). **Roadmap §5 Phase 7** (deterministic Tier 2 handler sheet) is **not** executed as a release; Tier 2 RAG lives under Phase 4.x code. **Phase 8** hardening is closed at **`0d01d40`** (8.6 capstone; 8.1 seed calls still owner). **8.8.0** persona + **8.8.1a** docs are in **`3d4680b`**. **8.8.1b** code is next. **8.9** is planned pre-launch. Full table, commit hashes, and voice-battery history: handoff **§1d** only.

---

## 3. Repo structure at a glance

Top-level directories (deeper detail in handoff §6 and §15):

```
app/          FastAPI app: chat pipeline, contribute/correct, admin HTML, API routes, DB models
docs/         Handoff, persona brief, runbook, legal pages, checklists, phase reports, START_HERE
prompts/      LLM prompt files (Tier 2 parser/formatter, Tier 3 system prompt, voice audit rules)
scripts/      Regression batteries, voice audit runner, smoke/load scripts, cost analysis
tests/        Pytest suite (isolated temp DB via conftest)
alembic/      SQLAlchemy migrations
```

**Also at repo root:** `HAVA_CONCIERGE_HANDOFF.md` (architectural source of truth), `requirements.txt`, `README.md`, `.env` (local; not committed).

**Inside `app/` (one line each, no deep tree):**

- `app/chat/` — unified router, tiers 1–3, context builder, intake/correction, entity match, local voice matcher.
- `app/contrib/` — URL fetch, Places client, enrichment, approval to catalog, mention scanner, hours helpers.
- `app/api/routes/` — `chat`, `contribute`, admin JSON for contributions and mentions.
- `app/admin/` — HTML for contributions, categories, mentions; cookie auth.
- `app/db/` — models, seed, chat logging, contribution and mention stores.
- `app/core/` — rate limits, session, search, extraction, event quality, etc.
- `app/static/index.html` — single-page chat UI (no front-end build step).

**Inside `scripts/` (representative):** `run_query_battery.py` (120-query regression), `run_voice_audit.py` / `run_voice_spotcheck.py` (different scopes), `smoke_concurrent_chat.py` (load-style checks), `analyze_chat_costs.py` (token analytics). Output JSON/MD files may be gitignored or committed as baselines per phase.

**Inside `tests/`:** `conftest.py` forces an isolated temp SQLite DB for the session; do not run tests against `events.db` unless explicitly debugging (see handoff §10 “Test isolation”).

---

## 3b. Suggested reading order (zero context → productive)

1. **This file** (10 min) — orientation only.
2. **Handoff §1.1–§1.3, §1a, §1b, §1d snapshot** (15–20 min) — product, vision, routing, what shipped.
3. **Handoff §2** (10 min) — locked decisions; do not improvise around these.
4. **Handoff §3.2 flow diagram** + **§3.3–§3.5** skim (15 min) — how a query moves.
5. **`docs/persona-brief.md` §1–§3** (10 min) — voice/identity at a high level before editing prompts.
6. **`docs/runbook.md` §1–§2** (10 min) — if you will touch production or admin paths.

Stop when your task is narrow; go deeper on handoff **§4** (data) and **§8** (voice) only when you are editing templates, prompts, or user-visible strings.

### 3c. `docs/` layout (typical, not exhaustive)

- **`runbook.md`, `privacy.md`, `tos.md`, `pre-launch-checklist.md`, `known-issues.md`** — **operator / launch** surfaces; treat as live process docs.
- **`persona-brief.md`, `START_HERE.md`** — **onboarding and character**; align with handoff on naming (**Hava** not legacy product string in new prose).
- **`phase-*` and `SESSION_*`** — **historical**; many are read-first or close-out artifacts from a single day or session. Filename dates matter when reconciling.
- **Seed and master** (`HAVASU_CHAT_*`, etc.) — **data provenance**; can disagree with the DB; handoff **§12** names the risk.

If you are looking for a **bug fix** write-up, search `known-issues.md` **Open** and **Resolved**; if you are looking for **command-line proof** of a phase, the phase report in `docs/` is the right anchor — then confirm against **`git show <hash>`**.

### 3d. Prompts directory (`prompts/`)

- **`system_prompt.txt`** — Tier 3 *system* instructions: voice, anti-hallucination, community references (being revised in **8.8.1b** to match first-hand voice).
- **`tier2_parser.txt`**, **`tier2_formatter.txt`** — few-shot and formatting instructions for the Tier 2 stack.
- **`voice_audit.txt`** — rubric for automated voice scoring (do not conflate with **master** docs from older process — audits score against handoff **§8** per Phase 6 audit notes).

**Never** paste production **secrets** into prompt files. API keys stay in env; prompts reference **behavior**, not credentials.

---

## 4. Architecture in one page

**Four-tier routing (handoff §1b, §3):** (1) **Classifier** picks mode and sub-intent. (2) **Tier 1** — deterministic templates when sub-intent and entity match. (3) **gap_template** — no entity match for a fact lookup; short acknowledgment and pointer toward contribution. (4) **Tier 2** — parser extracts filters, DB returns rows, formatter LLM composes an answer (retrieve-then-generate, not a separate “roadmap Phase 7” deterministic handler sheet). (5) **Tier 3** — full-catalog synthesis when Tier 2 cannot run or returns nothing. (6) **chat mode** for small talk / out-of-scope without burning Tier 3. `tier_used` is logged on `chat_logs`.

**Modes (handoff §3):** **ask** (default discovery), **contribute** (intake state machine with slot filling), **correct** (challenges and contested fields), **chat** (greetings, off-topic per §8.7-style handling).

**Data model (handoff §4, names only):** `providers`, `programs`, `events`, `field_history` (contested/established), `contributions` (URL-backed growth + review), `chat_logs` (incl. feedback where implemented), `llm_mentioned_entities` (operator promotion to contributions). Schema details stay in `app/db/models.py` and migrations.

**Deployment:** FastAPI + SQLAlchemy. **PostgreSQL** on Railway (production); **SQLite** for local dev. Push to **`main`** triggers Railway deploy. Env vars listed in handoff §11 and `docs/runbook.md`.

**Community-grown catalog (handoff §1a, §1c):** Seed is scaffolding. Users submit via **`/contribute`** with URL evidence where required; **Google Places (New)** and **URL fetcher** enrich rows; **operator** approves into the live catalog. Tier 3 can surface LLM-**mentioned** entities for later promotion (mention scanner) — not auto-admitted.

**Post–Phase 5.6 cost picture (handoff §1d, §9):** Documented per-tier **means** are anchored to **Phase 5.6** measurements. Phases 6–8 did not replace that table with a new benchmark in-repo — treat **§1d cost state** as the formal reference; re-run analytics if pricing or routing mix shifts materially.

**Post–Phase 8.6 test count:** Full `pytest` run was **794** passed (+ subtests) at the 8.6 report — use `pytest` for the live number; handoff **§13** checklist references 794+ as a convenient anchor.

**Where the “implementation appendix” went:** After **§6** in the handoff, **§15** is a **post–Phase 5** file-path appendix with production wiring — prefer it over this file for “where is X implemented?”

### 4a. Chat pipeline (files to know)

The **unified router** (`app/chat/unified_router.py`) is the hub for **ask** mode: it tries Tier 1, gap, Tier 2, Tier 3 in the order defined by the handoff. The **intent classifier** (`app/chat/intent_classifier.py`) runs early; it uses the legacy OpenAI **gpt-4.1-mini** choice from Phase 2 — do not swap models without an owner decision (handoff §2.5). **Tier 1** is implemented as **handler + templates** (`tier1_handler.py`, `tier1_templates.py`) with explicit template paths for sub-intents like HOURS, PHONE, OPEN_NOW, etc. **Gap** is not an LLM tier; it is a small fixed response that steers users toward **/contribute** when the catalog has no entity match (Phase 3.8+ / 5.4 evolution).

**Tier 2** chains **Pydantic filters** (`tier2_schema.py`), an LLM **parser** (`tier2_parser.py` + `prompts/tier2_parser.txt`), a **DB query** layer (`tier2_db_query.py` — includes `open_now` using `hours_structured` when present), and an LLM **formatter** (`tier2_formatter.py` + `prompts/tier2_formatter.txt`). That entire path is the production “structured retrieval” story; it is **not** the unbuilt `tier2_handlers.py` “deterministic handlers” sheet from the **roadmap** Phase 7 in handoff **§5**.

**Tier 3** (`tier3_handler.py` + `prompts/system_prompt.txt`) does broad synthesis; **context_builder** assembles catalog + session hints. Post-response, the **mention scanner** may queue candidate names (`app/contrib/mention_scanner.py` → `llm_mentioned_entities`).

**Intake and correction** live under the same `app/chat` package: **intake** for contribute-mode slot filling, **correction** for user challenges feeding **field_history** and contested rules.

### 4b. Modes and user journeys (summary)

- **ask:** Default. Max traffic. Subject to full tiering and **§8** voice rules for user-visible replies.
- **contribute:** Collects a URL-backed (or event-exception) submission, enriches, queues for **admin** — see **§1c** and **§8.8** intake voice. Not the same code path as ask-mode tiers for the final success message, but still governed by the same app shell.
- **correct:** Feeds **field_history**; may set **contested** state and dual-answer templates for low-stakes fields per **§2.3**; high-stakes always toward review.
- **chat:** Greetings, small talk, and **out-of-scope** redirects. Classifier may route here without tier 3 cost when patterns match. **§3.2** diagram is authoritative.

### 4c. Operator and admin

Browser **HTML** under `/admin/…` (password in env) for **contributions** list + detail, **categories** dashboard, **mentioned entities** list. **JSON** admin APIs support scripted approval flows. The operator is not an end user of the public chat; they are Casey or a future delegate. Rate limits: public **/api/chat** and **/contribute** differ; see `app/core/rate_limit.py` and `contribution_store` (handoff has the numbers).

### 4d. Deployment and environments

- **Local:** SQLite file (often `events.db` in dev), venv, uvicorn. **Do not** point tests at the dev DB unless you know why (conftest).
- **Production:** Railway, Postgres, same codebase. Migrations via Alembic; `railway run … alembic upgrade head` per runbook. **Sentry** is wired; full alert *rules* are a checklist item, not a code default.
- **Main auto-deploys** on push; coordinate voice verification after deploy for anything user-visible.

### 4e. Design targets (not a SLA)

Handoff **§3.1** gives **rough tier mix targets** (e.g. Tier 1 share high, Tier 3 share bounded). They are product guardrails, not real-time autoscaling rules. If Tier 3 share grows, the response is new templates, Tier 2 coverage, or product narrowing — not a promise in this file.

### 4f. Cost and analytics (pointers)

**§1d** holds **per-tier mean** token counts from Phase 5.6-era benchmarking. **§9** has order-of-magnitude monthlies at 1k queries/day under old assumptions. **`scripts/analyze_chat_costs.py`** is how you re-derive today’s mix from `chat_logs` with input/output token columns. Nothing in this onboarding file replaces a fresh measurement when cost is contested.

### 4g. Testing pointers

**Unit/integration:** `pytest` is mandatory before merging major phases; count moves over time (794+ as of 8.6). **Batteries:** 120-query regression script vs 20-query spotcheck vs 55-sample **voice audit** — three different tools; do not compare numbers across them without context (handoff §1d voice history). **Load:** `smoke_concurrent_chat.py` and Phase 8.2 notes in runbook — environment-dependent latency; read phase-8-6 report before declaring regression.

### 4h. Schema, migrations, and one-off DBA work

**Alembic** (`alembic/versions/…`) is the only supported way to change production schema. **Do not** hand-edit production tables without a migration story unless the runbook’s emergency path applies. The handoff **§6** tree and **§15** appendix name representative migrations; there are more files on disk than the three-line summary shows — `alembic current` and the versions folder are source of truth for *what exists*.

**Seed and backfill scripts** under `app/db/` and one-off `scripts/*.py` exist for data hygiene; they are not automatically run in deploy. Anything that mutates many rows in production should be in the runbook or a phase report so the next operator can **repeat** and **verify**.

### 4i. External services (conceptual)

- **OpenAI** — Classifier and small structured tasks as wired (see code, not this file for exact calls).
- **Anthropic** — Haiku for Tier 2 and Tier 3 as wired.
- **Google Places (New)** — Enrichment for provider-type contributions; key restrictions and SKUs in handoff **§1c** and runbook.
- **Railway** — Hosting, Postgres, env, deploy hooks.
- **Sentry** — Exception capture; alert **rules** are a checklist item.

Each integration can fail independently; **§3.11** graceful paths and **Phase 8.3** work cover “what the user sees” when a vendor returns 5xx or times out. Do not re-spec that matrix here.

### 4j. “Why there is no React app”

The **§2.6** decision locks **vanilla** `index.html` with incremental JS. There is no `package.json` front-end build. UI changes are **surgical** edits to a single file plus CSS/JS patterns already present. A future rewrite is out of scope unless the owner re-opens the decision.

### 4k. Differences you might notice vs other chatbots

- **Single city** — no multi-tenant, no “pick your town.”
- **Restaurants** — listed in **§1.3** as *not* what the v1 app is *about*; **§1a** clarifies the exclusion list is “not pre-seeded,” not a permanent ban on user-contributed rows with URL evidence. Tier routing still uses **out-of-scope** style handling for *generic restaurant* questions in product tests — see handoff, not this summary, for the exact line.
- **No accounts for end users** in the v1 model described by the handoff; admin uses a **shared password** pattern for HTML tools.
- **Asking “what is Hava”** is an explicit case in the persona for **reactive** AI self-reference, unlike generic assistant boilerplate the voice rules avoid.

### 4l. Where **not** to look first

- `app/chat/router.py` — **Track A** legacy; unified router is the main path. Read **§15** to see which pieces still matter.
- Old **markdown** in `PHASE_5_PLAN.md` and similar **plan** files at root — may predate the handoff’s current numbering. Prefer **handoff §5** + **git log** over a frozen plan.

---

## 5. How work happens

- **Owner (Casey):** product decisions, approval of fix shape on substantive changes, review-before-commit, push approval for production-bound work, operator review of contributions, voice judgment calls, legal/launch gates.
- **Claude (design partner):** prompt and phase structure; drafts Cursor prompts with handoff **section references**.
- **Cursor / coding agent:** implements in repo; obeys **scope fences** in each prompt; **stops and asks** when a decision is not locked in the handoff.

**Phase-gate habits:** **Read-first** on large phases; owner approves the **shape** of the fix; **commit** and **push** are separate — many workflows hold commit until review, and hold **push** until explicit owner approval. “Push to `main`” deploys — treat it as production-affecting.

**Anti-drift:** Prompts should cite handoff **§ numbers**; do not re-open the **seven locked decisions** (handoff §2) without owner approval. Historical rows in §1d (e.g. Phase 3.6) stay as historical record even when later decisions supersede the narrative.

For the canonical process paragraph, see handoff **§0** and **Role split (Cursor + owner)** at the top of the handoff.

**Conventions that prevent wasted work:** Do not start a roadmap **§5** phase number unless the owner’s prompt names it. Do not conflate **roadmap “Phase 7”** (deterministic handlers in the build plan) with the **Phase 4.x Tier 2** stack already in production — see handoff **§1d** row for Phase 7. Do not “fix” **persona** or **legal** pages in a code phase unless the prompt explicitly includes them; many docs are **owner** or **lawyer** gates.

**Voice-affecting changes:** After a deploy, allow **Railway** a few minutes, then re-run the relevant **smoke** or **voice** script if the prompt asked for verification (handoff §0-style workflows).

**What “lock” means here:** The handoff is a **contract**. If the code and the handoff disagree, the owner decides whether the code is wrong, the handoff is stale, or a new decision is needed. The agent’s job is to surface the conflict, not to silently “fix” the handoff in the same pass as code unless the current prompt explicitly authorizes handoff edits.

**Artifacts vs source of truth:** `docs/phase-*.md` files are **historical reports** from past reads or executions. The **tip of `main`** and **`HAVA_CONCIERGE_HANDOFF.md`** beat an old report when they conflict, unless a phase explicitly re-validated the report. Phase completion tables in **§1d** are canonical *history* for shipped phases — append or correct, do not delete rows.

**Communication cadence with agents:** Favor **small, cited prompts** over giant dumps. If a response includes a handshake (“ready for the next sub-phase”), it is **not** an automatic go-ahead to code — it signals human readiness to **send the next prompt**, matching handoff §0.

**If you are an AI session:** Re-read the **User rule or prompt’s scope** every time. If the prompt says **docs only**, do not touch `app/`, `prompts/`, or `scripts/` unless the user explicitly widens scope. If the prompt says **read-only**, the same applies to all write paths. When uncertain whether a file is in scope, **stop**.

---

## 6. Where to pick up

*Update this block whenever something substantial ships.*

| Field | Current |
|--------|---------|
| **Branch / tip** | `main` — run `git log -1 --oneline` for tip (this file lands in the `docs: documentation refresh — onboarding + handoff catch-up` commit family). |
| **In-flight phase** | **8.8.1b** — prompt/template/code alignment to `docs/persona-brief.md` and handoff voice sections; **8.8.2** and **8.9** follow per brief. |
| **Last owner-facing doc milestone** | **8.8.1a** handoff + `docs/persona-brief.md` in tree (`3d4680b`); doc-only follow-ups: §1d hash fix (`adfa04c`), 8.8.1a completion report (`eb7b76f`), **`START_HERE` + handoff §1d/§5/§6 catch-up** (same commit series as this file). |
| **Active Cursor prompt** | *None hard-coded here* — the latest phase prompt is whatever the owner last sent. Next execution should quote **§2.1, §8, and `docs/persona-brief.md`** for 8.8.1b. |
| **Next owner action** | Approve **8.8.1b** scope, run voice/regression as needed after code lands, and prioritize **8.9** vs checklist items. |

**Quick resume commands (developer):** from repo root with venv, `.\.venv\Scripts\python.exe -m pytest -q` (Windows). Production ops: `docs/runbook.md` §1.

**If you only have three minutes:** read **§2** (snapshot) and **§6** (pick-up) of *this* file, then open **handoff §1d** for the exact table. If you have ten, add **handoff §3.2** and **`docs/persona-brief.md`** table of contents.

**If you are picking up someone else’s branch:** `main` is the integration line; feature branches may exist locally but **Railway** tracks **`main`**. Rebase/merge policy is team preference — the handoff assumes **linear** history on `main` for phase-close narratives.

**Doc-only refresh cadence:** Whenever §1d or §5 in the handoff **changes the official story of what shipped**, echo the minimum necessary delta into **this file’s §2 and §6** in the same commit family so `START_HERE` does not **lag** the handoff for more than a phase boundary.

**Tip commit for this document’s accuracy target:** documentation refresh commits should cite **`git rev-parse HEAD`** in the completion report; readers can diff `START_HERE` against that commit if narrative drifts.

**Line-count budget:** This file is intentionally **long** so newcomers can scroll once and land on the right section without opening six PDFs. Prefer editing **handoff** for normative changes; edit **here** for **navigation** and **time-boxed** summaries only.

**Versioning:** No separate semver; **git** is the version.

---

## 7. Authoritative references

| Path | Role |
|------|------|
| `HAVA_CONCIERGE_HANDOFF.md` | **Primary spec:** routing, modes, data model, §1a vision, **seven locked decisions (§2)**, architecture (§3–§4), build plan (§5), file map (§6), voice spec (§8), costs (§9), testing (§10), deployment (§11). |
| `docs/persona-brief.md` | **Persona and identity** for Hava; Phase 8.8.0+; ties to 8.8.1a/b and 8.9 notes. |
| `docs/runbook.md` | **Operations** — health checks, admin paths, SQL, Sentry, Railway, performance notes (Phase 8.4). |
| `docs/privacy.md` | **User-facing** privacy policy (8.7-era draft; lawyer review on checklist). |
| `docs/tos.md` | **User-facing** terms (8.5; lawyer review on checklist). |
| `docs/pre-launch-checklist.md` | **Gating** items before broad public launch (Sentry, legal, email, etc.). |
| `docs/known-issues.md` | **Open / resolved** deferred items and metrics notes (8.0+ reconciliation). |
| `README.md` | **Contributor-oriented** top-level entry (if present); use handoff for depth. |
| `docs/phase-8-6-implement-report.md` | **Phase 8.6** regression and voice-audit **numerical** baseline (55-sample audit). |

**Cross-links inside `docs/`:** Dozens of **phase-*-read-first-report.md** and similar files exist. Use them for **how a past decision was argued**, not as binding scope for new work unless the handoff explicitly points there. **`SESSION_RESUME_*.md`** files are optional human scratchpads.

**Root-level extras:** `README.md`, `HAVASU_CHAT_MASTER.md`, seed instruction docs — useful for **data provenance** and marketing copy outside the app; they can drift from code — **§12 known risks** in the handoff calls out seed/master drift.

---

## 8. Quick glossary

| Term | Meaning |
|------|---------|
| **Tier 1 / 2 / 3** | Deterministic template path; structured retrieval + LLM format; open-ended LLM synthesis — see handoff §1b / §3. |
| **gap_template** | No catalog entity for a fact lookup; canned gap response + contribute pointer (§1b). |
| **Intake** | **Contribute** mode: slot-filling state machine to add events/programs/providers (handoff §3, §8.8 voice). |
| **Contested state** | Field-level dispute with dual-answer behavior until resolved per **§2.3** (high- vs low-stakes). |
| **§8.7 carve-out** | Out-of-scope template for restaurants, weather, etc.; trailing question allowed there per tests — see `known-issues.md` if handoff text seems to conflict with §3.9 / §8.2. |
| **Firsthand local voice** | Hava speaks as a local, without attributing every fact to “the community” in text (**§2.1**, persona brief). Replaces old Option B “community-credit” *surface*; §1a URL-backed data model unchanged. |
| **Voice battery** | **20-query** `run_voice_spotcheck` vs **55-query** `run_voice_audit` — different scripts; §1d tracks both families where recorded. |
| **Community-credit (historical)** | **Phase 3.6** Option B stance — superseded in voice by 8.8; §1d history rows kept. |
| **Contributed vs seeded** | `source` and provenance chain — seed is bootstrap; user/admin paths add `user` / `llm_inferred` / etc. (handoff §1c). |
| **8.8.1a / 8.8.1b** | **Docs** handoff rename + brief (**closed**) vs **code** prompt/template work (**in flight**). |
| **8.9 (event ranking)** | Prefer one-time vs recurring in time-scoped event answers — brief §9.6; checklist line may lag — see handoff **§5 Phase 8.9** addendum. |
| **Track A** | Legacy `POST /chat` path; unified router and `POST /api/chat` are the production concierge path; analytics nuance in runbook. |
| **LlmMentionedEntity** | Table and admin path for Tier 3 **name-drops** queued for possible promotion to `contributions` (Phase 5.5). |
| **open_now** | Tier 2 filter using structured hours — requires `hours_structured` populated (many seed rows still `NULL`). |
| **RAG (informal)** | “Retrieve from DB, then call formatter LLM” = Tier 2 path in this codebase, not a separate product name. |
| **Dogfooding vs public** | “Soft” launch to trusted users vs checklist-cleared public — **pre-launch-checklist** is the explicit gate. |
| **Haiku / gpt-4.1-mini split** | **Anthropic Haiku** for Tier 2 parser+formatter and Tier 3; **OpenAI gpt-4.1-mini** for classifier and some extraction — cost and latency differ; see **§2.5** and **§1b**. |
| **field_history** | Audit trail for corrections: **established** vs **contested** values, stakes, deadlines — backs dual-answer templates. |
| **Provider / program / event** | Three catalog entity types with different fields; programs link to providers in many cases; events are dated occurrences. |
| **URL as trust anchor** | **§1a** — community claims expected to attach to a verifiable URL for businesses; events have a looser path. |
| **Review-before-commit (policy phrase)** | Handoff §0: agent completes work, **holds** VCS write until owner says commit/push in workflows that use that policy; do not assume every chat session uses the same gate — follow the **active prompt**. |
| **Sub-phase** | Phases (e.g. 6.1, 8.0.2) that are intentionally committable slices; still need explicit prompt to execute. |
| **Sentinel / placeholder `tier_used`** | Legacy `chat_logs` rows may have NULL or placeholder tier labels — analytics must filter; see `known-issues.md` and Phase 8.0.5 notes. |
| **Option 2 / Option 3 (rec voice)** | **§2.2** — list+standout default vs explicit “pick one” recommendation energy; Tier 3 prompt encodes the split. |

---

## 9. What this doc is not

- Not a **phase history table** — use handoff **§1d** (commit hashes, voice battery history, cost block, deferred log).
- Not the **full voice spec** — handoff **§8** and **`docs/persona-brief.md`**; this file only orients.
- No **install copy-paste** — venv, env vars, and deploy in handoff **§11** and **`docs/runbook.md`**.
- No **SQL or API request bodies** here — see runbook and `app/api/routes/`.
- Not a **substitute for the build plan** — handoff **§5** still defines roadmap intent; **§1d** records what actually shipped.
- Not **legal advice** — `tos.md` / `privacy.md` are drafts for lawyer review per checklist.
- Not a **data dictionary** — for column-level truth, `app/db/models.py` and Alembic **versions** beat prose.

When in doubt: **`HAVA_CONCIERGE_HANDOFF.md` wins** unless the owner says otherwise (handoff end matter).

**Maintenance rule:** When you complete a phase that changes **in-flight work**, **build plan reality**, or **tip-of-tree**, update **sections 2 and 6 of this file** (Current state; Where to pick up) so the 2/5/10 minute promises stay true. Prefer a one-line `git log -1` pointer over narrative drift.

---

*File introduced in Phase 8.X documentation refresh. Keep it accurate when phase status or tip-of-`main` changes materially.*

