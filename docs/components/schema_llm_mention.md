# schema_llm_mention

`app/schemas/llm_mention.py` (~47 lines)

## Purpose

Pydantic models for **`app/api/routes/admin_mentions.py`**: serialize **`LlmMentionedEntity`** rows for GET handlers and validate dismiss/promote POST bodies. Uses **`Literal`** enums for closed vocabularies matching DB conventions.

## Type aliases

- **`MentionStatus`** — **`unreviewed | promoted | dismissed`** (documentary; **`LlmMentionResponse.status`** is typed **`str`** for flexibility).
- **`DismissalReason`** — **`already_in_catalog | not_relevant | noise | external_reference | other`**

## Public surface

### `LlmMentionResponse`

**`model_config = ConfigDict(from_attributes=True)`**

Fields: **`id`**, **`chat_log_id`**, **`mentioned_name`**, **`context_snippet`**, **`detected_at`**, **`status`**, **`reviewed_at`**, **`dismissal_reason`**, **`promoted_to_contribution_id`**.

**Produced by:** **`GET /admin/api/mentioned-entities`**, **`GET …/{id}`**, **`POST …/dismiss`**, **`POST …/promote`** (`model_validate` from ORM row).

### `MentionDismissBody`

- **`reason: DismissalReason`**

**Consumed by:** **`POST /mentioned-entities/{mention_id}/dismiss`**.

### `MentionPromoteBody`

Promotion builds a **`ContributionCreate`** downstream — fields overlap partially:

- **`entity_type: Literal["provider", "program", "event", "tip"]`**
- **`submission_name`** — 1–200
- Optional **`submission_url`** (**`HttpUrl | None`**), **`submission_category_hint`**, **`submission_notes`**
- Optional **`event_date`**, **`event_time_start`**, **`event_time_end`** (**`datetime.time`**)

**Notably absent vs full `ContributionCreate`:** **`event_end_date`**, **`source_url`**, email, **`source`**, **`llm_source_chat_log_id`** — those are injected/set at route/service layer when constructing **`ContributionCreate`**.

**Consumed by:** **`POST /mentioned-entities/{mention_id}/promote`**.

## Inputs and outputs

Admin routes require **cookie auth** (**`require_admin`**) — outside this schema file.

Dismiss/promote responses return refreshed **`LlmMentionResponse`** snapshots.

## Internal structure

No **`model_validator`** — constraints are **`Field`** lengths and **`Literal`** / **`HttpUrl`** types only.

## Conventions

**Dismissal reasons** must stay aligned with admin UI option lists and any analytics that aggregate reasons.

## Known limitations and design notes

**Promote body is a subset schema** — callers must not assume every **`ContributionCreate`** field is client-supplied; **`admin_mentions`** merges server fields.

## Configuration

None.

## Related

**Direct consumers:**

- **`app/api/routes/admin_mentions.py`**

**Cross-references:**

- **`docs/components/llm_mention_store.md`**
- **`docs/components/schema_contribution.md`** — **`ContributionCreate`** full shape.
- **`docs/components/mention_scanner.md`** — upstream candidate creation.
