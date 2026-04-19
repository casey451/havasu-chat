# Havasu Chat — Project Handoff Document

> **Track B / concierge spec:** Repo-root **`HAVASU_CHAT_MASTER.md`** (3-tier program Q&A, seed YAML) and **`HAVASU_CHAT_CONCIERGE_HANDOFF.md`** (build plan, Phase 1+). This file stays focused on the **shipping events-search app** (Track A).

> **Purpose:** Single source of truth for starting a fresh Cursor or Claude Code session **for Track A**. Do not summarize or skip sections. Every detail here was chosen deliberately.

---

## 1. Project Overview

### What it is
Havasu Chat is a conversational events assistant for Lake Havasu City, Arizona. Users type natural-language queries ("boat races this weekend," "something for my kids Saturday") and get back a curated list of local events. Users can also submit new events through the chat. It is aimed at tourists and locals who want to discover what's happening in the area without navigating a clunky events website.

### Who it's for
- **End users:** Tourists and Lake Havasu City residents on mobile browsers.
- **Event organizers:** Local hosts who want a dead-simple way to post an event.
- **Admin:** Casey (the owner), who reviews submitted events before they go live.

### Live URL
`https://web-production-bbe17.up.railway.app`

### Repository
`https://github.com/casey451/havasu-chat` — main branch, Railway auto-deploys on every push.

### Tech stack
| Layer | Technology |
|---|---|
| Web framework | FastAPI (Python) |
| Database | SQLite locally; PostgreSQL on Railway via `DATABASE_URL` |
| ORM + migrations | SQLAlchemy + Alembic |
| AI — embeddings | OpenAI `text-embedding-3-small` (queries in `search.py`, events in `extraction.py`) |
| AI — extraction | OpenAI `gpt-4.1-mini` via `client.responses.create` |
| Auth | `itsdangerous` signed cookies for the admin panel |
| Rate limiting | `slowapi` |
| Deployment | Railway (Nixpacks), auto-deploy from `main` |
| Frontend | Vanilla HTML/CSS/JS — single file `app/static/index.html` |

### How to run locally
```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables (copy .env.example or create .env)
# Minimum needed:
OPENAI_API_KEY=sk-...
ADMIN_PASSWORD=yourpassword

# 4. Run (auto-seeds DB on first run if RAILWAY_ENVIRONMENT is set;
#    locally you may need to trigger seed manually or run tests first)
uvicorn app.main:app --reload --port 8000
```

### How it deploys
Push any commit to `main` on GitHub → Railway detects it via webhook → Nixpacks builds the container → `uvicorn app.main:app --host 0.0.0.0 --port $PORT` starts. Deploy takes 2–5 minutes. The DB is auto-seeded on first boot when `RAILWAY_ENVIRONMENT` is set.

---

## 2. Current State

