# chat_logging

`app/db/chat_logging.py` (~60 lines)

## Purpose

Persist **one assistant-turn row** per unified-router completion into `chat_logs`. The unified concierge (`app/chat/unified_router.py`) always attempts logging before returning `ChatResponse`, including fallback paths — failures must not break the user-facing reply. This module wraps insert + commit in a broad `try/except`, rolls back on failure, logs at exception level, and returns `None` instead of raising.

## Public surface

**`log_unified_route(db: Session, *, session_id, query_text_hashed, normalized_query, mode, sub_intent, entity_matched, tier_used, latency_ms, response_text, llm_tokens_used=None, llm_input_tokens=None, llm_output_tokens=None, feedback_signal=None) -> str | None`**

- Builds a `ChatLog` ORM row with `role="assistant"`.
- Returns **`str(row.id)`** (UUID string primary key) on success.
- Returns **`None`** on any persistence failure (after best-effort `rollback`).

Keyword-only arguments mirror analytics fields on `ChatLog` (see `docs/components/models.md`, `chat_logs` table).

## Inputs and outputs

**Inputs.**

- **`db`:** active SQLAlchemy `Session` (caller-owned lifecycle).
- **Tracing fields:** `session_id`, hashed query, normalized query, classifier `mode` / `sub_intent`, matched entity label, `tier_used`, wall-clock `latency_ms`.
- **`response_text`:** assistant body (truncated to 48_000 chars before insert).
- **Optional LLM accounting:** `llm_tokens_used`, `llm_input_tokens`, `llm_output_tokens` — populated when the router records Anthropic usage from consolidated callers.
- **`feedback_signal`:** Tier-3 thumb / feedback channel when set.

**Outputs.**

- Success: new row’s **`id`** as string (UUID).
- Failure: **`None`** — caller treats as non-fatal.

## Internal structure

Single function:

1. **`legacy_intent`** — `(sub_intent or mode or "")[:64]` or `None`, stored in the legacy `intent` column for backward-compatible analytics queries that predate split `mode` / `sub_intent`.
2. **`ChatLog(...)`** construction with defensive slicing on string fields (`session_id`, `query_text_hashed`, entity name, modes, feedback).
3. **`db.add` + `db.commit`**.
4. **`except Exception`:** `rollback` (nested try so rollback failures don’t mask the original error), `logging.exception("unified route chat_logs insert failed")`, return `None`.

## Conventions

**Never raises.** Router-level callers wrap even this helper in another try/except in places — defense in depth.

**Assistant-only path.** User messages are not logged here; only unified-router completion rows.

**Truncation at insert boundary.** Long responses are clipped to 48k chars so pathological LLM output cannot overflow the `Text` column binding path unduly.

## Known limitations and design notes

**Separate transaction per log.** Each call commits independently; there is no request-scoped outer transaction tying chat answer + log row.

**Legacy `intent` column duplication.** New analytics should prefer `mode`, `sub_intent`, and `tier_used`; `intent` is a compatibility shim.

**No retry.** Transient DB errors produce `None` once; no queue or backoff.

## Configuration

None in this module. Database URL and engine come from `app/db/database.py`.

## Related

**Direct callers:**

- `app/chat/unified_router.py` — `_finish` path invokes `log_unified_route`; outer try/except logs `"log_unified_route wrapper failure"` if the helper itself misbehaves.

**Direct dependencies:**

- `app.db.models.ChatLog`.

**Cross-references:**

- `docs/components/unified_router.md` — logging step in the pipeline.
- `docs/components/models.md` — `chat_logs` column inventory and migration notes.
- `HAVA_CONCIERGE_HANDOFF.md` §4 — `chat_logs` in the high-level model sketch.
