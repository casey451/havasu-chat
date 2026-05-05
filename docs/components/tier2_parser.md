# tier2_parser

`app/chat/tier2_parser.py`

## Purpose

The Tier 2 parser is the LLM step that turns a free-form user query into a structured `Tier2Filters` object the rest of the Tier 2 stack can run a SQL query against. It calls Anthropic with a system prompt assembled from `prompts/tier2_parser.txt` plus a runtime-injected date-context preamble (Slice 24, Backlog #3), expects a JSON object back, validates it against the `Tier2Filters` Pydantic schema, and returns either the validated filters or `None`. On any failure path it returns `None` cleanly — never raises across its boundary — so the Tier 2 handler can fall back to Tier 3 without exception handling.

## Public surface

One callable:

**`parse(query: str) -> tuple[Optional[Tier2Filters], int | None, int | None]`**

The sole exported function. Returns a 3-tuple of `(filters, input_tokens, output_tokens)`. On full success: `filters` is a validated `Tier2Filters`, token counts are integers from the Anthropic usage object. On any failure: `filters` is `None`. Token counts are integers when the API call succeeded but JSON parsing or validation failed afterward — so the caller can distinguish "billed but unusable" from "no API call made". Token counts are `None` only when the API call itself wasn't made or returned no usage.

The schema `Tier2Filters` is defined in `app/chat/tier2_schema.py` and pulled in via `from app.chat.tier2_schema import Tier2Filters`. Callers receive instances and should treat them as immutable.

## Inputs and outputs

**Input.** `query` is a raw string. The parser strips it via `query.strip()` before sending to the LLM as the user message (`User query:\n{query}\n`). Empty or whitespace-only queries pass through to the LLM rather than short-circuit; the LLM can still emit a low-confidence parse with `fallback_to_tier3=true`. (The `tier2_handler` empty-query gate normally fires first.)

**Output.** The 3-tuple. The four meaningful return shapes:

| Path | `filters` | `in_tok` | `out_tok` | Cause |
|------|-----------|----------|-----------|-------|
| Success | `Tier2Filters` | `int` | `int` | API call ok, JSON valid, schema validates |
| Validation fail | `None` | `int` | `int` | API call ok, JSON valid, schema rejects |
| Bad JSON | `None` | `int` | `int` | API call ok, output is not a JSON object |
| Pre-call fail | `None` | `None` | `None` | No API key, prompt load fails, API call fails |

Token-on-billable-failure is a deliberate convention so chat logs can record API spend even when the parse was unusable.

## Internal structure

`parse()` is a linear nine-step function with a single happy path:

1. **API key check.** Read `ANTHROPIC_API_KEY` from env. Empty → return `(None, None, None)`. Logs `INFO`: `tier2_parser: ANTHROPIC_API_KEY unset`.
2. **System prompt load.** `load_prompt("tier2_parser")` reads `prompts/tier2_parser.txt`. Any `OSError` → return `(None, None, None)`. Logs `EXCEPTION`.
3. **Date context prepend (Slice 24, Backlog #3).** Compute today via `now_lake_havasu().strftime("%Y-%m-%d")`. Build a paragraph: `Today's date is YYYY-MM-DD (Lake Havasu City, Arizona; MST/UTC-7, no DST). Use this to resolve year for ambiguous calendar queries (e.g. "May 8" without a year means the next May 8 from today's date).` Prepend that paragraph (plus a blank line) to the static system prompt. The result is what the LLM sees.
4. **User text.** `User query:\n{query.strip()}\n` — sent as the user-role message.
5. **API call.** `call_anthropic_messages(system_prompt=..., user_text=..., max_tokens=300, temperature=0.3, model=None)`. Default model resolution lives in `app/core/llm_messages.py`. `result is None` → return `(None, None, None)`. Logs `ERROR`: `tier2_parser: Anthropic messages.create failed`.
6. **Token capture.** `in_tok = result.usage.billable_input` (cache-aware), `out_tok = result.usage.output_tokens`. Captured before parsing so they survive validation failures.
7. **JSON coercion.** `coerce_llm_text_to_json_object(result.text)` strips optional fence markers and calls `json.loads`. Returns `None` for non-object output. `parsed is None` → return `(None, in_tok, out_tok)`. Logs `WARNING`: `tier2_parser: LLM output is not valid JSON`.
8. **Schema validation.** `Tier2Filters.model_validate(parsed)` runs Pydantic v2 validation including the parser's structural rules (one-temporal-group enforcement, etc.). On `ValidationError` → return `(None, in_tok, out_tok)`. Logs `WARNING`: `tier2_parser: JSON does not validate against Tier2Filters`.
9. **Return.** On success, the validated `Tier2Filters`, plus the captured tokens.

Any other exception is caught at step 8's `except Exception` clause, logged with traceback, and returned as `(None, in_tok, out_tok)`. The `in_tok`/`out_tok` may be `None` if the unexpected exception fired before token capture, but the catch is broad enough to handle that gracefully.

## Conventions

**Tunable knobs are module-level constants.** `_MAX_OUTPUT_TOKENS = 300` and `_TEMPERATURE = 0.3` live at the top of the module. Tests can patch via `monkeypatch.setattr` — keep them module-level rather than buried in function locals.

**Failure is `None`, never an exception.** Every path that doesn't produce a valid `Tier2Filters` returns `None` for filters. The handler's contract with `tier2_handler` and the unified router depends on this — a raised exception would propagate to `unified_router._handle_ask` and could bypass intended fallback logic.

**Token-on-billable-failure.** When the API call succeeds but downstream parsing/validation fails, return token counts so callers can record API spend. This is not just for accounting — it lets the unified router's `chat_logs` row reflect "Tier 2 was attempted, here's what it cost" even when Tier 2 fell back to Tier 3.

**Date prepend is runtime, not on-disk.** The date-context paragraph is built each call from `now_lake_havasu()`. The static `prompts/tier2_parser.txt` does NOT contain a hard-coded date. This is intentional — date in a static file would go stale; runtime prepend is always current. This convention is shared with `tier3_handler` and `unified_router`'s `now_line` plumbing, all of which use `app.core.timezone.now_lake_havasu` as the single source.

**One log line per failure path.** `tier2_parser:` prefix on every log line, with the cause appended. Makes log triage straightforward: a Tier 2 handler fallback can be traced to which parser step failed by grepping the log tail for the prefix.

**Strict typing on the boundary.** The 3-tuple return shape is part of the parser's public contract. Don't introduce a 4-tuple variant or a dataclass return — the handler unpacks via `f, p_in, p_out = tier2_parser.parse(q)`.

## Current state

What's actually deployed (refer to `STATE.md` for the current commit and recent history; SHAs are not pinned here to avoid drift):

- The parser is wired into `tier2_handler.try_tier2_with_usage` at the parser-step gate. It is NOT called when the LLM router emits `Tier2Filters` directly (the `try_tier2_with_filters_with_usage` entry point skips the parser).
- Runtime date-context prepend has been live since Slice 24 (Backlog #3 close, 2026-05-04). The prepend paragraph is rebuilt on every call.
- `_MAX_OUTPUT_TOKENS = 300`, `_TEMPERATURE = 0.3` are unchanged from Phase 4.1's original wiring.
- The `Tier2Filters` schema in `app/chat/tier2_schema.py` includes a `parser_confidence` field that the parser's prompt requires the LLM to emit on every response. The handler's confidence gate (`tier2_handler.TIER2_CONFIDENCE_THRESHOLD = 0.7`) reads this field.

When updating this section, refresh the prepend description and re-check `prompts/tier2_parser.txt` for any contract changes.

## Known limitations and design notes

**Confidence is the LLM's self-report.** `parser_confidence` is whatever the LLM decides to write into the JSON; it's not a validated probability. Low-confidence parses are treated as "the LLM thinks this isn't a Tier 2 query" rather than as a real probability of correctness. The handler's threshold gate (0.7) is calibrated against observed LLM behavior, not statistically.

**`fallback_to_tier3` is also LLM-emitted.** The parser prompt instructs the LLM to set `fallback_to_tier3=true` on queries that aren't Tier 2-shaped. The `tier2_handler` parser-refused gate (step 3 of its chain) reads this. Combined with `parser_confidence`, this gives the LLM two ways to signal "send to Tier 3", both of which the handler honors.

**Bad-JSON path billable.** Step 7's failure (LLM emitted non-JSON) still returns the token counts. This is correct — the API was called and used input/output tokens — but it means a malfunctioning prompt that always fails JSON validation would silently rack up cost. Worth monitoring via `chat_logs.tier_used = TIER2` rows where `tier_used` shows TIER3 (parser fell back); a high rate of those with non-zero `llm_tokens_used` indicates parser instability.

**Date-context paragraph is hard-coded text.** The phrasing of the prepend (`Use this to resolve year for ambiguous calendar queries (e.g. "May 8" without a year means the next May 8 from today's date).`) was written to be explicit and prescriptive. If the LLM ignores the rule under stress, the natural fix is to make the rule even more prescriptive in the static prompt's "Priority" section — not to rewrite the runtime prepend, which is meant to stay short.

**No retries.** A single API call; if it fails, return `None` immediately. The handler's chain treats this as a fall-back signal. Adding retries here would defeat the fallback design — better to fall back fast than to delay the user's response.

## Related components

**Direct callers:**

- `app/chat/tier2_handler.py` — calls `parse(query)` in `try_tier2_with_usage` (step 2 of its chain). Drops the result on parser failure or low confidence; otherwise passes the filters to `tier2_db_query.query`.

**Direct callees:**

- `app/core/llm_messages.py` — provides `call_anthropic_messages`, `coerce_llm_text_to_json_object`, `load_prompt`. The H2 consolidation point for Anthropic calls.
- `app/core/timezone.py` — provides `now_lake_havasu`. Reused from tier3_handler / unified_router for the same temporal-grounding purpose.
- `app/chat/tier2_schema.py` — provides `Tier2Filters` Pydantic schema and the temporal-plan / category enums.

**Prompt:**

- `prompts/tier2_parser.txt` — system prompt body (Schema, Temporal plan rules, Priority, few-shots). Edits to the prompt change parser behavior; treat as a risky LLM-prompt change per WORKING_AGREEMENT.md.

**Tests:**

- `tests/test_tier2_parser.py` — covers high-confidence parses, fallback parses, SDK error handling, JSON-coercion failure, and the runtime date-context wiring (Slice 34 addition).
- `tests/test_tier2_parser_date_extraction.py` — covers `date_exact` and date-range parsing specifically.