### Features complete and working
- **Conversational search** — users type natural-language queries; the app extracts date range, activity family, audience, and location hints from the message, then runs a combined semantic + keyword search.
- **Intent detection** — correctly routes GREETING, SEARCH_EVENTS, LISTING_INTENT, ADD_EVENT, REFINEMENT, SOFT_CANCEL, HARD_RESET, UNCLEAR, SERVICE_REQUEST, DEAL_SEARCH, OUT_OF_SCOPE (including category `commercial_services` for rentals/venue-shopping phrasing).
- **Slot extraction** — date ranges (today, tonight, tomorrow, this weekend, next Friday, next week, etc.), activity families, audience (kids/family/adults), location hints.
- **Synonym expansion** — `QUERY_SYNONYMS` in `slots.py`: e.g. "boat race" expands for embeddings; calendar hooks include `fireworks` → July 4 / Independence Day phrases.
- **Semantic search** — OpenAI embeddings for events; cosine similarity scored; fallback to deterministic embedding if API unavailable.
- **Strict literal matching (short queries)** — two-word and other short noun-focused queries require literal/synonym alignment and word-boundary matching so generic events do not flood results; multi-word synonym phrases (e.g. "poker run" for "boat race") satisfy literals when raw tokens differ (boats/racing vs boat/race).
- **Specific-noun query handling** — queries naming a specific thing use a raised embedding threshold and literal/synonym bonuses; honest no-match when nothing qualifies.
- **Honest no-match** — when no events match a specific noun query, the app says so honestly instead of showing loosely related events.
- **Commercial / out-of-scope routing** — rentals, venue shopping, and similar service queries can return templated OUT_OF_SCOPE replies instead of dumping generic events.
- **Event submission via chat** — multi-turn flow collecting title, date, time, location, description, URL, contact. OpenAI extracts structure from free text. Duplicate detection via embedding cosine similarity.
- **Event permalinks & sharing** — `GET /events/{id}` renders a single event with Open Graph meta tags for link previews; share button with clipboard copy and fallback for older browsers.
- **Session state hardening** — stale `date_range` cleared for broad follow-ups; message-level date handling and week-after advancement (Session N).
- **Defensive UI self-heal** — welcome chips re-checked after a short delay if the first render missed them (Session O).
- **Admin panel** — password-protected dashboard at `/admin`. Tabs: Pending review / Live events. Approve/reject/delete actions. Session cookie with `itsdangerous` signing.
- **Event status flow** — submitted events go to `pending_review` with a **72-hour** review deadline (`admin_review_by` in code). Expired pending events are auto-deleted by an hourly background task.
- **Re-embed endpoint** — `POST /admin/reembed-all` regenerates OpenAI embeddings for all events. Protected by admin cookie.
- **Re-seed endpoint** — `POST /admin/reseed` wipes seed rows and re-inserts. Protected by admin cookie.
- **AI tags on submission** — new submitted events get AI-generated tags in `extract_event()` via `generate_event_tags()`, using the same `client.responses.create` pattern as extraction.
- **Retag endpoint** — `POST /admin/retag-all` backfills/regenerates tags for all events. Protected by admin cookie.
- **Diagnostic logging** — `app/core/search_log.py` writes per-query logs (intent, slots, DB params, candidate scores) to `search_debug.log`. Stdout diagnostic prints also appear in Railway logs.
- **Rate limiting** — 10 requests/minute on `/events`, applied via slowapi.
- **Welcome UI** — first-time users see a welcome message and three example chips (weekend events, kids activities, add an event). Chips disappear after first send.
- **120-query regression battery** — documented expectations in `docs/query-test-battery.md`; production runner `scripts/run_query_battery.py` (see Section 9).
- **29 real seed events** — Lake Havasu–style events (concerts, boat races, markets, parks, fitness, named recurring hooks, etc.) with ISO dates **May through July 2026** and real OpenAI embeddings via the re-embed endpoint.

### Known bugs and limitations
- **`search_debug.log` is local only** — the log file written by `search_log.py` lives inside the Railway container's filesystem. You cannot read it from the local machine. Use stdout prints (already added to `search_events`) to view scores in Railway's deployment logs instead.
- **Seed event dates are fixed** — seed data uses hardcoded dates (roughly May–July 2026). When those dates pass, most events will fall out of search results (future-only filter). Plan periodic refresh (see roadmap).
- **Thin category coverage** — with ~29 seeded events, some categories are sparse; scaling the catalog is a roadmap item.
- **No pagination** — search returns up to 25 events. No page 2.
- **Venue-vs-events precedence (intentional)** — queries that name a venue that also has seeded *events* may return those calendar events rather than a venue-only redirect. The 120-query battery rows 22, 44, 46, and 49 reflect this product choice; do not treat them as accidental bugs without an explicit decision to change precedence.
- **No onboarding for returning users** — the welcome chips only show on first visit (session-based, not account-based). Roadmap: Session I (localStorage).
- **OpenAI query embedding fallback** — if the OpenAI API call for query embedding fails, `embedding_from_openai` is False. The threshold filter is then based more heavily on literal/synonym bonuses. General queries get weaker embedding gating in fallback mode.

### Test count and status
**Full suite:** `python -m pytest tests -q` — **~172 tests** collected (includes newer `app/chat` tests: normalizer, entity matcher, tier1 templates). A legacy Phase 3 search test may occasionally fail (`test_weekend_search_asks_activity_then_returns_grouped_results`); fix before treating CI as green.

**Historical note (Session AD era):** This section previously listed **91 tests, all passing.** The repo has since gained programs, permalinks, AA-1, and tier-build tests.

**Core handoff-era test files:**
- `tests/test_phase1.py` — basic event CRUD
- `tests/test_phase2.py` — slot extraction
- `tests/test_phase3.py` — intent detection
- `tests/test_phase4.py` — deduplication
- `tests/test_phase5.py` — event quality / validation
- `tests/test_phase6.py` — search basics
- `tests/test_phase8.py` — admin panel (login, approve, reject, delete)
- `tests/test_phase8_5.py` — rate limiting, session, onboarding, date carryover
- `tests/test_search_relevance.py` — semantic search, literal match, honest no-match
- `tests/test_permalinks.py` — permalink route and OG behavior

