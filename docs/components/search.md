# search

`app/core/search.py` (~1,025 lines)

## Purpose

The core event-search pipeline — semantic + keyword retrieval, slot-driven strategy dispatch, conversational nudge formatting. Given the user's free-form message, a slot dict from `app/core/slots.py`, and a SQLAlchemy `Session`, returns a ranked list of `Event` rows along with structured outcome metadata (suppressed-low-relevance, slot-filter-exhausted, honest-no-match, all-recurring) that the chat formatter consumes to choose between an event list and a no-match nudge. Also provides display-side helpers (`format_search_results`, `_event_card`, group headings) and the strategy-decision logic (`decide_search_strategy`).

This module is the single largest in `app/core/` and has the deepest behavioral surface in this slice's batch. The pipeline is multi-stage: query embedding generation (OpenAI or 1536-dim deterministic fallback), candidate gathering via SQLAlchemy date-window queries, optional activity-family filtering, optional literal-match filtering for short noun-focused queries, embedding-based scoring with a +0.5 specific-phrase bonus, threshold filtering with separate logic for OpenAI vs deterministic embeddings, keyword-based scoring for events without embeddings, merge with dedup by id, time-scoped sort with recurring events deprioritized, and three outcome flags computed for the formatter.

## Public surface

**Search entry points:**

- **`search_events(db, date_context, activity_type, keywords, query_message="", *, strict_relevance=True, audience_hint=None, flags_query=None) -> SearchOutcome`** — main pipeline. Returns a frozen `SearchOutcome` dataclass.
- **`search_events_keyword_only(db, date_context, activity_type, keywords) -> list[Event]`** — keyword-only path (no embeddings, no scoring), used by lighter callers.
- **`decide_search_strategy(slots, listing_mode, message) -> SearchStrategy`** — string Literal; returns one of `"RUN_BROAD"`, `"RUN_FILTERED"`, `"RUN_WITH_NUDGE"`, `"CLARIFY_DATE"`.

**Display formatters:**

- **`format_search_results(events, strategy, slots, *, append_narrow_hint=None, message="", outcome=None) -> str`** — main formatter. Handles zero/one/2-3/4+ event cases with different layouts; surfaces nudge copy and narrow-down hints based on strategy.
- **`format_results(events, *, append_narrow_hint=None) -> str`** — convenience wrapper for callers/tests that don't have a strategy or slots. Defaults to `"RUN_FILTERED"` with empty slots.

**Post-search filters:**

- **`apply_audience_location_filters(events, audience, location_hint) -> list[Event]`** — soft-filter (filters only when at least one match remains; otherwise returns unfiltered).

**Embedding helpers:**

- **`generate_query_embedding_with_source(text) -> tuple[list[float], bool]`** — `(vector, openai_used)`. Vector is 1536-dim either way (OpenAI or deterministic).
- **`generate_query_embedding(text) -> list[float]`** — convenience wrapper returning just the vector.

**Diagnostic emitter:**

- **`emit_search_diag_embedding_block(...)`** — env-gated stdout diagnostics; no-op unless `SEARCH_DIAG_VERBOSE` is set (read via `app.core.search_log.is_search_diag_verbose`).

**Module-level types and constants:**

- **`SearchOutcome`** — frozen dataclass: `events: list[Event]`, plus four bool flags (`suppressed_low_relevance`, `slot_filter_exhausted`, `honest_no_match`, `all_recurring`).
- **`SearchStrategy`** — `Literal["RUN_BROAD", "RUN_FILTERED", "RUN_WITH_NUDGE", "CLARIFY_DATE"]`.
- **`ACTIVITY_TYPES`** — `dict[str, list[str]]` mapping the five family keys to title/description match terms. The keys match `app.core.slots.FAMILY_ALIASES` keys exactly.
- **Threshold constants** — `EMBEDDING_RELEVANCE_THRESHOLD = 0.35`, `KEYWORD_RELEVANCE_THRESHOLD = 0.35`, `SPECIFIC_QUERY_EMBEDDING_THRESHOLD = 0.55`.
- **`SEARCH_QUERY_EMBEDDING_MODEL = "text-embedding-3-small"`** — the OpenAI model name.
- **Display strings** — `NARROW_DOWN_CLOSING`, `SEARCH_ZERO`, `SEARCH_FEW_INTRO`, `GROUP_EMOJI`.

