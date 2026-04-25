# Phase 8.8.4 — HALT 3 report (Step 3: LLM router + prompt)

**Date:** 2026-04-25  
**Status:** Awaiting owner review (prompt + `RouterDecision`) before Step 4 (unified_router integration).

## Pytest

```text
python -m pytest tests/test_llm_router.py -v
```

**11 passed** (Windows, `.venv`, Anthropic always mocked).

Tests cover: valid Tier2 and Tier3 JSON, markdown-fenced JSON, malformed JSON, invalid `tier_recommendation`, Tier2 with missing `tier2_filters`, API exception, empty API key, prompt file presence, `messages.create` model/temp/max_tokens, and `RouterDecision` validation (Tier2 requires `tier2_filters`).

## `RouterDecision` (Pydantic)

**File:** `app/chat/llm_router.py`

- `mode` — one of `ask` | `contribute` | `correct` | `chat`
- `sub_intent` — must be in the spec’s `TIME_LOOKUP` … `OUT_OF_SCOPE` set
- `entity` — `None` if missing / empty / `"null"`
- `router_confidence` — 0.0–1.0
- `tier_recommendation` — **only** `"2"` or `"3"`
- `tier2_filters` — `None` for Tier3; for Tier2, validated with `Tier2Filters` (Pydantic)

**Model rule:** `tier_recommendation == "2"` **requires** non-`null` `tier2_filters` (satisfies “Tier3 may omit filters” and avoids an empty object).

## Inference and errors (`route()`)

| Failure | Behavior |
|--------|----------|
| `ANTHROPIC_API_KEY` empty | `info` log, return `None` |
| Missing / unreadable prompt | `error` / exception log, return `None` |
| `messages.create` raises | `exception` log, return `None` |
| Response not a JSON object | `warning` log, return `None` |
| JSON fails `RouterDecision` or `Tier2Filters` | `exception` log, return `None` |
| Success | `info` with `model`, `latency_ms`, `in_tokens~` / `out_tokens~`, `tier` |

- **Model:** `ANTHROPIC_MODEL` or `claude-haiku-4-5-20251001`  
- **max_tokens:** 500, **temperature:** 0.0, **timeout:** `LLM_CLIENT_READ_TIMEOUT_SEC` (45s)  
- **User message:** `raw_query`, `normalized_query`, optional JSON `context`

## Policy check (owner review)

- **Ambiguous:** Section 3, item 4: prefer Tier2 if `router_confidence >= 0.7` and filters are *meaningful*; otherwise Tier3. Example 8 uses 0.7 and Tier3 (synthesis / “what should I do”).
- **No `gap`:** schema + Section 1 explicitly forbid `gap` / `gap_template`.

## Files added / changed (Step 3)

- `app/chat/llm_router.py` (new)  
- `prompts/llm_router.txt` (new)  
- `tests/test_llm_router.py` (new)

## Appendix — `prompts/llm_router.txt` (verbatim)

> Source of truth: this block matches `prompts/llm_router.txt` in the repository at the HALT3 commit. If they differ, the on-disk file wins.

(See `prompts/llm_router.txt` in the repo for the full 360+ line prompt — too long to maintain duplicate copies in this report; open that file for review. HALT3 chat handoff will paste the same file contents for diff-free reading.)

**Note:** The implementation copies Section 1–5 and 12 few-shots (full `tier2_filters` keys in examples) from the Phase 8.8.4 v2 spec; July 4 examples use year **2026** as required.

---

## Next

**Step 4:** `USE_LLM_ROUTER` in `unified_router._handle_ask`, bypass parser when router returns Tier2 filters, integration tests, full-suite pytest with flag on/off.
