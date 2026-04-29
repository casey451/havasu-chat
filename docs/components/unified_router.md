# unified_router

`app/chat/unified_router.py`

## Purpose

The unified router is the single entry point for `POST /api/chat`. It takes a user query plus a session ID, runs it through a fixed pipeline (normalize the text, classify intent, extract optional onboarding hints, enrich with catalog-entity match, dispatch to a mode-specific handler, log the turn), and returns a structured response describing what was answered, how, and at what cost. Every step is wrapped to fail soft: if any non-handler stage raises, the router logs the exception and continues with degraded but still-useful state. If a handler raises, the router returns a graceful fallback message rather than a 500. The router itself contains no domain logic — it owns the pipeline shape and the dispatch decisions, and delegates everything else (Tier 1 templates, Tier 2 structured retrieval, Tier 3 LLM synthesis, intake placeholders) to handler modules.

## Public surface

Two symbols are imported by other code:

**`route(query: str, session_id: str | None, db: Session) -> ChatResponse`**

The pipeline entry point. Called once per chat turn. Never raises — all exceptions are caught internally and surface as a `ChatResponse` with `tier_used="placeholder"` and `response=FALLBACK_MESSAGE` (re-exported from `tier3_handler`). Always logs a row to `chat_logs` via `log_unified_route` before returning, regardless of success or graceful-degradation path.

**`ChatResponse` (dataclass)**

The return type. Fields:

- `response: str` — assistant message text to surface to the user.
- `mode: str` — one of `ask` | `contribute` | `correct` | `chat`. Reflects the classifier's decision, possibly overridden by the LLM router (see Internal structure).
- `sub_intent: str | None` — fine-grained intent label within mode (e.g. `TIME_LOOKUP`, `NEW_EVENT`, `GREETING`). Schema lives in `intent_classifier`.
- `entity: str | None` — canonical provider name if the query (or a fresh prior turn) resolves to a catalog provider; otherwise `None`.
- `tier_used: str` — which path produced the response. See "Tier-used taxonomy" below.
- `latency_ms: int` — wall-clock pipeline duration, floor 1.
- `llm_tokens_used: int | None` — total tokens (input + output) across all LLM calls in this turn. `None` when no LLM was called or counts weren't available.
- `llm_input_tokens: int | None` — input-side tokens only. Same null semantics.
- `llm_output_tokens: int | None` — output-side tokens only. Same null semantics.
- `chat_log_id: str | None` — UUID of the `chat_logs` row written for this turn, or `None` if the insert failed (the response itself still returns successfully).

There is no public class hierarchy or factory — `route()` is called directly with a SQLAlchemy `Session`.

## Inputs and outputs

**Input.** `query` is the raw user text. `session_id` may be `None` (anonymous) or a string up to 128 chars (longer is truncated for the log bucket; the raw value is also used as the session-store key when non-empty). `db` is a SQLAlchemy `Session` — the router uses it for entity matching, recommended-entity capture, and chat logging, and passes it through to handlers.

**Output.** A `ChatResponse` (see above). The API layer (`app/api/routes/chat.py`) projects this into `ConciergeChatResponse`, which is a strict subset — the wire format keeps `response`, `mode`, `sub_intent`, `entity`, `tier_used`, `latency_ms`, `llm_tokens_used`, `chat_log_id` and drops the split-out `llm_input_tokens` / `llm_output_tokens`. Those split fields stay on the dataclass for the eval harness, which reads them in-process.

**Tier-used taxonomy.** The `tier_used` field is the most-grepped piece of router output, so its values are worth enumerating precisely:

| Value | Emitted by | Meaning |
|-------|------------|---------|
| `"1"` | this component | Tier 1 template handled the query (provider lookup, hours, etc.) |
| `"2"` | this component | Tier 2 structured retrieval returned a non-empty result |
| `"3"` | this component | Tier 3 (Anthropic LLM) synthesized the response |
| `"gap_template"` | this component | Catalog-gap template — Tier-1-shaped fact lookup with no entity hit |
| `"chat"` | this component | `chat` mode handler (greeting, small talk, out-of-scope) |
| `"placeholder"` | this component | Either `contribute` / `correct` mode (Phase 4 stubs) or any graceful-fallback path after an exception |
| `"intake"` | reserved | Listed in dataclass docstring; not emitted today. Reserved for the Phase 4 contribute intake flow. |
| `"correction"` | reserved | Listed in dataclass docstring; not emitted today. Reserved for the Phase 4 correct flow. |
| `"track_a"` | other path | Defined in `app/db/chat_logging.TRACK_A_TIER_USED`. Tags rows from the legacy `POST /chat` endpoint. The unified router never emits this — but the value appears in `chat_logs` analytics. |

