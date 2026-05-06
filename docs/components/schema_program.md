# schema_program

`app/schemas/program.py` (~180 lines)

## Purpose

Pydantic models for **program** catalog JSON: **`ProgramCreate`** (insert payloads from **`programs/router`**, **`approval_service`**, admin **`ProgramCreate` parses**, tests) and **`ProgramRead`** (API responses including **`id`** and timestamps). **`ProgramBase`** centralizes field definitions and validators — especially **schedule times as native `datetime.time`** with **HH:MM string ingestion** at the schema boundary (Backlog #30 / Slice 56 campaign outcome).

## Public surface — `ProgramBase` fields

**Core:** **`title`**, **`description`**, **`activity_category`**, optional **`age_min` / `age_max`**, **`schedule_days`**, **`schedule_start_time`**, **`schedule_end_time`** (**`time`**), **`location_name`**, optional **`location_address`**, **`cost`**, **`provider_name`**, optional **`contact_phone`**, **`contact_email`**, **`contact_url`**, **`source`** (default **`admin`**), **`is_active`** (default **`True`**), **`tags`**, optional **`embedding`**.

### Validators (high signal)

| Field(s) | Validator | Behavior |
|----------|-----------|----------|
| **`title`**, **`description`**, **`activity_category`**, **`location_name`**, **`provider_name`** | **`strip_required_strings`** (`before`) | Strip whitespace. |
| **`title`** | length | ≥ 3 chars. |
| **`description`** | length | ≥ 20 chars. |
| **`activity_category`** | length | ≥ 2 chars. |
| **`provider_name`** | length | ≥ 2 chars. |
| **`location_name`** | length | ≥ 3 chars. |
| **`schedule_start_time`**, **`schedule_end_time`** | **`parse_hhmm`** (`before`) | **`time`** passthrough; **`str`** must match **`_HHMM_RE`** (`^([01]\d|2[0-3]):[0-5]\d$`) then **`time.fromisoformat`**. **`9:00`** (single-digit hour) **fails** — require **`09:00`**. **`09:00:00`** **fails** (regex rejects seconds). |
| **`schedule_days`** | **`validate_days`** | Each entry lowercased/stripped; must be **`monday`…`sunday`**. |
| **`source`** | **`validate_source`** | Allowed: **`provider`**, **`parent`**, **`admin`**, **`scraped`**. |
| **`age_min` / `age_max`** | **`age_non_negative`** | **`None`** OK; ints must be ≥ 0. |
| **`contact_phone`** | **`phone_looks_reasonable`** | ≥ 10 digits after stripping non-digits. |
| **`contact_email`** | **`email_looks_reasonable`** | Blank → **`None`**; else coarse **`@`** + **`.`** in domain check (not full RFC). |

### `ProgramCreate(ProgramBase)`

Marker subclass — **the** write schema for JSON APIs and internal factories.

### `ProgramRead(ProgramBase)`

Adds **`id`**, **`created_at`**, **`updated_at`**; **`from_attributes=True`** for ORM.

**`@field_serializer("schedule_start_time", "schedule_end_time")`** → **`serialize_hhmm`** returns **`v.strftime("%H:%M")`** so JSON responses stay **`HH:MM`** without **`:00`** seconds — **Pydantic v2 default `time` serialization would emit `HH:MM:SS`**, which existing tests and external clients avoided during the Slice 56 harmonization campaign.

## Inputs and outputs

**Inbound:** JSON may send schedule times as **strings**; **`parse_hhmm`** normalizes to **`time`** before SQLAlchemy bind.

**Outbound:** **`ProgramRead`** emits **`HH:MM`** strings for both schedule columns via serializer.

## Internal structure

Module constants **`_VALID_DAYS`** (`set` of lowercase weekdays) and **`_HHMM_RE`** (`re.compile`) support validators.

Docstrings on **`parse_hhmm`** / **`serialize_hhmm`** cite **Slice 56** rationale explicitly.

## Conventions

**Schedule validation is strict HH:MM** — aligns with operator-facing copy in **`programs_router`** HTML placeholders.

**`source` whitelist** must match ingestion semantics (**`parent`** HTML submit sets **`source`** server-side to **`parent`** in router even though raw dict passes **`ProgramCreate`** validation).

## Known limitations and design notes

**Admin contribution approval uses `ProgramApprovalFields`** (**string** `schedule_*`) — different schema module — see **`docs/components/schema_contribution.md`**. Conversion into **`Program`** / **`ProgramCreate`** happens in **`approval_service`**.

**Email validation is intentionally lightweight** — not **`EmailStr`** on **`ProgramBase`**.

## Configuration

None.

## Related

**Direct consumers:**

- **`app/programs/router.py`**
- **`app/admin/router.py`** (program create/edit form posts parsed into **`ProgramCreate`**)
- **`app/contrib/approval_service.py`**
- Tests: **`tests/test_programs.py`**, **`tests/test_program_schema_time_parsing.py`**, tier/router fixtures.

**Cross-references:**

- **`docs/maintainability/schema_time_harmonization_decision.md`** — Option B campaign; **`Program.schedule_*`** **`Time`** canonicalization and wire-format preservation rationale.
- **`docs/components/models.md`** — **`programs`** ORM table.
- **`docs/components/programs_router.md`**, **`docs/components/approval_service.md`**
