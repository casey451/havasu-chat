# extraction

`app/core/extraction.py` (~307 lines)

## Purpose

OpenAI-driven event-detail extraction from raw user text, with regex/heuristic fallbacks on every LLM path so the function never fails closed. Given a single message string like "Add a karate class at the dojo on Saturday at 9am, contact Sue 928-555-0100", returns a `dict` with the canonical event fields populated (title, date, start_time, location_name, description, event_url, contact_name, contact_phone) plus a generated embedding and a generated tag list.

The two-path structure (LLM-or-fallback) is the load-bearing design — heuristics are the source of truth for required fields (title/date/start_time/location/description) so the function returns a usable event even with no API key, no network, or a malformed LLM response. The LLM path improves the description (when ≥20 chars) and supplies optional fields (event_url, contact_name, contact_phone) when the heuristic regex misses them.

Currently called from `app/admin/router.py` during contribution review (re-embedding and re-tagging an event row before approval); also exercised in tests.

## Public surface

**`extract_event(message: str) -> dict`** — Main entry point. Runs LLM extraction + heuristic extraction, merges them, then attaches an embedding (`generate_embedding`) and tags (`generate_event_tags`). Always returns a complete dict; never raises.

**`generate_embedding(text: str) -> list[float]`** — OpenAI `text-embedding-3-small` if the API key + client are available, else a 32-dimensional deterministic fallback. Never raises.

**`generate_event_tags(event: dict) -> list[str]`** — OpenAI-driven tag generation (5–10 short lowercase tags). Returns an empty list when the API call fails, the response doesn't parse as a JSON array of strings, or the tag count would exceed 10 (the function caps + dedupes silently). Never raises.

**`EXTRACTION_PROMPT`** and **`TAGS_PROMPT`** — Module-level prompt templates. Exported for testing/inspection; not typically called directly.

## Inputs and outputs

**`extract_event` input.** A single message string, free-form.

**`extract_event` output.** A dict with the eight canonical event fields (`title`, `date`, `start_time`, `location_name`, `description`, `event_url`, `contact_name`, `contact_phone`) plus `embedding` (list of floats) and `tags` (list of strings). Field formats:

