# tier2_formatter

`app/chat/tier2_formatter.py`

## Purpose

Renders Tier 2 catalog rows into the user-facing response string. Two paths: deterministic Python rendering for empty-rows and all-event-rows (zero LLM tokens, structurally guaranteed row count and order), and Anthropic-backed rendering for mixed or non-event rows (rendered prose with event-link injection guarded by a deterministic post-processor).

## Public surface

**`format(query: str, rows: List[Dict[str, Any]]) -> tuple[Optional[str], int | None, int | None]`**

Sole exported function. Returns `(text, input_tokens, output_tokens)`. Empty rows and all-event rows return `(text, 0, 0)` — zero tokens because no LLM call. Mixed rows return token counts from the Anthropic call.

## Internal structure

Three branches, in order:

1. **Empty rows.** Return `(EMPTY_CATALOG_MESSAGE, 0, 0)`.
2. **All-event rows.** Strip legacy `_LEGACY_FALLBACK_RE` from each row's `description`, then `tier2_catalog_render.render_tier2_events(query, rows)`. Empty result → fallback `(None, None, None)`. Non-empty → `(text.strip(), 0, 0)`.
3. **Mixed / non-event rows.** `_format_via_llm(query, rows)` → returns `(text, in_tok, out_tok)`. Then `text = _inject_event_url_links(text, rows)` injects `[name](event_url)` markdown for any event row with non-empty `event_url` not already linked in the LLM output. Falls back to end-of-text append if the row's name doesn't appear inline.

The `_inject_event_url_links` post-processor is the deterministic safety net for Backlog #5: even when the LLM ignores or partially complies with the prompt's link-emission EXCEPTION, every event row with a URL gets a clickable link in the response.

## Conventions

**Deterministic-first.** All-event paths skip the LLM entirely. Saves tokens, eliminates count drift, guarantees row order matches SQL.

**Token-on-LLM-failure preserved.** Same convention as `tier2_parser` — billable failures still report tokens (`_format_via_llm` returns `(None, billable_input, output_tokens)` when text is empty but the API call succeeded).

**Post-processor uses word-boundary regex with inside-link guard.** Prevents injecting links inside existing markdown labels (`[Big Concert](other-url)` won't get `Concert` linked again inside the label).

**Case-sensitive name matching.** Matches the LLM's casing; falls back to end-append if the LLM lowercased.

## Known limitations

**Multi-word name overlap.** Event A "Boat Race" overlapping Event B "Annual Boat Race" can inject after the wrong occurrence. Acceptable for v1; documented in `_inject_event_url_links` docstring; refine to longest-name-first if observed in prod.

**Case sensitivity.** LLM lowercasing → orphan link at end. Acceptable v1.

**Token cost is small.** Prompt EXCEPTION line is ~30 chars; post-processor is zero-cost.

## Related

- `app/chat/tier2_handler.py` — caller (calls `format(query, rows)`).
- `app/chat/tier2_catalog_render.py` — deterministic all-event renderer (emits `[name](url)` directly).
- `prompts/tier2_formatter.txt` — system prompt for the LLM path; carries the EXCEPTION clause permitting `[name](event_url)` markdown.
- `app/core/llm_messages.py` — Anthropic helper.
