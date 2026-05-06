# intent

`app/core/intent.py` (~654 lines)

## Purpose

Deterministic, regex/heuristic-based intent detection — the template-layer cousin to `app/chat/intent_classifier.py` (the LLM-driven Tier 1 classifier). Given a user message and the current session state, returns one of twelve intent labels (`HARD_RESET`, `SOFT_CANCEL`, `GREETING`, `LISTING_INTENT`, `ADD_EVENT`, `SERVICE_REQUEST`, `DEAL_SEARCH`, `REFINEMENT`, `SEARCH_EVENTS`, `OUT_OF_SCOPE`, `UNCLEAR`, `CALENDAR_VIEW`). The classification is fully deterministic (no LLM) — every label is decided by curated phrase lists, regex patterns, or session-state inspection.

The module exports both the full `detect_intent` cascade and a number of single-purpose helpers (`is_calendar_open_phrase`, `detect_out_of_scope_category`, `is_greeting`, `is_confirmation`, `is_skip_optional_contact`, etc.) that are reused across the chat surface.

**Relationship to `app/chat/intent_classifier.py`.** That module is the LLM-driven Tier 1 classifier (Anthropic Haiku) used by the unified router; this module is the deterministic-template-layer intent surface. They share one function — `app/chat/intent_classifier.py` imports `detect_out_of_scope_category` from this module to pre-screen out-of-scope queries before invoking the LLM. Otherwise the two modules answer different questions: this one assigns a discrete intent label given current session state; the other classifies queries into the Tier 1/2/3 routing taxonomy. Confusing the two is the most common reading error in this surface.

## Public surface

**Intent labels (string constants):**

- `HARD_RESET` — total wipe ("start over", "cancel everything").
- `SOFT_CANCEL` — bail out of current sub-flow ("never mind", "scratch that").
- `GREETING` — short hello, no other content.
- `LISTING_INTENT` — "show me everything", "what events", broad listing.
- `ADD_EVENT` — explicit add-event phrasing or hosting/posting markers.
- `SERVICE_REQUEST` — plumber, electrician, "fix my X" — out-of-scope service lookup.
- `DEAL_SEARCH` — "happy hour", "deal", "coupon" — discount/promo search.
- `REFINEMENT` — narrow-down filter on an active search context.
- `SEARCH_EVENTS` — default; user is asking about events.
- `OUT_OF_SCOPE` — weather, lodging, dining recommendations, transportation.
- `UNCLEAR` — too short or ambiguous to classify.
- `CALENDAR_VIEW` — explicit ask to open the calendar overlay.

**Primary entry point:**

**`detect_intent(message: str, session: dict[str, Any] | None = None) -> str`** — Main cascade. Returns one of the twelve labels. Empty/missing session is tolerated (`session = session or {}`).

**Single-purpose detectors** (all `(message: str) -> bool` unless noted):

- **`is_hard_reset`**, **`is_soft_cancel`**, **`is_cancel_or_restart`** — reset-state detection.
- **`is_calendar_open_phrase`** — fires on the curated `_CALENDAR_OPEN_PHRASES` list.
- **`is_greeting`** — short hello detection (≤32 chars + leading hi/hello/hey).
- **`is_confirmation`** / **`is_rejection`** — yes/no recognition for confirmation flows.
- **`is_skip_optional_contact`** — "skip", "no thanks", "none" for optional-contact prompts.
- **`escape_to_search`** — mid-add-flow phrases that mean "abandon, just browse" ("just looking", "what's on").
- **`open_ended_search_message`** — fires on a small curated set ("what's good", "surprise me", "anything fun").
- **`detect_out_of_scope_category(message) -> str | None`** — returns one of `"weather"`, `"lodging"`, `"transportation"`, `"dining"`, `"commercial_services"`, or `None`.

**Module-level constants** (exported for cross-module reads):

- All twelve label strings.
- `SINGLE_WORD_ACTIVITIES` (frozenset) — bare-word activity tokens that route directly to `SEARCH_EVENTS` ("golf", "tennis", "yoga", etc.).
- `GREETING_TOKENS` (frozenset) — bare-token greetings.
- `CONFIRMATION_PHRASES`, `REJECTION_PHRASES`, `SKIP_OPTIONAL_CONTACT_PHRASES` — list/tuple constants used by the confirm-related detectors.

## Inputs and outputs

**`detect_intent` input.** A free-form message string and optional session dict. The session dict is consulted for two specific keys:

- `session["flow"]["awaiting"]` — when the value is `"narrow_followup"`, refinement detection becomes active. (Used to distinguish "soccer" mid-conversation as a filter on prior search vs as a fresh `SEARCH_EVENTS`.)
- `session["partial_event"]` and other `awaiting_*` flags — `_active_non_search_flow` returns `True` when any of these is truthy, suppressing the `GREETING` short-circuit.

**`detect_intent` output.** A single string from the twelve-label set.

**`detect_out_of_scope_category` output.** One of the five category names or `None`. Returns `None` when an event-signal token (`_EVENT_INDICATOR_WORDS`: "event", "festival", "parade", "fireworks", "tournament", "concert", "gala", "fundraiser", "tour") appears in the message — that's the "events-about-a-venue" rescue (a query like "hotel grand opening event tonight" should reach search, not be rejected as lodging).

