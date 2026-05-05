# tier3_handler

`app/chat/tier3_handler.py`

## Purpose

Tier 3 is the LLM-grounded synthesis path: when Tier 1 (deterministic templates) and Tier 2 (structured catalog retrieval) don't apply or return empty, the unified router delegates to `answer_with_tier3` for a Haiku-backed response constrained by a Context block built from the catalog. Output is short, factual, and voice-shaped per `docs/persona-brief.md`.

The handler never raises. Any failure (missing API key, missing Anthropic package, API error, empty response) returns `FALLBACK_MESSAGE` so the user always gets a coherent reply.

## Public surface

Two symbols are imported by other code:

**`answer_with_tier3(query, intent_result, db, *, onboarding_hints=None, now_line=None) -> tuple[str, int | None, int | None, int | None]`**

The Tier 3 entry point. Returns a 4-tuple: `(assistant_text, total_tokens, llm_input_tokens, llm_output_tokens)`. Token counts are `None` when no Anthropic call was made (graceful fallback path) or when usage data wasn't available on the API response.

The function is keyword-only for `onboarding_hints` and `now_line`. `now_line` overrides the default "Now: {Lake Havasu local time}" in the user prompt — used by tests and any caller that needs deterministic time framing.

**`FALLBACK_MESSAGE: str`**

The graceful-degradation message returned when Tier 3 cannot complete an Anthropic call. Re-exported from `unified_router` as `_GRACEFUL` for fallback paths in other tiers.

## Inputs and outputs

**Inputs.**

- `query: str` — the raw user text (already normalized upstream by the unified router).
- `intent_result: IntentResult` — output of `intent_classifier.classify`, providing `mode`, `sub_intent`, and `entity` for the Classifier block in the user prompt.
- `db: Session` — SQLAlchemy session passed through to `build_context_for_tier3` for catalog reads.
- `onboarding_hints: Mapping | None` — optional hints from the session store (`visitor_status`, `has_kids`, `age`, `location`). Used to construct the bias line.
- `now_line: str | None` — optional override for the "Now:" line; defaults to current Lake Havasu local time.

**Outputs.** A 4-tuple. The wire-format projection happens in `unified_router.route` via `ChatResponse`.

| Field | Type | Meaning |
|---|---|---|
| `assistant_text` | `str` | The model's reply, or `FALLBACK_MESSAGE` on failure. |
| `total_tokens` | `int \| None` | input + output tokens for this call; `None` if no call was made. |
| `llm_input_tokens` | `int \| None` | input-side billable tokens (cache-aware). |
| `llm_output_tokens` | `int \| None` | output-side tokens. |

The split tokens are surfaced for the eval harness; the wire format keeps only the total.

## Internal structure

Five-stage pipeline inside `answer_with_tier3`:

1. **API key + package guard.** If `ANTHROPIC_API_KEY` is unset OR the `anthropic` package didn't import (see `app.core.llm_messages.anthropic`), return `FALLBACK_MESSAGE` immediately with all token slots `None`.

2. **Context build.** `build_context_for_tier3(query, intent_result, db)` produces the catalog Context block (events / programs / providers relevant to the query). This is the grounding the model is constrained to.

3. **Mid-block assembly.** The user prompt's mid-section is composed of:
   - **Classifier line:** `Classifier: mode={...}, sub_intent={...}, entity={...}` — surfaces the upstream classification so the model can adjust register (e.g., greetings get a different shape than fact lookups).
   - **Bias line** (optional): from `user_context_line_for_tier3(onboarding_hints)`. Builds a comma-separated phrase from `visitor_status`, `has_kids`, `age`, `location`. Output line shape: `User context: visiting, with kids, age 8, downtown.`. Omitted entirely if no fields are set.
   - **Now line:** `Now: {format_now_lake_havasu()}` unless `now_line` was passed in. Always prefixed with `"Now:"` if the override didn't include it.
   - **Local voice block** (optional): up to 3 matching blurbs from `find_matching_blurbs`, rendered as a bulleted `Local voice:` block. Used to bias the model toward Hava-voice phrasing without injecting facts.

