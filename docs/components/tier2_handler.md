# tier2_handler

`app/chat/tier2_handler.py`

## Purpose

The Tier 2 handler chains the three Tier 2 stages — parser, structured DB query, formatter — into a single orchestrator and returns either a fully-rendered response string (with token totals) or a fallback signal that tells the unified router to try Tier 3 instead. It is the smallest of the tier handlers: it has no DB session, no LLM client, no fallbacks of its own — it only routes between the three Tier 2 stage modules and applies a single confidence gate. Every stage is given the option to refuse, and any refusal short-circuits the chain to a `None` response.

## Public surface

Three callables and one tunable constant:

**`TIER2_CONFIDENCE_THRESHOLD = 0.7`**

The minimum `parser_confidence` required to proceed past the parser stage. Below this, Tier 2 falls back. Defined as a module constant so tests can introspect or patch it.

**`try_tier2_with_usage(query: str) -> tuple[Optional[str], Optional[int], Optional[int], Optional[int]]`**

The full Tier 2 chain entry point. Calls the parser, then the DB query, then the formatter. On full success returns `(text, total_tokens, input_tokens, output_tokens)` where the token sums combine parser and formatter usage. On any fallback returns `(None, None, None, None)`. The docstring states: "On full success, `llm_tokens_used` is parser+formatter totals; on fallback `text` is `None` and token fields are `None`."

**`try_tier2_with_filters_with_usage(query: str, filters: Tier2Filters) -> tuple[Optional[str], Optional[int], Optional[int], Optional[int]]`**

The "skip the parser" entry point — used when an upstream component (the LLM router) has already produced a `Tier2Filters`. Same return shape as `try_tier2_with_usage`, but token totals reflect only the formatter (no parser was called). Docstring: "Run Tier 2 using precomputed filters (skip parser). Returns the same tuple shape as `try_tier2_with_usage`."

**`answer_with_tier2(query: str) -> Optional[str]`**

Thin wrapper around `try_tier2_with_usage` that drops the token fields and returns only `text`. Docstring: "Chain parser → DB query → formatter. Returns None to signal 'fall back to Tier 3'." Used by tests in this repo; no production callsite imports it.

## Inputs and outputs

**Input.** Both `try_*` entry points take `query` as a raw string; the handler strips whitespace and treats empty as fallback. `try_tier2_with_filters_with_usage` additionally takes `filters: Tier2Filters` (the schema that the parser would otherwise produce). No `Session` is passed in — the DB stage opens its own via `tier2_db_query.query(filters)`, which uses `SessionLocal()` internally.

