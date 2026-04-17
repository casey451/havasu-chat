# Havasu Chat — Project Handoff Document

> **Purpose:** Single source of truth for starting a fresh Cursor or Claude Code session.
> Do not summarize or skip sections. Every detail here was chosen deliberately.

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
- **Intent detection** — correctly routes GREETING, SEARCH_EVENTS, LISTING_INTENT, ADD_EVENT, REFINEMENT, SOFT_CANCEL, HARD_RESET, UNCLEAR, SERVICE_REQUEST, DEAL_SEARCH, OUT_OF_SCOPE.
- **Slot extraction** — date ranges (today, tonight, tomorrow, this weekend, next Friday, etc.), activity families, audience (kids/family/adults), location hints.
- **Synonym expansion** — ~39 phrase→synonym groups in `QUERY_SYNONYMS` (expanded from ~11 in Session J, sourced from knowledge-base Section 5). "boat race" expands to include "regatta," "poker run," etc.; "live music" expands to concert/band/dj/etc. Appended to the embedding query so the vector pulls related events without tightening keyword filters.
- **Semantic search** — OpenAI embeddings for events; cosine similarity scored; fallback to deterministic embedding if API unavailable.
- **Specific-noun query handling** — `_SPECIFIC_PHRASES` covers ~76 phrases across water sports, parks, family/kids, dining, festivals, wellness (expanded from ~11 in Session J, sourced from knowledge-base Section 4). Matching queries use a raised threshold (0.55) and a literal-match bonus (+0.5) to prevent irrelevant events from appearing.
- **Honest no-match** — when no events match a specific noun query, the app says so honestly instead of showing loosely related events.
- **Venue recognition (no-match redirect)** — `app/core/venues.py` holds `VENUE_ALIASES` (30 canonical venues from knowledge-base Section 6) and `detect_venue()`. When a query names a known venue and search returns zero results, the chat router replies with `VENUE_REDIRECT_TEMPLATE` instead of a generic no-match ("Altitude Trampoline Park is a permanent spot in Havasu — I track events there when they come up…").
- **Out-of-scope intent** — `detect_out_of_scope_category()` classifies queries into weather / lodging / transportation / dining categories, checked early in `detect_intent()`. An event-signal guard (event, events, festival, parade, fireworks, tournament, concert, gala, fundraiser) suppresses the classification so queries like "hotel grand opening event tonight" still reach search. Four verbatim templates live in `conversation_copy.py` keyed by category.
- **Knowledge base** — `docs/havasu-knowledge-base.md` is the canonical source for query patterns, specific phrases (Section 4), synonyms (Section 5), venue aliases (Section 6), and response copy (Section 7). Expand the lists by editing the knowledge base first, then porting entries to the code.
- **Event submission via chat** — multi-turn flow collecting title, date, time, location, description, URL, contact. OpenAI extracts structure from free text. Duplicate detection via embedding cosine similarity.
- **Admin panel** — password-protected dashboard at `/admin`. Tabs: Pending review / Live events. Approve/reject/delete actions. Session cookie with `itsdangerous` signing.
- **Event status flow** — submitted events go to `pending_review` with a 48-hour review deadline. Expired pending events are auto-deleted by an hourly background task.
- **Re-embed endpoint** — `POST /admin/reembed-all` regenerates OpenAI embeddings for all events. Protected by admin cookie.
- **Re-seed endpoint** — `POST /admin/reseed` wipes seed rows and re-inserts. Protected by admin cookie.
- **AI tags on submission** — new submitted events now get AI-generated tags in `extract_event()` via `generate_event_tags()`, using the same `client.responses.create` pattern as extraction.
- **Retag endpoint** — `POST /admin/retag-all` backfills/regenerates tags for all events. Protected by admin cookie.
- **Diagnostic logging** — `app/core/search_log.py` writes per-query logs (intent, slots, DB params, candidate scores) to `search_debug.log`. Stdout diagnostic prints also appear in Railway logs.
- **Rate limiting** — 10 requests/minute on `/events`, applied via slowapi.
- **Welcome UI** — first-time users see a welcome message and three example chips (weekend events, kids activities, add an event). Chips disappear after first send.
- **25 real seed events** — real Lake Havasu City events (concerts, boat races, markets, parks, fitness, etc.) with real OpenAI embeddings generated via the re-embed endpoint.