**Mode and sub-intent values.** `mode` is one of `ask` | `contribute` | `correct` | `chat`. Sub-intents differ by mode and are owned by `intent_classifier` (and, when on, the LLM router prompt). The full set the LLM router accepts is enumerated in `llm_router._SUB_INTENTS`; the heuristic classifier emits a subset. Document and keep these definitions in `intent_classifier` — the router treats them as opaque strings.

## Internal structure

The pipeline is a linear sequence of phases, each wrapped in try/except (with category-specific fallback behavior — see Conventions). At a glance, the eleven phases group into four chapters:

- **Prep (1–3):** setup, normalize, session touch.
- **Classification & memory (4–7):** classify, hint extraction, entity enrichment, query-side entity capture.
- **Dispatch & capture (8–10):** context build, mode dispatch, response-side recommended-entity capture.
- **Log (11):** single-exit log-and-return.

The phases in detail:

**1. Setup.** Capture start time, derive a stable session bucket for logging (`_stable_session_bucket` truncates a real session ID to 128 chars or generates a 24-char hex if absent), hash the query for the log row, and define two closures: `_ms()` for elapsed-time computation, and `_finish()` for single-exit logging-and-return.

**2. Normalize.** Call `normalizer.normalize(q_raw)` to lowercase, expand contractions, strip edge punctuation, collapse whitespace. If this fails, return `_GRACEFUL` immediately with `tier_used="placeholder"`. Without a normalized query, downstream classification is meaningless, so this is the only "hard" early-out before classification.

**3. Session touch.** If a non-empty `session_id` was provided, call `touch_session` (which auto-resets onboarding hints if the session has been idle >30 min), then read the session dict, increment `turn_number`, and capture `current_turn`. Failures here are caught and logged, but the pipeline continues — anonymous queries (no `session_id`) skip this phase entirely.

**4. Classify.** Call `intent_classifier.classify(nq_safe)` to produce an `IntentResult` with `mode`, `sub_intent`, `entity`, `confidence`, and the raw + normalized query strings. Classification failure is treated like normalize failure: return `_GRACEFUL` immediately. The router cannot dispatch without a mode.

**5. Hint extraction.** Call `hint_extractor.extract_hints(q_raw)`, which makes an OpenAI call (gpt-4.1-mini) to extract optional `age` and `location` from the query. If `OPENAI_API_KEY` is unset or the call fails, this returns `None` and the pipeline continues. If a session is active, `update_hints_from_extraction` runs afterward; it no-ops on `None` or empty extraction (latest-wins per field when hints exist).

**6. Entity enrichment.** Call `_enrich_entity_from_db`, which fills `intent_result.entity` if the classifier didn't already set it. Two strategies in order: (a) fuzzy-match the query against catalog provider names via `entity_matcher.match_entity` (rapidfuzz `token_set_ratio` strictly greater than 75); (b) if no match and the query contains a pronoun referent (`it`, `that`, `there`, `they`, `them`, `the place`, `that place`) and the session has a `prior_entity` from within the last 3 turns, reuse that prior entity. Failures here are caught and the pipeline continues with un-enriched classification.

**7. Entity capture (query-side).** If a session is active and the (now-possibly-enriched) `intent_result.entity` is non-empty, call `record_entity` to update the session's `prior_entity` slot. This is what feeds the pronoun-referent branch on the *next* turn.

**8. Context build.** Read `onboarding_hints` from the session if present (this populates the Tier 3 user-context line). Compute `now_line = "Now: {format_now_lake_havasu()}"` — Phoenix-time wall clock for inclusion in the Tier 3 prompt. Both are passed through to the ask handler regardless of mode, but only the ask path actually consumes them.

**9. Mode dispatch.** Branch on `intent_result.mode`:

- **`ask`** — the complex path; see "Ask handler" below.
- **`contribute`** — `_handle_contribute` returns a Phase-4 placeholder string (`"Contribute mode: type=…"`). `tier_used="placeholder"`.
- **`correct`** — `_handle_correct` returns the literal `"Huh, didn't know — want to update it?"`. `tier_used="placeholder"`.
- **`chat`** — `_handle_chat` dispatches on `sub_intent`: `GREETING` returns a session-stable variant from `_GREETINGS`; `OUT_OF_SCOPE` returns the canned out-of-scope reply; `SMALL_TALK` returns one of four short replies based on keyword detection (thanks/how-are-you/bye/default). `tier_used="chat"`.
- **fallthrough** — defensive; treats unknown modes as `ask`.