Run with: `py -3 -m pytest --tb=short -q`

---

## 3. File Map

```
havasu-chat/
├── app/
│   ├── main.py                  ★ FastAPI app entry point. Lifespan (DB init, seed, cleanup loop).
│   │                              Mounts chat and admin routers. /health, /events, GET /events/{id}
│   │                              (permalink + OG meta for previews).
│   ├── bootstrap_env.py           Loads .env without overriding Railway env vars.
│   ├── admin/
│   │   ├── auth.py                Admin password check + itsdangerous cookie signing.
│   │   └── router.py              Admin panel endpoints: login, dashboard, approve/reject/delete,
│   │                              reseed, reembed-all, retag-all. Full HTML generated server-side.
│   ├── chat/
│   │   ├── router.py            ★ Main chat endpoint (Track A). Intent detection → slot extraction →
│   │   │                          search execution → response formatting. _chat_inner() and
│   │   │                          _run_search_core() are the key functions.
│   │   ├── normalizer.py        Track B: query normalization for tiered program Q&A (HAVASU_CHAT_MASTER).
│   │   ├── entity_matcher.py    Track B: fuzzy provider match (`rapidfuzz`).
│   │   └── tier1_templates.py Track B: Tier 1 regex patterns + `render()` (not wired to POST /chat yet).
│   ├── core/
│   │   ├── conversation_copy.py   All user-facing strings (greeting, no-match, listing nudges).
│   │   ├── dedupe.py              Duplicate event detection via cosine similarity.
│   │   ├── event_quality.py       Validation helpers for event submission flow.
│   │   ├── extraction.py          OpenAI event extraction from free text + embedding generation.
│   │   │                          Uses gpt-4.1-mini for extraction/tags, text-embedding-3-small for embeddings.
│   │   ├── intent.py              detect_intent() — classifies user message into intent labels.
│   │   ├── rate_limit.py          slowapi limiter config.
│   │   ├── search.py            ★ Core search logic. search_events(), scoring, threshold,
│   │   │                          literal-match bonus, honest_no_match, ACTIVITY_TYPES map.
│   │   │                          MOST IMPORTANT FILE for search quality work.
│   │   ├── search_log.py          Diagnostic logging — writes to search_debug.log + stdout.
│   │   ├── session.py             In-memory session state management for multi-turn chat.
│   │   ├── slots.py             ★ Slot extraction: date ranges, activity families, audience,
│   │   │                          location hints. Also QUERY_SYNONYMS and expand_query_synonyms().
│   │   └── venues.py              Venue redirect helpers and venue copy for no-match flows.
│   ├── db/
│   │   ├── chat_logging.py        Logs each chat turn to the chat_logs table.
│   │   ├── database.py            SQLAlchemy engine, Base, SessionLocal, get_db, init_db.
│   │   ├── models.py              Event and ChatLog ORM models.
│   │   └── seed.py                29 real Lake Havasu City events (May–July 2026). Idempotent (skips existing seeds).
│   ├── schemas/
│   │   ├── chat.py                ChatRequest / ChatResponse Pydantic schemas.
│   │   └── event.py               EventCreate / EventRead Pydantic schemas with validators.
│   └── static/
│       └── index.html             Entire frontend — chat UI, welcome chips, event rendering.
│
├── alembic/
│   ├── env.py                     Alembic migration environment.
│   └── versions/
│       ├── 54d37d2c4d32_initial_events_table.py    Initial schema.
│       └── b2f8c1a9d0e1_add_chat_logs_table.py     Adds chat_logs table.
│
├── tests/                         91 tests across 10 files (see Section 2).
├── scripts/
│   ├── diagnose_search.py         Fires 25 test queries at the live app, saves output to
│   │                              diagnose_output.txt. Run with: py -3 scripts/diagnose_search.py
│   ├── verify_queries.py          Quick 6-query spot-check against the live app.
│   ├── run_query_battery.py       120-query production battery (HTTP). Writes JSON summary to stdout;
│   │                              save as scripts/battery_results.json for regression compares.
│   ├── battery_results.json       Canonical baseline capture (Session T: **96.67%** pass rate); see scripts/README.md.
│   └── (optional) Save ad-hoc battery JSON/log captures locally; do not commit generated session artifacts.
├── docs/
│   ├── project-handoff.md         This file (Track A deep-dive).
│   ├── HAVASU_CHAT_SEED_INSTRUCTIONS.md  Program/event seed source for `seed_from_havasu_instructions.py`.
│   └── query-test-battery.md      120-query expected labels + notes; keep in sync with runner.
├── HAVASU_CHAT_MASTER.md          (repo root) Full 3-tier spec + seed YAML (Track B + concierge).
├── Procfile                       Railway start command.
├── nixpacks.toml                  Railway build config (pip install + uvicorn start).
├── requirements.txt               Dependencies (pinned versions; see Session C).
├── alembic.ini                    Alembic config.
└── .env                           Local secrets (not committed). See Section 8.
```