- `date` — ISO `YYYY-MM-DD` string (heuristic resolves "today"/"tomorrow"/weekday names; otherwise falls back to today's date).
- `start_time` — `HH:MM:SS` string (heuristic parses `9am`/`9:30 PM`/etc.; falls back to `09:00:00` when no time is detected).
- `title`, `location_name` — title-cased strings; `_extract_title` strips trailing temporal phrasing, `_extract_location` finds an `at X` phrase or returns `"Location TBD"`.
- `event_url` — `http(s)://` or `www.` (auto-prefixed to `https://`); empty string when neither pattern hits.
- `contact_name`, `contact_phone` — empty string unless the LLM supplied them; the heuristic only extracts the phone number, never the name.
- `description` — the full message text, except when the LLM returns a description ≥20 chars (then the LLM version wins).

**`generate_embedding` output.** A list of floats. Two distinct shapes possible: 1536-dim (OpenAI) or 32-dim (deterministic fallback). See "Known limitations" for why this matters.

**`generate_event_tags` output.** Up to 10 lowercase strings, deduplicated in insertion order. Empty list on any failure.

## Internal structure

**`extract_event`** is a five-stage merge:

1. **Heuristic baseline** (`_heuristic_extract`) — populates every required field via regex/string parsing on the message text. This is the floor: the dict is fully populated even if everything else fails.
2. **LLM augmentation** (`_extract_with_openai`) — sends `EXTRACTION_PROMPT.format(message=...)` to `client.responses.create(...)`, parses the response as JSON, and returns the eight canonical fields stripped. Returns `None` on any failure (missing key, missing client, network exception, JSON parse error).
3. **Description override.** If the LLM description is ≥20 chars, replace the heuristic message-as-description with it.
4. **Optional-field overrides.** For `event_url`, `contact_name`, `contact_phone`: when the LLM supplied a non-empty value, override (with a `len(s) >= 4` guard on URLs to filter junk strings).
5. **Embedding + tags.** `_embedding_input(event)` concatenates `title | location_name | description | event_url` with `|` separators; the result is fed to `generate_embedding`. `generate_event_tags(event)` runs independently on title/location/description.

**`generate_embedding`** has two paths. The OpenAI path constructs an `OpenAI(api_key=..., timeout=LLM_CLIENT_READ_TIMEOUT_SEC)` client and calls `embeddings.create(model="text-embedding-3-small", input=text)`. Any exception during construction or call falls through to `_deterministic_embedding(text)`, which tokenizes the text via `re.findall(r"[a-z0-9]+", text.lower())`, counts tokens, distributes counts across 32 hash-bucketed dimensions, and L2-normalizes the result.

**`generate_event_tags`** uses `client.responses.create(...)` (the OpenAI Responses API, not Chat Completions) with `TAGS_PROMPT.format(...)`. The response's `output_text` must parse as a JSON array of strings; non-list, non-string-element, or unparseable responses produce an empty list. After parsing, tags are stripped, lowercased, deduplicated, and capped at 10.

**`_extract_with_openai`** has the same Responses-API + JSON-parse shape, with each field coerced to a stripped string (no None-passthrough; missing fields become empty strings).

**Heuristic helpers:**

- `_extract_url(message)` — first pattern matches `http(s)://` URLs and strips trailing `).,]`; second pattern matches `www.` and prefixes `https://`.
- `_extract_phone(message)` — North American 10-digit pattern with optional `+1`, with various separators.
- `_extract_title(message)` — splits on the first `\bon\b`/`\bat\b`/time pattern, takes the prefix, strips trailing punctuation, title-cases.
- `_extract_date(message)` — checks for "today", "tomorrow", then iterates `DATE_WORDS` for weekday names (next occurrence; if today's the named day, skip to next week). Falls through to today's date.
- `_extract_time(message)` — applies `TIME_PATTERN` (one regex covering `9`, `9:30`, `9am`, `9:30 PM`); applies AM/PM logic; returns ISO time. No match → `09:00:00`.
- `_extract_location(message)` — `\bat\s+([a-z0-9\s]+)` regex; `Location TBD` fallback.

## Conventions

**Heuristic floor, LLM ceiling.** Required fields always come from the heuristic; LLM only refines. Inverting the priority (LLM-required, heuristic-fallback) would mean network/API failures produce broken events instead of best-effort ones.

**Never raises.** Every public function catches `Exception` at the LLM boundary and falls through. Callers can treat failure as silent (empty embedding, empty tags, heuristic-only event).

**Title-casing.** `_title_case(value: str) -> str` is `value.strip().title()`. Applied to title and location_name; description is left as-is.

**Description override threshold (≥20 chars).** Below 20 chars, the LLM's output is treated as too sparse to win against the full message text. The 20-char threshold is empirical, not load-bearing.

**URL override threshold (≥4 chars).** Below 4 chars, the LLM's `event_url` is treated as junk. Real URLs are ≥10 chars in practice.

**`responses.create` API.** Both LLM paths use the OpenAI Responses API via `client.responses.create(...)`, not the Chat Completions API. The model is `OPENAI_MODEL` env var or `gpt-4.1-mini` default.

**Deterministic embedding is 32-dim.** The fallback is intentionally cheap and small. It does NOT match the 1536-dim OpenAI shape (see "Known limitations").

## Known limitations and design notes

**Embedding-dimension mismatch.** OpenAI returns 1536-dim vectors; the fallback returns 32-dim vectors. Events extracted via the fallback path therefore have 32-dim embeddings stored in their `Event.embedding` column. `app/core/search.py` and `app/core/dedupe.py` both gate on `len(emb) == dim` before computing cosine similarity, so dimension-mismatched events are silently routed to keyword-only paths rather than corrupted-score paths. This is graceful but means fallback-extracted events lose semantic searchability. The query side (in `search.py`) has its own 1536-dim fallback for symmetry; the asymmetry is between query (always 1536-dim if computed) and stored events (32-dim if extracted while OpenAI was unreachable). Production seeing an offline-extracted event re-process via `app/admin/router.py:778-810` will overwrite with a 1536-dim embedding once OpenAI is reachable.

**Fallback determinism is hash-based.** `_deterministic_embedding` uses Python's `hash()`, which is randomized per process by default. Within a single process the function is deterministic; across restarts the same text produces different vectors. Fine for runtime use; surprising for tests that pickle vectors across runs.

**Title heuristic is greedy.** `_extract_title` splits on the FIRST `on`/`at`/time pattern. For messages like "Sunday on the lake, music at 7pm", the split-at-`on` fires first and produces a sub-optimal title.

**Date heuristic is naive.** No year handling, no month names, no specific dates ("December 5"). Only relative phrases (today/tomorrow/Monday) and a today-fallback.

**Phone regex is North-America-only.** International numbers (E.164, +44, +91) won't match.

**Tag generation has no retry.** A single OpenAI failure → empty tags. Callers that care about tags should retry at the call site.

**Embedding vs tag failures are independent.** `generate_embedding` and `generate_event_tags` are called separately; an embedding success + tag failure (or vice versa) is normal.

## Configuration

**Environment variables.**

- `OPENAI_API_KEY` — required for any LLM path. Missing key → all LLM functions short-circuit to fallback/empty.
- `OPENAI_MODEL` — chat model name; defaults to `gpt-4.1-mini`.

**Imported timeout.** `LLM_CLIENT_READ_TIMEOUT_SEC` from `app.core.llm_http` is passed to every `OpenAI(...)` constructor.

**Module-level constants.** `EXTRACTION_PROMPT`, `TAGS_PROMPT` (prompt strings); `TIME_PATTERN` (regex); `DATE_WORDS` (weekday name → integer 0–6).

## Related

**Direct callers:**

- `app/admin/router.py:778-810` — re-runs `_embedding_input + generate_embedding` and `generate_event_tags` on partial events during contribution review.
- `tests/test_phase8.py` — direct exercise of the extraction surface.

**Direct dependencies:**

- `app/bootstrap_env.ensure_dotenv_loaded` — loaded at module import.
- `app/core/llm_http.LLM_CLIENT_READ_TIMEOUT_SEC` — read timeout for all OpenAI clients.
- `openai.OpenAI` — optional import; module is `None` when unavailable, all LLM paths short-circuit.

**Cross-references:**

- `docs/components/llm_http.md` — timeout helpers used by every OpenAI client construction in this module.
- `docs/components/dedupe.md` — consumes `Event.embedding` (set by this module) for `cosine_similarity`.
- `docs/components/search.md` — also generates query-side embeddings via its own 1536-dim fallback path; gates on dimension match before scoring.