## Inputs and outputs

**`search_events` inputs:**

- `db: Session` — SQLAlchemy session.
- `date_context: dict[str, date] | None` — typically `{"start": date, "end": date}` from `slots.extract_date_range`. `None` means "future events from today onward".
- `activity_type: str | None` — one of the `ACTIVITY_TYPES` keys (`"sports"`, `"arts"`, etc.) or `None` for no family filter.
- `keywords: list[str]` — extra terms for the SQL `LIKE` filter and the keyword-row scoring path.
- `query_message: str` — the (potentially synonym-expanded) embedding source. Used for embedding generation.
- `strict_relevance: bool = True` — when `False`, threshold filtering is bypassed and events without embeddings come back with score `0.0`.
- `audience_hint: str | None = None` — optional bias for the keyword scorer (`"kids"`, `"adults"`, `"family"`).
- `flags_query: str | None = None` — the user's *raw* (no-synonym-expansion) words for short-query and literal rules. When `None`, falls back to `query_message`.

**`search_events` output: `SearchOutcome`.** The `.events` list is ordered (relevance-first when no date context; recurring-deprioritized + chronological when time-scoped). The four flags drive the formatter's no-match-vs-list choice:

- `suppressed_low_relevance` — strict mode found candidates but every embedding/keyword score was below threshold; events list is empty by suppression.
- `slot_filter_exhausted` — activity-family filter eliminated all candidates from a non-empty pre-filter set.
- `honest_no_match` — strict mode + non-empty candidates + the user named a specific activity/noun → events list is empty and the formatter should say so explicitly.
- `all_recurring` — time-scoped + non-empty events + every event's `is_recurring` is True. Surfaces in the formatter as a hint to the user.

**`decide_search_strategy` output:**

- `"RUN_BROAD"` — listing mode; show everything with no relevance gate.
- `"RUN_FILTERED"` — both date and activity slots present; tight-filter run with strict thresholds.
- `"RUN_WITH_NUDGE"` — partial slots; run + append a "tell me more" nudge.
- `"CLARIFY_DATE"` — open-ended search query with no slots filled (e.g., "what's good?"); ask for a date before searching.

**`format_search_results` output.** A string formatted for chat display. Layout depends on event count:

- **0 events** — outcome-aware empty message via `_honest_no_match_body` (when any outcome flag is set) or `_empty_message_for_slots` otherwise.
- **1 event** — "Found one that might work:\n\n" + `_event_card(e)`.
- **2–3 events** — `SEARCH_FEW_INTRO` ("Here are your matches:") + numbered list of `_event_card`s.
- **4+ events** — grouped by `_classify_event_type` with `_group_heading`s and `GROUP_EMOJI`s; appends `NARROW_DOWN_CLOSING` when `append_narrow_hint=True` (or `len(events) >= 4` by default).
- **>8 events** — caps display at 8 with a "…and N more" tail.

## Internal structure

**`search_events` is a ten-stage pipeline:**

