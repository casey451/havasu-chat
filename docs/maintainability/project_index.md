<!--
PURPOSE: High-level navigation index for the havasu-chat repo — where major
code and docs live, which end-to-end flows matter, and what is already written
down vs missing. Intended for an external Claude session that cannot browse the
tree.

AUDIENCE: Project owner and assistants planning work or answering questions
about the codebase. Map only: descriptive, not evaluative. For chat pipeline
detail see docs/maintainability/chat_behavior_followup_plan.md (refs) and the
prior session's unified-router trace; this doc stays one level up.
-->

# Project index

## 1. What this project is

**Hava** is a conversational concierge for Lake Havasu City, Arizona: a FastAPI backend with SQLAlchemy and Postgres (production on Railway; SQLite possible for local dev) that exposes chat, contribution intake, admin review surfaces, and static UI. User questions are normalized and classified, then handled through **Tier 1** (deterministic catalog lookups where applicable), **Tier 2** (LLM-parsed structured filters → SQL over events/programs/providers → formatter), and **Tier 3** (Anthropic Haiku with a catalog context block built from the DB). Prompts live under `prompts/`; orchestration is centered in `app/chat/unified_router.py`. As of **2026-05-03**, production catalog posture described in maintenance docs is **River Scene–sourced events only** (non–River-Scene seed and lanes removed); the app still contains code paths for providers, programs, and contributions when those tables are populated.

## 2. Module map

**`app/`** — Application package: FastAPI app (`app/main.py`), HTTP routers, chat stack, DB models and stores, admin HTML and APIs, core utilities (LLM clients, dedupe, timezone, rate limits), eval harness, schemas, static assets, and small `programs` and `data` helpers. **`app/main.py`** wires routers (concierge chat, public contribute, admin, programs) and middleware.

**`app/api/`** — FastAPI route modules mounted from `main`. Notable: **`routes/chat.py`** (`POST /api/chat`, onboarding, feedback) calls **`unified_router.route`**; **`routes/contribute.py`** public contribution submission; **`routes/admin_contributions.py`** and **`routes/admin_mentions.py`** JSON endpoints under `/admin/api` (cookie auth via **`app/admin/auth.py`**).

**`app/chat/`** — Unified concierge pipeline. **`unified_router.py`** orchestrates normalize → classify → hint extraction → entity enrichment → mode-specific handling. **`intent_classifier.py`** heuristic mode/sub-intent; **`normalizer.py`**; **`hint_extractor.py`** optional OpenAI JSON hints; **`entity_matcher.py`** catalog matching; **`tier1_handler.py`** + **`tier1_templates.py`** deterministic provider/program/event answers; **`tier2_parser.py`**, **`tier2_db_query.py`**, **`tier2_schema.py`**, **`tier2_handler.py`**, **`tier2_formatter.py`**, **`tier2_catalog_render.py`** for structured retrieval; **`tier3_handler.py`** + **`context_builder.py`** for grounded Haiku replies; **`llm_router.py`** optional Anthropic routing when `USE_LLM_ROUTER` is set; **`local_voice_matcher.py`** reads **`app/data/local_voice.py`** for Tier 3 bias lines.

**`app/contrib/`** — Cross-cutting ingestion and helpers: **`river_scene.py`** (fetch/parse/normalize River Scene listings), **`river_scene_pull.py`** (`run_pull` used by CLI), **`approval_service.py`** (pending contribution → `Provider` / `Program` / `Event` rows), **`enrichment.py`**, **`mention_scanner.py`**, **`hours_helper.py`**, **`url_fetcher.py`**, **`places_client.py`**, **`event_date_line.py`**, etc.

**`app/db/`** — SQLAlchemy **`models.py`**, session **`database.py`**, **`contribution_store.py`**, **`chat_logging.py`** (`ChatLog` inserts), **`llm_mention_store.py`**.

**`app/eval/`** — Confabulation eval stack: **`confabulation_invoker.py`**, **`confabulation_query_gen.py`**, **`confabulation_evidence.py`**, **`confabulation_detector.py`**, **`confabulation_report.py`** (see `docs/confabulation-eval-runbook.md`).

**`app/admin/`** — Password/cookie-gated HTML UIs and **`router.py`** for login and pages (contributions queue, categories, feedback, mentions); works with **`admin_contributions`** API for approve/reject/enrich flows.

**`app/core/`** — Shared logic: **`llm_messages.py`** (Anthropic `messages.create`, `load_prompt`), **`llm_http.py`**, **`session.py`** (in-memory session store, prior entity), **`rate_limit.py`**, **`dedupe.py`**, **`event_recurrence.py`**, **`intent.py`**, **`timezone.py`**, **`slots.py`**, **`field_tracking.py`**, **`event_quality.py`**, **`search.py`**, **`program_search.py`**, **`provider_name.py`**, **`extraction.py`**, **`conversation_copy.py`**, **`search_log.py`**, etc.

