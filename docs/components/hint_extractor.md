# hint_extractor

`app/chat/hint_extractor.py`

## Purpose

Optional OpenAI call (gpt-4.1-mini, JSON mode) that pulls structured `age` and `location` hints from a user query when explicitly stated. Used to enrich session memory across multi-turn conversations. **Opt-in only**: returns `None` if `OPENAI_API_KEY` is unset or the `openai` package isn't installed. The unified router treats `None` as "no hints, proceed normally" — there's no fallback path because there's nothing to fall back from.

This is the **only OpenAI caller** in the codebase. (Tier 2 parser, Tier 3 handler, and llm_router all use Anthropic.) Backlog #17 tracks extracting an `app/core/llm_chat.py` helper if a second OpenAI caller appears.

## Public surface

**`extract_hints(query: str) -> ExtractedHints | None`**

The primary exported function. Returns:
- `ExtractedHints(age=..., location=...)` when the LLM extracted at least one valid hint.
- `None` when the API key is unset, OpenAI is unavailable, the call fails, JSON parsing fails, or no usable hint was extracted.

**`ExtractedHints` (Pydantic model)** — Fields: `age: int | str | None`, `location: str | None`. Note the `int | str` union on age — the prompt allows the LLM to return a numeric age ("6") or a string range ("teen", "5-10"); the consumer normalizes downstream.

**`has_hint_signal(query: str) -> bool`** — the cheap regex prefilter (see Modes). Exported so callers/tests can ask "would this query pass the gate?" without making the API call.

**`get_hint_extractor_telemetry() -> dict[str, int]` / `reset_hint_extractor_telemetry()`** — per-outcome call counts (`skipped_prefilter`, `called`, `memoized` (reserved), `skipped_mode_off`, `skipped_no_key`, `skipped_empty`) since process start / last reset. Lets the call mix be measured on real traffic; `memoized` is reserved for future session-memoization.

## Modes

`HINT_EXTRACTOR_MODE` (default **`conditional`**) controls when the LLM is called:

- **`conditional`** — call only when `has_hint_signal()` finds a plausible age/location signal (the shipped default; ~86–89% of turns skip the call on the intent-phrase-bank corpus).
- **`always`** — call on every turn (the pre-gate behavior).
- **`off`** — never call.

Back-compat: the legacy `HINT_GATE` env still works (`HINT_GATE=off` → `always`, else `conditional`); `HINT_EXTRACTOR_MODE` wins when both are set. The signal regex matches an explicit child age or a specific Lake Havasu place, and deliberately **excludes** the empty deictic "near me" / "nearby" / "near here" (measurement found those were 25% of gate passers and can never yield a location hint).

## Internal structure

`extract_hints()` is:

1. **Empty-query short-circuit.** Whitespace-only input → `None`.
2. **Mode gate.** `off` → `None`; `conditional` + no `has_hint_signal()` → `None` (no API call). `always` skips the prefilter.
3. **Env / package check.** No API key OR `openai` import failed → `None`.
4. **Prompt load.** `_load_hint_prompt()` reads `prompts/hint_extractor.txt`; falls back to a hard-coded one-line default if the file is absent (rare; defense against missing prompt during dev).
5. **API call.** `client.chat.completions.create(model, messages, response_format={"type":"json_object"}, temperature=0.1)` with the configured `OPENAI_MODEL` env var or default `gpt-4.1-mini`. Wrapped in `try/except Exception` — any failure logs and returns `None`.
6. **Token-budget audit.** If usage exceeds 400 input or 100 output tokens, log a `WARNING`. Soft budget; the call already succeeded.
7. **JSON parse + validation.** `json.loads(raw)` → `_HintEnvelope.model_validate(...)` → unwrap to `ExtractedHints`. Only return non-`None` if at least one of `age` or `location` is non-empty.

Each terminal outcome bumps a telemetry counter (see Public surface).

## Conventions

**No retries.** Single API call; failure → `None`. The unified router doesn't depend on hints, so retry latency would be wasted on a non-load-bearing call.

**Wrapped in `try/except Exception`.** OpenAI client and pydantic validation surface different exception types; one broad catch keeps the function from raising up to the unified router.

**`response_format={"type":"json_object"}`.** Forces JSON-mode output. Failures here are usually validation, not parse.

**Temperature 0.1.** Near-deterministic; reproducibility matters for hint extraction (we want the same hint on retry).

**Soft token budget at 400/100.** Doesn't fail the call, just logs. If budget violations become common, the prompt is the place to tune.

## Known limitations

**No memoization yet.** Same gate-passing query asked twice in the same session triggers two API calls. The `conditional` prefilter already removes ~86–89% of calls; session memoization is deferred until the `get_hint_extractor_telemetry()` call mix on real traffic shows it would pay for itself (the `memoized` counter bucket is reserved for it).

**English-only prompt.** Prompt assumes Lake Havasu local phrasing; non-English queries likely return `None` from the LLM (which is the correct behavior).

**Age field is loosely typed.** The `int | str | None` union accepts whatever the LLM returns; downstream consumers (`unified_router._enrich_with_hints`) normalize.

**Soft budget only.** A truly runaway prompt would still bill the full request before the warning logs.

## Related

**Direct consumers:** `app/chat/unified_router.py` — calls `extract_hints` after `classify()` to enrich session context.
**Direct dependencies:** `openai.OpenAI`, `pydantic.BaseModel`, `app.core.llm_http.LLM_CLIENT_READ_TIMEOUT_SEC`.
**Prompt:** `prompts/hint_extractor.txt` (consumed by `_load_hint_prompt`; falls back to inline default if absent).
**Adjacent backlog:** #17 (extract `app/core/llm_chat.py` helper) — DEFERRED until a second OpenAI caller appears.
