# llm_router

`app/chat/llm_router.py` (~180 lines)

## Purpose

Optional Anthropic structured-routing layer that runs as a single LLM call returning a `RouterDecision` (mode + sub-intent + entity + tier_recommendation + tier2_filters). When `USE_LLM_ROUTER` env is on, the unified router prefers this decision over the heuristic `intent_classifier.classify()` for ask-mode queries. **Off by default in production.**

The router can produce filtered Tier 2 input directly (skipping the parser step), or recommend Tier 3 when the query isn't structured-retrieval-shaped. It's an alternative to the heuristic pipeline, not a complement; only one wins per turn.

## Public surface

**`route(query, normalized_query, context=None) -> RouterDecision | None`**

The sole exported function. Returns:
- `RouterDecision` on full success (API call ok, JSON valid, schema validates including the `tier_recommendation == "2" requires tier2_filters` cross-field rule).
- `None` on any failure path. The unified router treats `None` as "fall back to heuristic + tier handlers."

**`RouterDecision` (Pydantic model)** — Fields:
- `mode: str` — validated against `{ask, contribute, correct, chat}`.
- `sub_intent: str` — validated against the `_SUB_INTENTS` frozenset (must match `intent_classifier.py`'s sub-intent space).
- `entity: Optional[str]` — empty/null/none strings normalized to `None`.
- `router_confidence: float` — `0.0` ≤ value ≤ `1.0`.
- `tier_recommendation: str` — `"2"` or `"3"` only.
- `tier2_filters: Optional[Tier2Filters]` — populated when `tier_recommendation == "2"`; required by a `model_validator`.

## Internal structure

`route()` is seven steps with single-pass control flow:

1. **API key check.** Empty `ANTHROPIC_API_KEY` → log INFO, return `None`.
2. **System prompt load.** `_load_router_system_prompt()` reads `prompts/llm_router.txt`. `OSError` → log ERROR, return `None`.
3. **User text construction.** Combines raw query, normalized query, and optional `context` dict (JSON-serialized, with a fallback to `repr(context)` for unserializable cases).
4. **API call.** `call_anthropic_messages(...)` with `_MAX_TOKENS=500`, `_TEMPERATURE=0.0`. Latency timed via `time.perf_counter`. `result is None` → log ERROR, return `None`.
5. **Token capture.** From `result.usage` if present; `(None, None)` otherwise. Captured for the success-path log line, not used in the return.
6. **JSON coerce.** `coerce_llm_text_to_json_object(result.text)`. Empty/non-object → log WARNING with latency, return `None`.
7. **Schema validate.** `Tier2Filters.model_validate(...)` for the nested filters, then `RouterDecision.model_validate(...)` for the outer object. Any exception → log EXCEPTION with latency, return `None`. On success → log INFO with model + latency + tokens + tier, return the decision.

## Conventions

**Temperature 0.0.** Deterministic; reproducibility matters for routing.

**500-token output budget.** Larger than tier2_parser (300) because the router's JSON includes the nested `Tier2Filters` block when `tier_recommendation == "2"`.

**Cross-field validator on `tier2_filters`.** `RouterDecision._tier2_if_recommended` enforces the contract: if you say "Tier 2", you must produce filters. Prevents the unified router from receiving an undecidable decision shape.

**Sub-intent label space matches `intent_classifier.py`.** The `_SUB_INTENTS` frozenset at the top of the module mirrors what the heuristic produces. Drift between the two would cause `chat_logs.sub_intent` analytics to fragment; treat the two as a coupled pair when changing.

**Latency is logged on success and on JSON-failure paths.** Operators see how long the LLM took regardless of validity, so degraded perf shows up even when validation is fine.

**Token counts logged when available.** Same convention as tier2_parser — billable inputs (cache-aware) and output tokens.

## Configuration

- `USE_LLM_ROUTER` env: feature flag; OFF by default. The unified router checks this before calling `route`.
- `ANTHROPIC_API_KEY` env: required.
- `ANTHROPIC_MODEL` env: optional override; defaults to the `DEFAULT_MODEL` constant.

## Known limitations

**Single LLM call, no retry.** Same as tier2_parser — fall back to heuristic+tier-handlers is faster than retrying.

**Sub-intent space is duplicated.** The frozenset here and the heuristic patterns in `intent_classifier.py` enumerate sub-intents independently. Adding a new sub-intent requires touching both files (and the prompt). Acceptable for now; consolidation candidate if drift becomes a problem.

**No streaming.** Full JSON object returned at once. Not on the critical path (heuristic runs first when LLM router is off; when on, this single call is the routing gate).

**`tier_recommendation` is binary.** Only `"2"` and `"3"`. Tier 1 routing is heuristic-only — the LLM router can't recommend Tier 1 because Tier 1 requires a specific entity-and-sub-intent match the LLM doesn't have visibility into.

**Validation cost on bad output.** A bad JSON path still bills tokens. Same convention as tier2_parser; worth monitoring `chat_logs` for high-token Tier-3-fallback rows.

## Related

**Direct consumers:** `app/chat/unified_router.py` `_handle_ask` — calls `route(query, normalized_query, context)` when `USE_LLM_ROUTER` env is set.
**Direct dependencies:** `app.core.llm_messages.call_anthropic_messages`, `coerce_llm_text_to_json_object`, `app.chat.tier2_schema.Tier2Filters`.
**Prompt:** `prompts/llm_router.txt`.
**Adjacent doc:** `docs/components/intent_classifier.md` (heuristic alternative, shares sub-intent label space), `docs/components/tier2_handler.md` (downstream consumer of `tier2_filters`).
