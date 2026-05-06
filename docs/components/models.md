# models

`app/db/models.py` (~322 lines)

## Purpose

**Declarative SQLAlchemy 2.0 ORM definitions** for the whole product catalog, intake queues, chat telemetry, and legacy correction metadata. This file is the **in-repo schema source of truth** beside Alembic revisions under `alembic/versions/`. Every table maps to a `Base` subclass imported from `app.db.database.Base`.

High-level grouping aligns with **`HAVA_CONCIERGE_HANDOFF.md` §4**:

- **Catalog:** `Provider`, `Program`, `Event`
- **Queues:** `Contribution`, `LlmMentionedEntity`
- **Telemetry:** `ChatLog`
- **Legacy / sparse:** `FieldHistory`

## Public surface

The module exports **ORM mapped classes** consumed across routers, chat tiers, contrib pipelines, and scripts:

| Class | Table |
|-------|-------|
| `Provider` | `providers` |
| `FieldHistory` | `field_history` |
| `Event` | `events` |
| `ChatLog` | `chat_logs` |
| `Program` | `programs` |
| `Contribution` | `contributions` |
| `LlmMentionedEntity` | `llm_mentioned_entities` |

There is no free-function API in this module. **`Event.from_create(cls, payload: EventCreate)`** is the only classmethod — builds an `Event` from the Pydantic create schema with normalization and verification defaults.

## Inputs and outputs

ORM objects are constructed by callers with keyword args matching mapped columns; relationships hydrate via **`relationship(..., back_populates=...)`** when queried with a session. **`Event.from_create`** accepts **`EventCreate`** (`app.schemas.event`) and returns an unpersisted **`Event`** instance (caller adds/commits).

---

## Table reference

### `Provider` (`providers`)

**Purpose.** Top-level business / venue row for Tier 1–3 catalog context, programs, and linked events. Approval flows and admin create surfaces write here.

**Key columns.**

- **Identity:** `id` (`String` PK, UUID string default).
- **Display / contact:** `provider_name`, `category`, `address`, `phone`, `email`, `website`, `facebook`, `hours` (`Text`), `hours_structured` (`JSON`), `description`.
- **Commercial flags:** `tier`, `sponsored_until`, `featured_description`.
- **Lifecycle:** `draft`, `verified`, `is_active`, `pending_review`, `admin_review_by`.
- **Provenance:** `source` (defaults **`seed`**), `created_at`, `updated_at`.
- **Geo / enrichment:** `google_place_id` (**indexed**), `lat`, `lng`, `embedding` (`JSON`, null-normalized at migration layer — see Alembic note below), `match_confidence`, `enrichment_version`, `raw_enrichment_json`.

**Relationships.**

- **`programs`**, **`events`** — one-to-many via `Program.provider_id` / `Event.provider_id`.

**Constraints / indexes.**

- PK on `id`.
- Index on **`google_place_id`** (`index=True`).

---

### `FieldHistory` (`field_history`)

**Purpose.** Row-per-field correction / dispute workflow (Phase AA-era design). Stores old/new values, confirmation/dispute counts, resolution timestamps. **Sparse in production** after RS-only cleanup — retained for schema continuity and **`scripts/cleanup_non_river_scene.py`** / tests.

**Key columns.**

- **Target:** `entity_type`, `entity_id`, `field_name`.
- **Values:** `old_value`, `new_value` (`Text`).
- **Workflow:** `source`, `submitted_by_session`, `submitted_at`, `state`, `confirmations`, `disputes`, `resolution_deadline`, `resolved_at`, `resolved_value`, `resolution_source`.

**Relationships.** None declared — loose coupling by string `entity_id`.

**Constraints / indexes.** PK `id` (UUID string). No composite indexes in ORM (see migrations if added).

---

### `Event` (`events`)

**Purpose.** Calendar occurrence rows — Tier 2 SQL retrieval, Tier 3 context, dedupe (`app/core/dedupe.py`), permalinks, River Scene import.

**Key columns.**

- **When / where:** `title`, `normalized_title`, `date`, `end_date`, `start_time` (**`Time`**, not string), `end_time`, `location_name`, `location_normalized`.
- **Content:** `description` (`Text`), `tags` (`JSON` list), `embedding` (`JSON`, nullable).
- **URLs:** `event_url` (`String(2048)`, default `""`), `source_url` (`String(2048)` nullable).
- **Contacts:** `contact_name`, `contact_phone`.
- **Lifecycle:** `status` (default **`live`**), `source`, `verified`, `created_at`, `created_by`, `admin_review_by`.
- **Linkage:** `provider_id` → **`providers.id`** (`nullable=True`).
- **Recurrence flag:** `is_recurring` (`Boolean`, server default false).

**Relationships.**

- **`provider`** — many-to-one optional.

