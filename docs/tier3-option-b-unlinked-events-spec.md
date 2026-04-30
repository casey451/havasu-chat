# Tier 3 Option B — unlinked future events in context (implementation spec)

**Status:** Design / pre-implementation  
**Date:** 2026-04-25  
**Scope:** Written spec only; no code in this document.  
**Related:** `docs/tier3-event-visibility-investigation.md`, `docs/known-issues.md` (Tier 3 `provider_id` gating).

**Decision:** Extend Tier 3 to include a bounded set of **unlinked** future events (`provider_id IS NULL`) as a **general-calendar** context block. **Not** Option A (link at approval) or Option C (route to Tier 2).

Conventions: `docs/CURSOR_ORIENTATION.md` (tight scope, push approval on implement, pytest local).

---

## 1. Investigation — `app/chat/context_builder.py`

| Function | Lines | Signature / purpose |
|----------|-------|----------------------|
| `_truncate_hours` | 24–30 | `(h: str \| None) -> str` — truncates free-text hours to `_HOURS_MAX_LEN` (200). |
| `_word_count` | 33–34 | `(text: str) -> int` — simple split word count. |
| `_trim_to_word_budget` | 37–41 | `(text, max_words) -> str` — hard-truncates to first N words. |
| `_fetch_provider_rows` | 44–66 | `(db, entity: str \| None) -> list[Provider]` — up to 10 active non-draft providers; if none, falls back to up to 10 **verified** only; entity name match first if `entity` set. |
| `_programs_for` | 69–72 | `(db, provider_id) -> Sequence[Program]` — active programs for one provider. |
| `_events_future_for` | 75–85 | `(db, provider_id, today) -> Sequence[Event]` — event query (see predicates below). |
| `build_context_for_tier3` | 88–141 | `(query, intent_result, db) -> str` — only public entry; assembles full context string. |

### Flow of `build_context_for_tier3`

1. `today = date.today()`.
2. `providers = _fetch_provider_rows(...)`.
3. If **no** providers → early return a fixed two-sentence “no catalog” string (lines 92–96) — does not run any event query today.
4. Otherwise: header `Context — Lake Havasu catalog snapshot (programs and events may be partial):` (line 99), then for each provider: `Provider:` block, `Program:` lines, then lines from `_events_future_for`:  
   `  Upcoming event: {title} on {date} at {HH:MM} — {location_name}` (lines 132–135).
5. `body = "\n\n".join(parts)` then `_trim_to_word_budget(body, MAX_CONTEXT_WORDS)` (lines 139–140).  
   **`MAX_CONTEXT_WORDS = 1500`** (line 20).

### Event query — current predicates

Only in `_events_future_for` (lines 75–85):

- `Event.provider_id == provider_id`
- `Event.status == "live"`
- `Event.date >= today`
- `order_by(Event.date.asc(), Event.start_time.asc())`
- `limit(8)`

There is **no** query for `provider_id IS NULL` events in this file today.

---

## 2. `unified_router` and Tier 3 use of context

- `_handle_ask` (`app/chat/unified_router.py` ~118–140): Tier 1 → (explicit rec or Tier 2) → `answer_with_tier3` from `tier3_handler`.
- **Context** is a **single string** from `build_context_for_tier3`, passed as the last segment of the **user** message (`app/chat/tier3_handler.py` lines 134, 162):

  `user_text = f"User query:\n{query.strip()}\n\n{mid}\n\n{context}"`

- `mid` = classifier + optional User context + `Now:` + optional Local voice. **No** event structure there.
- **“Upcoming event”** wording is only from `context_builder` lines 132–135, not a separate Jinja/prompt template under `app/chat/prompts/`.

---

## 3. Tier 3 “templates”

- **System** prompt: `prompts/system_prompt.txt` (loaded via `_load_tier3_system_prompt()` in `tier3_handler`, which calls `app.core.llm_messages.load_prompt("system_prompt")` with graceful `OSError` fallback). Describes **Context block** behavior; no per-field JSON. Optional labels like `Now:`, `User context:`, `Local voice:` are documented; a **General calendar** (or **Standalone events**) header is consistent.
- **No** separate file formats individual event rows; formatting is only in `context_builder.py`.

**Provider-tied line format today:**  
`  Upcoming event: {title} on {date} at {time} — {location_name}`

---

## 4. Tier 2 reference — `_query_events` (`app/chat/tier2_db_query.py` 293–327)

Predicates (baseline for standalone `Event` SQL):

- `Event.status == "live"`
- `Event.date >= lower` (time window or **today**)
- Optional: `Event.date <= win_end`
- Optional: `ilike` on title/description, location, category, weekday post-filter
- **No** `provider_id` filter
- Capped in SQL to 80 rows, then `[:MAX_ROWS]` (8) for formatted output

**Takeaway for Option B:** match `live` + `date >= today` (+ optional **end** cap). Do **not** require `provider_id`. Do **not** filter on `source` for v1.

---

## A. Where to add the new query

