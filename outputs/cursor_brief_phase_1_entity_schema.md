# Cursor Brief — Phase 1: Unified ENTITY Schema Foundation

> **Operator note:** paste this brief to a fresh Cursor chat. **This is the largest single lane attempted on havasu-chat to date — estimated 3-4 weeks of dispatched effort, multi-session.** It is the foundational refactor that gates Phases 2-12 of the master build plan (`docs/maintainability/master_build_plan.md`). Sequential single-lane dispatch — no parallel agents on any file in `app/db/`, `app/providers/`, `app/chat/`, `app/contrib/places_client.py`, or `scripts/places_load.py` while this lane is open.
>
> The brief is structured around **four explicit sub-phase boundaries (Phase 1A, 1B, 1C, 1D)**, each independently committable + pytest-green. **You are expected to HALT and report after each sub-phase so the operator can commit before you proceed.** Each sub-phase is sized to one Cursor session; do not attempt multiple sub-phases in one session unless the operator explicitly authorizes it in follow-up. Authored 2026-05-14 by Cowork primary from `docs/maintainability/master_build_plan.md` §4 Phase 1 + `outputs/chatgpt_taxonomy_research_synthesis.md` §3 + `outputs/opus_design_handoff/README.md` §2.1, §4.

---

## §0 Baseline confirmation (do this FIRST and report before touching code)

Before any edits, confirm and report:

1. `git log --oneline -5` — top of `main` should be on session-13/14 ship commits. Report the top 5 SHAs.
2. `git status` — should be clean.
3. `python -m pytest -q --collect-only 2>&1 | tail -3` — collected count should be **≥1476** tests (baseline grew through session-14; treat 1476 as floor, not exact).
4. `python -m alembic heads` — single head `f1a2b3c4d5e6` (Provider.slug field + backfill migration).
5. `python -m alembic current` — may differ from head. If `(mergepoint)` label appears on an unexpected revision, **don't alarm** — chain-walk down_revision via `grep ^down_revision alembic/versions/*.py` first. Local dev SQLite drift is benign per dispatch_channels.md gotcha #10.
6. **Read these four docs end-to-end before writing any code:**
   - `docs/maintainability/master_build_plan.md` §4 Phase 1 (the deliverables checklist that drives this lane)
   - `outputs/chatgpt_taxonomy_research_synthesis.md` §3 (the locked ENTITY schema decision)
   - `outputs/opus_design_handoff/README.md` §2.1 + §4 (the unified Hava card grammar + Events-as-ENTITY data model)
   - `docs/maintainability/place_model_design.md` (superseded for **table shape** by ENTITY, but the Place-specific FIELD shapes — place_type discriminator, amenities JSON, boat_access, heat_exposure — carry forward as ENTITY extension fields)
7. **Read these source files** so you have current line offsets for the anchored edits in §7:
   - `app/db/models.py` end-to-end (~610 lines; Provider class lines 31-133, Event class 159-234, Program class 270-335, Sponsor class 503-577, Category class 580-598)
   - `app/providers/queries.py` end-to-end
   - `app/providers/view_models.py` end-to-end
   - `app/chat/tier2_db_query.py` end-to-end (note the `_category_needle_set` synonym expansion near :469)
   - `app/contrib/places_client.py` end-to-end (~150 lines)
   - `app/contrib/enrichment.py` end-to-end
   - `scripts/places_load.py` end-to-end
   - `tests/test_directory_schema.py` (the precedent pattern for additive schema tests)
8. Report all baseline values + confirm reads complete. Only then proceed to §1.

If any baseline value mismatches or any file has materially moved from these descriptions, **HALT and report** before proceeding.

---

## §1 Why this lane exists

The current schema has four separate top-level "thing" tables — `providers`, `programs`, `events`, and (deferred) a `places` table that was never built. Each carries its own subset of name/location/hours/contact/category/source-tracking columns. The directory pivot (2026-05-12) and the ChatGPT taxonomy research (2026-05-14) both converge on a single conclusion: the V1 directory needs **one core entity table with a discriminator and N extension tables**, not four parallel top-level tables.

**Locked decision 2026-05-14 (master plan §10):** Unified ENTITY schema. Single `entities` core table with `entity_type` column discriminating commercial / place / event / program; 11 extension tables for category memberships, location, hours, contact points, features, offerings, service areas, schedules, source evidence, and sponsorship slots. The locked Place model design (Option A — separate `places` table) is **superseded** by this — the Place field shapes carry forward as ENTITY extension fields; the table shape changes.

**Why first:** every subsequent phase depends on this. Phase 2 (account-lite + R2 + search), Phase 3 (v1.1 schema additions), Phase 4 (background-jobs + scrapers), Phase 5 (Tier 1 data gathering), Phase 6 (Tier 1 UI build), Phase 7 (Tier 2 + chat), Phase 8 (trust + conditions + alerts), Phase 9 (Events + Classes), Phase 11 (monetization) — all read from and write to ENTITY. Doing the migration NOW (with ~71 RiverScene Event rows + 0 active providers/programs production-side) avoids painful production data surgery later when the database is densely populated.

**Texture rule reminder:** zero user-visible behavior change in Phase 1. Every existing chat-route response, every Provider profile render, every Tier 2 catalog lookup must produce identical output after Phase 1 as before. This is a refactor, not a feature ship. The brief is loud about test coverage for exactly this reason.

---

## §2 Locked decisions (do not relitigate)