**Constraints / indexes.**

- FK **`provider_id` → providers.id**.
- **`from_create`** sets `normalized_*` fields lowercase-stripped; **`verified`** defaults from payload or `source == "admin"` policy inside classmethod.

**Alembic notes.**

- Multi-day support: **`end_date`** migration (`f2e1d0c9b8a7_add_events_and_contributions_end_date`).
- **`provider_id`** (`e8a1c2d3e404_add_events_provider_id`).
- **`source_url`** (`7d8c9e0f1a2b_add_source_url_to_contributions_and_events`).
- **`is_recurring`** (`f3a1b2c3d4e5_add_events_is_recurring`).

---

### `ChatLog` (`chat_logs`)

**Purpose.** Persist chat turns — historically multi-role; unified concierge logs **assistant** completions with analytics extensions (`app/db/chat_logging.py`).

**Key columns.**

- **Core:** `id` (UUID string PK), **`session_id`** (**indexed**), `message` (`Text`), **`role`**, legacy **`intent`** (nullable).
- **Timestamps:** **`created_at`** (**indexed**, default now).
- **Unified router analytics (nullable for legacy rows):** `query_text_hashed`, `normalized_query`, `mode`, `sub_intent`, `entity_matched`, `tier_used`, `latency_ms`, `llm_tokens_used`, `llm_input_tokens`, `llm_output_tokens`, `feedback_signal`.

**Relationships.**

- **`Contribution.llm_source_chat_log_id`** references **`chat_logs.id`**.
- **`LlmMentionedEntity.chat_log_id`** references **`chat_logs.id`**.

**Constraints / indexes.**

- Indexes on **`session_id`** and **`created_at`** per mapped_column flags.

**Alembic notes.**

- Table creation: **`b2f8c1a9d0e1_add_chat_logs_table`**.
- Unified-router columns: **`f1a2b3c4d506_chat_logs_unified_router_columns`**.
- **`llm_input_tokens` / `llm_output_tokens`:** **`7a8b9c0d1e2f_add_llm_input_output_token_columns`**.
- **`created_at` index:** **`a8f2c1d0e1ab_add_chat_logs_created_at_index`**.

---

### `Program` (`programs`)

**Purpose.** Recurring / structured offerings (classes, leagues) hanging off providers — Tier 1 age/time windows, Tier 2 retrieval, Tier 3 context blocks.

**Key columns.**

- **Identity / description:** `id` (UUID string), `title`, `description`, `activity_category`.
- **Audience:** `age_min`, `age_max`.
- **Schedule:** `schedule_days` (`JSON` list), **`schedule_start_time`** / **`schedule_end_time`** — canonical SQL types **`Time`** (Slice 56 campaign closed dual-write string era — see below).
- **Venue / contact:** `location_name`, `location_address`, `cost`, `provider_name`, `contact_phone`, `contact_email`, `contact_url`.
- **Lifecycle:** `source`, `verified`, `is_active`, `tags`, `embedding`, `created_at`, `updated_at`.
- **Provider link:** `provider_id` → **`providers.id`** (nullable).
- **UX flags:** `show_pricing_cta`, `cost_description`, `schedule_note`.
- **Review:** `draft`, `pending_review`, `admin_review_by`.

**Relationships.**

- **`provider`** — many-to-one optional.

**Constraints / indexes.**

- FK **`provider_id`**.

**Alembic / type-evolution notes (important).**

- Initial programs table: **`c3a9e2f5b801_add_programs_table`**.
- Concierge column expansion: **`e8a1c2d3e403_expand_programs_concierge_columns`**.
- **`source` / `verified`**: **`d4b7e2f1c902_add_source_and_verified`** (also touched events).
- Typed shadow columns (dual-write phase): **`f4a5b6c7d8e9_add_program_typed_time_columns`** (superseded by Slice 56 end state).
- **Canonical `Time` columns today:** **`a7b8c9d0e1f2_drop_program_strings_rename_typed_canonical`** — drops legacy `String(5)` schedule columns and renames typed columns to `schedule_start_time` / `schedule_end_time`. ORM comments in `models.py` point at **`ProgramCreate`** validators for HH:MM parsing at the schema boundary.

---

### `Contribution` (`contributions`)

**Purpose.** Intake queue for public submits, River Scene imports, and LLM-mention promotions — see **`contribution_store`** and **`approval_service`**.

**Key columns.**