**Most important files for search quality work (in priority order):**
1. `app/core/search.py` — all scoring, thresholds, bonuses, filtering
2. `app/chat/router.py` — synonym expansion wiring, query_message enrichment
3. `app/core/slots.py` — QUERY_SYNONYMS dictionary, slot extraction
4. `app/db/seed.py` — event content quality directly affects search results
5. `app/core/extraction.py` — embedding generation for new/updated events

---

## 4. Completed Work (historical steps + Sessions H–T)

### Step 1 — Diagnostic logging (`cf700e2`)
**What:** Added `app/core/search_log.py` with `log_query()`, `log_db_params()`, `log_candidates()`. Wired into `app/chat/router.py` (`_run_search_core`) and `app/core/search.py` (`search_events`).
**Why:** Needed to understand why "boat races" was returning unrelated events. Logging captures: raw query, intent, extracted slots, DB params, and every candidate event's score.
**Files changed:** `app/core/search_log.py` (new), `app/chat/router.py`, `app/core/search.py`.

### Step 2 — `tonight`, synonyms, honest no-match (`0b6e956`)
**What:**
- Added `"tonight"` to `extract_date_range` in `slots.py` → maps to today's date.
- Added `QUERY_SYNONYMS` dict and `expand_query_synonyms()` function in `slots.py`.
- Added `_query_has_specific_noun()` helper in `search.py` and updated `honest_no_match` logic to trigger for specific noun phrases (boat race, concert, farmers market, etc.).
**Files changed:** `app/core/slots.py`, `app/core/search.py`.

### Re-embed endpoint (`0fd5bca` → `5176a5b` → `a694e13` → `6fcbdba`)
**What:** Added `POST /admin/reembed-all` in `app/admin/router.py`. Temporarily changed to GET and removed auth to allow one-time browser trigger. After re-embedding 25 events with real OpenAI vectors, reverted to POST with full auth.
**Why:** All 25 seed events had fake deterministic embeddings because `OPENAI_API_KEY` wasn't set during initial seed. Real semantic search requires real embeddings.
**Files changed:** `app/admin/router.py`.

### Step 2a — Wire synonym expansion into search (`2467167`)
**What:** In `app/chat/router.py`, `_run_search_core()`, after building `query_message`, calls `expand_query_synonyms(message)` and appends the synonyms to `query_message`. This enriches the embedding query — "boat race" becomes "boat race regatta boat racing poker run" — so the OpenAI embedding of the query is semantically closer to the Desert Storm Poker Run event embedding.

