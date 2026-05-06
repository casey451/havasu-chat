# conversation_copy

`app/core/conversation_copy.py` (~145 lines)

## Purpose

**Canonical module for casual user-visible chat strings** (Phase 7 onward): greetings, clarification prompts, search/program intros, duplicate-merge prompts, out-of-scope deflections, and Phase 8.5 listing/search UX lines. Editing tone happens **here** rather than scattering literals across routers — **`search.py`** imports focused subsets for relevance messaging.

The constants intentionally avoid **`tier1_handler`** today (**Slice 67a grep**) — Tier 1 uses **`tier1_templates`**.

## Public surface (grouped by role — names only)

**Idle greeting**

- **`GREETING_REPLY`**

**Intent ambiguity**

- **`UNCLEAR_REPLY`**, **`GREETING_MID_SEARCH`**

**Confirmation / cancel / restart flows**

- **`CANCEL_REPLY`**, **`REJECTION_FIX`**, **`SOFT_CANCEL_REPLY`**, **`HARD_RESET_REPLY`**, **`ESCAPE_HATCH_REPLY`**

**Add-event / duplicate-merge ladder**

- **`DUPLICATE_PROMPT`** (**`.format(title=...)`**), **`MERGE_FOLLOWUP`**, **`MERGE_KEPT`**, **`MERGE_UPDATED`**, **`ADDED_LIVE`**, **`preview_event_line(...)`** (function builds confirmation sentence)

**Search scaffolding**

- **`SEARCH_EMPTY`**, **`SEARCH_INTRO_MANY`**, **`MISSING_FIELD_GLITCH`**, **`CHAT_SOFT_FAIL`**, **`STALE_SESSION_REPLY`**

**Phase 8.5 refinement prompts**

- **`CLARIFY_DATE`**, **`CLARIFY_ACTIVITY`**, **`LISTING_NUDGE_*`**, **`NOTHING_IN_RANGE`**, **`NOTHING_FOR_ACTIVITY`**, **`NO_MATCH_HONEST`**, **`NO_MATCH_BROADEN`**, **`VENUE_REDIRECT_TEMPLATE`**

**Service/deals stubs**

- **`SERVICE_STUB_REPLY`**, **`DEAL_STUB_REPLY`**

**Out-of-scope bucket**

- **`OUT_OF_SCOPE_*`** strings plus **`OUT_OF_SCOPE_REPLIES`** dict keyed by semantic buckets (**`weather`**, **`lodging`**, **`transportation`**, **`dining`**, **`commercial_services`**).

**Programs branch**

- **`PROGRAMS_INTRO`**, **`PROGRAMS_NONE`**

**Calendar UX**

- **`CALENDAR_OPEN_REPLY`**

For verbatim wording open **`app/core/conversation_copy.py`** — avoid duplicating long strings in this doc to reduce drift when copy tweaks ship.

## Inputs and outputs

Most symbols are **`str`** constants; **`preview_event_line`** is the lone **small formatter function**.

Template-bearing constants rely on **`.format(...)`** or **`str.format`** by callers — missing kwargs surface at runtime.

## Internal structure

Flat module — grouping is conceptual only (comments in source separate Phase markers).

## Conventions

**Emoji usage is deliberate** in a handful of strings (merge celebration / icons). Changing emoji impacts UX regression snapshots across **`search`** formatting paths — grep callers before edits.

## Known limitations and design notes

**Duplicate literals risk:** **`search.py`** defines **`SEARCH_ZERO`** separately mirroring **`SEARCH_EMPTY`** — two sources exist historically; consolidating requires verifying **`search.py`** imports vs legacy **`SEARCH_ZERO`** references.

## Configuration

None — copy is code-owned.

## Related

**Direct importers:**

- **`app/core/search.py`** — listing / honest-no-match / venue templates subset.
- **`app/core/program_search.py`** — **`PROGRAMS_INTRO`**, **`PROGRAMS_NONE`**.

**Cross-references:**

- **`docs/components/search.md`** (Slice **67b**) — embedding/search orchestration importing these strings.
- **`docs/components/program_search.md`** — program-card formatter glue.