| # | Locked answer | Source |
|---|---|---|
| Unified ENTITY core | Single `entities` table with `entity_type` discriminator (`commercial` / `place` / `event` / `program`) replaces parallel top-level Provider/Event/Program/Place tables. | Master plan §10 + taxonomy synthesis §3 |
| 12-category Tier 1/2/3 taxonomy | Category table already shipped (12 seeded rows). M:M via `entity_categories` extension. Original Provider.category_id + Program.category_id FKs stay during transition; ENTITY queries replace them. | Taxonomy synthesis §1 + LOCKED 2026-05-14 |
| 11 extension tables | `entity_categories`, `locations`, `hours`, `seasonal_hours`, `contact_points`, `features`, `offerings`, `service_areas`, `schedules`, `source_evidence`, `sponsorship_slots`. Names are LOCKED (downstream phases reference them). | Master plan §4 Phase 1 + taxonomy synthesis §3 |
| Migration shape | Additive across all sub-phases. Old tables (`providers`, `events`, `programs`) keep their rows for the full transition window. New ENTITY rows are created alongside via backfill. App layer reads from ENTITY going forward; writes dual-target during transition. Legacy table drops are **deferred to V1.5+** (Phase 13). | Build-first / sell-after sequencing + Rule 8 isolation |
| Sponsor.entity_type discriminator | New column on Sponsor table; existing rows default to `entity_type="commercial"` (mirrors the current Provider-only sponsor pattern). `Sponsor.business_id` continues to have no DB-level FK (per `app/db/models.py:545` comment); validation in app layer. | Master plan §4 Phase 1 |
| Alembic op.execute vs separate script | **Recommend Alembic batch operations + Python within `op.execute`** for the data backfill in Phase 1B. Atomicity matters; a half-finished backfill leaves the system in an inconsistent state. If batch operations don't scale to production row counts (currently fine — ~71 events, ~0 providers), a separate post-migration Python script with idempotency guards is the fallback. | Master plan §4 Phase 1 open question + operator-recommended path |
| Sub-phase commit boundaries | Four sub-phases (1A schema / 1B backfill / 1C app-layer read pivot / 1D writes dual-target + close-out). Each ships green pytest. Operator commits each. | This brief §3 |

---

## §3 Sub-phase boundaries (the rhythm of this lane)

This lane will not ship in one session. The work splits into four sub-phases, each independently shippable + pytest-green. Halt-and-report after each.

### Phase 1A — Schema additive (target: 5-8 days)
Add `entities` table + 11 extension tables. Add `Sponsor.entity_type`. **Zero app-layer code changes. Zero data writes.** Pytest stays green at 1476+; new tests pin schema shape + relationships. Alembic head advances by one migration.

**Acceptance:** new tables exist; foreign keys defined; relationships navigable on the ORM; new tests pin every column type + nullable + uniqueness; no chat-route or Provider-profile behavior change.

### Phase 1B — Data backfill (target: 5-8 days) — SHIPPED 2026-05-14 at `d475b06`
New migration backfills existing Provider/Event/Program rows into `entities` + relevant extension records. Adds nullable `entity_id` columns to providers/events/programs pointing back to entities (so the legacy tables and ENTITY can be cross-joined during transition). Backfill populates those `entity_id` columns. **The NOT NULL flip originally specified for stage 3 of this migration is DEFERRED to Phase 1D** per amendment 2026-05-14 — existing test fixtures create Provider/Event/Program rows directly without populating entity_id, and a non-null flip before Phase 1D's dual-write helpers exist would fail integrity. Stage 3 moves into Phase 1D's deliverables (§8). Still zero app-layer code changes in 1B.

**Acceptance:** for every existing Provider row, an `entities` row with `entity_type="commercial"` exists with matching `entity_id`. Same for Events (`entity_type="event"`) and Programs (`entity_type="program"`). Extension records (`locations`, `hours`, `contact_points`, `entity_categories`) populated from the source rows. Pytest stays green; new tests pin backfill correctness for at least 5 representative row shapes. `entity_id` FK columns remain nullable; deviation pinned in test.

### Phase 1C — Application read pivot (target: 7-10 days)
Application-layer queries pivot to read from `entities` + extensions instead of `providers`/`events`/`programs` directly. Writes still go to the legacy tables (1D handles dual-writes). **This is the biggest sub-phase.** Files touched: `app/providers/queries.py`, `app/providers/view_models.py`, `app/chat/tier2_db_query.py`, `app/contrib/places_client.py`, `app/contrib/enrichment.py`, `scripts/places_load.py`, plus any other read path the baseline reads in §0.7 surface.

**Acceptance:** pytest stays green. Every existing chat-route query returns identical results to pre-pivot (regression suite required; see §10). Provider profile page renders identically. Tier 2 catalog lookup returns identical rows in identical order.

### Phase 1D — Write dual-target + close-out (target: 3-5 days)
New writes (Provider creation, Event ingest, Program ingest) write to BOTH `entities` + extension records AND the legacy table. This unlocks Phase 2-12 to write directly to ENTITY without breaking legacy reads (which may still exist in admin tooling / scripts). Add the `place` entity_type seed path (no Place rows yet — just the code path). Update Sponsor.entity_type-aware queries.

**Acceptance:** new Provider/Event/Program creation populates both legacy and ENTITY in a single transaction. Test coverage pins this for every ingest path. Sponsor queries route through ENTITY discriminator. Pytest stays green.

### Important — phase boundary etiquette

After completing each sub-phase:

1. Confirm `python -m pytest -q` is green and report final count.
2. Confirm `python -m ruff check .` is clean.
3. Confirm `python -m alembic upgrade head` applies cleanly against a fresh dev DB.
4. Produce the final report per §13 for THAT sub-phase only.
5. **STOP. Do not start the next sub-phase.** Operator commits the current sub-phase and re-dispatches you (likely in a fresh session) for the next.

If you discover mid-sub-phase that the scope is bigger than estimated, **halt early** and report what's done + what's outstanding. Do not push past a half-broken state to "make progress."

---

## §4 Target schema in detail

The schema design below is canonical. Field names + types + nullability + FK shapes are LOCKED — downstream phases reference them by name. Naming follows the project's existing pattern (snake_case table names; `Mapped[...]` typed columns; `relationship(back_populates=...)`).

### §4.1 `entities` — the core table

```python
class Entity(Base):
    """Unified core entity table — one row per directory thing.

    Replaces the parallel Provider/Event/Program/Place top-level tables with
    a single core + discriminator. Existing top-level tables remain during
    transition (Phase 1B backfills them into entities; Phase 1C pivots app
    reads to entities; Phase 1D pivots writes to dual-target; legacy table
    drops are deferred to V1.5+/Phase 13 per master plan).

    See docs/maintainability/master_build_plan.md §4 Phase 1.
    """

    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    entity_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # commercial | place | event | program
    slug: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        TZAwareDateTime(), nullable=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="seed")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships (back_populates wired on each extension table)
    categories: Mapped[list["EntityCategory"]] = relationship(back_populates="entity")
    location: Mapped["Location | None"] = relationship(
        back_populates="entity", uselist=False
    )
    hours: Mapped[list["Hours"]] = relationship(back_populates="entity")
    seasonal_hours: Mapped[list["SeasonalHours"]] = relationship(back_populates="entity")
    contact_points: Mapped[list["ContactPoint"]] = relationship(back_populates="entity")
    features: Mapped[list["Feature"]] = relationship(back_populates="entity")
    offerings: Mapped[list["Offering"]] = relationship(back_populates="entity")
    service_areas: Mapped[list["ServiceArea"]] = relationship(back_populates="entity")
    schedules: Mapped[list["Schedule"]] = relationship(back_populates="entity")
    source_evidence: Mapped[list["SourceEvidence"]] = relationship(back_populates="entity")
    sponsorship_slots: Mapped[list["SponsorshipSlot"]] = relationship(back_populates="entity")
```

