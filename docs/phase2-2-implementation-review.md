# Phase 2.2 — implementation review (for Claude)

Paste-friendly summary of what was built for **Phase 2.2 (unified router)**. Full suite: **331 tests passed** (+11 from `test_unified_router.py`). **Not committed** at the time this note was written unless the owner already committed afterward.

---

## What was added / changed

### New: `app/chat/unified_router.py`

- **`ChatResponse`** dataclass: `response`, `mode`, `sub_intent`, `entity`, `tier_used`, `latency_ms`.
- **`route(query, session_id, db) -> ChatResponse`**
  - `time.perf_counter()` for **`latency_ms`** (floored at **1** so it is never 0).
  - **`normalize`** → **`classify(nq_safe)`** (normalized string, per Phase 2.2 prompt).
  - **Entity enrichment:** if `intent_result.entity` is `None`, **`refresh_entity_matcher(db)`** then **`match_entity(query, db)`** on the **original** `query`; **`dataclasses.replace`** updates only `entity` (routing unchanged).
  - **Session:** `session_id` only passed into handlers that take it; **no session dict writes** (Track A `app/core/session.py` unchanged).
  - **Failures (§3.11-style):** normalize / classify / mode handler → log exception, return **`Something went sideways on my end — try that again in a sec.`**, still **`log_unified_route`** with whatever mode/sub/entity we have.
- **Placeholders**
  - **Ask:** `Ask mode: intent=[sub], entity=[…]. Retrieval will be implemented in Phase 3.`
  - **Contribute:** `Contribute mode: type=[sub]. Intake flow will be implemented in Phase 4.`
  - **Correct:** `Correct mode: received. Correction flow will be implemented in Phase 5.`
- **Chat (real copy)**
  - **GREETING:** rotate **`"Hey — what are you looking for?"` / `"What's up?"` / `"Heya."`** with **`sha256(session_id or "__anon__") % 3`** so the same session gets a stable variant.
  - **OUT_OF_SCOPE:** **§8.7** string (Unicode **—**):  
    `That's outside what I cover right now — I stick to things-to-do, local businesses, and events. Want me to point you to anything else?`
  - **SMALL_TALK:** thanks/thank you/thx/appreciate → **`anytime.`**; **`how are you`** → **`doing alright. what can I find for you?`** (per owner prompt); bye/goodbye/goodnight → **`see you.`**; else **`alright.`**
- **`tier_used`:** **`chat`** for chat mode; **`placeholder`** for ask / contribute / correct (handlers are stubs, so not labeling **`intake`** / **`correction`** yet).

### `app/db/chat_logging.py`

- New **`log_unified_route(...)`**: inserts **`ChatLog`** with **`role="assistant"`**, **`message=response_text`**, legacy **`intent=(sub_intent or mode)[:64]`**, plus the new analytics fields. Same **never-raise** pattern as **`log_chat_turn`**.

### `app/db/models.py` — **`ChatLog`** (nullable columns for legacy rows)

- `query_text_hashed`, `normalized_query`, `mode`, `sub_intent`, `entity_matched`, `tier_used`, `latency_ms`, `llm_tokens_used`, `feedback_signal`

### New migration: `alembic/versions/f1a2b3c4d506_chat_logs_unified_router_columns.py`

- **`down_revision = e8a1c2d3e404`** (head chain at time of implementation).

### New: `tests/test_unified_router.py`

- Per-mode metadata, real chat strings, **`classify` raises** → graceful + new log row, handler raise, **`0 < latency_ms < 500`**, entity enrichment with **`Program`** + patched **`classify`**.

---

## Deviations / flags (for review)

1. **`models.py` + migration** — Phase 2.2 prompt only explicitly allowed extending **`chat_logging.py`**, but **§3.10** fields cannot persist without **`ChatLog`** columns. One migration + model fields were added. Alternative would be encoding metadata only in **`message`**, which was avoided.
2. **§3.9 vs GREETING copy** — Owner asked for three greeting lines including **“Hey — what are you looking for?”** and **“What’s up?”** while §3.9 discourages follow-up questions outside intake/correction. Implementation followed the **Phase 2.2 prompt** literally; copy can be tightened in a later voice pass.
3. **`tier_used`** — **`placeholder`** for contribute/correct (and ask) so real **intake** / **correction** pipelines are not implied in **2.2**.
4. **User-visible text** is stored in existing **`message`**; there is **no separate `response_text` column** (avoids duplicating the same string).

---

## Not touched (per Phase 2.2 constraints)

- **`app/chat/router.py`**, **`intent_classifier.py`**, **`normalizer.py`**, **`entity_matcher.py`**, **`tier1_templates.py`**
- **No new HTTP endpoint**, **no LLM**

---

## Commit status

At generation time, the owner was asked to **review before commit**; commit when they say **commit** (or provide an amended message).

---

*Generated from the assistant Phase 2.2 checkpoint message.*
