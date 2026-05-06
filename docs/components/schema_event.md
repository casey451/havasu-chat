# schema_event

`app/schemas/event.py` (~119 lines)

## Purpose

Pydantic models for **event catalog** shapes: **`EventCreate`** (construction + ingestion helpers), **`EventRead`** (API read projection including computed normalization fields), and **`normalize_event_url`** (shared URL coercion used inside validators). **`EventBase`** holds shared fields and validation logic consumed by both create and read.

## Public surface

### `normalize_event_url(value: str) -> str`

Pure helper: **strip**; if empty return empty; if already **`http(s)://`** return as-is; if string contains **`.`** prepend **`https://`**; else return stripped original (may fail downstream validator).

**Used by:** **`EventBase`** **`event_url`** **`field_validator`** (`after`).

### `EventBase`

**Temporal / location:** **`title`**, **`date`**, optional **`end_date`**, **`start_time`** (**`datetime.time`**), optional **`end_time`**, **`location_name`**, **`description`**, **`event_url`**, optional **`source_url`**, optional **`contact_name` / `contact_phone`**, **`tags`** (default list), **`is_recurring`**, optional **`source`**, optional **`embedding`**, **`status`** (default **`live`**), **`created_by`** (default **`user`**), optional **`admin_review_by`**.

**Validators:**

| Validator | Mode | Behavior |
|-----------|------|----------|
| **`end_date_on_or_after_start`** | `model_validator` after | **`end_date >= date`** when **`end_date`** set. |
| **`strip_strings`** | before | Strips **`title`**, **`location_name`**, **`description`**, **`event_url`**. |
| **`empty_contact_to_none`** | before | Blank **`contact_name` / `contact_phone`** → **`None`**. |
| **`validate_loose_url`** | after | Runs **`normalize_event_url`**; requires non-empty result; must be **`http(s)://`** or contain **`.`** (friendly **`ValueError`** messages). |
| **`title_length`** | plain | Length ≥ 3. |
| **`location_length`** | plain | Length ≥ 3. |
| **`description_length`** | plain | Length ≥ 20. |
| **`phone_looks_reasonable`** | plain | If set: strip non-digits; require ≥ **10** digits (area code + number). |

### `EventCreate(EventBase)`

Empty subclass — **the** inbound schema for **`Event.from_create`** (`app/db/models.py`) and tests/fixtures.

### `EventRead(EventBase)`

Adds **`id`**, **`normalized_title`**, **`location_normalized`**, **`created_at`**; **`model_config = {"from_attributes": True}`** for ORM reads.

**Consumed by:** **`GET /events`** in **`app/main.py`** (`response_model=list[EventRead]`).

## Inputs and outputs

**Create path:** Accepts ISO dates and **`time`** instances (or JSON-native representations Pydantic coerces). **URLs** tolerate bare domains → **`https://`** injection.

**Read path:** Projects stored **`Event`** rows including server-derived normalized strings.

## Internal structure

**`regex`** (`re`) powers **`phone_looks_reasonable`** digit counting — permissive formatting (dashes/parens allowed).

**No `HttpUrl` type** on **`event_url`** — deliberate loose URL policy for Facebook/Eventbrite-style pasted links.

## Conventions

**Verification defaults** live on **`Event.from_create`**, not **`EventBase`** — schema validates shape; ORM factory decides **`verified`** from **`source`**.

## Known limitations and design notes

**Loose URL rule** allows strings that are not globally valid URLs if they include **`.`** after normalization — trade-off for contributor UX.

**Multi-day** correctness relies on **`end_date_on_or_after_start`**; overlapping retrieval semantics are **`tier2_db_query`** concerns.

## Configuration

None.

## Related

**Direct consumers:**

- **`app/db/models.Event.from_create`**
- **`app/contrib/approval_service.py`** (builds **`EventCreate`**)
- **`app/main.py`** — **`EventRead`** list endpoint (mount unchanged in Slice 66)

**Cross-references:**

- **`docs/components/models.md`** — **`events`** table columns.
- **`docs/components/schema_contribution.md`** — **`EventApprovalFields`** for contribution approve forms.