4. **Anthropic call.** `call_anthropic_messages` is invoked with:
   - `system_prompt` from `_load_tier3_system_prompt()` — loads `prompts/system_prompt.txt`, falls back to `_INLINE_SYSTEM_PROMPT_FALLBACK` if the file is missing.
   - `user_text` = `User query: {query}\n\n{mid}\n\n{context}`.
   - `max_tokens=150`, `temperature=0.3`, default model.

5. **Result handling.** If the call returned `None` (API failure), or returned text was empty, return `FALLBACK_MESSAGE` with `None` tokens. Otherwise return the text plus token splits.

## System prompt loading

`_load_tier3_system_prompt` is a tier3-specific helper. Per the function's docstring, the graceful fallback to `_INLINE_SYSTEM_PROMPT_FALLBACK` is **intentional behavior, not boilerplate** — Tier 3 keeps a minimal inline prompt so a missing file in deploy doesn't take the chat down. Other tiers use `load_prompt` directly without fallback.

If `prompts/system_prompt.txt` is missing, the inline fallback is:

> "You are a Lake Havasu City concierge. Answer in 1–3 short sentences, contractions, no filler, no follow-up questions. Use only the Context block for facts."

The full prompt file (`prompts/system_prompt.txt`) is the canonical version; the inline string is a degraded mode.

## Failure modes and graceful behavior

| Condition | Return value |
|---|---|
| `ANTHROPIC_API_KEY` unset | `(FALLBACK_MESSAGE, None, None, None)` + log info. |
| `anthropic` package not installed | `(FALLBACK_MESSAGE, None, None, None)` + log error. |
| `call_anthropic_messages` returns `None` (API error) | `(FALLBACK_MESSAGE, None, None, None)` + log error. |
| API returned empty text | `(FALLBACK_MESSAGE, None, None, None)`. |
| API returned text but no usage object on `result.raw` | `(text, None, None, None)`. |
| Normal success | `(text, total, in, out)`. |

Token counts are `None` whenever the call didn't complete OR the API response shape lacked usage. This shows up in `chat_logs.llm_tokens_used` as NULL, which is the signal that the turn either didn't reach the model or the bookkeeping wasn't available — important for cost monitoring.

## Tunable constants

- `_MAX_OUTPUT_TOKENS = 150` — caps assistant reply length. Persona brief target is 1-3 short sentences; 150 tokens is generous.
- `_TEMPERATURE = 0.3` — modest variance for natural-sounding replies without going off the rails.
- `_INLINE_SYSTEM_PROMPT_FALLBACK` — see "System prompt loading" above.

Changes to these constants are user-visible behavior changes; require WORKING_AGREEMENT.md verification (multi-sample LLM behavior).

## Cross-references

- **Caller:** `app/chat/unified_router.py` — multiple call sites (Tier 2 fallback, direct Tier 3 routing, tier1 gap fallback). Search `answer_with_tier3` to enumerate.
- **Context builder:** `app/chat/context_builder.py` — produces the Context block.
- **Local voice:** `app/chat/local_voice_matcher.py` and `app/data/local_voice.py` — bias phrases.
- **LLM client:** `app/core/llm_messages.py` — `call_anthropic_messages`, `load_prompt`, `anthropic` re-export.
- **Time helper:** `app/core/timezone.py` — `format_now_lake_havasu`, `now_lake_havasu`.
- **Prompt file:** `prompts/system_prompt.txt`.
- **Persona spec:** `docs/persona-brief.md` — voice rules the model is targeted to follow.
- **Architecture:** `HAVA_CONCIERGE_HANDOFF.md` §3.5, §5.

## Update discipline

Per `docs/WORKING_AGREEMENT.md` §5 (Component doc currency): when `tier3_handler.py` changes behavior or public contract, update this doc in the same commit. If a change is purely internal (e.g., refactor without contract change), the commit message body must state "no doc update — internal refactor with no behavior change" or equivalent.