1. **Embedding source preparation.** `embedding_source` defaults to `query_message`, falling back to space-joined keywords or `activity_type` or `"events"`. `flags_text` (raw user words) is used for short-query/literal rules so synonym expansion in `query_message` doesn't widen literal-match logic.
2. **Query embedding.** `generate_query_embedding_with_source` returns `(vector, openai_used)`; `dim = len(vector)` (1536 either way).
3. **Specific-query detection.** `_query_has_specific_noun(flags_text)` checks for any of ~80 curated specific phrases (`_SPECIFIC_PHRASES`: water sports, places, dining, entertainment, wellness). When a specific phrase fires, the embedding threshold is raised to `0.55`.
4. **Short-noun-focused detection.** `_is_short_noun_focused_query(flags_text)` — fires for 1–2 word queries that aren't generic listing phrases. When fires + literal terms exist, the candidate set is filtered down to events that match those literal terms (per `_event_matches_literal_query`).
5. **Candidate gathering.** `_base_future_events_query(db, date_context)` builds a SQLAlchemy query with date-overlap logic: when `date_context` is supplied, filter events whose `[date, end_date or date]` range overlaps `[start, end]`; otherwise filter for `coalesce(end_date, date) >= today`.
6. **Activity filter.** When `activity_type` is supplied, narrow candidates to those with any term from `ACTIVITY_TYPES[activity_type]` in the title or description. If the filter produces an empty set from a non-empty pre-filter, returns `SearchOutcome(events=[], slot_filter_exhausted=True, ...)` and exits early.
7. **Literal-match filter.** When `require_literal_match` is set, narrow candidates to those passing `_event_matches_literal_query(e, literal_terms, flags_text)`. Tracks the set of literal-matched event ids for later threshold-bypass logic.
8. **Embedding split + scoring.** Each candidate with `len(event.embedding) == dim` goes to `with_emb` (paired with its cosine score); others go to `without_emb`. For specific queries with embeddings, a +0.5 bonus is applied to events whose title/description contains a matching specific phrase or expanded synonym (`slots.expand_query_synonyms`).
9. **Threshold filtering.** Strict mode + non-empty `with_emb`:
   - **OpenAI embedding path:** the `effective_threshold` (0.35 or 0.55) gates non-literal-matched events. If even the best non-literal score is below threshold, only literal-matched events survive. Otherwise events at or above threshold survive, plus any literal-matched.
   - **Deterministic fallback path:** for specific queries only, drops events with score ≤ 0.45 (the 0.5 bonus floor) unless they're literal-matched. The fallback path's scores are noisy so threshold-by-magnitude is the only meaningful gate.
10. **Keyword path + merge + sort.** `with_emb` sorts by score descending. `keyword_rows` accumulates from `without_emb`: in strict mode, each event must pass `_event_matches_keyword_terms` (all `keywords` substrings present) AND `_keyword_passes_threshold` (token-overlap score ≥ 0.35 with at least one field hit). Literal-matched events bypass the threshold check (explicit override). The two lists merge with id-dedup (embedding rows win on ties). `_apply_time_scoped_merged_sort` sorts time-scoped results as `(is_recurring, -score, date, start_time)` — pushes recurring events to the bottom — and otherwise as `(-score, date, start_time)`.

After the pipeline, three outcome flags are computed:

- **`suppressed`** — strict + OpenAI embedding + empty results + non-empty candidates + (best embedding score < threshold OR best keyword score < threshold).
- **`honest_no_match`** — strict + empty results + non-empty candidates + the user named an activity token / specific noun / required literal match.
- **`all_recurring`** — time-scoped + non-empty events + all `is_recurring=True`.

**`decide_search_strategy`** is a flat dispatch on the three slot booleans (date / activity / audience / location). When all four are empty AND the message is open-ended ("what's good"), returns `"CLARIFY_DATE"`. Otherwise the only `"RUN_FILTERED"` case is date+activity both present; everything else is either `"RUN_BROAD"` (listing mode) or `"RUN_WITH_NUDGE"` (any partial-slot configuration).

**`format_search_results`** is layered on event count:

- Empty + outcome flag set → `_honest_no_match_body(message, slots)` calls `slots.extract_search_label` and `slots.extract_broaden_category` to compose `NO_MATCH_HONEST` + optionally `NO_MATCH_BROADEN`.
- Empty + no outcome flag → `_empty_message_for_slots` picks between `NOTHING_IN_RANGE`, `NOTHING_FOR_ACTIVITY`, or `SEARCH_ZERO` based on which slots are present.
- Non-empty + `RUN_WITH_NUDGE` → appends `LISTING_NUDGE_DATE_SET` / `LISTING_NUDGE_ACTIVITY_SET` / `LISTING_NUDGE_NONE` based on which slots are present.
- Non-empty + 4+ events → groups via `_classify_event_type` + `_group_heading`, sorted with `"General"` last; appends narrow-down closing line by default.

**`generate_query_embedding_with_source`** has two paths: OpenAI `embeddings.create(model=SEARCH_QUERY_EMBEDDING_MODEL, input=text)` returning a 1536-dim vector, or `_deterministic_embedding_1536(text)` falling back to a 1536-dim hash-bucketed L2-normalized vector. The deterministic path spreads each token across 16 hash positions (offset by `i * 7919`) with weights `1.0 / (i + 1)`, then normalizes. Same-text reproducibility within a process; cross-process variance because Python's `hash()` is randomized.

