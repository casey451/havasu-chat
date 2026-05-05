# context_builder

`app/chat/context_builder.py` (~141 lines)

## Purpose

Assemble the **catalog context block** that Tier 3 sends to Anthropic Haiku. The block is plain text shaped as "Provider X / category / address / phone / programs / upcoming events" — capped at `MAX_CONTEXT_WORDS = 1500` words so the prompt stays well within Haiku's input budget after the system prompt and user message are added. Excludes drafts, inactive programs, and past events; favors the entity-matched provider (if any) by listing it first.

## Public surface

**`build_context_for_tier3(query: str, intent_result: IntentResult, db: Session) -> str`** — Return a plain-text context string. Never empty: when the catalog has no usable rows, returns the canonical "no providers available, answer conservatively" message so Tier 3 still has something to ground on.

**`MAX_PROVIDERS = 10`** — Cap on providers in the block.

**`MAX_CONTEXT_WORDS = 1500`** — Word-budget cap. Empirical, tuned so the block + system prompt + user query stays comfortably under Haiku's input limit with prompt caching active.

## Inputs and outputs

**Input.**
- `query`: free-text user query (currently unused inside the function but in the signature for future query-aware fetching).
- `intent_result`: classifier output. The `entity` field, if non-empty, is used to bring a specific provider to the front.
- `db`: SQLAlchemy session.

**Output.** A plain-text block of variable length, always under `MAX_CONTEXT_WORDS`. Format:

```
Context — Lake Havasu catalog snapshot (programs and events may be partial):

Provider: <name>
  category: <category>
  address: <address>
  phone: <phone>
  website: <website>
  hours: <hours-truncated-to-200-chars>
  verified: yes
  Program: <title> | ages X-Y | schedule HH:MM-HH:MM | cost: <cost> | note: <schedule_note>
  Upcoming event: <title> on YYYY-MM-DD at HH:MM — <location_name>
...
```

## Internal structure

`_fetch_provider_rows` is the routing logic:

1. Fetch active, non-draft providers (`Provider.draft = False AND Provider.is_active = True`).
2. If none, fall back to **verified, non-draft** providers ordered by name, capped at `MAX_PROVIDERS`. (The fallback is the empty-catalog-ish path; the message string returned by `build_context_for_tier3` warns Tier 3 to answer conservatively.)
3. If `intent_result.entity` is non-empty, partition active providers into `matched + rest` so the entity-matched row is first. Otherwise sort by `(not verified, name)` so verified rows lead.
4. Cap to `MAX_PROVIDERS`.

`_programs_for` and `_events_future_for` query per-provider. Programs filter by `is_active = True`. Events filter by `status = 'live' AND date >= today`, ordered ASC by date+start_time, capped at 8 per provider.

`_truncate_hours` clamps the `Provider.hours` Text field to 200 characters with an ellipsis. Hours are free text in the schema (legacy from pre-`hours_structured` era); long entries from contribution form fields would otherwise dominate the budget.

`_trim_to_word_budget` is the final guard: count whitespace-split words, take the first `MAX_CONTEXT_WORDS` if over budget. Not token-aware (a word ≠ a token), but conservative — `1500 words` ≈ 2000 tokens, leaving substantial headroom for system prompt + user text + response budget.

## Conventions

**Provider-first ordering.** The block is provider-centric: each provider gets its own section with its programs and events nested. Tier 3 is then prompted to ground answers in this structure rather than reasoning across event-only or program-only lists.

**Entity-match wins position, not budget.** A matched provider is listed first, but its program/event nesting is still capped at the same per-provider numbers. The rationale: even when the user names a provider, Haiku may need adjacent rows to suggest alternatives.

**Word budget over token budget.** `MAX_CONTEXT_WORDS = 1500` is approximate; actual tokens depend on tokenizer behavior. Acceptable because the budget leaves substantial headroom against Haiku's input limit, and any over-budget request would surface as a clear API error rather than silently truncating mid-response.

**Live events only.** `status='live' AND date >= today`. Pending and past events are excluded — pending because the user would be told something not yet approved; past because Tier 3 should not surface stale events.

**Programs use `is_active`, events use `status`.** Different status models (programs are evergreen with an active flag; events are time-windowed with a lifecycle). Documented in `docs/components/tier1_handler.md` and the model definitions.

## Known limitations and design notes

**Word budget is not tokenizer-aware.** A 1500-word block with many long URLs or unusual punctuation could tokenize denser than expected. The headroom usually covers this; if Tier 3 ever errors on input length, lower `MAX_CONTEXT_WORDS` rather than adding tokenizer integration.

**No query-aware filtering.** `query` is in the signature but unused. Every Tier 3 call gets roughly the same block (modulo entity matching). A future improvement: BM25 or embedding-based provider ranking against the query before the `MAX_PROVIDERS` cap. Out of scope until production data shows the block is the bottleneck.

**Schedule format is `HH:MM-HH:MM` literal.** `Program.schedule_start_time` is stored as a `String(5)` (the schema-time-type inconsistency flagged in the structural review), so the block embeds the strings raw. If/when the schema is harmonized to `Time`, this site needs updating.

**`hours` truncation is naïve.** `_truncate_hours` chops at 200 chars + ellipsis, which can land mid-word or mid-day-name. Acceptable because Tier 3 reads the block holistically; users see only the model's reasoning over it, not the raw block.

**Per-provider event cap is hard-coded at 8.** No tunable. With 10 providers × 8 events = potentially 80 events plus 10 provider headers — the word budget is the real cap.

**No provider-id passthrough.** The block names providers but doesn't pass `Provider.id`. Downstream tasks that need to attribute back to a row (e.g., `mention_scanner` in `app/contrib/`) re-resolve by name. Acceptable; names are stable enough.

## Configuration

No environment configuration. Module constants are the only knobs.

## Related

**Direct callers:**

- `app/chat/tier3_handler.py` `answer_with_tier3` — calls once per Tier-3 turn; the result is the `context` portion of `user_text`.
- `tests/test_context_builder.py` — coverage of provider ordering, budget enforcement, fallback path, and entity-first behavior.

**Direct dependencies:**

- `app.db.models.Provider`, `app.db.models.Program`, `app.db.models.Event`.
- `app.chat.intent_classifier.IntentResult` — for the `entity` field.

**Cross-references:**

- `docs/components/tier3_handler.md` — describes the prompt assembly that uses this block.
- `docs/persona-brief.md` §3.9 — Tier 3 grounding-only carve-outs.
