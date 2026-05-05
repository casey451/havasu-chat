# llm_messages

`app/core/llm_messages.py` (~184 lines)

## Purpose

H2 consolidation point for Anthropic Messages API calls. Every Anthropic-LLM caller in the codebase routes through `call_anthropic_messages`. Centralizes API-key checks, package-availability checks, client construction, the `messages.create` call, response extraction, and usage normalization. Provides `coerce_llm_text_to_json_object` for callers that expect JSON output and `load_prompt` for static-prompt loading from `prompts/<name>.txt`.

The module's `__doc__` documents **mock-seam invariants** that the test suite depends on. Edits that regress those invariants break the suite; this is by design — keeping the seam pinned makes per-caller tests trivially easy.

## Public surface

**`call_anthropic_messages(*, system_prompt, user_text, max_tokens, temperature, model=None) -> AnthropicResult | None`**

The sole API entry point. Returns:
- `AnthropicResult(text, usage, raw)` on success — including when `text=""` (the API responded with billable tokens but empty content).
- `None` on no-response paths: missing/empty `ANTHROPIC_API_KEY`, `anthropic` package not installed, any exception during `messages.create`, or a missing/falsy response object.

Callers that distinguish "billed but empty" from "no call" branch on `result is None` first, then on `result.text`.

**`Usage` (frozen dataclass)** — Fields: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`.
- `Usage.billable_input` (property) — sums all input-side tokens (regular + cache reads + cache creation). This is what callers report as `llm_tokens_used` for cost analytics.
- `Usage.from_sdk_usage(sdk_usage)` (classmethod) — coerces an Anthropic SDK usage object (or `None`) into a `Usage`. Missing fields default to 0; `None` → all zeros. Resilient to SDK-version changes that add or remove usage fields.

**`AnthropicResult` (frozen dataclass)** — Fields: `text` (extracted text content), `usage` (`Usage` object), `raw` (the raw SDK message for callers that need it).

**`coerce_llm_text_to_json_object(raw: str) -> dict | None`** — Strips optional triple-backtick fences (with or without language tag) and parses as JSON. Returns the parsed dict if the result is a JSON object, `None` otherwise (parse failure, empty input, or non-object root).

**`load_prompt(name: str) -> str`** — Reads `prompts/<name>.txt` at repo root, returns the stripped text. Raises `FileNotFoundError` if the file is missing — no optional fallback parameter; caller-side fallbacks stay at call sites that need them (e.g., `hint_extractor.py` has its own inline default).

**`DEFAULT_MODEL`** — Module constant `"claude-haiku-4-5-20251001"`. Used when caller passes `model=None` and `ANTHROPIC_MODEL` env is unset.

## Inputs and outputs

**`call_anthropic_messages` inputs:**

- `system_prompt: str` — system role content. Wrapped at runtime into `[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]` — every caller gets ephemeral prompt-caching for free.
- `user_text: str` — user role message body. Wrapped into `[{"role": "user", "content": user_text}]`.
- `max_tokens: int` — output budget; passed through to the SDK.
- `temperature: float` — passed through.
- `model: str | None` — when `None`, falls through to `_resolve_model` which checks `ANTHROPIC_MODEL` env then `DEFAULT_MODEL`.

**Outputs:**

- `AnthropicResult` on success.
- `None` on no-call or call-failure.

The 4-step success path returns `AnthropicResult(text=<extracted>, usage=Usage.from_sdk_usage(<sdk_usage>), raw=<msg>)`.

## Internal structure

`call_anthropic_messages` is six steps:

1. **API key check.** Strip `ANTHROPIC_API_KEY`. Empty → return `None`.
2. **Package check.** `anthropic is None` → return `None` (import-time guard catches missing package).
3. **Model resolve.** `_resolve_model(model)` — returns `model` if non-empty, else env `ANTHROPIC_MODEL`, else `DEFAULT_MODEL`.
4. **System block construction.** Wrap `system_prompt` into the cache-controlled blocks list.
5. **API call.** `client = anthropic.Anthropic(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)`; `msg = client.messages.create(model=resolved_model, max_tokens, temperature, system=system_blocks, messages=user_message)`. Wrapped in `try/except Exception` — any failure → return `None`.
6. **Result extraction.** Falsy `msg` → return `None`. Otherwise: `text = _extract_text_from_message(msg)`, `usage = Usage.from_sdk_usage(msg.usage)`, return `AnthropicResult(text, usage, raw=msg)`.

`_extract_text_from_message` iterates `msg.content`, concatenating `text`-typed blocks; ignores other block types (tool_use, image, etc.); returns `""` if no text blocks.

## Mock-seam invariants

The module docstring lists three invariants that **must not regress** without coordinated test updates:

1. **Use `import anthropic` (package-level), never `from anthropic import Anthropic`.** This makes `patch.object(anthropic, "Anthropic", ...)` and `app.core.llm_messages.anthropic.Anthropic` patches hit the same class. Tests rely on the package-level handle for monkeypatching.
2. **Construct the client only as `anthropic.Anthropic(api_key=..., timeout=LLM_CLIENT_READ_TIMEOUT_SEC)` with no extra kwargs.** Adding kwargs (e.g., `max_retries=`) breaks the seam because tests assert on the call signature.
3. **Call `client.messages.create` with exactly these kwargs and no others:** `model`, `max_tokens`, `temperature`, `system`, `messages`. Adding new kwargs requires updating every test that asserts on the call signature.

If a future change needs to violate one of these (e.g., adding `tool_use` support), update the invariant comment AND every affected test in the same commit.

## Conventions

**`AnthropicResult` carries the raw SDK message.** Callers that want to introspect non-text content blocks or response metadata can reach `result.raw`. Most callers don't need it; it's there because removing it would require predicting all future caller needs.

**`Usage` aggregates cache and non-cache inputs.** `billable_input` is what gets logged as token usage; cache reads and cache creation are billed (at different rates), so the sum is the right billing-side number. Internal token-cost analytics that need to break out cache vs non-cache tokens can read the individual fields.

**No retries.** Single API call; failure → `None`. Callers that want retries implement them at their level. The decision was made during H2 consolidation: retries belong to the caller, not the helper.

**No streaming.** Always non-streaming. Streaming is opt-in at the caller level via the SDK directly (no caller currently does this). Adding streaming support to this helper would expand the seam significantly.

**`load_prompt` raises, doesn't return None.** Missing prompt files are a deployment error, not a runtime fall-through. Callers that want to fall through wrap the call (e.g., `hint_extractor.py` does this with its inline default).

**`coerce_llm_text_to_json_object` returns `None` for non-objects.** Even valid JSON arrays or scalars return `None`. Callers expect dict-shaped output; arrays would surprise them.

## Configuration

- `ANTHROPIC_API_KEY` env: required for any successful call.
- `ANTHROPIC_MODEL` env: optional model override. Caller's `model` arg takes precedence.
- `LLM_CLIENT_READ_TIMEOUT_SEC`: imported from `app.core.llm_http` (see that module for the actual value and its rationale).

## Known limitations and design notes

**No native streaming, batching, or tool-use support.** The helper is scoped to single-call non-streaming text generation. Tier 3's grounded responses, Tier 2's parser/formatter, and the LLM router all fit in this shape. Tools or streaming would require expanding the helper or bypassing it.

**Single-keyword construction is rigid.** Adding any kwarg to `messages.create` (e.g., `top_p`, `stop_sequences`) requires expanding the helper signature AND updating tests. This is the cost of the mock-seam discipline; the benefit is trivially-mockable tests across all callers.

**Exception broadly caught.** `try/except Exception` around the SDK call eats specific error types (rate limits, auth errors, validation errors). Callers see `None` and treat as "API didn't work." Operationally fine; debugging requires looking at the exception path's logging at the caller layer (not all callers log the exception type).

**Cache control is hardcoded.** Every call gets `cache_control={"type": "ephemeral"}` on the system block. This is correct for production traffic (system prompts repeat across queries) but tests can't easily disable it without monkeypatching. Acceptable for now; if a caller ever needs non-cached system, parameterize then.

## Related components

**Direct callers (Anthropic):**

- `app/chat/tier2_parser.py` — see `docs/components/tier2_parser.md`.
- `app/chat/tier2_formatter.py` — formatter LLM call (mixed-row path).
- `app/chat/tier3_handler.py` — see `docs/components/tier3_handler.md`.
- `app/chat/llm_router.py` — see `docs/components/llm_router.md`.
- `scripts/run_voice_audit.py` — voice-audit script (Backlog #16, migrated Slice 17).

**Direct dependencies:**

- `anthropic` (Python SDK).
- `app.core.llm_http.LLM_CLIENT_READ_TIMEOUT_SEC`.

**Cross-references:**

- `docs/maintainability/h2_consolidation_decision.md` — design retrospective for this helper. Lists what was consolidated and why.
- `relay/component_doc_audit.md` — places this module in priority for documentation.
- `app/chat/hint_extractor.py` — uses OpenAI, not this helper. The OpenAI parallel (`app/core/llm_chat.py`) is DEFERRED per Backlog #17 until a second OpenAI caller appears.
