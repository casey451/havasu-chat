# Phase 3.2 — Tier 3 & context builder (implementation report)

Handoff for Claude / future sessions. **No real Anthropic calls** were used in tests; Tier 3 is mocked in router/API integration tests where needed.

---

## Summary

- **Tier 1 miss → Tier 3:** `app/chat/unified_router.py` `_handle_ask` calls `try_tier1` first; on `None`, calls `answer_with_tier3`, returns `tier_used="3"`.
- **Tokens:** `answer_with_tier3` returns `(text, tokens | None)`. `llm_tokens_used` flows through `ChatResponse`, `POST /api/chat` (`ConciergeChatResponse`), and `log_unified_route` / `chat_logs.llm_tokens_used`.
- **System prompt caching:** Tier 3 passes  
  `system=[{"type": "text", "text": <prompt>, "cache_control": {"type": "ephemeral"}}]`  
  to `anthropic` `messages.create` (ephemeral prompt cache per Anthropic).
- **Context:** `app/chat/context_builder.py` — `build_context_for_tier3` (word budget ≤1500, max 10 providers, excludes draft providers, inactive programs, past events; truncates long hours; non-empty fallback when catalog would otherwise be empty).

**Constraints honored (from original spec):** No edits to `tier1_handler.py`, `tier1_templates.py`, `intent_classifier.py`, `entity_matcher.py`, `normalizer.py`; no DB schema/model changes; tests mock Anthropic unconditionally.

---

## Files created

| Path | Role |
|------|------|
| `app/chat/context_builder.py` | Catalog → plain-text context for Tier 3 |
| `app/chat/tier3_handler.py` | `answer_with_tier3`; Anthropic + usage sum + fallbacks |
| `tests/test_context_builder.py` | Context rules + DB isolation (savepoint + `flush`) |
| `tests/test_tier3_handler.py` | Tier 3 behavior; `anthropic.Anthropic` mocked |
| `prompts/system_prompt.txt` | Concierge system instructions (loaded by Tier 3) |

---

## Files modified

| Path | Role |
|------|------|
| `app/chat/unified_router.py` | Ask path, `ChatResponse.llm_tokens_used`, logging |
| `app/schemas/chat.py` | `ConciergeChatResponse.llm_tokens_used` |
| `app/api/routes/chat.py` | Map `llm_tokens_used` on API response |
| `requirements.txt` | `anthropic==0.96.0` |
| `tests/test_unified_router.py` | Tier 3 expectations + mocks + token log assertions |
| `tests/test_api_chat.py` | Response keys + tier 3 mock for open-ended ask |
| `tests/test_phase2_integration.py` | Ask tier `"3"`, `llm_tokens_used` body vs log, mock |

---

## Pytest

- **After implementation:** **385 passed** (full `tests/` suite).
- **Prior failing run (handoff):** 383 passed, 2 failed (same 385 tests total) — failures were `test_context_builder` entity assertion + `test_phase3` search pollution from shared DB; fixed via isolated savepoint in context builder tests + `flush()` instead of `commit()` inside the savepoint.

---

## Token budget (rough)

| Component | Estimate |
|-----------|----------|
| System prompt | ~150–250 tokens (short rules in `prompts/system_prompt.txt`; first call also incurs cache-creation billing per Anthropic) |
| User message | Classifier line + user query + context block |
| Context | Capped at **≤1500 words** (~1.9k–2.2k tokens depending on wording) |
| Typical total input | Often ~**2.2k–3.5k** tokens before repeat hits benefit from cache reads |
| Output | `max_tokens=150`, `temperature=0.3` — replies usually **well under** 150 tokens |

---

## Anthropic SDK (`anthropic==0.96.0`)

- `messages.create(..., system=[{ "type":"text", "text":..., "cache_control":{"type":"ephemeral"} }], ...)` matches current API shape.
- `Message.usage` includes `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`; Tier 3 sums these for `llm_tokens_used` when `usage` is present.
- If SDK or cache-control behavior drifts, re-verify against [Anthropic docs](https://docs.anthropic.com) for your target date.

---

## Sample context shape (not the system prompt)

Plain text; first block is a fixed header, then one stanza per provider (programs/events as lines under that provider):

```text
Context — Lake Havasu catalog snapshot (programs and events may be partial):

Provider: Sample Marina
  category: recreation
  phone: 555-0100
  hours: Dawn to dusk daily
  verified: yes

Provider: Another Business
  category: food
  address: …
  Program: … | ages … | schedule …
  Upcoming event: … on YYYY-MM-DD at HH:MM — …
```

---

## Local DB note

During a one-off diagnostic, a temporary `Sample Marina` provider row may have been inserted into the default SQLite DB and was **removed** afterward. If you see odd rows, check `providers` for stray test names.

---

## Scope caveat (original “create only” list)

The original hard constraint listed only certain new files and minimal edits. **Also required in practice:** `prompts/system_prompt.txt`, `app/schemas/chat.py`, and `app/api/routes/chat.py` so Tier 3 has a system file and clients/logs receive `llm_tokens_used`. If you need a stricter file list, define how `llm_tokens_used` should be exposed without schema/API changes.

---

## Key entry points (for code search)

- Router: `app/chat/unified_router.py` — `_handle_ask`, `route`, `ChatResponse`, `_finish` → `log_unified_route`
- Tier 3: `app/chat/tier3_handler.py` — `answer_with_tier3`, `_load_system_prompt`, `_sum_usage`
- Context: `app/chat/context_builder.py` — `build_context_for_tier3`