**Notes:**
- `entity_type` is a String (not a SQLAlchemy `Enum`) for the same reason `Sponsor.slot` is — adding new types in code shouldn't require a migration. App-layer validation lives in a new `app/db/entity_types.py` constants module: `ENTITY_TYPE_COMMERCIAL = "commercial"`, etc.
- `slug` is globally unique across all entity types. URL routing in Phase 6 will use slug as the primary key for `/entity/<slug>` (and category-specific routes like `/provider/<slug>`).
- `is_active` defaults to true; existing Provider/Event/Program rows with `is_active=False` carry that over in the Phase 1B backfill.

### §4.2 Extension tables — locked names and shapes

For each, write the SQLAlchemy class + Alembic migration. All extension tables have a FK to `entities.id` named `entity_id`, indexed.

**`entity_categories`** (M:M between Entity and Category)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, indexed)
category_id: int (FK categories.id, indexed)
is_primary: bool (default False; one row per entity should be is_primary=True; not enforced by constraint in V1)
created_at: datetime
UniqueConstraint("entity_id", "category_id")  # one row per (entity, category) pair
```

**`locations`** (1:1 with Entity)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, UNIQUE — 1:1 enforced)
address: str(255) | None
address_normalized: str(255) | None  # lowercase trimmed for dedup
city: str(64) | None  # default "Lake Havasu City" for backfilled rows
state: str(8) | None  # default "AZ"
zip: str(16) | None
lat: float | None
lng: float | None
google_place_id: str(64) | None (indexed)
district: str(64) | None  # carries forward Provider.district during transition; Phase 3 promotes to FK
created_at: datetime
updated_at: datetime
```

**`hours`** (1:N — daily hours per entity)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, indexed)
day_of_week: int  # 0=Monday, 6=Sunday (Python's calendar convention)
opens_at: time | None  # null means closed all day
closes_at: time | None  # null means closed all day
is_24h: bool (default False)
notes: str(255) | None
created_at: datetime
```

Special hours pattern: Phase 1B's backfill reads `Provider.hours_structured` (JSON) and explodes it into 7 hours rows per entity. Free-text `Provider.hours` is preserved on the legacy table; only structured hours get backfilled into the hours extension. Providers without `hours_structured` get zero rows in `hours` — that's OK; renderer falls back to the legacy free-text path during transition.

**`seasonal_hours`** (1:N — for snowbird-season operating windows; Opus #3)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, indexed)
season: str(16)  # summer | winter | shoulder
applies_from: date | None  # e.g. May 1
applies_to: date | None  # e.g. Sep 30
hours_overlay: JSON  # same shape as hours_structured: {monday: {opens: "...", closes: "..."}, ...}
notes: str(255) | None
created_at: datetime
```

**Schema-only in Phase 1.** No data backfilled — `seasonal_hours` ships empty. Phase 3 (v1.1 schema pass) and Phase 5 (operator data entry) populate it.

**`contact_points`** (1:N — phone, email, web, social per entity)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, indexed)
kind: str(32)  # phone | email | website | facebook | instagram | twitter | tiktok | youtube | other
value: str(512)  # the actual phone number / email / URL
label: str(64) | None  # "main" | "after_hours" | "emergency" | "booking" — operator-controlled
display_order: int (default 0)
is_primary: bool (default False)  # the "preferred" contact for that kind
created_at: datetime
```

Phase 1B backfill: Provider.phone → ContactPoint(kind="phone", value=phone, is_primary=True). Provider.email → ContactPoint(kind="email"). Provider.website → ContactPoint(kind="website"). Provider.facebook → ContactPoint(kind="facebook"). Event/Program contact_phone/contact_email/contact_url same.

**`features`** (1:N — boolean / enum flags per entity)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, indexed)
key: str(64)  # heat_exposure | boat_accessible | wifi | kid_friendly | dog_friendly | accessible_ada | etc.
value: str(255) | None  # for enum-shaped features (heat_exposure: indoor|shaded|outdoor|water_adjacent); for booleans, value is "true"
created_at: datetime
UniqueConstraint("entity_id", "key")  # one row per (entity, key) pair
```

Phase 1 ships schema only. The 7 locked Opus features (conditions, heat-aware, seasonal hours, boat-access, crowd context, mobile-services, alerts) get data in Phase 3 + Phase 5.

**`offerings`** (1:N — services/menu items/programs offered by an entity)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, indexed)
name: str(255)
description: Text | None
price_text: str(64) | None  # "From $25/hr", "Free with reservation" — free text, not a typed amount
price_min_cents: int | None  # optional structured price for filtering
price_max_cents: int | None
duration_minutes: int | None  # for services/classes that have a fixed duration
url: str(2048) | None  # offering-specific booking URL
display_order: int (default 0)
created_at: datetime
updated_at: datetime
```

Schema-only in Phase 1. Some Program-level data (name, description, cost) maps into offerings during Phase 1B backfill — see §6.3.

**`service_areas`** (1:N — for mobile-service businesses; Opus #6)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, indexed)
zone_name: str(128)  # "Lake Havasu City", "North end", "Parker (overflow only)"
zone_type: str(32)  # city | neighborhood | radius_miles | custom
radius_miles: int | None  # when zone_type=radius_miles
notes: str(255) | None
created_at: datetime
```

Schema-only in Phase 1. Operator data entry in Phase 5.