- **New function (suggested name):** `_unlinked_future_events` (or `_general_calendar_events`) in **`context_builder.py`**, same style as `_events_future_for` (module-private, `Session` + `today` + cap + dedup input).
- **Call site:** inside `build_context_for_tier3`, **after** the `for p in providers:` loop (after line 137, before `body = "\n\n".join(parts)"` at line 139), **if** the early return at 92–96 was **not** taken.

**Narrative order:** keep per-provider blocks **first**; **append** one new section for unlinked (do not interleave with providers).

**Gap (product):** when `providers` is **empty**, today’s code returns before any events. This spec **does not** add unlinked-only context in that path unless a follow-up explicitly changes the early return.

---

## B. Query shape

**Must**

- `Event.status == "live"`.
- `Event.date >= today` (same `date.today()` as the rest of the function).
- `Event.provider_id.is_(None)`.
- Do **not** filter on `source`, `created_by`, or `embedding`.

**Deduplication**

- While iterating providers, collect `linked_event_ids: set[str]` of every `ev.id` from `_events_future_for`.
- After fetching unlinked rows, **drop** any with `id in linked_event_ids` (defensive; normally disjoint).

**Order:** `order_by(Event.date.asc(), Event.start_time.asc())`.

**Limit:** suggest **`limit(10)` to `12`** in SQL, then slice after dedup. Rationale: 8 is per **provider**; a single global cap ~10 keeps tokens under the existing word budget.

**Date upper bound (recommended):**  
`Event.date <= today + timedelta(days=365)` (or 270–365 days) so late-year one-offs (e.g. November) are included without pulling multi-year junk. Unbounded `date` is allowed in SQL but worse for the word budget.

---

## C. How results integrate into Tier 3 context

**Placement:** new section **after** all `Provider:` blocks, still the same `Context` string for `user_text`.

**Suggested copy structure**

```text
General calendar (upcoming, not attached to a listed business above):
  Upcoming event: {title} on {date} at {time} — {location_name} — {event_url or —}
  …
```

**Fields per line (v1):** at minimum `title`, `date` (ISO), `start_time`, `location_name`, `event_url`.  
Optional one-line description truncate (~120 chars) only if word budget allows; **default off** in v1.

**Prompt:** `system_prompt.txt` already binds facts to the Context block; **optional** one line clarifying that *General calendar* lists events not tied to a `Provider` row above.

---

## D. Edge cases

| Case | Behavior |
|------|------------|
| Overlap of id between linked and unlinked | Normally impossible (NULL vs non-NULL `provider_id`); dedup set handles defensive overlap. |
| Zero unlinked after filter/dedup | **Omit** entire General calendar section (no empty header). |
| Tier 3 relevance / embeddings | **No** embedding ranking in `build_context_for_tier3` today; v1 = **chronological** only. |
| No providers in DB | Early return unchanged in v1; unlinked block **not** shown. |

---

## E. Risks and assumptions

1. **System prompt (anti-pivot / anti-hallucination):** supplying a **factual** block is intended grounding; long blocks may still invite over-listing in the assistant — mitigate with **cap** and **trim** discipline.
2. **Word budget — critical:** `_trim_to_word_budget` (lines 37–41) keeps the **first** `max_words` words of the **entire** joined string. If the **unlinked** section is **appended after** provider text, the **end** of the string is the **first** to fall off the budget when over limit — the new block can disappear entirely.
   - **Implementation must** either: trim **provider** portion in a way that **preserves** a reserved tail for General calendar, **or** place a **compact** unlinked block **earlier** (e.g. right after the header — product may dislike order), **or** raise `MAX_CONTEXT_WORDS`, **or** two-phase assembly: trim `head` then append `tail`.
3. **Tests** asserting full `build_context_for_tier3` output may need updates when structure changes.
4. **Assumption:** `provider_id IS NULL` is the correct “standalone” definition — validate in prod.
5. **Multi-day** events: still one `Event` row; no Option B schema change.

---

## F. Implementation size estimate

| Item | Rough estimate |
|------|----------------|
| `context_builder.py` | +60–120 lines (helper, id collection, formatting, trim strategy). |
| `prompts/system_prompt.txt` | +0–2 lines optional. |
| `tests/test_context_builder.py` | +40–80 lines. |
| `tier3_handler.py` / `unified_router.py` | 0 unless system prompt is edited. |

**Tests (suggested in `tests/test_context_builder.py`):** unlinked event appears; cap respected; section omitted when none; word-budget / ordering behavior once trim strategy is chosen.

**pytest:** local per `docs/CURSOR_ORIENTATION.md`.

---

## Option B harder than it looks?

- **No** JSON or API shape conflict — plain text.
- The **word-budget / truncation** interaction is the main non-obvious risk; must be part of the implementation pass, or Option B will **silently** drop the new block under heavy provider context.

**Alternatives if trim is thorny:** short **prepended** summary (3–5 lines) right after the snapshot header, or a modest **increase** in `MAX_CONTEXT_WORDS` with owner approval.

---

*End of spec. Implementation phase: mechanical once trim/order is decided.*