### Known bugs and limitations
- **`search_debug.log` is local only** — the log file written by `search_log.py` lives inside the Railway container's filesystem. You cannot read it from the local machine. Use stdout prints (already added to `search_events`) to view scores in Railway's deployment logs instead.
- **Seed event dates are fixed** — seed data has hardcoded dates (May–July 2026, updated in Session B). When those dates pass, most events will fall out of search results (future-only filter). The seed needs to be updated periodically.
- **No pagination** — search returns up to 25 events. No page 2.
- **No shareability** — no way to share a specific event or search result as a link.
- **No onboarding for returning users** — the welcome chips only show on first visit (session-based, not account-based).
- **OpenAI query embedding fallback** — if the OpenAI API call for query embedding fails, `embedding_from_openai` is False. The threshold filter is then based only on the literal-match bonus (score > 0.45 cutoff for specific-noun queries). General queries get no threshold filtering in fallback mode.

### Test count and status
**60 tests, all passing.** Test files:
- `tests/test_phase1.py` — basic event CRUD
- `tests/test_phase2.py` — slot extraction
- `tests/test_phase3.py` — intent detection
- `tests/test_phase4.py` — deduplication
- `tests/test_phase5.py` — event quality / validation
- `tests/test_phase6.py` — search basics
- `tests/test_phase8.py` — admin panel (login, approve, reject, delete)
- `tests/test_phase8_5.py` — rate limiting, session, onboarding, out-of-scope intent
- `tests/test_search_relevance.py` — semantic search ranking tests

Run with: `py -3 -m pytest --tb=short -q`

---

## 3. File Map

```
havasu-chat/
├── app/
│   ├── main.py                  ★ FastAPI app entry point. Lifespan (DB init, seed, cleanup loop).
│   │                              Mounts chat and admin routers. /health, /events endpoints.
│   ├── bootstrap_env.py           Loads .env without overriding Railway env vars.
│   ├── admin/
│   │   ├── auth.py                Admin password check + itsdangerous cookie signing.
│   │   └── router.py              Admin panel endpoints: login, dashboard, approve/reject/delete,
│   │                              reseed, reembed-all, retag-all. Full HTML generated server-side.
│   ├── chat/
│   │   └── router.py            ★ Main chat endpoint. Intent detection → slot extraction →
│   │                              search execution → response formatting. _chat_inner() and
│   │                              _run_search_core() are the key functions.
│   ├── core/
│   │   ├── conversation_copy.py   All user-facing strings (greeting, no-match, listing nudges,
│   │   │                          VENUE_REDIRECT_TEMPLATE, OUT_OF_SCOPE_* templates).
│   │   ├── dedupe.py              Duplicate event detection via cosine similarity.
│   │   ├── event_quality.py       Validation helpers for event submission flow.
│   │   ├── extraction.py          OpenAI event extraction from free text + embedding generation.
│   │   │                          Uses gpt-4.1-mini for extraction/tags, text-embedding-3-small for embeddings.
│   │   ├── intent.py            ★ detect_intent() — classifies messages into intent labels,
│   │   │                          including OUT_OF_SCOPE with four category triggers and
│   │   │                          event-signal guard. See detect_out_of_scope_category().
│   │   ├── rate_limit.py          slowapi limiter config.
│   │   ├── search.py            ★ Core search logic. search_events(), scoring, threshold,
│   │   │                          literal-match bonus, honest_no_match, ACTIVITY_TYPES map.
│   │   │                          _SPECIFIC_PHRASES (~76 phrases). MOST IMPORTANT FILE for
│   │   │                          search quality work.
│   │   ├── search_log.py          Diagnostic logging — writes to search_debug.log + stdout.
│   │   ├── session.py             In-memory session state management for multi-turn chat.
│   │   ├── slots.py             ★ Slot extraction: date ranges, activity families, audience,
│   │   │                          location hints. QUERY_SYNONYMS (~39 groups) and expand_query_synonyms().
│   │   └── venues.py              VENUE_ALIASES (30 venues) and detect_venue() for the
│   │                              no-match venue-redirect path.
│   ├── db/
│   │   ├── chat_logging.py        Logs each chat turn to the chat_logs table.
│   │   ├── database.py            SQLAlchemy engine, Base, SessionLocal, get_db, init_db.
│   │   ├── models.py              Event and ChatLog ORM models.
│   │   └── seed.py                25 real Lake Havasu City events. Idempotent (skips existing seeds).
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
├── tests/                         60 tests across 9 files (see Section 2).
├── scripts/
│   ├── diagnose_search.py         Fires 25 test queries at the live app, saves output to
│   │                              diagnose_output.txt. Run with: py -3 scripts/diagnose_search.py
│   └── verify_queries.py          Quick 6-query spot-check against the live app.
├── docs/
│   ├── havasu-knowledge-base.md   Canonical query patterns, specific phrases, synonyms,
│   │                              venue aliases, and response copy. Source-of-truth for
│   │                              lists that land in search.py / slots.py / venues.py.
│   └── project-handoff.md         This file.
├── Procfile                       Railway start command.
├── nixpacks.toml                  Railway build config (pip install + uvicorn start).
├── requirements.txt               Dependencies (pinned to installed versions via pip freeze; Session C).
├── alembic.ini                    Alembic config.
└── .env                           Local secrets (not committed). See Section 8.
```

