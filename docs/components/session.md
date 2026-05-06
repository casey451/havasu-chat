# session

`app/core/session.py` (~240 lines)

## Purpose

Process-local **in-memory session store** for conversational state: search slots, flow awaits, duplicate-merge scaffolding, onboarding hints, **`prior_entity`** pronoun memory, monotonic blocking TTLs, and optional search-slot snapshot stack.

Primary consumer is **`app/chat/unified_router.py`**; onboarding routes touch **`onboarding_hints`** directly via **`get_session`**.

## Public surface — module state

**`sessions: dict[str, dict[str, Any]]`** — Keyed by **`session_id`** string; values are heterogeneous dicts.

**`BLOCKING_SESSION_TTL_SEC = 300.0`** — Five-minute ceiling on blocking clarification flows (**`time.monotonic()`** based).

**`IDLE_SESSION_RESET_SEC = 30 * 60`** — Thirty idle minutes triggers hint **`prior_entity`** wipe inside **`touch_session`**.

## Public surface — factories / accessors

**`_default_search()`**, **`_default_flow()`**, **`_default_onboarding_hints()`** — Canonical nested defaults (`slots`, listing flags, onboarding **`visitor_status` / `has_kids` / `age` / `location`**, etc.).

**`get_session(session_id) -> dict`** — Lazily **`clear_session_state`** when unseen; **`setdefault`** merges missing keys for backward compatibility (**`age`/`location`** hints added post-hoc).

**`touch_session(session_id)`** — Updates **`last_activity_at`** (UTC aware); if idle window exceeded, resets **`onboarding_hints`** + **`prior_entity`** only (search memory intentionally survives shorter idle gaps).

**`clear_session_state(session_id)`** — Hard reset dict template (**full wipe** of conversational markers).

**`clear_current_flow` / `clear_add_branch` / `soft_clear_awaits`** — Layered partial clears preserving search memory differently per helper docstrings.

**`update_hints_from_extraction(session_id, extracted)`** — Merges **`hint_extractor`** dataclass fields **`age` / `location`** when present.

**`record_entity(session_id, entity_name, turn_number, db)`** — Resolves provider **`id`** via SQLAlchemy **`select(Provider)`** lookup by **`provider_name`** match (falls back to raw string **`id`** on DB failure).

**`push_search_snapshot(session)`** — Maintains **single-slot** **`snapshot_stack`** (**deepcopy** of current **`slots`**, clears stack before append — effectively one undo frame).

## Flow / blocking helpers

**`any_awaiting_user_reply`**, **`blocking_session_expired`**, **`arm_session_blocking`**, **`set_flow_awaiting`**, **`get_flow`**, **`get_search`** — orchestrate **`flow.awaiting`** timestamps vs legacy boolean awaits (**`awaiting_confirmation`**, duplicate-merge flags, etc.).

## Inputs and outputs

Functions mutate dicts **in place**; **`get_session`** returns live references — callers must not alias across sessions without copying.

## Internal structure

**`blocking_mono`** stores **`time.monotonic()`** floats — resilient to wall-clock jumps unlike **`datetime`** alone.

**`awaiting_since`** naive UTC **`datetime`** mirrors legacy SQLite-friendly storage patterns used elsewhere.

## Known limitations and design notes (load-bearing)

**Process-local only:**

- **Survives neither deploy/restart nor horizontal scale.** Multiple Railway dynos each hold disjoint dictionaries — a user pinned to another worker loses session continuity.

**No eviction/TTL beyond idle onboarding reset** — stale **`session_id`** keys linger until accessed again (memory leak risk only under adversarial session-id churn).

**`record_entity` assumes provider-type pronouns** — stores **`type: provider`** even when future tiers might resolve programs/events.

## Configuration

None — TTL constants are code-level.

## Related

**Direct callers:**

- **`app/chat/unified_router.py`** — bulk imports (**`get_session`**, clears, flow helpers, **`record_entity`**).
- **`app/api/routes/chat.py`** — onboarding **`get_session`** reads/writes hints.

**Tests:**

- **`tests/test_session_memory.py`**, **`tests/test_prior_entity_router.py`**, **`tests/test_classifier_hint_extraction.py`**, **`tests/test_api_chat_onboarding.py`**, **`tests/test_phase8.py`**, **`tests/test_phase8_5.py`**.

**Cross-references:**

- **`docs/components/unified_router.md`** — session lifecycle coupling.