**Output.** The 4-tuple `(text, llm_tokens_used, llm_input_tokens, llm_output_tokens)` for the `try_*` functions, or `Optional[str]` for `answer_with_tier2`. `text` is the formatter-rendered response string. Token fields are non-negative integers on success and all four positions hold `None` on any fallback (an all-or-nothing convention matching the unified router's expectation that "no result" means "no usage either"). Tokens are summed from the parser's `(p_in, p_out)` and the formatter's `(f_in, f_out)`; `None`-valued sub-totals are coerced to `0` before summation, which means a successful return path with one stage reporting no tokens still produces a numeric total.

## Internal structure

`try_tier2_with_usage` is a fixed seven-step chain. Every step has exactly one "continue" outcome and one "fallback to `(None, None, None, None)`" outcome:

1. **Empty-query gate.** `q = (query or "").strip()`; empty → fallback. Logs `"tier2_handler: fallback: empty query"`.
2. **Parser.** `tier2_parser.parse(q)` returns `(filters, p_in, p_out)`. `filters is None` → fallback. Logs `"tier2_handler: fallback: parser error"`.
3. **Parser-refused gate.** `filters.fallback_to_tier3` true → fallback. Logs `"tier2_handler: fallback: parser refused"`. This is the parser explicitly signalling that the query is not Tier-2-shaped.
4. **Confidence gate.** `filters.parser_confidence < TIER2_CONFIDENCE_THRESHOLD` → fallback. Logs `"tier2_handler: fallback: low confidence"`. Note this is a strict less-than: confidence equal to the threshold passes.
5. **DB query.** `tier2_db_query.query(filters)` returns a list of row dicts. `len(rows) == 0` → fallback. Logs `"tier2_handler: fallback: no matches"`.
6. **Formatter.** `tier2_formatter.format(q, rows)` returns `(text, f_in, f_out)`. `text is None` → fallback. Logs `"tier2_handler: fallback: formatter error"`.
7. **Token sum.** `pi, po = (p_in or 0), (p_out or 0); fi, fo = (f_in or 0), (f_out or 0); in_sum = pi + fi; out_sum = po + fo; total = in_sum + out_sum`. Return `(text, total, in_sum, out_sum)`.

`try_tier2_with_filters_with_usage` is a five-step chain — steps 1, 3, 4, 5, 6 of the above (the parser step is skipped because `filters` is provided by the caller). The `parser_refused` and `low_confidence` gates fire on the caller-supplied filters with these log messages: `"tier2_handler: fallback: router filters marked fallback_to_tier3"` and `"tier2_handler: fallback: router filters low confidence"`. The token sum at the end uses formatter tokens only: `in_sum = f_in or 0; out_sum = f_out or 0; total = in_sum + out_sum`.

`answer_with_tier2` is a one-line wrapper: `text, _, _, _ = try_tier2_with_usage(query); return text`.

## Conventions

**Fallback is `(None, None, None, None)` everywhere.** Every gate uses the same return shape on refusal — no partial returns, no exceptions raised across the boundary. The unified router relies on this: it checks `t2_text is not None` and treats anything else as "Tier 2 didn't answer; try Tier 3." Don't introduce a fallback variant that returns text but `None` tokens, or vice versa; the caller pattern is binary.

**One log line per fallback path.** Each gate logs at `INFO` with the prefix `"tier2_handler: fallback: <reason>"`. The prefix makes log triage straightforward when investigating why a query that "looks like" Tier 2 actually fell through to Tier 3. New gates should follow this convention.

**No exception handling here.** This module does not wrap its calls in try/except. Each stage module (`tier2_parser`, `tier2_db_query`, `tier2_formatter`) handles its own exceptions internally and surfaces failure as a `None` in its return tuple (parser) or an empty list (DB query) or `None` text (formatter). The handler trusts that contract. If a stage raises despite that, the exception propagates up to `unified_router._handle_ask`, which catches it at the dispatch level.

**Confidence threshold is module-level.** `TIER2_CONFIDENCE_THRESHOLD = 0.7` lives at the top of the module. The comment on its definition reads: "Parser scores below this threshold skip Tier 2 and defer to Tier 3 (tunable in a later phase)." Tests both read it (`assert filters.parser_confidence >= TIER2_CONFIDENCE_THRESHOLD`) and patch it via `monkeypatch.setattr` — keep it module-level rather than buried in function locals.

**Token coercion uses `or 0`, not `is None` checks.** Stage modules can return either an integer or `None` for their input/output token counts. The handler normalizes via `(p_in or 0)`, which also coerces `0` to `0` — that's intentional and correct because a real `0` is also a valid "no tokens" value (e.g. cached responses). Don't switch to `(p_in if p_in is not None else 0)`; the current form handles both cases identically.

## Current state

What's actually deployed (refer to `STATE.md` for the current commit and recent history; SHAs are not pinned here to avoid drift):

- All three entry points are wired and live.
- `try_tier2_with_usage` is the path the unified router takes when `USE_LLM_ROUTER` is off (the production default as of April 2026).
- `try_tier2_with_filters_with_usage` is the path the unified router takes when `USE_LLM_ROUTER` is on and the LLM router emits `tier_recommendation="2"` with non-`None` `tier2_filters`. With the flag off in production, this entry point is exercised primarily by tests.
- `answer_with_tier2` has no production callsite; it is exercised by `tests/test_tier2_handler.py` (which also tests the full `try_tier2_with_usage` path).
- `TIER2_CONFIDENCE_THRESHOLD` is `0.7` in code; it has not been tuned since the original Phase 4.1 wiring.

When updating this section, refresh the date and the env-var value; re-cross-check `STATE.md`'s "Recently shipped" entries for any tier2_handler touches.

## Known limitations and design notes

**No DB session reuse.** `tier2_db_query.query(filters)` opens a fresh `SessionLocal()` per call rather than reusing the one the unified router already holds. The handler's signature does not accept a `Session` parameter, so passing one through would require adding it. Not currently a problem at production scale (one Tier 2 call per chat turn), but if Tier 2 ever fans out (e.g. multi-filter retry) the per-call session open becomes worth revisiting.

**Confidence gate is binary.** The handler treats `parser_confidence < 0.7` as a hard fallback; there is no partial-credit path (e.g. "low-confidence Tier 2 if the DB returned exact matches anyway"). This is by design — the alternative is that low-confidence parses produce garbage filters, which produce technically-non-empty but irrelevant DB results, which the formatter then dutifully renders. The hard cutoff prevents that whole failure mode.

**Empty-query gate duplicates the unified router's normalization.** The unified router calls `normalizer.normalize` before dispatch, so an empty `query` reaching this handler is unusual. The check exists for safety against direct callers and tests; it is not load-bearing for the production path.

**`answer_with_tier2` exists for a former production caller.** The function predates `try_tier2_with_usage`; the unified router migrated to the token-aware entry point so it could populate `llm_tokens_used` on the response. `answer_with_tier2` was kept rather than removed so the existing tests didn't all need rewriting at the same time.

**Fallback log messages for `try_tier2_with_filters_with_usage` are slightly different.** The "parser refused" and "low confidence" log strings differ from `try_tier2_with_usage` — they say `"router filters marked fallback_to_tier3"` and `"router filters low confidence"` respectively. The provenance of the filters (parser vs. LLM router) is preserved in the log message, which helps when triaging which upstream produced a bad filter set.

No items in `BACKLOG.md` currently target tier2_handler directly. Open items in the Tier 2 area are about parser context (Backlog #3, year inference) and broad-span sampling (Backlog #2), both of which flow through this handler but are seated in `tier2_parser` and `tier2_db_query` respectively.

## Related components

**Direct dependencies (one-hop, called from the entry points):**

- `app/chat/tier2_parser.py` — exports `parse(query: str) -> tuple[Optional[Tier2Filters], int | None, int | None]`. Anthropic LLM call to extract structured filters from the raw query. Called by `try_tier2_with_usage` only.
- `app/chat/tier2_db_query.py` — exports `query(filters: Tier2Filters) -> list[dict[str, Any]]`. Opens its own `SessionLocal()`, returns up to `MAX_ROWS = 8` JSON-serializable row dicts.
- `app/chat/tier2_formatter.py` — exports `format(query: str, rows: List[Dict[str, Any]]) -> tuple[Optional[str], int | None, int | None]`. Empty rows and all-event rows use deterministic Python rendering (0 tokens); mixed/non-event rows use Anthropic.
- `app/chat/tier2_schema.py` — defines `Tier2Filters` (Pydantic model) plus the temporal-plan and category enums the parser populates.

**Callsites (where the entry points are invoked):**

- `app/chat/unified_router.py` (`_handle_ask`) — calls `try_tier2_with_filters_with_usage(query, decision.tier2_filters)` on the LLM-router branch when `decision.tier_recommendation == "2"`, and `try_tier2_with_usage(query)` on the heuristic branch after the explicit-rec check. Both calls live inline in `_handle_ask`; see `unified_router.md` "Ask handler" for the dispatch shape.
- `tests/test_tier2_handler.py` — covers `answer_with_tier2`, `try_tier2_with_usage`, and the threshold constant. The LLM-router-branch entry point has dedicated coverage in `tests/test_llm_router_integration.py` and adjacent files.

**Indirect (called via the stage modules):** the parser uses `app/core/llm_messages` (`call_anthropic_messages`, `coerce_llm_text_to_json_object`, `load_prompt`); the DB query uses `app/db/database.SessionLocal`, `app/db/models.{Event,Program,Provider}`, and `app/contrib/hours_helper.is_open_at`; the formatter uses `app/chat/tier2_catalog_render` and `app/core/llm_messages`. The handler itself has no transitive awareness of these — it only knows the three stage modules' public functions.
