# llm_http

`app/core/llm_http.py` (~11 lines)

## Purpose

Defines a single shared **HTTP read timeout** used when constructing **Anthropic** and **OpenAI** Python SDK clients. The SDK accepts **`timeout=`** on client construction; this value caps how long a stuck outbound LLM request blocks a worker before the underlying **`httpx`** stack raises (typically **`httpx.ReadTimeout`**), which callers handle via broad **`except`** paths and user-facing graceful copy where applicable.

## Public surface

**`LLM_CLIENT_READ_TIMEOUT_SEC = 45.0`** — Float seconds; passed verbatim to SDK constructors.

## Inputs and outputs

Not applicable — module-level constant only.

## Internal structure

Single assignment plus module docstring describing the behavioral contract.

## Conventions

**Centralized timeout.** Call sites must import this constant rather than embedding literals so tests can monkeypatch one symbol (**`tests/test_llm_messages.py`** asserts **`Anthropic(..., timeout=LLM_CLIENT_READ_TIMEOUT_SEC)`**).

## Known limitations and design notes

**Read-timeout only.** Does not configure connect timeouts, write timeouts, or retries — those remain SDK defaults unless a caller overrides elsewhere.

**No OpenAI-specific tuning.** OpenAI and Anthropic share the same numeric timeout despite different typical latencies; asymmetric tuning would require splitting constants.

## Configuration

No environment variable — value is fixed in code. Changing it requires a deliberate edit + coordinated test updates.

## Related

**Direct importers:**

- **`app/core/llm_messages.py`** — **`anthropic.Anthropic(api_key=..., timeout=LLM_CLIENT_READ_TIMEOUT_SEC)`** (documented in **`docs/components/llm_messages.md`** mock-seam invariants).
- **`app/core/hint_extractor.py`** — OpenAI client construction.
- **`app/core/extraction.py`** — multiple OpenAI client constructions (Slice **67b** documents **`extraction.py`** separately).
- **`app/core/search.py`** — OpenAI embedding client construction.

**Cross-references:**

- **`docs/components/llm_messages.md`** — Anthropic seam and timeout coupling.