**`app/schemas/`** — Pydantic request/response models (e.g. **`chat.py`**, **`contribution.py`**, **`event.py`**, **`program.py`**, **`llm_mention.py`**).

**`app/programs/`** — **`router.py`** for program-related HTTP (mounted from `main`).

**`app/data/`** — Packaged data such as **`local_voice.py`** for voice blurbs.

**`app/static/`** — **`index.html`** and related static front-end for the hosted UI.

**`app/bootstrap_env.py`** — Dotenv loading helper imported early from `main`.

**`tests/`** — Pytest suite mirroring features: API (`test_api_chat.py`, contribute, admin), tier1–3, router, River Scene phases, confabulation, mentions, etc.; **`tests/fixtures/`** holds HTML and text fixtures.

**`prompts/`** — Plain-text system prompts loaded by name via **`app/core/llm_messages.load_prompt`** (e.g. `system_prompt.txt`, `tier2_parser.txt`, `tier2_formatter.txt`, `llm_router.txt`, `hint_extractor.txt`, voice audit prompts).

**`scripts/`** — Operational CLIs and one-off tools: **`river_scene_pull.py`** (thin wrapper over **`app.contrib.river_scene_pull.run_pull`**), backfills, query batteries, confabulation result dirs, voice audit JSON; **`scripts/README.md`** summarizes several entries. **`alembic/`** — migration versions and env for schema changes.

**`docs/`** — Project documentation (see section 4).

**`relay/`** — Ephemeral working directory for HALT transcripts, sanity-check outputs, and similar files produced during owner ↔ assistant relay sessions. Root **`.gitignore`** ignores everything under **`relay/`** except **`relay/README.md`** (which explains the convention); other files there are local-only and not part of git history. **`docs/STATE.md`** records that ignore pattern as part of a docs-tree cleanup. Not a git submodule (no `.gitmodules` at repo root).

**`alembic.ini`**, **`pytest.ini`**, **`.cursorrules`**, **`.cursor/rules/`** — Tooling and editor/agent configuration (not application runtime code).

## 3. Key flows

**Chat answer composition** — User message hits **`POST /api/chat`** in **`app/api/routes/chat.py`**, which calls **`unified_router.route`** in **`app/chat/unified_router.py`**. The router normalizes text, classifies mode/sub-intent, optionally extracts session hints and enriches entity from the DB, then runs ask-mode logic: Tier 1 template/DB lookup when entity + sub-intent match, else optional LLM router (`USE_LLM_ROUTER`), else Tier 2 parser→query→formatter, else Tier 3 with **`context_builder`**. Responses are logged to **`chat_logs`**; Tier 3 turns may trigger background mention scanning. **See also:** `docs/maintainability/chat_behavior_followup_plan.md` (code pointers §6); `docs/components/unified_router.md`; prior session trace of `unified_router.route` → tiers → `log_unified_route`.

**River Scene → database** — **`scripts/river_scene_pull.py`** invokes **`run_pull`** in **`app/contrib/river_scene_pull.py`**, which uses **`app/contrib/river_scene.py`** to read the magazine sitemap and event pages, normalize rows into contribution-shaped payloads, and write **pending** rows into the contributions pipeline (with dedupe / overlap logic in the same module). Operators or automation then **approve** contributions so catalog tables update. **See also:** `docs/maintainability/river_scene_event_output_decision.md`, `docs/maintainability/non_river_scene_cleanup.md`, `docs/maintainability/river_scene_backfill_prod_dryrun_runbook.md`.

**Admin / correction / approval** — **Yes, flows exist.** Cookie-based admin login (**`app/admin/router.py`**, **`app/admin/auth.py`**) serves HTML for reviewing the queue (**`contributions_html.py`**, etc.). **`app/api/routes/admin_contributions.py`** exposes JSON for listing contributions, status updates, optional **`enrich_contribution`** background work, and approval paths that delegate to **`app/contrib/approval_service.py`** (`approve_contribution_as_event`, provider/program variants) to create or update **`Event`** / **`Program`** / **`Provider`** rows from pending **`Contribution`** records. Separate admin routes cover mentions (**`admin_mentions.py`**). Public **`POST`** contribute flow lives in **`app/api/routes/contribute.py`** with **`contribution_store`**. **See also:** `docs/runbook.md`; tests such as **`tests/test_approve_pending_river_scene.py`**, **`tests/test_admin_feedback.py`**.

**Confabulation eval (offline / operator)** — **`app/eval/confabulation_invoker.py`** can call **`unified_router.route`** in-process or hit **`POST /api/chat`** over HTTP; evidence and reports are assembled by sibling modules. **See also:** `docs/confabulation-eval-runbook.md`.

## 4. Existing docs index