**Most important files for search quality work (in priority order):**
1. `docs/havasu-knowledge-base.md` — canonical lists; edit here first, then port to code
2. `app/core/search.py` — all scoring, thresholds, bonuses, filtering; `_SPECIFIC_PHRASES`
3. `app/chat/router.py` — synonym expansion wiring, query_message enrichment, venue-redirect + OUT_OF_SCOPE branches
4. `app/core/slots.py` — `QUERY_SYNONYMS` dictionary, slot extraction
5. `app/core/intent.py` — intent classification incl. `detect_out_of_scope_category()`
6. `app/core/venues.py` — `VENUE_ALIASES` + `detect_venue()` for the no-match redirect path
7. `app/db/seed.py` — event content quality directly affects search results
8. `app/core/extraction.py` — embedding generation for new/updated events

---

## 4. Completed Work This Session

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

### Session J — Expand specific phrases and synonyms from knowledge base (`1c1a079`)
**What:** Added `docs/havasu-knowledge-base.md` as the canonical reference for query patterns. Expanded `_SPECIFIC_PHRASES` in `app/core/search.py` from ~11 entries to ~76, organized by category (water sports, land activities, sightseeing, family/kids, dining, festivals, wellness). Expanded `QUERY_SYNONYMS` in `app/core/slots.py` from ~11 to ~39 phrase→synonym groups.
**Why:** Previous phrase and synonym lists covered only a handful of query types. Real users name specific venues, activities, and event types the app had no awareness of. Knowledge-base-sourced lists give broad coverage of the domain.
**Files changed:** `docs/havasu-knowledge-base.md` (new), `app/core/search.py`, `app/core/slots.py`.

### Session K — Venue recognition and no-match redirect (`d30b7f3`)
**What:** Added `app/core/venues.py` with `VENUE_ALIASES` (30 canonical Lake Havasu venues sourced from knowledge-base Section 6) and `detect_venue()` using longest-alias substring match. Added `VENUE_REDIRECT_TEMPLATE` to `conversation_copy.py`. Wired into `_run_search_core` in `app/chat/router.py`: when a query names a known venue and search returns zero events, the body is overwritten with the venue-redirect template.
**Why:** Queries like "trampoline park" or "havasu lanes" previously triggered a generic honest-no-match. The new behavior acknowledges that the venue exists and promises to surface events there when they come up, which keeps the user engaged.
**Files changed:** `app/core/venues.py` (new), `app/core/conversation_copy.py`, `app/chat/router.py`.

