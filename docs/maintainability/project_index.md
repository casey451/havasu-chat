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

**`alembic.ini`**, **`pytest.ini`**, **`.gitattributes`**, **`.cursorrules`**, **`.cursor/rules/`** — Tooling and editor/agent configuration (not application runtime code).

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
| `HAVA_CONCIERGE_HANDOFF.md` (repo root) | Architecture spine: tiers, data model summary, pointers to persona + maintainability decisions. | Current |
| `docs/START_HERE.md` | Bootstrap for new Claude sessions: stack, branch, where to read next. | Current |
| `docs/CURSOR_ORIENTATION.md` | Shorter Cursor-focused orientation. | Current |
| `docs/CURSOR_NEW_CHAT_PLAN.md` | Mode A vs B playbook for new Cursor sessions: full doc read order, paste templates, ship close-out. | Current |
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
| `docs/components/tier2_handler.md` | Component note for Tier 2 handler chain (parser → DB → formatter); see also unified_router.md. | Current |
| `docs/components/tier2_parser.md` | Component note for Tier 2 parser (Anthropic JSON extraction → Tier2Filters); see also tier2_handler.md, tier2_schema.py. | Current |
| `docs/components/tier2_formatter.md` | Component note for the Tier 2 formatter (deterministic events path + LLM mixed path with post-processor link injection). | Current |
| `docs/components/tier3_handler.md` | Component note for Tier 3 LLM synthesis (`answer_with_tier3` + `FALLBACK_MESSAGE`); see also unified_router.md. | Current |
| `docs/components/intent_classifier.md` | Component note for the heuristic intent classifier (mode + sub-intent + entity + confidence). | Current |
| `docs/components/hint_extractor.md` | Component note for the optional OpenAI age/location hint extractor (sole OpenAI caller in the codebase). | Current |
| `docs/components/llm_router.md` | Component note for the optional Anthropic structured router (USE_LLM_ROUTER feature flag). | Current |
| `docs/components/river_scene.md` | Component note for the River Scene ingestion lane (sole live catalog source post-2026-04-30 cleanup); fetch/parse + orchestration, dedupe, auto-approval flow. | Current |
| `docs/components/enrichment.md` | Component note for background contribution enrichment (URL fetch + Places lookup session orchestration). | Current |
| `docs/components/event_date_line.md` | Component note for River Scene–style Date line parsing (single day vs same-month range). | Current |
| `docs/components/hours_helper.md` | Component note for Places periods → structured hours + OPEN_NOW `is_open_at` (Lake Havasu tz). | Current |
| `docs/components/places_client.md` | Component note for Google Places API (New) text search client used in provider enrichment. | Current |
| `docs/components/river_scene_pull.md` | Component note for River Scene pull orchestration (`run_pull`: sitemap → contributions → auto-approval). | Current |
| `docs/components/url_fetcher.md` | Component note for SSRF-aware URL metadata fetch (title/description extraction). | Current |
| `docs/components/tier1_handler.md` | Component note for the Tier 1 deterministic-template handler (zero-LLM-token direct DB lookups). | Current |
| `docs/components/approval_service.md` | Component note for the contribution → catalog-row materialization service (sole catalog-write path: Provider/Program/Event approval). | Current |
| `docs/components/llm_messages.md` | Component note for the H2 Anthropic-Messages-API consolidation helper (sole Anthropic call site; mock-seam invariants documented). | Current |
| `docs/components/admin_auth.md` | Component note for admin cookie-gate auth (`app/admin/auth.py`) — security-sensitive; documents threat model. | Current |
| `docs/components/admin_router.md` | Component note for the admin router (`app/admin/router.py`) — overview, route inventory, conventions; pairs with admin_auth.md. | Current |
| `docs/components/admin_categories_html.md` | Component note for the admin categories listing renderer. | Current |
| `docs/components/admin_contributions_html.md` | Component note for the contribution review HTML surface (form, submit/approve/reject paths, ProgramApprovalFields writer). | Current |
| `docs/components/admin_feedback_html.md` | Component note for the admin feedback page (Tier-3 thumb signal aggregation). | Current |
| `docs/components/admin_mentions_html.md` | Component note for the Tier-3 LLM-mention review surface. | Current |
| `docs/components/admin_nav_html.md` | Component note for the shared admin nav fragment. | Current |
| `docs/components/mention_scanner.md` | Component note for Tier 3 mention scanner (Path 3 catalog-creation feedback loop; title-case entity extraction with stop-list filtering). | Current |
| `docs/components/event_quality.md` | Component note for the FastAPI request-validation pretty-printer (`friendly_errors` for ConciergeChatRequest); post-Slice-21 minimal surface. | Current |
| `docs/components/rate_limit.md` | Component note for the shared slowapi `Limiter` (per-IP request budgets; env-toggleable for tests). | Current |
| `docs/components/dedupe.md` | Component note for embedding + date + location three-gate event duplicate detection. | Current |
| `docs/components/conversation_copy.md` | Component note for user-facing casual-copy string constants (search/program/out-of-scope templates). | Current |
| `docs/components/event_recurrence.md` | Component note for regex-based event recurrence heuristics (`is_recurring` approval path). | Current |
| `docs/components/field_tracking.md` | Component note for Provider/Program/Event tracked-field tuples (`field_history` baselines). | Current |
| `docs/components/llm_http.md` | Component note for shared LLM SDK HTTP read-timeout constant (`LLM_CLIENT_READ_TIMEOUT_SEC`). | Current |
| `docs/components/program_search.md` | Component note for program search + card formatting (Session Z-2; slots synonym expansion). | Current |
| `docs/components/provider_name.md` | Component note for provider display-name normalization (Unicode folding + legacy suffix strips). | Current |
| `docs/components/search_log.md` | Component note for SEARCH_DIAG_VERBOSE-gated search diagnostic file logging. | Current |
| `docs/components/session.md` | Component note for in-memory session store (TTLs, onboarding hints, multi-worker caveats). | Current |
| `docs/components/timezone.md` | Component note for Lake Havasu local time helpers (`America/Phoenix`, no DST). | Current |
| `docs/components/tier1_templates.md` | Component note for Tier 1 regex+template engine (intent patterns + per-intent response variants). | Current |
| `docs/components/tier2_schema.md` | Component note for the Tier2Filters Pydantic schema (parser output / DB query input). | Current |
| `docs/components/normalizer.md` | Component note for the pre-classification text normalizer (lowercase, edge-strip, contraction expand). | Current |
| `docs/components/entity_matcher.md` | Component note for fuzzy provider-name matching (`token_set_ratio` > 75 against Program.provider_name; CANONICAL_EXTRAS alias map). | Current |
| `docs/components/local_voice_matcher.md` | Component note for curated-blurb matching (Phase 6.5-lite; whole-word keyword scoring + season/hint filters). | Current |
| `docs/components/context_builder.md` | Component note for Tier 3 catalog context assembly (provider-first; word-budget capped; entity-matched first). | Current |
| `docs/components/chat_logging.md` | Component note for unified-router `chat_logs` inserts (`log_unified_route`; non-fatal failures). | Current |
| `docs/components/contribution_store.md` | Component note for Contribution queue CRUD, URL normalization, and IP rate-limit counting helpers. | Current |
| `docs/components/database.md` | Component note for SQLAlchemy engine, SessionLocal, Base, get_db, init_db Alembic bootstrap. | Current |
| `docs/components/llm_mention_store.md` | Component note for LLM mention queue persistence (create/list/dismiss/promote; IntegrityError dedupe). | Current |
| `docs/components/models.md` | Component note for ORM schema source of truth (all mapped tables, relationships, indexes, migration pointers). | Current |
| `docs/components/programs_router.md` | Component note for `/programs` JSON + `/programs/submit` HTML router (slowapi limits, ProgramCreate wiring). | Current |
| `docs/components/schema_chat.md` | Component note for concierge/onboarding/feedback Pydantic models (`app/schemas/chat.py`). | Current |
| `docs/components/schema_contribution.md` | Component note for Contribution intake/approval/API schemas (`app/schemas/contribution.py`). | Current |
| `docs/components/schema_event.md` | Component note for EventCreate/EventRead and loose URL + phone validators (`app/schemas/event.py`). | Current |
| `docs/components/schema_llm_mention.md` | Component note for LLM mention admin JSON schemas (`app/schemas/llm_mention.py`). | Current |
| `docs/components/schema_program.md` | Component note for ProgramCreate/Read, HH:MM parsing/serialization (`app/schemas/program.py`; #30 campaign). | Current |
| `docs/components/confabulation_query_gen.md` | Component note for eval probe generation from live Provider/Program rows and fixed template sets. | Current |
| `docs/components/confabulation_invoker.md` | Component note for in-process and HTTP invocation strategies plus normalized invocation result shape. | Current |
| `docs/components/confabulation_evidence.md` | Component note for harness-only tier2_formatter monkeypatch capture seam. | Current |
| `docs/components/confabulation_detector.md` | Component note for Layer 1 advisory + Layer 2/3 gating confabulation detection logic. | Current |
| `docs/components/confabulation_report.md` | Component note for JSONL/CSV/Markdown report writers and inclusion-policy summary logic. | Current |
| `docs/components/extraction.md` | Component note for OpenAI-driven event-detail extraction with regex fallback (LLM-or-fallback two-path; embedding + tag generation). | Current |
| `docs/components/slots.md` | Component note for structured search slot extraction (`date_range`, `activity_family`, `audience`, `location_hint`) + `QUERY_SYNONYMS` expansion. | Current |
| `docs/components/intent.md` | Component note for deterministic template-layer intent detection (12 labels + `detect_intent` cascade; distinct from `app/chat/intent_classifier.py`). | Current |
| `docs/components/search.md` | Component note for the core event-search pipeline (semantic + keyword retrieval; slot-driven strategy; specific-noun threshold raise; outcome flags). | Current |
| `docs/components/admin_contributions_route.md` | Component note for the admin-gated JSON contribution-review API at `app/api/routes/admin_contributions.py` (paired with the HTML surface at `admin_contributions_html.md`). | Current |
| `docs/components/admin_mentions_route.md` | Component note for the admin-gated JSON LLM-mention review API at `app/api/routes/admin_mentions.py` (paired with the HTML surface at `admin_mentions_html.md`). | Current |
| `docs/components/bootstrap_env.md` | Component note for the `.env` loader at `app/bootstrap_env.py` (`ensure_dotenv_loaded`; idempotent; doesn't clobber platform-injected env). | Current |
| `docs/components/chat_route.md` | Component note for the `POST /api/chat` concierge JSON API at `app/api/routes/chat.py` (request/response shape, slowapi rate limit, dispatch to unified router). | Current |
| `docs/components/contribute_route.md` | Component note for the public contribution intake at `app/api/routes/contribute.py` (HTML form; custom DB-tracked IP-hash limiter; ContributionCreate validation). | Current |
| `docs/components/main.md` | Component note for the FastAPI app entry point at `app/main.py` (mounts, exception handlers, three template-rendered pages, router includes, /health). | Current |

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
| `docs/maintainability/project_manager_organization_brief.md` | PM onboarding: zero-context summary, org/scaling plan (phases A–D), anti-patterns. | Current |
| `docs/maintainability/railway_layout.md` | Railway service layout: process types, env var matrix, DB URL resolution, deploy flow. | Current |
| `docs/maintainability/http_api.md` | HTTP API sketch: mount layout, public/admin routes by group, auth posture, rate limits. | Current |
| `docs/maintainability/end_to_end_creation.md` | End-to-end paths producing catalog rows (Provider / Program / Event); Contribution + LlmMentionedEntity queues. | Current |
| `docs/maintainability/schema_time_harmonization_decision.md` | Decision doc for harmonizing `Program.schedule_*_time` (String) and `Event.start_time` (Time). Recommends phased migration (Option B); campaign sketched. | Current |
| `docs/maintainability/static_html_extraction_decision.md` | Decision doc for extracting monolithic `app/static/index.html` into split static assets; recommends vanilla Option A. | Current |
| `docs/maintainability/intent_module_disposition_decision.md` | Decision doc surveying the dead-code surface in `app/core/intent.py` (Slice 67b finding); proposes four disposition options. | Current |

**Convention.** Session transcripts, ad-hoc captures, and slice-complete writeups are removed from the working tree once their value is captured in canonical docs (`BACKLOG`, `STATE`, decision retrospectives) or git history. Live-session captures (HALT transcripts, sanity-check outputs) belong in **`relay/`** (gitignored) per **`relay/README.md`**, not `docs/`. Older phase and tier work — Tier 2 / Tier 3 grounding specs and inline reports, voice-audit samples, Railway migration and database diagnostics, dated production smoke-test and verification writeups, the legacy router deletion ship, pre-launch scope revisions, H2 slim handoff files, and similar — followed this pattern: filed as individual Markdown files in `docs/` or `docs/maintainability/`, then removed from the working tree once they were no longer actively-maintained reference material. **git history** retains their content; search `git log` / `git log --all -- <path>` to recover.

## 5. What is not yet documented

- There is **no dedicated design doc** for a **future provider ingestion lane** (the followup plan lists options; the cleanup retrospective explains removed lanes — no forward-looking provider pipeline spec in-tree as a standalone file).
- **Automated chat regression / versioned query battery** beyond confabulation tooling is **not described as a shipped subsystem** in its own “how to run in CI” doc (the followup plan notes the gap).