- **Surrogate PK:** `id` (`Integer`, autoincrement).
- **Timestamps:** `submitted_at` (**server_default `now()`**).
- **Submitter:** `submitter_email`, `submitter_ip_hash`.
- **Payload:** `entity_type`, `submission_name`, `submission_url`, `source_url`, hints/notes, optional **`event_*`** date/time fields.
- **URL fetch enrichment:** `url_title`, `url_description`, `url_fetch_status`, `url_fetched_at`.
- **Places enrichment:** `google_place_id`, `google_enriched_data` (`JSON`).
- **Review:** `status`, `review_notes`, `reviewed_at`, `rejection_reason`.
- **Materialization FKs (nullable until approved):** `created_provider_id`, `created_program_id`, `created_event_id`.
- **Provenance:** `source` (default **`user_submission`**), **`llm_source_chat_log_id`** → `chat_logs.id`, **`unverified`** flag.

**Relationships.** Declared only via FK columns (no `relationship()` backrefs on `Contribution` in this file).

**Indexes (`__table_args__`).**

- **`ix_contributions_status`**, **`ix_contributions_source`**, **`ix_contributions_submitted_at`**.

**Alembic notes.**

- Table creation: **`b5c6d7e8f901_add_contributions_table`**.
- **`source_url`**: **`7d8c9e0f1a2b`** (contributions + events).
- Multi-day event fields on contributions: **`f2e1d0c9b8a7`**.

---

### `LlmMentionedEntity` (`llm_mentioned_entities`)

**Purpose.** Tier-3 response mention candidates for operator promotion/dismissal (`llm_mention_store`, `mention_scanner`).

**Key columns.**

- **Surrogate PK:** `id`.
- **Traceability:** **`chat_log_id`** → `chat_logs.id`, **`mentioned_name`**, optional **`context_snippet`**.
- **Workflow:** **`detected_at`** (server default now), **`status`** (default **`unreviewed`**), **`reviewed_at`**, **`dismissal_reason`**, **`promoted_to_contribution_id`** → `contributions.id`.

**Constraints / indexes (`__table_args__`).**

- **`UniqueConstraint("chat_log_id", "mentioned_name", name="uq_llm_mention_chat_name")`** — DB-level dedupe per turn + surface form.
- Indexes: **`detected_at`**, **`status`**, **`chat_log_id`**, **`mentioned_name`**.

**Alembic notes.**

- **`c6d7e8f9a012_add_llm_mentioned_entities`**.

---

## Internal structure

**Imports.** SQLAlchemy typing-heavy column declarations (`Mapped`, `mapped_column`), JSON/String/Text/Time/Date/DateTime primitives, `relationship`, `ForeignKey`, `UniqueConstraint`, `Index`, `false`, `func`.

**Defaults.** Widespread `datetime.now(UTC)` defaults for created/updated columns; UUID string lambdas for string PKs.

**Cross-schema coupling.** `Event.from_create` imports **`EventCreate`** — models depend on Pydantic schemas for one factory path only (acceptable tight coupling to avoid duplicating field logic).

## Conventions

**String UUID PKs** for catalog entities (`Provider`, `Event`, `Program`, `ChatLog`) vs **integer PKs** for operator-queue rows (`Contribution`, `LlmMentionedEntity`) — intentional shape split.

**Embeddings as JSON lists** — not pgvector; dedupe and search load full vectors in Python where needed.

**Timezone storage.** ORM defaults use aware UTC then various code paths **strip to naive** for SQLite compatibility — stores and helpers document “naive UTC” where relevant.

## Known limitations and design notes

**No declarative CHECK constraints** for enums like `Contribution.status` or `Event.status` at ORM level — enforcement is application-side (`contribution_store._VALID_STATUSES`, ingestion conventions).

**FieldHistory dormant.** Retained schema without active writer path in unified-router era; do not assume rows exist.

**Provider/program/event embedding columns** share JSON list representation but are not typed distinctly — callers must not mix dimensions across entity kinds.

## Configuration

None at ORM layer — **`DATABASE_URL`** drives bind via `database.py`.

## Alembic migration index (cross-reference)

Authoritative ordering is the Alembic graph; highlights above tie tables to notable revisions. Full history: **`alembic/versions/`** (21 revisions at Slice 64 inventory). Structural retrospectives: **`docs/maintainability/schema_time_harmonization_decision.md`** (Program `Time` campaign), **`docs/maintainability/river_scene_event_output_decision.md`** (event URL / source columns).

## Related

**Primary consumers (partial):**

- `app/chat/tier1_handler.py`, `tier2_db_query.py`, `context_builder.py` — catalog reads.
- `app/contrib/approval_service.py` — writes catalog rows from contributions.
- `app/db/contribution_store.py`, `chat_logging.py`, `llm_mention_store.py` — queue + log persistence helpers.
- `app/admin/router.py`, `app/api/routes/*` — CRUD and analytics.

**Cross-references:**

- `docs/components/database.md` — engine/session/Base.
- `HAVA_CONCIERGE_HANDOFF.md` §4 — architecture sketch vs this file’s detail.
- `docs/maintainability/end_to_end_creation.md` — flows touching `Contribution` and mentions.
