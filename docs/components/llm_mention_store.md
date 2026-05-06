# llm_mention_store

`app/db/llm_mention_store.py` (~111 lines)

## Purpose

CRUD and listing helpers for **`llm_mentioned_entities`** — Tier-3 **mention candidates** captured after assistant replies (`app/contrib/mention_scanner.py`) for operator review, dismissal, or promotion into the **`contributions`** queue. Inserts respect the **`(chat_log_id, mentioned_name)`** uniqueness constraint; collisions return **`None`** rather than raising.

## Public surface

**`create_mention(db, chat_log_id, mentioned_name, context_snippet) -> LlmMentionedEntity | None`**

- Inserts row; **`mentioned_name`** truncated to 300 chars; **`context_snippet`** to 500 (empty string stored as `NULL`).
- **`IntegrityError`** → `rollback`, return **`None`** (duplicate mention for same log + name).

**`get_mention(db, mention_id) -> LlmMentionedEntity | None`**

**`list_mentions(db, status=None, detected_from=None, detected_to=None, limit=50, offset=0) -> Sequence[LlmMentionedEntity]`** — Ordered **`detected_at DESC`**.

**`count_mentions(db, ...)`** — Matching filters for pagination UI.

**`dismiss_mention(db, mention_id, dismissal_reason) -> LlmMentionedEntity | None`** — Sets **`status="dismissed"`**, **`reviewed_at`** (UTC naive), **`dismissal_reason[:128]`**.

**`promote_mention(db, mention_id, contribution_id) -> LlmMentionedEntity | None`** — Sets **`status="promoted"`**, **`promoted_to_contribution_id`**, **`reviewed_at`**, clears **`dismissal_reason`**.

## Inputs and outputs

**`chat_log_id`** references **`chat_logs.id`** (UUID string FK) — ties mention back to the logged Tier-3 turn.

**Filters** use inclusive datetime bounds on **`detected_at`** when provided.

**Mutation helpers** return **`None`** if the mention row doesn’t exist.

## Internal structure

**`_naive_utc_now()`** — `datetime.now(UTC).replace(tzinfo=None)` shared pattern with `contribution_store` for reviewed timestamps.

**`create_mention`** uses try/except around **`commit`** specifically for **`IntegrityError`** — other exceptions propagate (unexpected schema/driver faults).

## Conventions

**Status strings are not centralized in a Python enum here.** Valid values are implied by admin flows (`unreviewed`, `dismissed`, `promoted`) — changing literals requires coordinated router/HTML/API updates.

**Promotion stores FK only.** Linking a promoted contribution to catalog rows happens later via **`approval_service`** after operator approval.

## Known limitations and design notes

**Duplicate = silent None.** Scanner and callers don’t distinguish “DB dead” vs “duplicate”; acceptable because duplicates are idempotent by definition.

**No bulk insert API.** Each candidate is its own transaction from `create_mention`.

**Pagination offset/limit only.** No cursor-based paging for large queues.

## Configuration

None.

## Related

**Direct callers:**

- `app/contrib/mention_scanner.py` — `scan_and_save_mentions` → `create_mention`.
- `app/api/routes/admin_mentions.py` — JSON list/get/dismiss/promote + background enrichment.
- `app/admin/mentions_html.py` — operator HTML surface.

**Direct dependencies:**

- `app.db.models.LlmMentionedEntity`
- `sqlalchemy.exc.IntegrityError`

**Cross-references:**

- `docs/components/mention_scanner.md` — extraction heuristics and stop-list.
- `docs/components/models.md` — table constraints and indexes.
- `docs/components/admin_mentions_html.md` — HTML wiring.
- `HAVA_CONCIERGE_HANDOFF.md` §4 — mentions in schema sketch.