## Conventions

**Strict relevance is the default.** `search_events` defaults to `strict_relevance=True` and applies threshold filtering. Callers wanting all candidates regardless of score must opt in with `strict_relevance=False`.

**Specific-noun queries raise the embedding bar.** When `_SPECIFIC_PHRASES` matches, the embedding threshold goes from `0.35` → `0.55`. The +0.5 bonus on title/description matches makes literal hits surface as ~0.85+ scores even when the raw embedding score is mediocre, so the higher bar still admits literal hits while suppressing junk.

**Literal-match bypass.** Events explicitly matching `_event_matches_literal_query` skip threshold filtering. Without this, a specific query like "boat race" might suppress genuinely-matching events whose embeddings happen to score below 0.55. The bypass is conservative — only fires when literal terms exist AND the query is short-noun-focused.

**Embedding-row dedup wins.** When merging `with_emb` and `keyword_rows`, embedding rows (with their cosine scores) keep their position; matching keyword rows are dropped. This avoids double-counting the same event under different score regimes.

**Time-scoped recurring-deprioritization.** When a date context is present, recurring events sort to the bottom of the merged list (`is_recurring` first key in the sort tuple). Rationale: a date-bounded query like "this Saturday" should highlight one-off events rather than a recurring weekly class that happens to fall in range.

**`activity_type` is a substring match against title + description.** No fuzzy matching, no embedding consultation. The `ACTIVITY_TYPES` term lists are deliberately tight; expanding them widens false positives.

**Audience hint is a keyword-scorer boost, not a hard filter.** `audience_hint="kids"` raises the keyword score and field-hit count for events containing kid/child/youth/teen/family/tween/student tokens — but doesn't filter out non-matching events. Hard audience filtering happens later in `apply_audience_location_filters` (separate function, called separately).

**Location hint is a soft filter.** `apply_audience_location_filters` filters by `location_hint` substring match, but only when at least one event matches; otherwise the unfiltered list is returned. Same pattern for audience filtering — soft-filter degrades gracefully when no event matches.

**Group heading display order.** `format_search_results` sorts groups with `(category != "General", category)` — so `"General"` always appears first when present. Other categories sort alphabetically.

## Known limitations and design notes

**Full table scan on every search.** `_base_future_events_query` has a date-window filter but no embedding-side index. With ~hundreds of events the embedding loop is fast; at ten thousand it would become the dominant latency. pgvector or a similar embedded vector index is the upgrade path; not warranted at current scale.

**Embedding fallback noise.** `_deterministic_embedding_1536` produces structured-but-arbitrary vectors. Cosine scores between fallback vectors are statistically uncorrelated with semantic similarity; the only meaningful behavior is "exact-text matches still score higher than unrelated." The threshold logic for the fallback path (drop scores ≤ 0.45 unless literal-matched) reflects this — magnitude-based gating, not similarity-based.

**Hash randomization across processes.** Python's `hash()` is randomized per process by default. Same query text produces different fallback vectors across uvicorn workers/restarts. Acceptable because OpenAI is the production path; the fallback only fires when the API is unreachable.

