# slots

`app/core/slots.py` (~437 lines)

## Purpose

Structured-search slot extraction from free-form user messages — Phase 8.5 search-routing infrastructure. Given text like "kids gymnastics classes this weekend near London Bridge", produces named slots: `date_range` (start/end dates), `activity_family` (one of five family categories), `audience` (kids / adults / family), `location_hint` (free-text). Plus a synonym-expansion table for keyword search and two label-generation helpers used by the conversational copy in `app/core/conversation_copy.py`.

This module is one of the most-imported in `app/core/`. Consumers include `app/core/search.py` (the multi-stage event search), `app/chat/tier2_db_query.py`, `app/core/program_search.py`, `app/chat/intent_classifier.py`, and `app/core/intent.py` — all four extractors plus the synonym expander are used somewhere downstream.

## Public surface

**Slot extractors** (each returns the slot value or `None`):

- **`extract_date_range(text: str) -> DateRange | None`** — relative phrases ("today", "tomorrow", "this weekend", "this week", "next week", "next month", "this month"), weekday names ("Saturday"), and explicit ISO dates (`2026-05-09`).
- **`extract_activity_family(text: str) -> str | None`** — returns one of `"martial_arts"`, `"sports"`, `"arts"`, `"education"`, `"outdoors"` based on `FAMILY_ALIASES` matching, or `None`.
- **`extract_audience(text: str) -> str | None`** — returns `"kids"`, `"adults"`, `"family"`, or `None` based on phrase matching.
- **`extract_location_hint(text: str) -> str | None`** — extracts a multi-word place name from `at X` / `near X` patterns; returns up to 120 chars or `None`.

**Slot mergers** (last-non-`None` wins):

- **`merge_date_range`**, **`merge_activity_family`**, **`merge_audience`**, **`merge_location_hint`** — given an existing value and a new value, return the new value if non-`None`, else the existing. All four have identical logic; the type-specific signatures are bookkeeping.

**Conversational copy helpers** (used by `search.py` and the chat formatters):

- **`extract_search_label(message: str, slots: dict) -> str`** — human-readable label for what the user searched for, biased toward UX-friendly phrasing ("gymnastics classes for kids", "weekend events", "events for that time"). Always returns a non-empty string; falls back to the longest non-stop-word in the message, then to `"events matching that"`.
- **`extract_broaden_category(slots: dict) -> str | None`** — short noun phrase for the broaden line ("kids activities", "weekend events", "outdoor activities"), or `None` when no slot offers useful context.

**Synonym expansion:**

- **`expand_query_synonyms(message: str) -> list[str]`** — returns extra keywords to search for based on substring-matched phrases against `QUERY_SYNONYMS`. Used by the embedding-search bonus path in `search.py`.

**Session helpers:**

- **`push_recent_utterance(search_block: dict, phrase: str) -> None`** — appends `phrase` to `search_block["recent_utterances"]` (mutating dict); caps at 3 entries (FIFO eviction).
- **`slots_filled(slots: dict) -> dict[str, bool]`** — returns `{"date": bool, "activity": bool, "audience": bool, "location": bool}` reporting which slots have non-empty values.

**Module-level constants** (exported for cross-module reads):

- **`DAY_NAMES`** — `dict[str, int]` mapping `"monday"`–`"sunday"` to `0`–`6` (matches `datetime.date.weekday()`).
- **`FAMILY_ALIASES`** — `dict[str, list[str]]` mapping the five family keys to their alias terms.
- **`QUERY_SYNONYMS`** — `dict[str, list[str]]` mapping ~50 anchor phrases ("boat race", "yoga", "live music", etc.) to lists of synonyms.
- **`DateRange`** — `TypedDict` with `start: date`, `end: date`.

## Inputs and outputs

**`extract_date_range`** returns `{"start": date, "end": date}` or `None`. Single-day ranges have `start == end` (e.g., "today" produces a one-day range, not a span). "This weekend" returns Saturday + Sunday (span of 1 day, where `_is_weekend_date_range` recognizes the `(end - start).days == 1` shape). "This week" returns today through the upcoming Sunday. "Next week" returns the upcoming Monday through the following Sunday (always Mon–Sun).