**`schedules`** (1:N — for events, recurring programs, time-windowed offerings)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, indexed)
schedule_type: str(32)  # one_off | recurring | time_window
start_date: date | None
end_date: date | None
start_time: time | None
end_time: time | None
recurrence_rule: str(255) | None  # RRULE format (Phase 9 wires the parser)
days_of_week: JSON | None  # list[int] for simple weekly recurrence (legacy Program.schedule_days mirror)
capacity: int | None
capacity_label: str(64) | None  # "Drop-in", "Full", "Limited" — operator-controlled
notes: str(255) | None
created_at: datetime
updated_at: datetime
```

Phase 1B backfill: Event rows → one Schedule per event (`schedule_type="one_off"`, `start_date=event.date`, etc.). Recurring events stay as one-offs in Phase 1; the RRULE collapse logic lands in Phase 9. Program rows → one Schedule per program (`schedule_type="recurring"`, `days_of_week=program.schedule_days`).

**`source_evidence`** (1:N — provenance per entity per data field)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, indexed)
field_path: str(64)  # "name" | "phone" | "hours.monday.opens_at" | "location.address" — dot-path
source_type: str(64)  # google_places | osm | city_open_data | npi | manual | owner_claimed
source_url: str(2048) | None
verified_at: datetime
verification_method: str(32) | None  # mirrors current Provider.verification_method
notes: Text | None
created_at: datetime
```

Phase 1 ships schema only. The existing `Provider.source` + `Provider.last_verified_at` + `Provider.verification_method` columns continue to function during transition; Phase 1B's backfill creates a single SourceEvidence row per Provider with `field_path="(provider_record)"`, `source_type=provider.source`, `verified_at=provider.last_verified_at`, `verification_method=provider.verification_method`. Per-field provenance arrives gradually as scrapers in Phase 4-5 write evidence rows directly.

**`sponsorship_slots`** (1:N — connects Entity to active Sponsor records)
```python
id: int (PK, autoincrement)
entity_id: str (FK entities.id, ON DELETE CASCADE, indexed)
sponsor_id: str (FK sponsors.id, ON DELETE CASCADE, indexed)
slot_type: str(32)  # marquee | spotlight | promoted | supporter | category_visibility | intent_cluster | seasonal_takeover
priority: int (default 0)
created_at: datetime
UniqueConstraint("entity_id", "sponsor_id", "slot_type")
```

**Sponsor.entity_type new column** (added to existing sponsors table):
```python
entity_type: str(32) | None  # commercial | place | event | program — null on legacy rows until backfill
```

Phase 1B backfill: every existing Sponsor row gets `entity_type="commercial"` (current production reality — only Provider-backed sponsors exist). `Sponsor.business_id` continues to have no DB-level FK; app-layer disambiguation in Phase 1C makes the query route through `entity_type` + `business_id` instead of assuming Provider.

---

## §5 Phase 1A — Schema additive migration (5-8 days estimate)

### §5.1 New file: `app/db/entity_types.py`

```python
"""Canonical entity_type values for the unified ENTITY schema.

Stored as plain string in entities.entity_type — Postgres ENUM types are
avoided here so adding a new type in code doesn't require an Alembic
migration (matches the AdSlot/SponsorStatus pattern in models.py).

Validation happens in app-layer code, not at the DB level.
"""

from __future__ import annotations

ENTITY_TYPE_COMMERCIAL = "commercial"
ENTITY_TYPE_PLACE = "place"
ENTITY_TYPE_EVENT = "event"
ENTITY_TYPE_PROGRAM = "program"

ENTITY_TYPES: frozenset[str] = frozenset({
    ENTITY_TYPE_COMMERCIAL,
    ENTITY_TYPE_PLACE,
    ENTITY_TYPE_EVENT,
    ENTITY_TYPE_PROGRAM,
})


def is_valid_entity_type(value: str) -> bool:
    return value in ENTITY_TYPES
```

### §5.2 Edit `app/db/models.py` — append new classes

**Anchored Edit only.** Append the new classes (Entity + 11 extension classes + Sponsor.entity_type column addition) at the bottom of the file, immediately before the `def _register_provider_slug_listeners()` block (currently line 601). Do not modify any existing class; this is purely additive.

The classes follow the precise shapes in §4. Match the project's style:
- `from __future__ import annotations` already imported (line 1)
- `Mapped[...] = mapped_column(...)` style
- `TZAwareDateTime()` for `last_verified_at`-style columns; `DateTime` for `created_at` / `updated_at`
- `relationship(back_populates=...)` with forward-ref strings for the M:M and 1:N relationships
- `__tablename__ = "..."` snake_case
- Module-level docstring on each class explaining its role in the ENTITY model

For `Sponsor.entity_type`, add it as a new column on the existing `Sponsor` class (anchored insert after the `business_id` column at line 547):

```python
    # Phase 1 ENTITY schema (2026-05-XX): discriminator for which entity_type
    # the business_id references. Null until backfill completes; backfilled
    # by the entity_schema migration to "commercial" for legacy rows (which
    # all reference Provider records). Phase 1C app-layer routing keys off
    # this column to disambiguate Provider vs Place vs Event sponsor refs.
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
```

**Important — DO NOT delete or modify existing columns on Provider/Event/Program/Sponsor in this sub-phase.** Phase 1A is purely additive.

### §5.3 New file: `alembic/versions/<rev>_entity_schema_additive.py`

Generate a new migration with a unique 12-char hex revision id. Suggested: `a1b2c3d4e5f6` — verify it doesn't exist on disk before writing.

The migration:
- Chains off `f1a2b3c4d5e6` (the current head — Provider.slug).
- Creates `entities` table with all columns + indexes from §4.1.
- Creates each of the 11 extension tables from §4.2 with FKs + indexes + unique constraints.
- Adds `sponsors.entity_type` column (nullable).
- Uses `op.batch_alter_table` everywhere a column is added to an existing table (SQLite-friendliness, mirroring the `e7f8a9b0c1d2` and `f1a2b3c4d5e6` precedent).
- Provides a working `downgrade()` that drops everything in reverse order (events/programs/providers schemas restored to pre-1A state).

**No data writes in this migration.** All tables ship empty.

### §5.4 Tests — new file `tests/test_entity_schema.py`

Pattern from `tests/test_directory_schema.py`. Required tests:

1. `test_entities_table_exists_after_migration` — table exists with all expected columns + types.
2. `test_entity_type_column_nullable_false` — entities.entity_type is NOT NULL.
3. `test_entity_slug_unique` — inserting two entities with the same slug raises IntegrityError.
4. `test_entity_extension_tables_exist` — parametrized check that each of the 11 extension tables exists.
5. `test_entity_category_unique_constraint` — `(entity_id, category_id)` unique.
6. `test_location_one_to_one_with_entity` — `locations.entity_id` is UNIQUE.
7. `test_contact_point_polymorphic_kinds` — can insert phone, email, website, facebook entries all referencing same entity.
8. `test_sponsor_entity_type_column_exists` — sponsors.entity_type column present + nullable.
9. `test_entity_relationships_navigable` — create an entity + a location + 2 hours rows + 1 contact_point; assert entity.location is non-null, len(entity.hours) == 2, len(entity.contact_points) == 1.
10. `test_entity_cascade_delete` — delete an entity; assert its locations/hours/contact_points rows are also deleted (ON DELETE CASCADE).
11. `test_entity_type_constants` — assert `ENTITY_TYPES` contains exactly the 4 expected values; `is_valid_entity_type` returns True/False correctly.

If any test can't be cleanly expressed against the project's existing test harness (likely the cascade delete one if SQLite needs PRAGMA foreign_keys=ON), fall back to a lighter assertion + note in the docstring.

### §5.5 Phase 1A acceptance + commit

After Phase 1A:
- `python -m pytest -q` shows ≥1487 (baseline + 11 new tests). Report exact count.
- `python -m ruff check .` clean.
- `python -m alembic upgrade head` applies cleanly against a fresh dev DB.
- `python -m alembic heads` shows single head = your new revision id.
- Final report per §13 for Phase 1A only.
- **HALT.** Operator commits Phase 1A. Re-dispatch for Phase 1B in a new session.

Suggested commit subject: `feat(db): Phase 1A — unified ENTITY schema + 11 extension tables (additive)`

---

## §6 Phase 1B — Data backfill (5-8 days estimate)

### §6.1 New migration `<rev>_entity_backfill.py`

Chains off Phase 1A's migration. Adds `entity_id` columns to `providers`, `events`, `programs` (nullable initially), then runs the backfill via `op.execute` blocks, then flips the `entity_id` columns to NOT NULL.

**Two-stage shape (amended 2026-05-14 per Phase 1B ship deviation — original three-stage spec at `f1a2b3c4d5e6` precedent had a NOT NULL flip in stage 3, but that flip is deferred to Phase 1D once dual-write helpers exist):**

1. Add nullable `entity_id` String FK columns to providers/events/programs.
2. Run backfill: for each Provider/Event/Program row, INSERT into entities + extension tables, populate the legacy row's `entity_id`.
3. ~~Flip `entity_id` to NOT NULL on all three legacy tables.~~ **DEFERRED to Phase 1D** — existing test fixtures construct Provider/Event/Program rows directly without populating entity_id; non-null flip before dual-write helpers fails integrity. Phase 1D's dual-write helper populates entity_id at write time; once that's in, Phase 1D can flip NOT NULL safely.

### §6.2 Provider → Entity backfill rules

For each Provider row (in stable id order for deterministic test fixtures):
1. INSERT entities row: `id=uuid4()`, `entity_type="commercial"`, `slug=provider.slug`, `name=provider.provider_name`, `description=provider.description`, `last_verified_at=provider.last_verified_at`, `source=provider.source`, `is_active=provider.is_active`, `created_at=provider.created_at`, `updated_at=provider.updated_at`.
2. If `provider.category_id` is non-null: INSERT entity_categories row with `is_primary=True`. If null (legacy string-only category), leave entity_categories empty; Phase 5+ operator workflow lands the category mapping per the `category_backfill_mapping_DRAFT.md` work.
3. INSERT locations row: address fields + lat/lng + google_place_id + district + city/state defaulted.
4. If `provider.hours_structured` non-null: explode into up to 7 hours rows (one per weekday with non-null opens_at/closes_at).
5. INSERT contact_points rows: one per non-null phone/email/website/facebook value.
6. INSERT source_evidence row: `field_path="(provider_record)"`, source_type=provider.source, verified_at=provider.last_verified_at, verification_method=provider.verification_method.
7. UPDATE providers SET entity_id = (the new entities.id) WHERE id = provider.id.

### §6.3 Program → Entity backfill rules

For each Program row:
1. INSERT entities row: `entity_type="program"`, `slug=` derived (use `make_unique_slug` from `app/utils/slug.py` with base `program.title`; track used slugs across the whole backfill batch). `name=program.title`. `description=program.description`. `last_verified_at=None`. `source=program.source`. `is_active=program.is_active`.
2. If `program.category_id` non-null: INSERT entity_categories with `is_primary=True`.
3. If `program.location_address` non-null: INSERT locations row with just address fields (no lat/lng for programs in current schema).
4. INSERT contact_points: one per non-null contact_phone/contact_email/contact_url.
5. INSERT schedules row: `schedule_type="recurring"`, `days_of_week=program.schedule_days`, `start_time=program.schedule_start_time`, `end_time=program.schedule_end_time`, `notes=program.schedule_note`.
6. If program.title/description/cost is meaningful: INSERT offerings row: `name=program.title`, `description=program.description`, `price_text=program.cost`.
7. INSERT source_evidence row.
8. If `program.provider_id` non-null: this program belongs to a Provider. The Provider has its own entities row from §6.2; the program's entities row stands on its own. (Provider-Program parent relationship is preserved on the legacy table; ENTITY-level relationship modeling for parent-child entities is deferred.)
9. UPDATE programs SET entity_id = (new entities.id).

### §6.4 Event → Entity backfill rules

For each Event row:
1. INSERT entities row: `entity_type="event"`, `slug=` derived from `event.title` (collision-handled), `name=event.title`, `description=event.description`. `source=event.source`. `is_active=True` if `event.status == "live"` else False.
2. INSERT locations row from `event.location_name` (no structured address — events use only `location_name`).
3. INSERT schedules row: `schedule_type="one_off"`, `start_date=event.date`, `end_date=event.end_date`, `start_time=event.start_time`, `end_time=event.end_time`.
4. If `event.contact_phone` / `event.contact_name` non-null: INSERT contact_points.
5. If `event.event_url` non-null: INSERT contact_point with kind="website".
6. INSERT source_evidence row.
7. UPDATE events SET entity_id = (new entities.id).

### §6.5 Sponsor.entity_type backfill

Single UPDATE: `UPDATE sponsors SET entity_type = "commercial" WHERE entity_type IS NULL`. Then leave it nullable in the model (the column is theoretically extensible; future Place-backed or Event-backed sponsors might land null and get backfilled by their respective ingest paths).

### §6.6 Idempotency