If any handler raises, the router catches and returns `_GRACEFUL` with the current `tier_used` (often `"placeholder"`).

**10. Recommended-entity capture (response-side).** After a Tier 2 or Tier 3 response, the router scans the *response text* for catalog provider mentions via `extract_catalog_entities_from_text`. If exactly one provider is mentioned, it gets recorded as the new `prior_entity`. Two-or-more mentions are ignored (ambiguous; can't pick a referent). Zero mentions also ignored. Tier 1, gap-template, chat, and placeholder responses skip this entirely.

**11. Log and return.** `_finish()` is called with the response text and metadata. It computes final latency, writes a `chat_logs` row via `log_unified_route` (which itself is wrapped in try/except — log failures don't break the user-facing response), and returns the `ChatResponse`.

### Ask handler

`_handle_ask` is where the real branching lives. The flow is:

```
                          ┌─→ try_tier1 ─→ tier_used="1" (if hit)
                          │
ask query ──→ catalog gap?─┤  USE_LLM_ROUTER on?
                          │      │
                          │      ├─ yes ─→ llm_router.route()
                          │      │            │
                          │      │            ├─ None ─→ tier 3
                          │      │            ├─ tier="2" + filters ─→ tier 2 → tier 3 on miss
                          │      │            └─ tier="3" ─→ tier 3
                          │      │
                          │      └─ no ──→ explicit-rec phrase? ─→ tier 3
                          │                  │
                          │                  └─ no ──→ tier 2 → tier 3 on miss
                          │
                          └─ if catalog gap (unentitied fact lookup):
                             same flow but allow_tier3_fallback=False;
                             on placeholder return, emit gap_template instead
```

The catalog-gap branch is not a separate pipeline — it runs the same Tier 1 / LLM-router / Tier 2 machinery as the normal ask path. The only differences are that `allow_tier3_fallback=False` is passed in (so a full miss returns `None` instead of falling through to Tier 3), and the outer caller substitutes the templated gap response with `tier_used="gap_template"` when that `None` comes back.

If the diagram doesn't render cleanly, the linear form is: Tier 1 → (USE_LLM_ROUTER on: LLM router → Tier 2 with precomputed filters or Tier 3) / (USE_LLM_ROUTER off: explicit-rec check → Tier 2 parser → Tier 3); catalog gap reroutes a placeholder return to the templated gap response.

A **catalog gap** is a Tier-1-shaped fact lookup (`DATE_LOOKUP`, `LOCATION_LOOKUP`, `HOURS_LOOKUP`) where no entity was matched — i.e., the user is asking about a specific thing that isn't in the catalog. In that shape, falling through to Tier 3 would let the LLM hallucinate facts about a place we don't know. The router instead returns a templated "I don't have that yet — add it at /contribute" message.

The **LLM router branch** activates when the `USE_LLM_ROUTER` env var is one of `1`, `true`, `yes`, `on` (case-insensitive). When on, after Tier 1 misses, the router calls `llm_router.route()` — a single Anthropic Haiku call returning a structured `RouterDecision` with `mode`, `sub_intent`, `entity`, `tier_recommendation` (`"2"` or `"3"`), and optional `tier2_filters` (a `Tier2Filters` schema, parser-output-shaped). On `RouterDecision`:

- The router's `mode`, `sub_intent`, `entity` overwrite the heuristic classifier's values for response purposes (via `router_meta`, see Conventions).
- If `tier_recommendation="2"`, the precomputed `tier2_filters` go straight into `try_tier2_with_filters_with_usage` (skipping the Tier 2 parser LLM call entirely). On Tier 2 miss, falls through to Tier 3.
- If `tier_recommendation="3"`, calls Tier 3 directly.
- If `llm_router.route` returns `None` (auth, network, JSON parse, validation failure — all caught inside the router module), the ask handler falls through to Tier 3.

The **heuristic branch** (default) activates when `USE_LLM_ROUTER` is unset or any value other than the four truthy strings. After Tier 1 misses, the router checks for explicit-recommendation phrasing (`_EXPLICIT_REC_PATTERNS`: "what should I do", "pick one", "which is best", "best", "worth it", "your favorite", "what would you do"). If matched, jump straight to Tier 3 — these queries want LLM voice, not catalog row dumps. Otherwise, try Tier 2 via the parser-driven `try_tier2_with_usage`, fall through to Tier 3 on miss.

## Conventions

**Router policy.** Extend behavior in handlers and classifiers; extend orchestration here only when the pipeline shape itself changes. The router's job is dispatch, not domain logic.

**Defensive try/except is the dominant pattern.** Almost every step in `route()` is wrapped, and the wrappers fall into three categories:

1. *Critical preconditions* (normalize, classify) — failure returns `_GRACEFUL` immediately. The pipeline can't continue without these.
2. *Best-effort enrichment* (session touch, hint extraction, entity enrichment, entity capture, onboarding-hints read, recommended-entity capture) — failure logs and continues. The user gets a response; the session might be slightly stale.
3. *Mode dispatch* — failure returns `_GRACEFUL` with whatever `tier_used` was last set. The `try` here is the broadest; specific handlers also have their own internal error handling.

When extending the pipeline with a new step, decide which category it falls into and wrap accordingly. The pattern is `logging.exception("unified_router: <step> failed")` for category 2 — the prefix makes log triage straightforward.

**`_finish()` is the single exit point.** All return paths in `route()` go through the `_finish` closure, which computes latency, writes the chat log, and constructs the `ChatResponse`. This guarantees every turn is logged exactly once, regardless of which branch produced the response. Don't add early `return ChatResponse(...)` statements; route them through `_finish`.

**`router_meta` as out-parameter.** `_handle_ask` accepts a `router_meta: dict | None` and writes the LLM router's `mode` / `sub_intent` / `entity` overrides into it when an LLM-routed decision is made. The outer `route()` reads `router_meta` after the handler returns to update the response fields. This is unusual (Python prefers tuple returns), but the alternative (returning a 6-tuple) was uglier and the override is conditional. If more override fields accumulate, refactor to a small result dataclass instead of growing the dict further.

**`now_line` is built once per turn and threaded through.** The Phoenix-time stamp is computed at context-build (phase 8) and currently consumed only by the ask path. Chat-mode and contribute-mode handlers don't receive it. Negligible cost (one `format_now_lake_havasu()` call) — if a future handler needs the timestamp, it's already computed; just thread it through the same way.

**`tier_used` naming convention.** Numeric strings (`"1"`, `"2"`, `"3"`) for the three handler tiers. Named strings (`"gap_template"`, `"chat"`, `"placeholder"`, `"intake"`, `"correction"`, `"track_a"`) for non-tier paths and reserved values. Keep this split when adding new values — don't introduce `"4"` for a new code path; it will read as a tier and confuse analytics.

**`USE_LLM_ROUTER` flag handling.** Read once per request via `_use_llm_router()` (no caching) so changes propagate per-turn. The eval harness (`app/eval/confabulation_invoker.py`) toggles this env var per probe to compare on/off behavior; the read-once-per-request pattern is what makes that possible. Many router-focused test modules pin the flag off via a `_disable_llm_router` autouse fixture (e.g. `test_unified_router.py`, `test_tier2_routing.py`, `test_classifier_hint_extraction.py`); other modules drive the flag explicitly with `patch.dict` (e.g. `test_llm_router_integration.py`). Pick the pattern that matches whether the test asserts default behavior or the LLM-router path specifically.

**Entity-matcher row cache.** `entity_matcher._rows` is process-global and refreshed lazily on first `match_entity` call (and explicitly on bulk imports via `refresh_entity_matcher`). If a provider is added between entity-matcher init and the next bulk-import refresh, that provider won't match until the index is refreshed — a stale-index window, not a router bug, but visible through the router.

**Where new code goes when extending.** New ask sub-intents → add to `intent_classifier` and (if LLM router is in scope) `llm_router._SUB_INTENTS`. New mode → add a `_handle_<mode>` function and a branch in the mode-dispatch block. New tier-used value → add to the `ChatResponse` docstring and update the taxonomy table in this doc. New session field → add to `_default_*` in `core.session` and read via `get_session().get(...)` with a default. Don't expand `route()` itself with new domain logic — its job is dispatch, not behavior.

## Current state

What's actually deployed (refer to `STATE.md` for the current deployed commit and recent history; SHAs are not pinned here to avoid drift):

- All paths described in this doc are wired and live.
- `USE_LLM_ROUTER=false` in Railway production as of April 2026. The heuristic ask branch (Tier 1 → explicit-rec check → Tier 2 parser → Tier 3) is the live path; the LLM router branch is dormant. Flipping the flag is a one-line config change.
- `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are set in production — Tier 3, Tier 2 parser, hint extractor, and the LLM router (when on) all function.
- Recent activity has been downstream — the Tier 2 formatter went deterministic for all-event responses, but the formatter hands back the same `(text, in_tokens, out_tokens)` tuple shape, so the router didn't need to change. The router is mature; most planned activity in this area is in handlers, parsers, and formatters rather than in the dispatch shell itself.

When updating this section, refresh the date and the env-var value, and re-cross-check `STATE.md`'s "Recently shipped" entries for any unified_router touches.

## Known limitations and design notes

**Vestigial `tier_used` values.** `"intake"` and `"correction"` are listed in the `ChatResponse` docstring but never emitted. They're Phase 4 reservations for when the contribute and correct flows are built out. Until then, both modes emit `"placeholder"`. Anyone grepping the codebase for `"intake"` or `"correction"` won't find an emitter; that's expected.

**In-memory session storage.** `core.session.sessions` is a process-local `dict`. With a single-worker uvicorn deployment this is fine; with multi-worker or multi-replica, sessions are per-worker and `prior_entity` / `onboarding_hints` will be inconsistent across turns served by different workers. Production currently runs single-worker.

**Pronoun-referent regex is small.** `_PRONOUN_REFERENT` matches: `it`, `that`, `there`, `they`, `them`, `the place`, `that place`. Queries like "is it any good" trigger it; queries like "what about that one" don't (no match for `that one`). Expanding the set is safe — it only gates the prior-entity reuse branch, which has its own freshness check.

**Hardcoded 3-turn freshness window.** `_prior_entity_fresh` uses `current_turn - turn_recorded <= 3`. Not configurable. If the freshness boundary needs tuning, it's a constant-extraction refactor.

**Recommended-entity capture is exactly-one.** When a Tier 2 or Tier 3 response mentions multiple providers, none are captured as `prior_entity` — the rule is "one mention or skip." For event-listing responses (which often mention many providers), this means follow-up "tell me more about it" queries can't resolve. Working as intended (ambiguity-avoidance), but it's a known UX edge.

No items in `BACKLOG.md` currently target `unified_router` directly — open items there concern Tier 2 ranking, parser context injection, and clickable source URLs; the router is the conduit for those changes, not the primary edit surface.

## Related components

**Direct dependencies (one-hop, called from `route()` or its helpers):**

- `app/chat/normalizer.py` — text normalization. Pure, stateless, no I/O.
- `app/chat/intent_classifier.py` — heuristic mode + sub-intent + entity classification. No DB; reads canonical entity names from `entity_matcher.CANONICAL_EXTRAS`.
- `app/chat/hint_extractor.py` — OpenAI gpt-4.1-mini call for optional age/location hints.
- `app/chat/entity_matcher.py` — fuzzy-match queries to catalog provider names. Caches provider rows in process memory.
- `app/chat/llm_router.py` — Anthropic Haiku structured-routing call. Active only when `USE_LLM_ROUTER` is on.
- `app/chat/tier1_handler.py` — Tier 1 template lookup. See `try_tier1`. (future component doc)
- `app/chat/tier2_handler.py` — Tier 2 orchestrator (parser → DB → formatter). Two entry points: `try_tier2_with_usage` (heuristic path), `try_tier2_with_filters_with_usage` (LLM-router path with precomputed filters). (future component doc)
- `app/chat/tier3_handler.py` — Tier 3 Anthropic synthesis. Exports `FALLBACK_MESSAGE` (re-imported here as `_GRACEFUL`) and `answer_with_tier3`. (future component doc)
- `app/core/session.py` — in-memory session store, onboarding hints, `prior_entity` tracking.
- `app/core/timezone.py` — Phoenix-time formatting for the Tier 3 prompt's `now_line`.
- `app/db/chat_logging.py` — `log_unified_route` writes the per-turn `chat_logs` row.

**Callsites (where `route()` is invoked):**

- `app/api/routes/chat.py` (`post_concierge_chat`) — the production HTTP endpoint. Calls `route()` synchronously, projects the result into `ConciergeChatResponse`, and (for Tier 3 responses with a successful `chat_log_id`) schedules a background `scan_and_save_mentions` task.
- `app/eval/confabulation_invoker.py` (`InProcessInvoker.invoke`) — eval harness. Toggles `USE_LLM_ROUTER` per-probe, calls `route()` in-process with a dedicated session ID, captures evidence, restores the flag.
- `app/schemas/chat.py` — defines `ConciergeChatRequest` and `ConciergeChatResponse`. The response schema is the wire-format projection of `ChatResponse`.

**Indirect (called by handlers, not by the router itself):** Tier 2 internals (`tier2_parser` for the structured filter LLM call and `Tier2Filters` construction, `tier2_db_query.query`, `tier2_formatter.format`), Tier 1 template/DB logic inside `tier1_handler`, and Tier 3 prompt assembly plus Anthropic usage inside `tier3_handler`.
