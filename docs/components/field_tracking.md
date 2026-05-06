# field_tracking

`app/core/field_tracking.py` (~32 lines)

## Purpose

Declares **immutable tuples of ORM attribute names** intended as **`field_history`** baselines for Phase 5 correction flows: which **`Provider`**, **`Program`**, and **`Event`** columns are tracked when comparing user-submitted corrections against catalog rows.

## Public surface

**`PROVIDER_TRACKED_FIELDS`** — **`("phone", "email", "address", "hours", "website")`**

**`PROGRAM_TRACKED_FIELDS`** — **`cost`**, **`schedule_start_time`**, **`schedule_end_time`**, **`schedule_note`**, **`age_min`**, **`age_max`**, **`contact_phone`**

**`EVENT_TRACKED_FIELDS`** — **`("date", "start_time", "end_time", "location_name")`**

## Inputs and outputs

Constants only — imported by future or adjacent correction machinery.

## Internal structure

Module docstring explains mismatches vs high-level handoff shorthand:

- **`Event`** uses **`start_time` / `end_time`**, not a single **`time`** column.
- **`Event`** uses **`location_name`**, not **`location`**.
- **`Event`** has **no `cost` column** — event cost cannot be baselined until a schema addition lands.

## Conventions

**Strings must match `app/db/models.py` mapped attribute names exactly** — typos silently break baseline comparisons.

## Known limitations and design notes

**No runtime imports found at Slice 67a audit** — tuples are authoritative declarations for **`FieldHistory`**-shaped work; wiring may live in deferred correction routes or operators-only tooling. **`approval_service`** / **`FieldHistory`** ORM remain the semantic anchors (**`docs/components/models.md`**, **`docs/components/approval_service.md`**).

## Configuration

None.

## Related

**Cross-references:**

- **`app/db/models.FieldHistory`** — persistence shape for tracked deltas.
- **`docs/components/models.md`** — column inventory per entity.