## Internal structure

**`detect_intent`** is a fifteen-step cascade. Order is load-bearing:

1. **`is_hard_reset(msg)`** → `HARD_RESET`.
2. **`is_soft_cancel(msg)`** → `SOFT_CANCEL`.
3. **`_explicit_add_event_route(msg)`** → `ADD_EVENT`. Standalone phrases like "add an event", "submit an event", "I want to add", with no date required.
4. **`is_calendar_open_phrase(msg)`** → `CALENDAR_VIEW`.
5. **`detect_out_of_scope_category(msg) is not None`** → `OUT_OF_SCOPE`. Categories: weather, lodging, transportation, dining, commercial_services.
6. **`is_greeting(msg) and not _listing_hit(msg) and not _active_non_search_flow(session)`** → `GREETING`. Triple-conjunction: short hello AND not a listing query AND no active flow.
7. **`_listing_hit(msg)`** → `LISTING_INTENT`. Substring match against `_LISTING_PHRASES`.
8. **`_SERVICE_MARKERS`** substring → `SERVICE_REQUEST`.
9. **`_DEAL_MARKERS`** substring → `DEAL_SEARCH`.
10. **`_add_meta_intent_question(msg)`** → `ADD_EVENT`. How-to/permission phrasing ("can I add an event", "how do I post").
11. **`awaiting == "narrow_followup" and _refinement_looks_like_filter(msg)`** → `REFINEMENT`. Only fires inside an active search-followup flow.
12. **Single-word activity** (one of `SINGLE_WORD_ACTIVITIES`) → `SEARCH_EVENTS`.
13. **`_add_creation_language(msg) and _has_time_or_date_reference(msg)`** → `ADD_EVENT`. Hosting/teaching markers + a temporal anchor.
14. **`_add_creation_language(msg) and not _has_time_or_date_reference(msg)`** → `SEARCH_EVENTS`. The same markers without a date are treated as searches (e.g., "I'm hosting a workshop?" without a specific time = browsing).
15. **`len(msg) < 3 and not _active_non_search_flow(session) and awaiting is None`** → `UNCLEAR`. Short messages with no flow context.

**Default fallthrough:** `SEARCH_EVENTS`. The cascade ends at the most-common case rather than treating unknown queries as `UNCLEAR`.

**`detect_out_of_scope_category`** has its own three-layer guard:

1. `"restaurant week"` → return `None` (rescue for the festival).
2. `"X night"` for `_NIGHT_ACTIVITY_WORDS` ("bike night", "trivia night", "comedy night") → return `None`.
3. `_commercial_services_query(m)` → return `"commercial_services"` when phrasing is rental/venue-shopping (cheap/affordable, "rentals", "hire", "book a", "venue for", "birthday party", "wedding venue"), with a guard rescue for `_COMMERCIAL_EVENT_RESCUE_PHRASES` ("rental event", "open house", "ribbon cutting", "grand opening").
4. **Event-signal rescue**: if any `_EVENT_INDICATOR_WORDS` token appears, return `None` (skip the category checks entirely).
5. **Category iteration**: scan `_OUT_OF_SCOPE_TRIGGERS` (weather/lodging/transportation/dining); return the first matching category name.

**`_refinement_looks_like_filter`** is the gate for `REFINEMENT` detection. Returns `True` for: a single bare word in `SINGLE_WORD_ACTIVITIES`, any message yielding a `date_range`/`activity_family`/`audience` slot, or a single short bare word from a curated set ("sports", "arts", "kids", "family", "outdoors", "learning", "classes"). The detector calls into `app.core.slots.extract_*` for the slot signals.

**`_query_looks_like_program`** is exported but **not used** by `detect_intent` itself — it's a side helper for callers that need a recurring-class signal (program/lessons/classes phrasing) separately from the main cascade.

## Conventions

**Lowercase + strip + rstrip-punct as preprocessing.** Most detectors do `message.lower().strip().rstrip("?!. ")` so trailing punctuation doesn't break substring matches. Exceptions: `is_hard_reset`/`is_soft_cancel` only `.lower().strip()` (no punctuation strip).

**Substring-match-by-default.** Most phrase detection uses `in` on lowercased text. Word-boundary regex is reserved for ambiguous tokens (`_word_boundary` helper) — used by `is_hard_reset` (for "reset") and `is_soft_cancel` (for "cancel"), and by `_has_time_or_date_reference` for date/time tokens.

**Cascade order is load-bearing.** Reordering specific steps would change classifications:

- Step 5 (`OUT_OF_SCOPE`) before step 6 (`GREETING`) means "weather hello" classifies as out-of-scope, not greeting.
- Step 7 (`LISTING_INTENT`) after step 6 (`GREETING`) — but the greeting branch's triple-conjunction requires `not _listing_hit(msg)`, so a greeting that's also a listing query still routes to `LISTING_INTENT`. (Both checks happen in step 6.)
- Step 13 (`ADD_EVENT`) requires `_has_time_or_date_reference`; without it, step 14 routes to `SEARCH_EVENTS` instead. The split is deliberate — bare hosting language without a date is treated as browsing intent.