**Embedding dimension assumed 1536.** The query path always produces 1536-dim. Stored event embeddings can be 1536-dim (extracted via OpenAI in `app/core/extraction.py`) or 32-dim (extracted via `extraction.py`'s deterministic fallback). The dim-match guard at `with_emb` split silently routes mismatched events to keyword-only scoring. See `docs/components/extraction.md` for the asymmetry detail.

**Keyword scorer is token-overlap, not TF-IDF.** Score is `matched_tokens / total_query_tokens`. No corpus-level term-rarity weighting. `keywords` parameter is treated as substring filters (must all be present in title+desc+location), and the scorer derives its own tokens from `query_text` independently.

**`_SPECIFIC_PHRASES` is curated and frozen.** Adding a new specific noun to bias the threshold requires a code change; no dictionary lookup or learned vocab.

**Activity-family filter cascades from slots.py.** When `activity_type=None` is passed but the user's message contains an activity term, the filter is skipped — the caller is responsible for resolving slots before calling. A tighter coupling would re-extract slots inside `search_events`; intentionally not done to keep the function call-shape small.

**`format_search_results`'s grouping is by activity classification, not search relevance.** Events grouped by `_classify_event_type` across the four-or-more case lose their relevance ordering — within a group, events appear in their merged-sort order, but cross-group ordering is alphabetic. Tradeoff: visual scanability for relevance fidelity.

**Diagnostic emitter is stdout-only.** `emit_search_diag_embedding_block` writes to stdout, not a logger. Driven by env var `SEARCH_DIAG_VERBOSE`. Useful for local debugging; not picked up by structured logs in production.

**`_next_weekday` is duplicated.** The same helper exists in `app/core/slots.py` with identical signature and body. Refactoring opportunity, not load-bearing.

## Configuration

**Environment variables.**

- `OPENAI_API_KEY` — required for the OpenAI embedding path. Missing key triggers the deterministic 1536-dim fallback.
- `SEARCH_DIAG_VERBOSE` — when set (read via `app.core.search_log.is_search_diag_verbose`), emits per-search stdout diagnostics with the top-5 candidates by embedding score.

**Imported timeout.** `LLM_CLIENT_READ_TIMEOUT_SEC` from `app.core.llm_http` is passed to every `OpenAI(...)` constructor.

**Module-level thresholds:**

- `EMBEDDING_RELEVANCE_THRESHOLD = 0.35` (general queries).
- `KEYWORD_RELEVANCE_THRESHOLD = 0.35` (keyword path + audience-hint floor).
- `SPECIFIC_QUERY_EMBEDDING_THRESHOLD = 0.55` (raised bar for queries containing `_SPECIFIC_PHRASES` terms).
- `SEARCH_QUERY_EMBEDDING_MODEL = "text-embedding-3-small"` (OpenAI model name).

## Related

**Direct callers in `app/`:**

- `app/admin/router.py:336` — imports `_deterministic_embedding_1536` for embedding regeneration (not the full search pipeline).
- (No `app/chat/*` runtime caller of `search_events` / `format_search_results` post the legacy `/chat` removal — search is now invoked from the chat surface via Tier 2 / Tier 3 routes that build their own SQL queries. This module remains the canonical source of search/scoring/formatting logic for direct callers.)

**Direct callers in `tests/`:**

- `tests/test_phase8.py`, `tests/test_phase8_5.py`, `tests/test_phase8_9_event_ranking.py`, `tests/test_phase5.py`, `tests/test_phase87_privacy.py` — exercise the full search pipeline + display formatting.

**Direct dependencies:**

- `sqlalchemy` (`and_`, `or_`, `func`, `Session`) — query builder.
- `app.db.models.Event` — the row type being filtered/sorted.
- `app.core.slots` — `extract_broaden_category`, `extract_search_label`, `expand_query_synonyms`, plus `QUERY_SYNONYMS` (imported lazily inside helpers).
- `app.core.dedupe.cosine_similarity` — the math helper for embedding score.
- `app.core.intent.open_ended_search_message` — the "what's good?" detector.
- `app.core.conversation_copy` — `LISTING_NUDGE_*`, `NO_MATCH_*`, `NOTHING_*`, `SEARCH_INTRO_MANY` strings.
- `app.core.search_log.is_search_diag_verbose`, `log_candidates` — diagnostic + telemetry hooks.
- `app.core.llm_http.LLM_CLIENT_READ_TIMEOUT_SEC` — OpenAI timeout.

**Cross-references:**

- `docs/components/slots.md` — the slot dict shape this module consumes; describes `extract_search_label` and `extract_broaden_category` semantics.
- `docs/components/dedupe.md` — `cosine_similarity` semantics and the related Event-storage embedding shape (1536-dim or 32-dim).
- `docs/components/extraction.md` — the source of stored `Event.embedding` vectors; explains the dim-mismatch handling.
- `docs/components/conversation_copy.md` — the nudge / no-match copy strings consumed by the formatter.
- `docs/components/llm_http.md` — timeout helper shared across OpenAI clients.
- `docs/search-pipeline-for-claude.md` — historical pipeline doc with the full algorithmic spec.