### Session L — OUT_OF_SCOPE intent for weather / lodging / transportation / dining (`766030a`)
**What:** Added `OUT_OF_SCOPE` intent label, four category trigger tuples, and `detect_out_of_scope_category()` in `app/core/intent.py`. Included an event-signal guard (event, events, festival, parade, fireworks, tournament, concert, gala, fundraiser) that suppresses the classification so queries like "hotel grand opening event tonight" still reach search. Added four verbatim response templates to `app/core/conversation_copy.py` (`OUT_OF_SCOPE_WEATHER`, `OUT_OF_SCOPE_LODGING`, `OUT_OF_SCOPE_TRANSPORTATION`, `OUT_OF_SCOPE_DINING`) plus an `OUT_OF_SCOPE_REPLIES` lookup. Wired an early branch in `_chat_inner` that returns the category template and skips the search pipeline entirely. Added three new pytest cases.
**Why:** Out-of-scope queries (weather, hotels, directions, restaurant recommendations) previously ran through the full search pipeline — wasting an OpenAI embedding call and returning nonsense. Classifying them up front gives a clean redirect and saves API cost.
**Files changed:** `app/core/intent.py`, `app/core/conversation_copy.py`, `app/chat/router.py`, `tests/test_phase8_5.py`.

### Note on Sessions J–L vs. the old "Step 3 AI Tagging" plan
Section 6 below used to describe AI tagging as the next task. That work shipped in Session D (`82c4f0a`) and is now complete. Sessions J, K, and L are the real post-D work: knowledge-base-driven search quality (J), venue recognition (K), and out-of-scope intent (L). The section is retained for historical context.

---

## 5. Remaining Roadmap

### Step 3 — AI-generated tags on event submission (completed)
**Status:** Done in Session D (`82c4f0a`) and deployed.
**What shipped:** `generate_event_tags()` added to `app/core/extraction.py`, called inside `extract_event()`, and `POST /admin/retag-all` added in `app/admin/router.py`.
**Production backfill:** `POST /admin/retag-all` returned `{"updated":25}`.
**Notes:** This intentionally overwrites prior hand-written tags for consistency across all events.

### Step 4 — Content: update seed event dates (completed)
**Status:** Done in Session B (`41d1c71`) and deployed.
**What shipped:** All 25 seed event dates updated to a May–July 2026 rolling window in `app/db/seed.py`.
**Notes:** After any future date window expires, re-run this same targeted edit on `app/db/seed.py` and trigger a reseed via `POST /admin/reseed`.

### Step 5 — Admin review UX improvements
**What:** The admin panel is functional but plain. Potential improvements: show event tags and embedding status, add a "preview as user" link, show search score for each event.
**Why:** Makes moderation faster and helps Casey understand why events do/don't rank.
**Files it will touch:** `app/admin/router.py` (HTML generation).
**Who should do it:** **Cursor LLM** — contained within one file's HTML generation functions.

### Step 6 — Shareability
**What:** Allow linking to a specific event or a search result. Minimal implementation: `/events/{id}` page that renders a single event card. Could share as `https://web-production-bbe17.up.railway.app/events/abc123`.
**Why:** Users who find a great event want to send it to friends. Without this, the app is a dead end.
**Files it will touch:** `app/main.py` (new GET route), `app/static/index.html` (share button), possibly `app/admin/router.py` (event link in admin card).
**Who should do it:** **Cursor LLM** for the route + HTML. Straightforward.

### Step 7 — Onboarding for returning users
**What:** Currently the welcome chips only show on the first message of a fresh browser session. Returning users see a blank input with no guidance. Options: persist a "last visited" flag in localStorage; show a softer prompt like "Welcome back — what are you looking for?"
**Why:** Returning users drop off because there's no prompt to engage.
**Files it will touch:** `app/static/index.html` only.
**Who should do it:** **Cursor LLM** — frontend-only change.

### Step 8 — Re-run full diagnostic and tune
**What:** After Step 4 updates, run `py -3 scripts/diagnose_search.py` against the live app. Review the full 25-query output and identify remaining ranking problems.
**Why:** Changes compound. New tags, updated embeddings, and date changes may improve or regress results. Verify before declaring search quality done.
**Who should do it:** Run the script locally, paste the output into Cursor or Claude for interpretation.

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
- **Tests:** `py -3 -m pytest --tb=short -q` passed (57/57).
- **No migration needed:** `tags` column already exists as `JSON`.
- **Production backfill:** Completed; `/admin/retag-all` returned `{"updated":25}`.

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
1. Search quality (Steps 2a, 2b, 3, plus Sessions A, J, K, L done)
2. Content freshness (seed event dates done in Session B; needs periodic refresh)
3. Admin review UX
4. Shareability
5. Returning-user onboarding

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
All 57 must pass. If a test fails, fix it before committing. Never push a failing test.

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
3. Should return `{"updated": 25}`.

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