**`extract_activity_family`** returns the first matching family in the priority order `["martial_arts", "sports", "arts", "education", "outdoors"]`. The ordering is intentional: `martial_arts` is checked first because its terms ("karate", "bjj", etc.) are highly specific and shouldn't be overshadowed by the broader `sports` list. `outdoors` is last because its terms ("park", "outdoor") have higher overlap with locations.

**`extract_audience`** has explicit checks: `\b\d{1,2}\s*year\s*old\b` regex first ("8 year old"), then a tuple of `kids`-marker substrings (including `"kid "`, `" kid"`, `"my daughter"`, `"my son"`, `"for students"`), then `adults` markers (`"21+"`, `"adults only"`), then `family`. The kids/adults/family branches are mutually exclusive — first-match wins.

**`extract_location_hint`** returns the captured group from `\b(?:at|near)\s+([A-Za-z0-9][A-Za-z0-9\s,'-]{2,60})`, capped at 120 chars. Returns `None` when no match or when the match is ≤2 chars.

## Internal structure

**`extract_date_range`** is a linear cascade — substring checks in priority order, falling through to weekday-name iteration, falling through to ISO-date regex, then `None`. Critical ordering details:

- `"this weekend"` is checked **before** `"this week"` (substring would otherwise match the longer phrase).
- `"first friday"` short-circuits to `None` — it's a recurring event name, not a date filter.
- `"tonight"` is treated as `"today"` (same start/end).

**`_next_weekday(start_date, weekday, allow_today)`** is the helper for forward-looking weekday resolution. When `allow_today=True` and today is the named day, returns today. When `allow_today=False`, always returns at least 7 days ahead.

**`_term_matches_in_text(lowered, term)`** has a length-based switch: terms ≤4 chars use a strict word-boundary regex (`(?<![a-z0-9])term(?![a-z0-9])`) to prevent false-positive matches like "gym" inside "gymnastics"; terms >4 chars use plain substring match. The threshold matches the fact that all FAMILY_ALIASES terms with potential collisions ("gym", "art", "kid") are short.

**`extract_search_label`** is a curated cascade with hand-tuned shortcuts for high-frequency queries (gymnastics, golf lessons, yoga + weekend, kids activities + weekend). When no shortcut matches, it derives a label from slot state (sports / arts / education / outdoors / martial_arts + date_range presence). The terminal fallback picks the longest non-stop-word ≥4 chars from the message, replacing underscores with spaces. Final fallback is the literal `"events matching that"`.

**`extract_broaden_category`** has a fixed priority: `audience == "kids"` first, then `date_range` presence, then activity family. Audience-first because "kids activities" is the most common UX-friendly broaden phrase.

**`expand_query_synonyms`** is a flat scan: for each `QUERY_SYNONYMS` key, if the key appears as a substring in the lowercased message, append all its synonyms. No deduplication of the returned list — callers are responsible for handling duplicates.

**`push_recent_utterance`** mutates `search_block["recent_utterances"]` in place via `setdefault([])` then `append(...)` then `pop(0)` until length ≤3. Phrases <2 chars after stripping are silently dropped.

## Conventions

**Last-write-wins merging.** All four `merge_*` helpers return the new value if non-`None`, else the existing. This means a fresh extraction always overrides whatever was in session state; partial extractions don't accumulate. Acceptable because each `extract_*` is run on each turn.

**Priority ordering matters.** `extract_activity_family`'s `["martial_arts", "sports", "arts", "education", "outdoors"]` is deliberate. Rearranging it changes which family wins for messages mentioning multiple terms.

**Substring-match-by-default.** Most matching uses Python's `in` operator on lowercased text. The only word-boundary exceptions are short terms in `_term_matches_in_text` and the `\b\d{1,2}\s*year\s*old\b` regex in `extract_audience`.