The backfill must be safe to run twice. Each stage 2 INSERT checks for existence first (e.g., `INSERT INTO entities ... SELECT ... WHERE NOT EXISTS (SELECT 1 FROM entities WHERE ...)`). Alternatively, the whole stage 2 can guard against `legacy_table.entity_id IS NOT NULL` and skip already-backfilled rows. Either pattern is acceptable; pick one and document the choice in the migration's docstring.

### §6.7 Tests — extend `tests/test_entity_schema.py`

Add a new test class or module `tests/test_entity_backfill.py`:

1. `test_provider_backfilled_to_entity` — insert a Provider row before the backfill migration; run the migration; assert an entities row with `entity_type="commercial"` and matching slug exists, plus expected extension rows.
2. `test_event_backfilled_to_entity` — same shape for Events.
3. `test_program_backfilled_to_entity` — same for Programs.
4. `test_sponsor_entity_type_backfilled` — pre-existing Sponsor rows end up with `entity_type="commercial"`.
5. `test_backfill_idempotent` — running the backfill twice doesn't create duplicate entities rows.
6. `test_legacy_entity_id_nonnull_after_backfill` — `providers.entity_id` IS NOT NULL after migration; same for events and programs.

These tests require a careful fixture pattern. Look at `tests/test_provider_slug_migration.py` for the precedent — the project's fixture style is to use `init_db()` to run the full chain, then SQL-insert pre-existing rows that simulate the pre-backfill state. If the fixture pattern doesn't cleanly support testing a partial migration state, fall back to unit-testing the backfill helper functions in isolation + one integration test that asserts post-backfill correctness on the fully-migrated DB. Report the chosen approach in the final report.

### §6.8 Phase 1B acceptance + commit

After Phase 1B:
- Pytest green (count grew by 6+).
- Ruff clean.
- `alembic upgrade head` applies cleanly.
- Inspect post-backfill state: SELECT count(*) from entities = count(*) from (providers + events + programs).
- Final report per §13.
- **HALT.** Operator commits Phase 1B.

Suggested commit subject: `feat(db): Phase 1B — backfill Provider/Event/Program into entities + extensions`

---

## §7 Phase 1C — Application read pivot (7-10 days estimate)

This is the largest sub-phase. App code stops reading directly from `providers`/`events`/`programs` for the data that has been migrated to ENTITY; it reads from `entities` + extensions joined back through the legacy table only where the legacy-only data lives (e.g. Program.age_min/age_max have no ENTITY equivalent yet — Phase 3 lands those as features rows).

### §7.1 Strategy

Two patterns to choose between per call site:

**Pattern A — "ENTITY-first":** Query starts at `entities`, joins relevant extensions, filters by `entity_type`, and joins back to the legacy table for fields not yet on ENTITY (Program-specific fields like age_min/age_max, Event-specific fields like `is_recurring`).

**Pattern B — "Legacy + alias":** Query continues at `providers` (or `events` or `programs`), but reads enriched data via `legacy.entity.location`/`legacy.entity.hours`/etc. join paths through the new ORM relationships.

**Recommend Pattern A** for `app/chat/tier2_db_query.py` (the chat catalog lookup — explicitly cross-type already; ENTITY-first is the natural shape). **Recommend Pattern B** for `app/providers/queries.py` + `app/providers/view_models.py` (Provider profile page is single-entity-type-specific; legacy-first keeps the diff small).

Pick a pattern per file. Document the choice in the file's module docstring.

### §7.2 Touch list

**`app/providers/queries.py`** — pivot to read enriched data via the new `Provider.entity` relationship (which you'll add as a 1:1 backref on Provider in Phase 1B's migration model edit). Provider profile page queries pull `provider.entity.location.address`, `provider.entity.hours`, `provider.entity.contact_points`, etc. Don't break the existing `/provider/<slug>` route's behavior.

