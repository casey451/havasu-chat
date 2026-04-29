# Havasu-chat

An AI-powered local concierge app for Lake Havasu City. Users ask questions in natural language; the system answers from a community-driven catalog of events, programs, and providers.

## What it is

Chat-first interface backed by a tiered routing system. The frontend is a single static HTML page with a chat composer. The backend is FastAPI. Data lives in SQLite locally and Postgres in production (Railway).

## Architecture

### Tiered routing

User queries route through one of three tiers based on what they're asking:

**Tier 1** — Templates. Hardcoded responses for common patterns (greetings, basic FAQs). Fast, deterministic, no LLM.

**Tier 2** — Structured retrieval. The user's query is parsed into structured filters (dates, categories, entity names), the catalog is queried via SQLAlchemy, and matching rows are rendered into a response. As of `d279165`, Tier 2 event listings are rendered deterministically in Python; mixed-type or non-event responses still use an LLM formatter.

**Tier 3** — LLM synthesis. Free-form chat for queries that don't fit Tier 1 templates or have no Tier 2 matches. Uses Anthropic's API.

### Data model

Three primary entity types:

- **Events** — Things happening on a date or date range. Have title, date, optional end_date for multi-day, start_time/end_time, location_name, description, event_url, tags. Status field gates visibility (`live` / pending / etc.).
- **Programs** — Ongoing activities (classes, leagues, recurring events). Have provider, category, schedule, age range, cost.
- **Providers** — Businesses, organizations, venues. Have category, address, phone, hours.

Catalog data is community-driven via contributions, corrections, and mentions. Some events are imported from RiverScene Magazine's calendar (source: `river_scene_import`); others are admin-entered.

### Chat pipeline

A query enters via `POST /api/chat`, hits `app/chat/unified_router.py` which selects a tier, then dispatches to the appropriate handler (`tier1_handler`, `tier2_handler`, or Tier 3 path). Tier 2's path is:

1. `tier2_parser` extracts structured filters from the query
2. `tier2_db_query._query_events` (or analogous functions for programs/providers) returns matching rows
3. `tier2_formatter.format` dispatches: empty rows → fixed empty-result string; all-event rows → `tier2_catalog_render.render_tier2_events` (deterministic Python); mixed/non-event rows → LLM formatter using `prompts/tier2_formatter.txt`
4. Response returned via `ConciergeChatResponse` schema with `tier_used` field

### Frontend

Single HTML file at `app/static/index.html`. Vanilla JavaScript, no build step. Chat bubbles rendered via `addRow` (plain text) and a success-handler path (`setBubbleContentFromAssistant`) that parses `[label](url)` markdown link syntax into clickable anchors. Calendar overlay is a separate UI accessible via the chat.

## Stack

- Python 3.11+, FastAPI, SQLAlchemy, Alembic
- SQLite (local dev), Postgres (Railway production)
- Anthropic API (Claude) for LLM-backed paths (Tier 3, parser, non-event Tier 2 formatter)
- Frontend: vanilla JS, no framework
- Tests: pytest

## Running locally

`uvicorn app.main:app --reload` starts the server. Open the chat at `http://localhost:8000/`. Tests via `python -m pytest -q`.

Production deploys via Railway; pushes to `main` trigger a deploy. `/health` endpoint reports basic status.

## Key files and their responsibilities

- `app/main.py` — FastAPI app entry
- `app/api/routes/chat.py` — `/api/chat` endpoint
- `app/chat/unified_router.py` — tier selection
- `app/chat/tier2_handler.py` — Tier 2 orchestration
- `app/chat/tier2_parser.py` — natural language → structured filters
- `app/chat/tier2_db_query.py` — catalog queries
- `app/chat/tier2_formatter.py` — response formatting (dispatches to deterministic renderer or LLM path)
- `app/chat/tier2_catalog_render.py` — deterministic Python rendering for all-event responses
- `app/db/models.py` — SQLAlchemy models
- `app/static/index.html` — frontend (chat UI, calendar)
- `prompts/tier2_formatter.txt` — LLM formatter system prompt (still active for mixed/non-event Tier 2 responses)

## Where to find more

- `docs/STATE.md` — current production state, deployed commit, recently shipped work, queued work
- `docs/WORKING_AGREEMENT.md` — session discipline for Claude/Cursor/Casey collaboration
- `docs/BACKLOG.md` — open and recently-closed backlog items with attribution to commits