**FAMILY_ALIASES → ACTIVITY_TYPES coupling.** The five family keys in `FAMILY_ALIASES` (`martial_arts`, `sports`, `arts`, `education`, `outdoors`) match the five keys in `app.core.search.ACTIVITY_TYPES`. The two dicts are read together; renaming a key in one without the other breaks the slot-filtering pipeline silently.

**Recent-utterance cap.** `push_recent_utterance` caps at 3 entries. Older entries fall off via FIFO. This is a session-state convention used by upstream callers; not load-bearing here, just enforced.

**`expand_query_synonyms` doesn't dedupe.** When two anchor phrases share synonyms (e.g., `"music"` and `"live music"`), duplicates appear in the returned list. Acceptable because callers (`search.py`) use the result as a substring scan, not a set membership test.

## Known limitations and design notes

**Date-range vocabulary is fixed.** No support for "in two weeks", "the 15th", "next Saturday morning", date-range syntax with hyphens, or month-name dates ("May 8"). Adding any of these requires extending the cascade. The Tier 2 LLM parser (`app/chat/tier2_parser.py`) handles the longer tail.

**`extract_audience`'s kids triggers are broad.** `"my daughter"` and `"my son"` fire even in non-search contexts (e.g., add-event flows). Callers must filter intent before consulting the audience slot.

**`expand_query_synonyms` is one-directional.** If the message contains `"poker run"` (a synonym for `"boat race"`), the synonyms for `"boat race"` are NOT returned — only matches against the canonical key trigger expansion. The synonym→key relation isn't bidirectional because the dict isn't structured as a graph.

**`extract_search_label`'s curated shortcuts can drift from copy.** The hand-tuned strings ("gymnastics classes for kids", "yoga events coming up") are in the source code; if `app/core/conversation_copy.py` evolves the broader voice, these stay frozen until manually updated.

**`_is_weekend_date_range` is span-based, not weekday-based.** A 2-day range starting on Wednesday would NOT be flagged as a weekend, but a 2-day Mon–Tue range WOULD be (`span == 1`). The function assumes callers only pass weekend-like ranges; misuse silently produces wrong labels.

**Stop-word list in `extract_search_label` is hardcoded.** ~25 stop words baked into the function body. Tuning requires code changes.

**`extract_location_hint` is permissive.** `"at the corner store"` returns `"the corner store"` — no entity-resolution, no validation against known locations. Downstream `search_events` uses this hint as a substring filter against `Event.location_name`.

## Configuration

No environment variables. All thresholds and curated lists are module-level constants:

- `DAY_NAMES`, `FAMILY_ALIASES`, `QUERY_SYNONYMS` — exported.
- `_term_matches_in_text` length threshold (`<= 4`) — module-private literal.
- `push_recent_utterance` cap (`> 3`) — module-private literal.
- `extract_location_hint` regex bounds (`{2,60}` capture, `[:120]` cap) — module-private literals.

## Related

**Direct callers:**

- `app/core/search.py` — primary consumer; uses `extract_search_label`, `extract_broaden_category`, `expand_query_synonyms`, plus indirect use of `FAMILY_ALIASES` keys via `ACTIVITY_TYPES` matching.
- `app/core/intent.py` — uses `extract_activity_family`, `extract_audience`, `extract_date_range` for refinement detection (see `_refinement_looks_like_filter`) and date-or-time gating.
- `app/core/program_search.py` — slot extraction for program (recurring class) search.
- `app/chat/tier2_db_query.py` — slot extraction for Tier 2 DB query routing.
- `app/chat/intent_classifier.py` — uses `extract_date_range` alongside the LLM-driven Tier 1 classification.

**Tests:**

- `tests/test_phase8_5.py`, `tests/test_phase2.py`, `tests/test_tier2_schema.py` — direct slot-extraction coverage.

**Direct dependencies:** `datetime`, `calendar.monthrange`, `re` (stdlib only).

**Cross-references:**

- `docs/components/search.md` — describes how the slot dict is consumed at the search pipeline.
- `docs/components/intent.md` — describes how slots gate intent refinement detection.
- `docs/search-pipeline-for-claude.md` — historical pipeline doc with full slot semantics.