**`app/providers/view_models.py`** — ProviderProfileVM reads from `provider.entity.*` extensions where possible. Existing fields like `viewer_is_owner`, `show_claim_cta`, `claim_url`, `upgrade_url` (already on the VM per the boot prompt's context-that-often-gets-lost section) stay where they are.

**`app/chat/tier2_db_query.py`** — the SELECT statements at line ~30+ swap from `select(Provider, Event, Program)` to `select(Entity).where(entity_type IN (...))` plus joins to relevant extensions for filter expressions (category, location, hours).
- **Preserve `_category_needle_set` synonym expansion at ~line 469.** That logic is load-bearing for cross-category chat queries; it now operates on `Entity.categories` (via entity_categories M:M) and Entity's display name + offerings.
- The `_event_covers_any_weekday` helper at line ~75 now operates on `Entity` + `Schedule` joins instead of bare `Event` rows.
- `MAX_ROWS = 8`, `BROAD_EVENT_SQL_LIMIT = 500`, `NARROW_EVENT_SQL_LIMIT = 80` constants stay.
- `is_open_at` / hours filtering still in Python after SQL fetch; the new path joins through `entity.hours` to assemble the structured hours dict.

**`app/contrib/places_client.py`** — `lookup_provider` is the runtime Google Places lookup path. In Phase 1C it stays Provider-aware (writes still go to Provider in this sub-phase; 1D adds the dual-write). Just ensure that any READ paths from the lookup result back to a stored row pivot to `Provider.entity.location.google_place_id` instead of `Provider.google_place_id` if the relevant code reads it post-write. Touch lightly — most of this file is the outbound API call.

**`app/contrib/enrichment.py`** — contribution-enrichment path. Update READ paths only; writes go to Provider in 1C (1D adds dual-write).

**`scripts/places_load.py`** — Places loader script. Same as above — reads pivot, writes stay Provider-targeted until 1D.

**Out of scope in 1C:** any write paths. Writes continue to land in `providers`/`events`/`programs` rows as before; Phase 1D adds the entities + extensions dual-write.

### §7.3 Regression coverage

**This is the highest-risk sub-phase.** The chat-route response shape must not change. Add or extend regression coverage:

- `tests/test_chat_route_integration.py` — extend existing ChatRoute integration class with at least 3 new test methods that pin output for representative queries pre-and-post pivot. The technique is to run the chat route's query against fixtures that have both legacy AND entity rows populated, and assert the returned response matches the legacy-only shape. Use `tier_used`, `entity_matched`, response text contents as the assertion points.
- `tests/test_provider_profile_page.py` (if exists; else create) — extend to assert profile page renders identical HTML pre-and-post pivot for a representative Provider with hours, contact info, and a category.
- `tests/test_tier2_db_query_entity_pivot.py` (new) — direct unit tests against `tier2_db_query.query()` asserting output dicts have the same keys + values as pre-pivot for ≥5 query shapes (entity-named, category-named, time-windowed, location-filtered, open-now).

### §7.4 Phase 1C acceptance + commit

- Pytest stays green; expect new test count growth.
- Chat-route integration tests pass.
- Provider profile page tests pass.
- Tier 2 catalog regression tests pass.
- Manual smoke check: hit `/provider/<slug>` for a representative provider in dev; confirm page renders identically (compare DOM snapshot if possible).
- Final report per §13.
- **HALT.** Operator commits Phase 1C.

Suggested commit subject: `refactor(app): Phase 1C — read pivot to ENTITY across providers/chat/contrib`

---

## §8 Phase 1D — Write dual-target + close-out + entity_id NOT NULL flip (3-5 days estimate)

### §8.0 entity_id NOT NULL flip (added 2026-05-14 per Phase 1B deferral)

The Phase 1B migration left `providers.entity_id`, `events.entity_id`, and `programs.entity_id` nullable because Phase 1B preceded the dual-write helpers. Phase 1D's dual-write helper (§8.1 below) populates `entity_id` at write time for new rows. Once the dual-write helpers ship and tests pass, this sub-phase adds a small migration that flips NOT NULL on all three columns. **Order matters within Phase 1D:** dual-write helpers must be in place + every test fixture path must populate `entity_id` BEFORE the NOT NULL flip migration runs. Run the full test suite immediately after the flip migration to catch any fixture path that still constructs raw Provider/Event/Program rows without going through the dual-write helper. The flip migration is small (single alembic file, `op.alter_column` × 3 with `nullable=False`); the risk surface is entirely in the dual-write coverage being complete.

### §8.1 Dual-write strategy

For each ingest path that creates a Provider/Event/Program row, add a sibling write that creates the corresponding entities row + extension records in the same SQLAlchemy session (atomic commit).

Touch list (verify each does INSERT-side work; some may only UPDATE):

- `app/admin/router.py` — admin form Provider create
- `app/contrib/approval_service.py` — contribution-approval Provider/Event/Program create
- `scripts/places_load.py` — Places loader Provider create
- `scripts/ingest/ingest_enrichment_csv.py` — CSV upsert
- `app/contrib/parks_rec_loader.py` — Parks & Rec Program create
- `app/contrib/river_scene_pull.py` / `app/contrib/river_scene.py` — River Scene Event create
- `app/api/routes/events.py` (or wherever Event POST lands) — public Event submission

For each: factor a shared helper `app/db/entity_dual_write.py::create_provider_and_entity(session, provider_kwargs) -> tuple[Provider, Entity]` (and analogs for Event + Program). The helper:
1. Constructs the Provider row (existing pattern).
2. Constructs the Entity row + LinkedExtensions in the same session.
3. Wires `provider.entity_id = entity.id` on the Provider.
4. Returns both for caller convenience.

Existing tests that depend on Provider-only creation should keep passing — the helper does the legacy work plus the new work, transparently.

### §8.2 Sponsor query routing

`app/sponsors/*.py` (or wherever sponsor lookup lives — grep for `Sponsor.business_id`) — update queries that resolve `sponsor.business_id` to its referenced entity. The current pattern likely assumes Provider (e.g., `Provider.id == Sponsor.business_id`). Update to route through `Sponsor.entity_type`:

```python
if sponsor.entity_type == "commercial":
    business = session.query(Provider).filter(Provider.id == sponsor.business_id).one()
elif sponsor.entity_type == "place":
    # No places yet; future Phase 2/5 will populate
    business = session.query(Entity).filter(
        Entity.id == sponsor.business_id, Entity.entity_type == "place"
    ).one()
# etc.
```

OR (cleaner): pivot the whole sponsor-to-business join through Entity uniformly:

```python
business = session.query(Entity).filter(Entity.id == sponsor.business_id).one()
```

This requires Sponsor.business_id to be an Entity.id String UUID, not a Provider int id. Investigate: the current `business_id` column is `Integer | None` per `app/db/models.py:547`. If sponsors actively reference legacy Provider int ids in production, this approach requires data migration. If sponsors are currently empty in production (likely — pivot is recent), leave business_id as Integer but document that Phase 11 monetization will reshape this. Prefer the discriminator-branching approach in 1D and let Phase 11 unify.

### §8.3 Tests

Extend each ingest-path test with assertions that both the legacy row AND the corresponding entities row + extensions are created. ~6-10 new tests across the ingest paths.

Sponsor-resolution test: insert a Sponsor with `entity_type="commercial"` + `business_id` pointing to a Provider; assert the resolution returns the right Provider.

### §8.4 Phase 1D acceptance + commit

- Pytest green.
- Every Provider/Event/Program ingest path now writes entities + extensions atomically.
- Sponsor lookups disambiguate via entity_type.
- Final report per §13.
- **HALT.** Operator commits Phase 1D. This completes Phase 1 of the master plan.

Suggested commit subject: `feat(app): Phase 1D — dual-write to entities + extensions across ingest paths`

---

## §9 What to do, in order (across all four sub-phases)

1. §0 baseline confirmation. Report values. Confirm reads complete.
2. **Phase 1A:** schema additive migration + new ORM classes + tests. Halt + report + operator commits.
3. **(Operator re-dispatches you in a new session.)**
4. **Phase 1B:** backfill migration + idempotency guards + backfill tests. Halt + report + operator commits.
5. **(Operator re-dispatches.)**
6. **Phase 1C:** application read pivot across the touch list + regression tests. Halt + report + operator commits.
7. **(Operator re-dispatches.)**
8. **Phase 1D:** dual-write helper + ingest-path updates + sponsor resolution + tests. Halt + report + operator commits.
9. Master plan §4 Phase 1 gets a "Shipped: <date> + commit SHA + actual effort vs estimate" line added by operator after 1D commits.

---

## §10 What NOT to do

- **Don't run `git add`, `git commit`, `git push`, `--amend`.** Report when each sub-phase is done; operator commits.
- **Don't ship multiple sub-phases in one session** unless the operator explicitly authorizes it. Halt-and-report between each is the rhythm.
- **Don't delete or rename any existing Provider/Event/Program column** in Phase 1. Phase 13 (V1.5+) handles legacy cleanup if/when it makes sense.
- **Don't drop the legacy `providers` / `events` / `programs` tables.** They remain alive for backward compat through the entire build.
- **Don't change the chat-route response shape.** This is a refactor. User-visible behavior is identical pre-and-post Phase 1.
- **Don't add new feature columns** in Phase 1 (e.g., heat_exposure, crowd_notes, boat_access) — those are Phase 3's v1.1 schema pass. The ENTITY extension tables ship in Phase 1; the data they hold ships in Phase 3+.
- **Don't add Place entity rows.** Place data gathering is Phase 5. Phase 1 only ships the schema + code path that supports `entity_type="place"`; no Place rows are created.
- **Don't add semantic search / FTS** — that's Phase 2B (`search_index_decision.md`). The `entities.description` Text column ships in 1A; the tsvector index ships in Phase 2B.
- **Don't add R2 photo storage references** — Phase 2B. Photos table is created in Phase 2B.
- **Don't touch the existing `Category` model.** It's already shipped with 12 seeded rows. Phase 1's `entity_categories` table joins to it via `category_id` FK.
- **Don't restructure existing tests.** Extend test files in place; add new test files when introducing new schema. The 1476+ baseline tests must all keep passing.
- **Don't add backwards-compat shims via Python properties on legacy classes** (e.g., `Provider.address` becomes a property that reads from `provider.entity.location.address`). That breaks SQLAlchemy query patterns and confuses the migration story. Keep legacy columns as data; route reads through new join paths explicitly.
- **Don't use Postgres ENUMs** for `entity_type` (matches the existing AdSlot/SponsorStatus pattern — strings + app-layer validation).
- **Don't `git commit --amend` anything** (Rule 12 of dispatch protocol).
- **Don't ignore PowerShell `$` interpolation** if the operator commits via PowerShell (Rule 4 extended per session-13 lessons — single-quote git commit subjects with `$` or sigils).
- **Don't proceed past a baseline mismatch.** Halt and report.

---

## §11 Pragmatic deviations are allowed (within guardrails)

You may deviate from the brief if you discover something on the ground that materially changes the right call. **Report every deviation in the final report.** Examples of acceptable deviations:

- A line offset is different than this brief states because of a recent commit (likely — the brief was authored 2026-05-14 before the actual dispatch).
- A field name needs adjustment because the existing data model has a name collision (e.g., `entity.hours` collides with `Provider.hours` if the relationship is wired the wrong way — rename to `entity.weekly_hours` if needed; document).
- A test fixture pattern doesn't exist for the case the brief expects, and a lighter assertion is the right fallback.
- The recommended schema field shape (e.g., `int | None` vs `str | None`) doesn't match the project's existing type conventions on similar columns — match the project's pattern.
- An extension table's relationship needs `lazy="joined"` for query performance (V1 doesn't care about perf, but if you're already there, you might note it).

Unacceptable deviations (these are LOCKED):
- Renaming `entities` to a different name.
- Adding additional entity_type values beyond commercial/place/event/program.
- Adding additional extension tables beyond the 11 specified.
- Skipping or merging sub-phases.
- Dropping legacy table columns or rows.

---

## §12 Risk register for this lane

| # | Risk | Mitigation |
|---|---|---|
| 1 | ORM relationship wiring is fragile across new + legacy classes | Add Provider.entity / Event.entity / Program.entity 1:1 relationships in Phase 1B's model edit (when entity_id columns are added). Test relationship navigation at every sub-phase. |
| 2 | Chat-route regression — Tier 2 query returns different rows post-pivot | §7.3 regression tests pin response shape. Run full `python -m pytest -q` after every file edit in 1C. |
| 3 | Slug collisions during Phase 1B backfill — Provider.slug + new Event/Program slugs may collide because Entity.slug is globally unique | Use `make_unique_slug` from `app/utils/slug.py` with a shared `used` set across the whole backfill batch. Test for collision handling explicitly. |
| 4 | Backfill performance against production (Railway Postgres) | Current production data is small (~71 events + few/zero providers + few/zero programs). Backfill via `op.execute` is fine at this scale. Production deploys will apply the migration cleanly. |
| 5 | SQLite vs Postgres divergence on cascade deletes or JSON columns | Use `op.batch_alter_table` for SQLite-friendliness. Test on both dev (SQLite) and confirm Railway Postgres deploys cleanly when operator pushes. |
| 6 | Sponsor.business_id is Integer but Entity.id is String UUID | §8.2 keeps business_id as Integer; sponsor resolution branches on entity_type. Phase 11 monetization unifies. |
| 7 | Sub-phase scope blows up mid-session (especially 1C) | Halt-and-report etiquette in §3 is the safety valve. Better to ship 1C-partial cleanly + re-dispatch than push past a broken state. |
| 8 | The boot prompt's "1476 tests" baseline may be off by a few from when this brief was authored | §0 step 3 treats 1476 as a floor. Adjust working baseline to the actual count returned by `pytest --collect-only`. |

---

## §13 Final report format (per sub-phase)

After each sub-phase, paste back a single message:

1. **Sub-phase identifier** — 1A / 1B / 1C / 1D.
2. **§0 baseline values** (HEAD, pytest count, alembic head, alembic current).
3. **Files created** (paths + line counts).
4. **Files modified** (paths + net line counts).
5. **Migration revision id chosen** + `down_revision`.
6. **Tests added** (count + brief description of each).
7. **Final pytest count** (expected to be baseline + tests added).
8. **`python -m alembic upgrade head` result** against fresh dev DB (success/failure + any output).
9. **Ruff status** (clean / autofixes applied / remaining issues).
10. **Pragmatic deviations** — anything you adapted from this brief, with rationale. Be transparent; reasonable deviations are fine.
11. **Anything that surprised you** or that the operator should know before they commit.
12. **Confirmation you did NOT run `git add` / `git commit` / `git push` / `--amend`.**
13. **Next sub-phase preview** — if 1A: "Ready for 1B re-dispatch — schema is in, no app code touched yet." If 1B: "Ready for 1C — backfill complete, app still reads legacy." If 1C: "Ready for 1D — reads pivoted, writes still legacy-only." If 1D: "Phase 1 complete; master plan §4 ready for Shipped: line."

---

Ready. Start at §0. Halt at the first sub-phase boundary.