**Why appended to `query_message` instead of `keywords`:** Keywords use AND logic in the SQL filter — adding synonyms as keywords would require ALL synonym terms to appear in each event, which excluded valid events (e.g., "Morning Kids Soccer Kickabout" doesn't contain "children" from the kids-activities synonym expansion). Appending to `query_message` is purely additive and affects only the embedding vector, never filters.
**Files changed:** `app/chat/router.py`.

### Step 2b — Tighten threshold + literal-match bonus (`a695aa8`, `f6b7d9a`, `eb8a690`)
**What:** Three sub-changes across three commits:
1. Added `_SPECIFIC_PHRASES` module-level tuple and `_matching_specific_phrases()` helper in `search.py`. Computed `is_specific_query` and `effective_threshold` (0.55 for specific noun queries, 0.35 otherwise). Applied a +0.5 score bonus to any event whose title or description contains a bonus term. Fixed the threshold filter to work even when `embedding_from_openai` is False.
2. Extracted `SPECIFIC_QUERY_EMBEDDING_THRESHOLD = 0.55` as a named constant.
3. Added stdout `print()` diagnostic in `search_events` to expose scores in Railway logs, and fixed the threshold logic to handle the OpenAI fallback case: when `embedding_from_openai=False` and `is_specific_query=True`, keep only events with score > 0.45 (i.e., only events that received the +0.5 literal-match bonus, since raw fake cosines are near zero).

**The key bug fixed in commit `eb8a690`:** The original code gated the entire threshold check on `if strict_relevance and embedding_from_openai`. When Railway's OpenAI query-embedding call failed transiently, `embedding_from_openai=False`, the gate was never entered, all 25 events passed through, and Desert Storm ranked #4 by meaningless cosine values. The fix splits into two code paths: real embeddings use the 0.55 threshold, fallback embeddings use the bonus-score cutoff.
**Files changed:** `app/core/search.py`.

### Session A — Fix query embedding model mismatch (`626e0ae`)
**What:** `app/core/search.py` was calling the OpenAI embeddings API with a different model than the one used to generate event embeddings in `extraction.py`. Both are now explicitly set to `text-embedding-3-small`.
**Why:** Cosine similarity scores between query and event vectors are only meaningful when both vectors are produced by the same model. The mismatch caused unpredictable ranking.
**Files changed:** `app/core/search.py`.

### Session B — Update seed event dates to May–July 2026 (`41d1c71`)
**What:** Updated all 25 seed event dates in `app/db/seed.py` from the original April–May 2026 window to a May–July 2026 rolling window.
**Why:** The future-only filter in search drops events whose dates have passed. Without this update, the app would return empty results for nearly all queries.
**Files changed:** `app/db/seed.py`.

### Session C — Pin dependency versions in `requirements.txt` (`f12d196`)
**What:** Added explicit version pins to every package in `requirements.txt` so Railway builds are reproducible.
**Why:** Unpinned dependencies can silently break on Railway when a new package version is released. Pins lock the build to the exact environment that was tested.
**Files changed:** `requirements.txt`.

### Verified behavior (latest production checks)
```
boat race                   → COUNT 1   → Wednesday, May 20, 2:00 PM (date moved out of April)
boat races this weekend     → COUNT 0   → Honest no-match
live music                  → COUNT 4   → Fun Activities section
concert tonight             → COUNT 0   → Honest no-match
kids activities             → COUNT 7   → Fun Activities section
things to do this weekend   → COUNT 0   → Honest no-match (current data window)
```

### Session G — Admin UX polish (`0aa9554`)
**What:** Admin dashboard cards show AI tag pills, embedding status (real vs deterministic heuristic), preview links for **live** events, and list sorting controls. Analytics page at `/admin/analytics` (counts, top queries, zero-result pairs, funnel).
**Why:** Casey can triage pending events and sanity-check vectors/tags without leaving the panel.
**Files changed:** Primarily `app/admin/router.py`; tests in `tests/test_phase8.py`.
**Reference:** `docs/session-g-summary-for-claude.md`.

### Session H — Event shareability (`d2b2107`)
**What:** Public permalink `GET /events/{id}` for a single event; Open Graph `<meta>` tags for rich link previews; clipboard share button on event cards with non-clipboard fallback for older browsers.
**Why:** Users can share one event as a stable URL; previews look correct in iMessage, Slack, and social apps.
**Files changed:** `app/main.py`, `app/static/index.html`, `tests/test_permalinks.py`.

### Session N — Session state / date carryover (`2c0e924`)
**What:** Fixed stale `date_range` persisting across unrelated follow-up queries; message-level date phrase detection; clearing stale dates for broad queries; +7 day advancement for “week after” style follow-ups.
**Why:** A narrowed date from an earlier turn was incorrectly filtering later broad questions (“anything fun?”).
**Files changed:** `app/chat/router.py`, `tests/test_phase8_5.py`.

### Session O — Welcome chip self-heal (`e98ef94`)
**What:** After 150ms, a deferred check re-renders welcome suggestion chips if the first paint missed them.
**Why:** Race conditions in the static frontend occasionally left first-time users without chips.
**Files changed:** `app/static/index.html`.

### Session P — Week/month date phrases (pending)
**Status:** Not committed as of Session U. `extract_date_range` already handles phrases such as `next week` in isolation; dedicated `this week`, `this month`, and `next month` ranges (as described for Session P) are not fully implemented under that session banner—treat as **planned** work.
**Planned what:** Extend `extract_date_range` to parse `this week`, `next week`, `this month`, `next month` consistently for calendar-style questions.
**Planned files:** `app/core/slots.py`, `tests/test_phase2.py`.
**Roadmap:** See Section 5.

### Session Q — Short-query literals + OUT_OF_SCOPE expansion (`a2a2e99`)
**What:** Require literal match for short noun-focused queries; wire synonym terms into scoring; expand OUT_OF_SCOPE triggers for weather, lodging, transportation, dining (alongside existing intent work).
**Why:** Reduce irrelevant event lists for specific phrasing and route non-event questions out of search.
**Files changed:** `app/core/search.py`, `app/core/intent.py`, `tests/test_search_relevance.py`, `tests/test_phase3.py`.
**Battery:** ~70.0% → ~80.8% pass rate on the 120-query production battery.

### Session R — Partial literal wiring (`0594731`, superseded)
**What:** Synonym scoring and word-boundary matching improvements landed only on one branch inside `search.py`.
**Why:** Incomplete—fallback path did not get the same behavior.
**Files changed:** `app/core/search.py`.
**Note:** Post-deploy battery was flat vs Session Q because the fix did not cover the fallback branch.

### Session S — Literal-survival on both branches (`9fd1027`)
**What:** Completed Session R by applying literal-survival to **both** embedding and fallback branches; require all tokens for multi-word short queries (with honest no-match when literals fail).
**Why:** Consistent relevance whether or not OpenAI query embeddings succeed.
**Files changed:** `app/core/search.py`, `tests/test_search_relevance.py`.
**Battery:** ~80.8% → ~89.2%.

### Session T — Final bug sweep (`27d9d67`, `ddce8a4`)
**What:** Named recurring events and discovery (e.g. sunset market, First Friday date handling, fireworks ↔ July 4 hooks in `QUERY_SYNONYMS`); `flags_query` vs embedding text to stop multi-word synonym expansion from breaking Session S short-query rules; `commercial_services` OUT_OF_SCOPE category and copy; explicit ADD_EVENT phrasing; seed additions aligned with tests. Second commit fixed a regression where stricter literals rejected “boat race” when copy used “boats”/“boating”/“racing” by allowing **multi-word synonym phrases** (e.g. “poker run”) to satisfy literal match for multi-word synonym keys.
**Why:** Close quality gaps on production battery without abandoning venue precedence or loosening relevance to arbitrary fuzzy matches.
**Files changed:** `app/core/search.py`, `app/core/intent.py`, `app/core/conversation_copy.py`, `app/chat/router.py`, `app/core/slots.py`, `app/db/seed.py`, `tests/test_search_relevance.py`, `tests/test_phase6.py`, `tests/test_phase8_5.py`, `docs/query-test-battery.md`, `scripts/run_query_battery.py`.
**Battery:** ~89.2% → ~96.67%.

### Query Test Battery (permanent quality gate)
- **Spec:** `docs/query-test-battery.md` — expected classification per query (EVENTS, NO_MATCH, OUT_OF_SCOPE variants, etc.).
- **Runner:** `scripts/run_query_battery.py` — hits production `POST /chat`; save stdout JSON to `scripts/battery_results.json` for before/after compares.
- **When to run:** After any change to search, intent, slots, venues, or seed content that affects user-facing matching (see Section 9).

---

## 5. Remaining Roadmap

### Session I — Returning-user onboarding
**What:** Persist light state (e.g. localStorage) so repeat visitors get a softer prompt instead of a blank composer.
**Files:** `app/static/index.html`.

### Session P — Week/month date parsing (if not done earlier)
**What:** Finish `extract_date_range` coverage for `this week`, `this month`, `next month` (and align with `next week` behavior).
**Files:** `app/core/slots.py`, `tests/test_phase2.py`.

### Seed data scale-up
**What:** Grow the catalog from ~29 toward **100–1000** events so thin categories fill in; re-embed after bulk imports.
**Files:** `app/db/seed.py`, ops via `/admin/reembed-all`.

### Periodic seed date refresh
**What:** Current seed dates are anchored around **mid-2026**; after they roll past, future-only search will empty out. Re-date and reseed on a cadence (or automate a rolling window).

---

## 6. Step 3 — AI Tagging (Completed)

### What was built
When a new event is created (and when `/admin/retag-all` is called), one GPT-4.1-mini call now generates 5–10 descriptive tags and stores them in the existing `tags` JSON column. No DB migration was needed.

### Why it matters
- User-submitted events arrive with empty `tags: []` (they pass EventCreate.tags defaulting to `[]`).
- The search scoring function (`_keyword_score_and_fields` in `search.py`) already reads `event.tags` as part of scoring:
  ```python
  tags = " ".join(str(t).lower() for t in (event.tags or []))
  fields = (title, desc, tags)
  ```
- So AI-generated tags immediately improve keyword matching for submitted events with no other changes.

### Files changed

#### 1. `app/core/extraction.py` — `generate_event_tags()` function added

```python
TAGS_PROMPT = """Generate 5 to 10 short, lowercase tags describing this event.
Tags should describe: what type of event it is, who it's for, what activities are involved,
whether it's free/paid, indoor/outdoor, daytime/evening.
Return ONLY a JSON array of strings, no other text.

Event:
Title: {title}
Location: {location_name}
Description: {description}
"""

def generate_event_tags(event: dict) -> list[str]:
    """Generate 5-10 short lowercase tags for an event using OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return []
    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=TAGS_PROMPT.format(
                title=event.get("title", ""),
                description=event.get("description", ""),
                location_name=event.get("location_name", ""),
            ),
        )
        raw_text = response.output_text.strip()
        parsed = json.loads(raw_text)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    # normalize + dedupe + cap
    ...
    return []
```

#### 2. `app/core/extraction.py` — `generate_event_tags()` called in `extract_event()`
In `extract_event()`, immediately after `event["embedding"] = generate_embedding(...)`:
```python
event["tags"] = generate_event_tags(event)
```

#### 3. `app/admin/router.py` — `POST /admin/retag-all` added
Implemented using the same cookie guard / loop / commit pattern as `POST /admin/reembed-all`:

```python
@router.post("/retag-all")
def admin_retag_all(request: Request, db: Session = Depends(get_db)) -> dict[str, int]:
    """One-time ops: regenerate AI tags for every event."""
    redir = _guard(request)
    if redir:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from app.core.extraction import generate_event_tags
    updated = 0
    for event in db.query(Event).all():
        event.tags = generate_event_tags({
            "title": event.title or "",
            "description": event.description or "",
            "location_name": event.location_name or "",
            "event_url": event.event_url or "",
        })
        updated += 1
    db.commit()
    return {"updated": updated}
```

### Test and production impact
- **Tests:** `py -3 -m pytest --tb=short -q` — see Section 2 for current count (**91** as of Session AD).
- **No migration needed:** `tags` column already exists as `JSON`.
- **Production backfill:** Completed; `/admin/retag-all` updated all live rows at time of run (count matches DB size).

### Commit
`82c4f0a` — `"Session D: AI-generated tags on event submission"`

---

## 7. Key Decisions Already Made

**No manual tags for submitted events.** AI generates them automatically. The prompt is tuned to produce search-relevant descriptors, not category labels.

**Pay once per event, never per search.** Embeddings are generated once at event creation (or re-embed). Tags are generated once at event creation (or retag). Search queries use free keyword matching + one embedding call per query. No per-search LLM calls.

**One session, one change.** Each working session targets exactly one thing. Tests must pass before committing. No scope creep within a session.

**Synonyms live in `slots.py`.** The `QUERY_SYNONYMS` dict is the canonical place to add new phrase→synonym mappings. Adding entries there automatically propagates to both the query enrichment in `router.py` and the bonus-terms calculation in `search.py`.

**Specific nouns get a higher bar.** Queries naming a concrete thing (boat race, concert, parade, etc.) use a 0.55 threshold instead of 0.35, and require a literal keyword match to rank high. This prevents loosely-related events (fitness classes, markets) from flooding results for specific searches.

**No scope creep until these arcs are done:**
1. Search quality (literal matching, synonyms, battery ≥ ~95% on production runs)
2. Content freshness (seed dates + catalog scale)
3. Admin review UX (Session G — **done**)
4. Shareability (Session H — done)
5. Returning-user onboarding (Session I)

---

## 8. Environment and Secrets

### Environment variables

| Variable | Required | Where set | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes (for AI features) | Railway → Variables | OpenAI API key. Used for event extraction (GPT-4.1-mini), embeddings (`text-embedding-3-small` for queries and events). Without it, app uses fake deterministic embeddings and skips AI extraction. |
| `ADMIN_PASSWORD` | Yes | Railway → Variables | Admin panel password. No fallback — if unset, defaults to `"changeme"` (see `app/admin/auth.py`). Change it in Railway after every session where it was visible in chat. |
| `DATABASE_URL` | Yes on Railway | Railway → Variables | PostgreSQL connection string. Auto-provided by Railway when you add a Postgres plugin. Locally, SQLite is used instead. |
| `RAILWAY_ENVIRONMENT` | Auto-set by Railway | Railway | When present, triggers auto-seed on startup. Do not set locally. |
| `OPENAI_MODEL` | Optional | Railway → Variables | Overrides the GPT model used for extraction. Defaults to `"gpt-4.1-mini"`. |
| `SENTRY_DSN` | No (app runs fine without it) | Railway → Variables | Error monitoring. When set, unhandled exceptions are reported to Sentry via the FastAPI integration; performance tracing sampled at 10%. Unset → Sentry is skipped silently at startup. |

### Local `.env` file
At repo root. Not committed to git (in `.gitignore`). Format:
```
OPENAI_API_KEY=sk-...
ADMIN_PASSWORD=localpassword
```

### Important notes
- After any session where `ADMIN_PASSWORD` appeared in chat, rotate it in Railway → Variables → edit → redeploy.
- The `OPENAI_API_KEY` must be set in Railway for semantic search to work. If it's missing or expired, all search queries fall back to fake deterministic embeddings — search rankings will be meaningless.
- Railway's Postgres `DATABASE_URL` is injected automatically; don't hardcode it.

---

## 9. How to Work With This Codebase

### One session, one change rule
Every working session should target exactly one feature or fix. Write out the plan at the start, confirm it, then execute only that one change. This keeps Railway deploy cycles short and makes rollback easy if something breaks.

### Always run tests before committing
```bash
py -3 -m pytest --tb=short -q
```
All tests must pass (Session AD: **91**). If a test fails, fix it before committing. Never push a failing test.

### Always push to main
Railway auto-deploys from `main`. Push directly — no PRs needed for this solo project.
```bash
git add <files>
git commit -m "Step X: description"
git push origin main
```

### Allow 2–5 minutes for Railway to deploy
After pushing, Railway builds and restarts. The old version stays live until the new one is ready. Use `py -3 scripts/verify_queries.py` after 3–5 minutes to confirm the new behavior is live.

### How to verify a deployment is live
The verify script fires 6 test queries and prints count + first result:
```bash
py -3 scripts/verify_queries.py
```
If `boat race` returns COUNT=1 (Desert Storm), Step 2b is deployed.
If `boat race` returns COUNT=25, the old code is still running — wait longer or check Railway for a build error.

### How to trigger re-embed after bulk changes
If seed event descriptions are changed, or a new batch of events is added, re-embed all events:
1. Log into `/admin` with the admin password.
2. In the browser, use a REST client (or curl) to `POST /admin/reembed-all` with the admin session cookie. (Or temporarily add a GET version — follow the same pattern used previously: change `@router.post` to `@router.get`, remove auth, deploy, hit URL, revert, redeploy.)

### How to trigger retag backfill
Same pattern as re-embed:
1. Log into `/admin`.
2. `POST /admin/retag-all`.
3. Response `updated` count equals the number of events in the database at that time.

### Running the Query Battery
After any change to **search**, **intent**, **slots**, **venues**, or **seed** content that could affect user-facing answers, run the 120-query production battery:

```bash
py -3 scripts/run_query_battery.py
```

Save the JSON output to `scripts/battery_results.json` (overwrite the previous file) and compare pass rate and per-query deltas to the last run. **Any drop below ~95% pass rate should be investigated** before merging the next session of work, unless the change intentionally updates expectations in `docs/query-test-battery.md` and the runner together.

### Cursor LLM vs Claude Code split
| Task type | Use |
|---|---|
| UI changes, HTML/CSS edits | Cursor LLM |
| Single-file targeted edits (strings, config, prompts) | Cursor LLM |
| Small bug fixes with clear location | Cursor LLM |
| Multi-file coordinated changes | Claude Code in terminal (`claude` command) |
| New modules, DB migrations, new endpoints | Claude Code in terminal |
| Diagnostic scripts, log analysis | Claude Code in terminal |
| Anything that requires reading 4+ files to understand context | Claude Code in terminal |

### PowerShell note (Windows)
Use semicolons to chain commands, not `&&`:
```powershell
# Correct
git add app/core/search.py; git commit -m "message"; git push origin main

# Wrong (PowerShell syntax error)
git add app/core/search.py && git commit -m "message" && git push origin main
```