Paths below are relative to repo root. **Status** is judgment from titles/banners/content, not file mtimes.

### Orientation and ongoing reference (current)

| Path | One-line | Status |
|------|----------|--------|
| `docs/START_HERE.md` | Bootstrap for new Claude sessions: stack, branch, where to read next. | Current |
| `docs/CURSOR_ORIENTATION.md` | Shorter Cursor-focused orientation. | Current |
| `docs/CLAUDE_SESSION_BRIEFING.md` | Session briefing / context for assistants. | Current |
| `docs/PROJECT.md` | Project overview. | Current |
| `docs/STATE.md` | Declared repo/product state snapshot. | Current |
| `docs/WORKING_AGREEMENT.md` | Collaboration and process agreements. | Current |
| `docs/persona-brief.md` | Hava voice and delivery rules (referenced by prompts). | Current |
| `docs/runbook.md` | Operational runbook. | Current |
| `docs/pre-launch-checklist.md` | Pre-launch checklist. | Current |
| `docs/POST_SHIP_CHECKLIST.md` | Post-ship checklist. | Current |
| `docs/BACKLOG.md` | Backlog items. | Current |
| `docs/query-test-battery.md` | Query test battery description. | Current |
| `docs/privacy.md` | Privacy policy text. | Current |
| `docs/tos.md` | Terms of service text. | Current |
| `docs/havasu-knowledge-base.md` | Knowledge base / content reference. | Current |
| `docs/havasu-development-plan.md` | Development plan narrative. | Current |
| `docs/search-pipeline-for-claude.md` | Search pipeline explanation for assistants. | Current |
| `docs/confabulation-eval-runbook.md` | How to run confabulation eval (invoker, probes, reports). | Current |
| `docs/known-issues.md` | Deferred bugs and findings; banner notes much is pre–H1 historical. | Mixed — still used for open items |
| `docs/components/unified_router.md` | Component note for unified router. | Current |

### Maintainability and retrospectives (current)

| Path | One-line | Status |
|------|----------|--------|
| `docs/maintainability/chat_behavior_followup_plan.md` | Post–cleanup chat followup: routing gap, eval plan, pointers. | Current |
| `docs/maintainability/non_river_scene_cleanup.md` | RS-only catalog cleanup retrospective and verification. | Current |
| `docs/maintainability/river_scene_event_output_decision.md` | River Scene parser/output retrospective. | Current |
| `docs/maintainability/h1_router_decision.md` | H1 router deletion / unified path decision. | Current |
| `docs/maintainability/h2_consolidation_decision.md` | H2 LLM consolidation decision. | Current |
| `docs/maintainability/findings_app_chat.md` | Findings note for `app/chat`. | Current |
| `docs/maintainability/river_scene_backfill_documentation_index.md` | Index of River Scene backfill docs. | Current |
| `docs/maintainability/river_scene_backfill_prod_dryrun_runbook.md` | Prod dry-run runbook for RS backfill. | Current |
| `docs/maintainability/river_scene_dryrun_quick_reference.md` | Short RS dry-run reference. | Current |
| `docs/maintainability/river_scene_sentinel_id_retention.md` | Sentinel ID retention decision. | Current |

Older phase and tier work — Tier 2 / Tier 3 grounding specs and inline reports, voice-audit samples, Railway migration and database diagnostics, dated production smoke-test and verification writeups, the legacy router deletion ship, pre-launch scope revisions, H2 slim handoff files, and similar slice-complete writeups — **were** filed as individual Markdown files under `docs/` and `docs/maintainability/`. Many of those files have since been **removed from the working tree** to reduce navigation noise; **git history** retains their content. When a specific filename or topic is needed, search `git log` / `git log --all -- full/path` or browse `docs/` for what remains.

## 5. What is not yet documented

- There is **no single doc in `docs/`** that exhaustively describes **Railway service layout** (process types, env var matrix, health checks) as a dedicated deployment architecture page; pieces appear in runbooks and railway-titled diagnostics.
- There is **no dedicated design doc** for a **future provider ingestion lane** (the followup plan lists options; the cleanup retrospective explains removed lanes — no forward-looking provider pipeline spec in-tree as a standalone file).
- There is **no `docs/` file** that is **only** an **API reference** listing every route, method, and schema (behavior is spread across `app/api/`, `app/main.py`, and narrative docs).
- **Automated chat regression / versioned query battery** beyond confabulation tooling is **not described as a shipped subsystem** in its own “how to run in CI” doc (the followup plan notes the gap).
- **End-to-end data flow for non–River-Scene provider/program creation** from empty tables is **not** centrally documented now that cleanup removed prior seed paths (code paths remain; narrative is split across retrospectives and code).
- The **repository root `README.md`** does not mention **`relay/`**; only **`relay/README.md`** and **`docs/STATE.md`** describe that directory’s role for contributors who read neither.
