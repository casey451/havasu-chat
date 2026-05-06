# schema_contribution

`app/schemas/contribution.py` (~144 lines)

## Purpose

Pydantic models for **Contribution** intake and operator workflows: public/API **create** payloads, **admin JSON** list/detail/status transitions, **approval** field bundles used when materializing **`Provider` / `Program` / `Event`** rows, and **`ContributionResponse`** ORM projection. Shared **`Literal`** aliases (`EntityType`, **`ContributionSource`**, **`ContributionStatus`**, **`RejectionReason`**) keep FastAPI and stores aligned with **`contribution_store`** validation.

## Type aliases (module level)

- **`EntityType`** — **`"provider" | "program" | "event" | "tip"`**
- **`ContributionSource`** — **`user_submission | llm_inferred | operator_backfill | river_scene_import`**
- **`ContributionStatus`** — **`pending | approved | rejected | needs_info`**
- **`RejectionReason`** — **`duplicate | out_of_area | spam | incomplete | unverifiable | other`**

## Public surface — models

### `ContributionCreate`

**Fields (high level):** **`entity_type`**, **`submission_name`** (1–200), optional **`submission_url`** (**`HttpUrl | None`**), **`source_url`**, hints/notes, optional **`event_*`** dates/times, optional **`submitter_email`** (**`EmailStr`**), **`source`** (default **`operator_backfill`**), **`llm_source_chat_log_id`**, **`unverified`**.

**`@model_validator(mode="after")`** — **`provider_requires_url`**: if **`entity_type == "provider"`** then **`submission_url`** must be non-**`None`**.

**Consumed by:** **`POST /admin/api/contributions`** (when mounted), **`POST`** public contribute (`contribute.py`), **`contribution_store.create_contribution`**, **`RiverSceneEvent.normalize_to_contribution`**, mention-promotion paths (`admin_mentions.py`, `mentions_html.py`), tests.

### `ContributionStatusUpdate`

**Fields:** **`status`**, optional **`review_notes`**, optional **`rejection_reason`**.

**`@model_validator(mode="after")`** — **`rejected_requires_reason`**: **`status == "rejected"`** ⇒ **`rejection_reason`** required.

**Consumed by:** **`PATCH`** contribution status on **`admin_contributions`** router.

### `ProviderApprovalFields`

Operator-edited **`Provider`** fields on approve: **`name`** (strip **`mode="before"`**), **`address`**, **`phone`**, **`hours`**, **`description`**, **`website`**.

**Consumed by:** **`approval_service`**, **`contributions_html`** approve POST parsing.

### `ProgramApprovalFields`

**HTML/form-shaped program approve bundle** — **`schedule_start_time` / `schedule_end_time`** remain **`str`** with **`min_length=5`, `max_length=5`** (**`HH:MM`** tokens as strings). Other fields: **`title`**, **`description`** (≥20 chars), ages, **`schedule_days`**, location, cost, **`provider_name`**, contacts, **`tags`**.

**Not** the same type profile as **`ProgramCreate`** in **`schema_program`** (which uses **`datetime.time`** + validators — see **`docs/components/schema_program.md`**). Admin HTML builds these structs before downstream conversion.

**Consumed by:** **`contributions_html`**, **`approval_service`**, tests.

### `EventApprovalFields`

**Fields:** **`title`**, **`description`** (≥20), **`date`**, optional **`end_date`**, **`start_time` / `end_time`** (**`datetime.time`**), **`location_name`**, **`event_url`**, optional **`source_url`**.

**Consumed by:** **`contributions_html`**, **`approval_service`**, **`river_scene_pull`** approval helpers, **`approve_pending_river_scene`** script.

### `ContributionResponse`

**`model_config = ConfigDict(from_attributes=True)`** — full Contribution row projection for admin/public APIs: ids, timestamps, submitter fields, entity payload, URL-fetch metadata, Places **`google_*`** blobs, status/review fields, **`created_*_id`** FK echoes, **`source`**, **`llm_source_chat_log_id`**, **`unverified`**.

**Produced by:** **`admin_contributions`** list/detail/create/status routes via **`model_validate(row)`**.

## Inputs and outputs

**Creates** accept normalized Python types (`date`, `time`, `HttpUrl`, `EmailStr`). **Responses** serialize from **`Contribution`** ORM rows.

## Internal structure

Validators are limited to **two `model_validator`s** (provider URL, rejection reason) plus **`ProviderApprovalFields.strip_name`**. No shared mixin — repeated length constraints live per approval struct.

## Conventions

**Default `ContributionCreate.source` is `operator_backfill`** — public **`contribute.py`** overwrites to **`user_submission`** (and RS import uses **`river_scene_import`**) at call sites.

**`tip` entity type** exists for forward-compatible intake; promotion flows mirror other kinds where wired.

## Known limitations and design notes

**`ProgramApprovalFields` vs ORM `Program`:** schedule columns on the database are **`Time`** (Slice 56); approval structs stay **string `HH:MM`** for form ergonomics — conversion happens in **`approval_service`** / **`ProgramCreate`** boundaries.

**`ContributionResponse.status` is plain `str`** in the schema despite **`ContributionStatus`** literal elsewhere — historical flexibility for unexpected DB values in admin UI.

## Configuration

None.

## Related

**Direct consumers:**

- **`app/api/routes/admin_contributions.py`**, **`contribute.py`**, **`admin_mentions.py`**
- **`app/admin/contributions_html.py`**, **`mentions_html.py`**
- **`app/contrib/approval_service.py`**, **`river_scene.py`**, **`river_scene_pull.py`**
- **`app/db/contribution_store.py`**

**Cross-references:**

- **`docs/components/schema_program.md`**, **`schema_event.md`** — typed catalog payloads adjacent to approval bundles.
- **`docs/components/contribution_store.md`**, **`approval_service.md`**
- **`docs/maintainability/end_to_end_creation.md`**