**`_active_non_search_flow` suppresses greetings.** When the session is mid-add-flow or awaiting confirmation, "hi" mid-stream is treated as part of the flow, not a fresh greeting. The greeting branch's `not _active_non_search_flow(session)` guard enforces this.

**`_OUT_OF_SCOPE_TRIGGERS` indentation has cosmetic 8-space-indented entries.** Look at the source — some sub-tuples are double-indented relative to siblings. This is a copy-paste artifact, not a structural difference; all entries function identically.

## Known limitations and design notes

**`detect_intent` has no live runtime caller in `app/`.** The module is exported and tested (heavily, in `tests/test_phase3.py`, `tests/test_phase8.py`, `tests/test_phase8_5.py`, `tests/test_calendar_intent.py`), and `app/chat/intent_classifier.py` reuses `detect_out_of_scope_category` from this file — but the main `detect_intent` cascade itself is not invoked from any production-path module post the legacy `/chat` removal (Slice H1, `61387e4..23a39a5`). The labels and helpers remain as documented contract; if a future router needs deterministic intent detection (e.g., for fast-path routing without LLM cost), this is the surface to use.

**Order-dependent cascade.** No "explain why" facility. Adding telemetry around which branch fired requires editing each `return` site.

**Phrase lists are flat-coupled to specific UX phrasings.** "Add an event" handles add-event UX; if the chat composer changes its onboarding copy, the trigger phrases here may go stale. There's no central phrase-source-of-truth.

**`detect_out_of_scope_category` is permissive on dining.** `"restaurant"` triggers `dining`, but "restaurant week" is rescued as a search. The rescue list is specific to known events; new restaurant-themed events would require manual rescue addition.

**Out-of-scope categories don't propagate.** The cascade returns `OUT_OF_SCOPE` (the bare label) without surfacing which category triggered. Callers wanting the category must call `detect_out_of_scope_category(msg)` separately.

**`SINGLE_WORD_ACTIVITIES` is curated and small.** ~13 entries. Adding a new sport requires a code change. The list intentionally excludes generic terms ("dance", "music") that overlap with other intent layers.

**`_explicit_add_event_route` doesn't enforce a question mark.** "Add event tonight at 7" routes to `ADD_EVENT` even when phrased as a statement. Inverse — a question with the same phrase ("add event tonight at 7?") does too. Both behaviors are intentional.

**`_refinement_looks_like_filter` consults `app.core.slots`.** A circular import concern is avoided because both modules already import each other (`slots.py` doesn't import `intent.py`; `intent.py` imports three slot extractors). Adding new slot consumers should preserve this direction.

## Configuration

No environment variables. All triggers are module-level constants:

- `_CALENDAR_OPEN_PHRASES`, `_HARD_RESET_PHRASES`, `_SOFT_CANCEL_PHRASES`, `_LISTING_PHRASES`, `_ADD_CREATION_MARKERS`, `_SERVICE_MARKERS`, `_DEAL_MARKERS` — phrase tuples.
- `_OUT_OF_SCOPE_TRIGGERS` — categorized trigger map.
- `_EVENT_INDICATOR_WORDS`, `_NIGHT_ACTIVITY_WORDS`, `_COMMERCIAL_EVENT_RESCUE_PHRASES` — rescue tuples.
- `_PROGRAM_KEYWORDS`, `_PROGRAM_QUESTION_PATTERNS`, `_PROGRAM_ACTIVITY_PHRASES` — used by the unrelated `_query_looks_like_program`.
- `SINGLE_WORD_ACTIVITIES`, `GREETING_TOKENS`, `CONFIRMATION_PHRASES`, `REJECTION_PHRASES`, `SKIP_OPTIONAL_CONTACT_PHRASES` — exported.

## Related

**Direct callers in `app/`:**

- `app/chat/intent_classifier.py:17` — imports `detect_out_of_scope_category` to pre-screen queries before LLM Tier 1 classification. The other helpers in this module are not currently consumed by the live runtime.

**Direct callers in `tests/`:**

- `tests/test_phase3.py`, `tests/test_phase8.py`, `tests/test_phase8_5.py` — full `detect_intent` cascade coverage.
- `tests/test_calendar_intent.py` — `is_calendar_open_phrase` and `CALENDAR_VIEW` routing.

**Direct dependencies:**

- `app.core.slots.extract_activity_family`, `extract_audience`, `extract_date_range` — slot detection for refinement gating.
- `re`, `typing.Any` (stdlib).

**Cross-references:**

- `docs/components/slots.md` — the slot extractors this module consults.
- `docs/components/intent_classifier.md` — the LLM-driven Tier 1 classifier (a different module — same conceptual neighborhood, different implementation strategy). The two share `detect_out_of_scope_category`; otherwise they answer different questions.
- `docs/search-pipeline-for-claude.md` — historical pipeline doc with the full cascade and the legacy router context.
- `.cursorrules` — references `detect_intent(message, session)` as the canonical intent surface.
