# Hava Concierge — Architecture handoff (repo root)

**Audience:** Engineers and AI sessions changing routing, retrieval, data shape, or ops.  
**Companion doc:** **`docs/persona-brief.md`** — canonical **persona, voice, blocklist, and delivery patterns** for Hava. This file does not duplicate that prose; it anchors **architecture, tiers, and “where to look next.”**

**Product name:** Hava — *the AI local of Lake Havasu.*

---

## §1 Product overview

Lake Havasu City concierge: one chat composer (`app/static/index.html`) talks to **`POST /api/chat`** (`app/api/routes/chat.py` → `app/chat/unified_router.py`). Answers are grounded in a Postgres (Railway) / SQLite (local) catalog of **events**, **programs**, and **providers**, plus operator review of **contributions**. As of the **2026 non–River-Scene cleanup** (`docs/maintainability/non_river_scene_cleanup.md`), production-first-party catalog growth is **River Scene import** plus **approved contributions**; legacy seed and bulk-ingest lanes were removed.

---

## §2 Where to read next

| Need | Doc |
|------|-----|
| Current ships, deploy posture, “where we are” | `docs/STATE.md` |
| Repo map, flows, doc index | `docs/maintainability/project_index.md` |
| Open work, ship log | `docs/BACKLOG.md` |
| Voice, identity, §8-style rules | `docs/persona-brief.md` |
| Router pipeline detail | `docs/components/unified_router.md` |
| Ops | `docs/runbook.md` |
| Deferred chat routing / eval plan | `docs/maintainability/chat_behavior_followup_plan.md` |
| H1/H2 maintainability decisions | `docs/maintainability/h1_router_decision.md`, `docs/maintainability/h2_consolidation_decision.md` |

---

## §3 Tiered routing (normative)

1. **Normalize** (`app/chat/normalizer.py`) then **classify** (`app/chat/intent_classifier.py`): mode (`ask` / `contribute` / `correct` / `chat`) and sub-intent heuristics.

2. **Tier 1** (`app/chat/tier1_handler.py`, `tier1_templates.py`): **deterministic** answers when the classifier supplies a **resolved catalog entity** (provider name) and a **Tier-1-shaped sub-intent** (hours, phone, location, website, cost, age, date/next occurrence, open-now, time). Reads **`Provider`** / **`Program`** / **`Event`** via SQLAlchemy; **no LLM** on the happy path.

3. **Tier 2** (`tier2_handler.py`): optional **LLM parser** (`tier2_parser.py`) → **`tier2_db_query`** over events/programs/providers → **`tier2_formatter`** (deterministic **all-event** path via `tier2_catalog_render.py`, else Anthropic formatter using `prompts/tier2_formatter.txt`).

4. **Tier 3** (`tier3_handler.py`): Anthropic Haiku with a **context block** from `context_builder.py` and system prompt `prompts/system_prompt.txt`.

5. **Optional LLM router** (`app/chat/llm_router.py`): when env **`USE_LLM_ROUTER`** is truthy, an extra Anthropic call may steer Tier 2 vs Tier 3 with structured filters (`prompts/llm_router.txt`).

**Small talk / greetings** for `mode=chat` are handled in **`unified_router._handle_chat`** (template strings), not Tier 1.

---

## §4 Data model (sketch)

- **`events`**, **`programs`**, **`providers`** — core catalog; `events.source` includes `river_scene_import` for magazine-backed rows.  
- **`contributions`** — intake queue; approval flows create or update catalog rows (`app/contrib/approval_service.py`).  
- **`chat_logs`** — unified-router turns (`app/db/chat_logging.py`).  
- **`llm_mentioned_entities`** — optional post–Tier-3 mention capture (`app/contrib/mention_scanner.py`).

Schema source of truth: **`app/db/models.py`** and Alembic migrations under **`alembic/versions/`**.

---

## §5 What’s next (living work)

Phases are **not** maintained as a table in this file. Use:

- **`docs/BACKLOG.md`** — numbered OPEN / DEFERRED items and ship log.  
- **`docs/STATE.md`** — last close-out narrative and verification notes.  
- **`docs/maintainability/chat_behavior_followup_plan.md`** — deferred chat eval + provider-routing followups.

---

## §6 Locked / recorded decisions (pointers)

- **Unified concierge only** — legacy `POST /chat` removed; see `docs/maintainability/h1_router_decision.md`.  
- **LLM call consolidation (H2)** — `app/core/llm_messages.py`; see `docs/maintainability/h2_consolidation_decision.md`.  
- **River Scene event URLs / dedupe / render** — `docs/maintainability/river_scene_event_output_decision.md`.  
- **RS-only catalog cleanup** — `docs/maintainability/non_river_scene_cleanup.md`.

---

## §8 Voice specification (cross-reference)

**Canonical normative text:** **`docs/persona-brief.md`** (identity, regional language, delivery, blocklist §8.1, response scaffolding §8.2, §6.7 curated vs bulk voice, fallback examples, etc.).

**Prompts** (`prompts/system_prompt.txt`, `prompts/tier2_formatter.txt`, `prompts/voice_audit.txt`, …) must stay aligned with the persona brief.

**Legacy “§8” mapping** (for audits and tests that cite handoff §8 by habit):

| Legacy §8 topic | Where it lives now |
|-----------------|-------------------|
| §8.1 Identity / blocklist | `docs/persona-brief.md` §2, §8.1 |
| §8.2 Hard rules (no filler, declarative endings) | `docs/persona-brief.md` §4.3, §3.9 carve-outs |
| §8.3–8.6 Patterns (rec, negative, not-in-catalog, etc.) | `docs/persona-brief.md` §6–§8 |
| §8.7 Out-of-scope template | `docs/persona-brief.md` §5.1 vs out-of-scope; **`unified_router`** treats `OUT_OF_SCOPE` as a carve-out — see `docs/known-issues.md` if spec/code appear to disagree |
| §8.8 / §8.9 Intake / correction | `docs/persona-brief.md` §5.2; contribute/correct modes in `unified_router` |

---

## §9 Session discipline

**`docs/WORKING_AGREEMENT.md`** — halt-and-report, UTF-8 commit messages, component-doc currency with code changes.

---

*File introduced 2026-05 as the in-repo architecture spine; older monolithic handoff prose, if any, lives in **git history** alongside removed `docs/project-handoff.md`.*
