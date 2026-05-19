# Phase 9 Architecture Design — Schedule-heavy expansion: Events + Classes/Sports/Recreation + RRULE recurrence + Event scraper subsystem

> **What this is:** architectural-decision-record-level design doc for Phase 9 of the havasu-chat build, per master plan §4 Phase 9 (lines 427-448). Input to the future Cursor dispatch wrapper; the wrapper itself comes later and chains off Phase 8's SHIP commit + alembic head + the operator prereq findings (event-source URLs + scrape-cadence locks).
>
> **Author:** Cowork plan-agent, post-`616fd8b` (2026-05-20).
>
> **Companion docs:**
> - `docs/maintainability/master_build_plan.md` §4 Phase 9 (scope canon), §4 Phase 6 (Phase 6.5 ships the `"What's on at this venue"` empty region anchor that Phase 9 fills), §4 Phase 8 (Phase 8 is the predecessor — `event_traffic` alert is wired in Phase 9.5 against the Events surface Phase 9 lands), §7 risk register #6 (schedule-heavy expansion refresh burden), §8 OQ #12 (capacity display — only honest if venue publishes real availability)
> - `outputs/phase_8_architecture_design.md` (the predecessor design — Phase 9 reuses the Railway-scheduled-job convention, the `with_retry` envelope, the source-isolation pattern, and the additive Alembic migration discipline)
> - `outputs/phase_7_handoff_note.md` (chat tier-2/tier-3 wiring against ENTITY — Phase 9 makes chat aware of event-typed entities)
> - `outputs/phase_6_4_close_out.md` (themed-group landing pattern that Phase 9's `things-to-do-group` extends; the parallel-session alembic-collision gotcha applies to Phase 9 dispatch)
> - `docs/operations/railway_scheduled_jobs_runbook.md` (operator-side spin-up of new scheduled services)
> - `app/contrib/river_scene.py` + `app/contrib/river_scene_pull.py` + `scripts/river_scene_pull.py` (Phase 4.x existing event-scraper pattern — Phase 9 generalizes this shape to 5 sources)
> - `app/core/event_recurrence.py` (the heuristic recurrence-detector that exists pre-Phase-9; Phase 9 layers RRULE storage + expansion on top, NOT replaces)

---

## §1 Scope summary + Phase 9 split

Per master plan §4 Phase 9, the canonical scope is *four compounding lanes*:

**Lane A — Event ENTITY surface + lifecycle**
- Events as entity_type='event' fully wired through the unified Hava card grammar (the schema already supports it from Phase 1A; Phase 6.1's `_event_status_line_for_card` already exists at `app/providers/queries.py:666-696` and emits "Tonight at 6:00pm" lake-blue per the brief grammar)
- Event lifecycle states properly modeled: `('draft', 'live', 'cancelled', 'expired')` — `Event.status` column already exists with default `'live'` (`app/db/models.py:185`); Phase 9 extends the surface to recognize the full state machine + operator-override semantics
- Event creation routes: admin form (operator-curated) + scraper ingest (the existing contributions queue is the seam — see §5)
- Event-card rendering verified end-to-end against the existing `build_card_view_model` event branch

**Lane B — RRULE recurrence handling**
- Storage shape: extend `Event` with `rrule: String(255) | None` + `rdate: JSON | None` + `exdate: JSON | None` (single-event-row-with-rule strategy — see §3 for the at-query-time vs row-expansion tradeoff)
- Expansion-at-query-time helpers in new `app/events/recurrence.py` module wrapping `dateutil.rrule`
- Date-range query helpers ("events this weekend" / "events next month") at `app/events/queries.py`
- Recurrence exceptions stored as RRULE `EXDATE` syntax (not a separate exceptions table — see §3.3)

**Lane C — Event scraper subsystem**
- Five sources (see §5): Chamber community calendar + Go Lake Havasu events + RiverScene Magazine (already exists from Phase 4.x; Phase 9 generalizes the pattern) + City of LHC library calendar + City of LHC parks-and-rec calendar
- Reuse `BaseIngestClient` pattern (`app/contrib/ingest_base.py`) + extend with event-specific payload subclass
- Cadence: daily for Chamber + Go Lake Havasu + RiverScene; weekly for city library + parks-rec (lower change frequency)
- Multi-source dedup via `(venue_entity_id, start_datetime, normalized_title)` tuple (see §6)
- Operator-curated vs scraper-sourced merge semantics — scraper writes to contributions queue; operator approves; once-approved scraper updates are field-tracked via existing `field_history` table (preserves operator overrides per Phase 5's manual-recovery pattern)

**Lane D — Surfaces (category pages, themed group, venue region)**
- Events category page (`/category/events`) — date-aware chip filters ("today" / "this weekend" / "next month")
- Classes / Sports / Recreation category page (`/category/classes-sports-recreation`) — recurring-schedule rendering + age band filters + drop-in vs registration chip
- "What's on at this venue" region on `provider_profile.html` (fills the Phase 6.5-shipped empty region; renders upcoming events tied to `entity_id` with RRULE expansion)
- Integrated stream on themed group pages — Phase 6.4 ships static interleaved Hava cards (entities only); Phase 9 makes the themed group landing actually interleave events + places per relevance score (§9)
- Themed group landing for `things-to-do-group` — categories bundled: cat-2 (Events) + cat-7 (Outdoors/Parks/Trails) + cat-9 (Classes/Sports/Recreation, partial); see §8 for the operator decision-lock on which categories bundle

**Recommended sub-phase split: Phase 9a + Phase 9b**

| Sub-phase | Lanes | Effort | Sequencing |
|---|---|---|---|
| **Phase 9a — Event ENTITY + RRULE foundation** | Lane A + Lane B + Lane D's `/category/events` + venue "What's on" region | ~6-8 days dispatch | Sequential; ships first |
| **Phase 9b — Scraper subsystem + Classes/Sports + Things-to-Do group + interleaving** | Lane C + Lane D's `/category/classes-sports-recreation` + `things-to-do-group` + themed-group interleaving upgrade | ~6-8 days dispatch | Sequential after 9a; reuses 9a's storage shape |

**Why the split:**
1. Lane B (RRULE) is the load-bearing storage decision. If Phase 9a ships and we discover the at-query-time expansion model has performance issues, Phase 9b adapts before scraper writes 1000s of recurring rows.
2. Lane C scrapers are independent of Lane A/B once the storage shape locks. They can fan out to 5 sources at Phase 9b dispatch time without re-touching schema.
3. Mirrors Phase 8a/8b discipline (`outputs/phase_8_architecture_design.md` §10.4).

Master plan §4 calls Phase 9 "L (12-18 days)" already. Splitting 9a/9b keeps each Cursor session focused + lets the operator review Phase 9a's actual recurrence-expansion query timings before authorizing 9b's bulk scraper writes.

---

## §2 Event schema additions (additive Alembic migration)

### §2.1 What already exists (Phase 1A)

The `Event` table at `app/db/models.py:166-246` ships these columns Phase 9 needs:

| Column | Type | Phase 9 usage |
|---|---|---|
| `id` | String PK (UUID) | Stable event identifier; the `entity_id` FK below is the unified-entity bridge |
| `entity_id` | String FK to `entities.id` (NOT NULL, indexed) | The ENTITY-pivot seam — Hava card grammar reads from `Entity` via this FK |
| `title` / `normalized_title` | String NOT NULL | Card name + dedup matching (see §6.2) |
| `date` / `end_date` | Date | Single-day OR date-range events (e.g. multi-day festival) |
| `start_time` / `end_time` | Time | Wall-clock start/end (Lake Havasu local time per `app/core/timezone.py`) |
| `location_name` / `location_normalized` | String | Venue label; dedup key component |
| `description` | Text | Card description / detail-page body |
| `event_url` / `source_url` | String(2048) | Outbound canonical URL + ingest provenance |
| `tags` | JSON list[str] | Free-form scrape-derived tags (Phase 4.x existing shape) |
| `status` | String DEFAULT `'live'` | The lifecycle column — Phase 9 widens it (see §2.3) |
| `source` | String DEFAULT `'admin'` | Provenance: `'admin'` / `'chamber'` / `'go_lake_havasu'` / `'river_scene'` / `'lhc_library'` / `'lhc_parks_rec'` (extended in §5) |
| `verified` | Boolean | Operator-confirmed flag |
| `is_recurring` | Boolean DEFAULT `false` | Existing flag — Phase 9 keeps this AND adds RRULE detail; the flag is a cheap pre-filter index target |
| `featured` | Boolean | Editorial "Hava's pick" — already on `Entity` too; redundant on `Event` for backward-compat |
| `last_verified_at` | TZAwareDateTime | Freshness anchor — Phase 6.1's `derive_freshness_band_from_updated_at` reads from `Entity.updated_at` today; Phase 9 swaps the source for event-typed cards (see §10) |
| `provider_id` | FK to `providers.id` NULLABLE | Venue link — the "What's on at this venue" region queries via this FK + the `entity_id` cross-link |
| `created_at` / `admin_review_by` | DateTime | Audit trail |

### §2.2 Phase 9 additive columns (single small migration)

| Column | Type | Nullable | Why |
|---|---|---|---|
| `rrule` | `String(255)` | Yes | RFC-5545 RRULE string (e.g. `FREQ=WEEKLY;BYDAY=TU;UNTIL=20261201T000000Z`). NULL = non-recurring single-instance event. Existing `is_recurring` Boolean stays as a cheap pre-filter — set to TRUE iff `rrule IS NOT NULL OR rdate IS NOT NULL`. App-layer invariant; not a DB-level CHECK. |
| `rdate` | `JSON list[str]` | Yes | Extra ISO-formatted date(time)s added on top of the rrule pattern (e.g. holiday class added outside the regular weekly cadence). Empty list or NULL = no extras. |
| `exdate` | `JSON list[str]` | Yes | Exception date(time)s removed from the rrule expansion (e.g. "this Friday's yoga is cancelled"). The "this Friday is cancelled" pattern stores `exdate=['2026-12-24']` rather than a separate row in an exceptions table. (See §3.3 for why.) |
| `scraped_at` | `TZAwareDateTime` | Yes | Freshness anchor for scraper-sourced events. Per master plan §4 Phase 9: "Freshness anchor on scrape timestamp." NULL for operator-curated events (those use `Entity.updated_at` for the band). Phase 9 reads this column for the tighter decay curve (green <7d / amber 7-21d / red >21d). |
| `cancellation_reason` | `Text` | Yes | Operator-supplied free-text reason when `status='cancelled'`. NULL when status is anything else. Rendered on event detail page; surfaced in the card's `status_line_text` only as "Cancelled" (terse) — full reason only on detail. |
| `operator_override` | `Boolean DEFAULT false` | No (server default) | Set TRUE by operator edit UI when operator manually changes a field on a scraper-sourced event. Prevents next-scrape from undoing the operator's change (see §7 — the manual-recovery + sustainability layer pattern from Phase 5). |
| `capacity` | `Integer` | Yes | Maximum attendance count when venue publishes it. NULL is the V1 default — per master plan §8 OQ #12, capacity is honest-only: NULL → no rendering. (§4.) |
| `capacity_source` | `String(64)` | Yes | Provenance: `'eventbrite'`, `'venue_published'`, `'operator_typed'`. Required to be non-NULL whenever `capacity IS NOT NULL`. App-layer invariant; no DB CHECK. |

**Important: No separate `event_recurrences` or `event_exceptions` table.** Phase 9 stores the recurrence rule + exceptions inline on `Event` and expands at query time. The case for a separate table is rejected — see §3.

### §2.3 `Event.status` CHECK constraint extension

Phase 1A shipped `status` as `String DEFAULT 'live'` with no CHECK constraint. Phase 9 adds an additive CHECK constraint:

```sql
ALTER TABLE events ADD CONSTRAINT ck_events_status
  CHECK (status IN ('draft', 'live', 'cancelled', 'expired'));
```

| `status` | Meaning | When set | Card visibility |
|---|---|---|---|
| `draft` | Scraper-sourced + awaiting operator review (likely transitional — most live events go straight to `'live'` via the contributions queue approval) | At ingest if confidence below threshold | Hidden from category page; visible only in admin queue |
| `live` | Active event, surfacing in card streams | Default at ingest after approval | Rendered everywhere |
| `cancelled` | Event was scheduled but is now off — operator-set, scraper cannot override | Operator action | Rendered with red status line "Cancelled" — kept visible until past date so users who had it on their calendar see it WAS cancelled |
| `expired` | Past-date archival state — derived, not operator-set | Background job (§2.5) sweeps once daily | Hidden from default category-page filters; surfaced only on venue archive view (V1.5) |

**The data-cleanup follow-up table from Phase 8's `delivery_status` CHECK extension is the precedent.** Phase 9's migration similarly drops + recreates the constraint (if a prior constraint exists in any deployed snapshot) and seeds the four allowed values.

### §2.4 Indexes added by Phase 9

```sql
CREATE INDEX ix_events_status_date ON events (status, date);  -- "live events upcoming" hot path
CREATE INDEX ix_events_is_recurring_date ON events (is_recurring, date);  -- recurrence-expansion filter pre-narrow
CREATE INDEX ix_events_provider_id_date ON events (provider_id, date);  -- "what's on at this venue"
CREATE INDEX ix_events_scraped_at ON events (scraped_at);  -- freshness-band batched reads + stale-purge background job
```

### §2.5 Background job: status transitions to `'expired'`

New script `scripts/expire_past_events.py` runs once daily (Railway cron `0 3 * * *` Lake Havasu local), pattern from `scripts/outbox_redrive.py`:

```sql
UPDATE events
SET status = 'expired'
WHERE status = 'live'
  AND date < CURRENT_DATE - INTERVAL '7 days'
  AND (rrule IS NULL OR rrule LIKE '%UNTIL=%'
       AND parsed_until_from_rrule(rrule) < CURRENT_DATE - INTERVAL '7 days');
```

The `parsed_until_from_rrule` semantics: for an open-ended recurrence (no `UNTIL=`), the event NEVER auto-expires — operator decides. For a bounded recurrence (`UNTIL=20261231T000000Z`), it expires 7 days after the UNTIL date. The 7-day grace matches the "Last week" / red status line at `app/providers/queries.py:687-688` — users who recently visited see "Last week" before the card disappears.

---

## §3 RRULE expansion strategy

### §3.1 The decision: at-query-time expansion, not row-expansion

The two candidate strategies:

| Strategy | Storage | Read path | Write path |
|---|---|---|---|
| **At-query-time expansion (RECOMMENDED)** | 1 row per logical event; `rrule` + `exdate` + `rdate` columns hold the rule | Read 1 row → expand via `dateutil.rrule` → filter to query window → in-memory sort | Operator edits 1 row; scraper writes 1 row |
| Row expansion (REJECTED for V1) | N rows per recurring event (1 per occurrence within a horizon, e.g. next 365 days) | Read N rows directly; simpler SQL `WHERE date BETWEEN ...` | Operator edit of master needs cascade UPDATE; scraper writes N rows + needs reconciliation logic when N changes |

**Decision:** ship V1 with at-query-time expansion. Reasoning:

1. **Storage simplicity beats query simplicity at our scale.** Expected steady-state: ~50-100 recurring events × ~52 weekly occurrences/year = 2,600-5,200 expanded rows IF we materialized. Plus equal count for one-off events. The row-expansion table would be 10-20× larger than the rule-storage table. At our scale (~200 events total at V1 launch) materialized rows save no meaningful query time but make every recurring-event edit a multi-row DML operation.
2. **Edit semantics are simpler.** Operator changes "Pickleball is now at 9am instead of 10am" — with rule storage, that's a 1-row UPDATE. With row expansion, it's "UPDATE every future-dated row WHERE source_event_id = X AND date > today". The latter is a real bug vector for missed/double updates.
3. **Exception semantics are simpler.** "Skip Dec 24" with rule storage = append to `exdate` JSON. With row expansion = DELETE specific row OR add cancelled flag. Both work; rule storage is closer to the underlying domain.
4. **`dateutil.rrule` is fast.** Expanding a typical weekly recurrence over a 1-month window takes < 1ms even for complex rules. The query window is always bounded (we never expand "all events forever") so worst-case work is bounded.

**Trade-offs accepted:**
- The "events this weekend" SQL can't be a simple `WHERE date BETWEEN ...` against the events table. Instead it's: SELECT all non-recurring events in window UNION SELECT all events with `rrule IS NOT NULL`, expand in Python, filter to window. The `is_recurring` Boolean + `ix_events_is_recurring_date` index lets us narrow the recurring set efficiently.
- Pagination semantics on a "this month's events" stream are slightly subtle (you paginate over expanded virtual instances, not DB rows). Phase 9 addresses this via deterministic in-memory sort + LIMIT after expansion — see §3.4.

**Future-proofing:** if profiling at V1.5 shows expansion is the bottleneck (it won't at <500 events), Phase 13 can introduce an `event_occurrences_materialized` table populated by a nightly background job. The rule-storage shape is forward-compatible; row-expansion-on-top is additive.

### §3.2 The expansion helper module

New `app/events/recurrence.py`:

```python
# app/events/recurrence.py
from datetime import date, datetime, time, timedelta
from typing import Iterable
from dateutil.rrule import rrulestr
from dateutil.tz import gettz
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.models import Event


def expand_event(
    event: Event,
    *,
    window_start: date,
    window_end: date,
    cap: int = 100,
) -> list[date]:
    """Return list of dates within [window_start, window_end] on which
    this event occurs. For non-recurring events, returns [event.date]
    if it's in window, else []. For recurring events, expands the
    rrule + applies rdate + exdate.

    `cap` is a safety ceiling — if expansion would produce more than
    `cap` dates, raises ValueError (defensive against pathological
    rules like daily-forever).
    """
    if not event.rrule and not event.rdate:
        # Single-instance event
        return [event.date] if window_start <= event.date <= window_end else []

    # Build the rule string with the event's start date as DTSTART
    dtstart = datetime.combine(event.date, event.start_time)
    if dtstart.tzinfo is None:
        dtstart = dtstart.replace(tzinfo=LAKE_HAVASU_TZ)

    rule_text = f"DTSTART:{dtstart.strftime('%Y%m%dT%H%M%S')}\n{event.rrule}"
    rule = rrulestr(rule_text)

    occurrences: list[date] = []
    for occ in rule.between(
        datetime.combine(window_start, time.min, tzinfo=LAKE_HAVASU_TZ),
        datetime.combine(window_end, time.max, tzinfo=LAKE_HAVASU_TZ),
        inc=True,
    ):
        occurrences.append(occ.date())
        if len(occurrences) > cap:
            raise ValueError(
                f"event.id={event.id} expansion exceeded cap={cap}; check rrule={event.rrule}"
            )

    # Add rdate extras
    for extra in event.rdate or []:
        d = date.fromisoformat(extra)
        if window_start <= d <= window_end and d not in occurrences:
            occurrences.append(d)

    # Remove exdates
    excluded = {date.fromisoformat(x) for x in (event.exdate or [])}
    occurrences = [d for d in occurrences if d not in excluded]

    occurrences.sort()
    return occurrences


def occurrences_in_window(
    events: Iterable[Event],
    *,
    window_start: date,
    window_end: date,
) -> list[tuple[Event, date]]:
    """Expand multiple events. Returns flat list of (event, occurrence_date)
    tuples, sorted by (date, start_time, name). Caller can LIMIT after."""
    flat: list[tuple[Event, date]] = []
    for ev in events:
        for d in expand_event(ev, window_start=window_start, window_end=window_end):
            flat.append((ev, d))
    flat.sort(key=lambda pair: (pair[1], pair[0].start_time, pair[0].normalized_title))
    return flat
```

### §3.3 Exception storage: EXDATE inline, NOT separate table

Two options were considered for storing exceptions ("this Friday's yoga is cancelled"):

| Option | Pros | Cons |
|---|---|---|
| **EXDATE on Event row (RECOMMENDED)** | One row per logical event; `dateutil.rrule` natively understands EXDATE; operator UI is "add date to exceptions list" | JSON list can grow unbounded over years (~52 exceptions × N years for weekly events) — but at V1 lifespan + ~50 recurring events, this is < 5 KB per row, negligible |
| Separate `event_exceptions` table (REJECTED) | Cleaner relational shape; each exception has its own audit trail (who cancelled, when, why) | Adds 1 table + FK; cancellation-audit query is `JOIN`; doubles edit-UI complexity for a feature operator uses ~weekly at most |

**Recommendation: EXDATE inline.** Cancellation audit lives in `field_history` (existing Phase 3 table) — every operator EXDATE add writes a `field_history` row with `field_name='exdate'`, capturing the who/when/why audit trail without a separate dedicated table.

### §3.4 Date-range query implementation

The "events this weekend" query at `app/events/queries.py`:

```python
# app/events/queries.py
def events_in_window(
    db: Session,
    *,
    window_start: date,
    window_end: date,
    category_slug: str | None = None,
    limit: int = 50,
) -> list[tuple[Event, date]]:
    """Return (event, occurrence_date) tuples sorted chronologically.

    Two-pass strategy: SQL pre-filter narrows to candidate events;
    Python expansion produces flat (event, date) tuples.
    """
    # Pre-filter: candidates are events where ANY occurrence COULD fall in window
    # - non-recurring: event.date IN window
    # - recurring with UNTIL: window_start <= until_date
    # - recurring without UNTIL: always a candidate
    q = (
        db.query(Event)
        .filter(Event.status == "live")
        .filter(
            or_(
                # Non-recurring + within window
                and_(Event.is_recurring == False, Event.date.between(window_start, window_end)),
                # Recurring: caller-side expansion will determine actual occurrences
                Event.is_recurring == True,
            )
        )
    )

    if category_slug:
        q = q.join(Entity, Entity.id == Event.entity_id)\
             .join(EntityCategory, EntityCategory.entity_id == Entity.id)\
             .join(Category, Category.id == EntityCategory.category_id)\
             .filter(Category.slug == category_slug)

    candidates = q.all()
    flat = occurrences_in_window(candidates, window_start=window_start, window_end=window_end)
    return flat[:limit]
```

**Query window presets** (the chip-filter values on `/category/events`):

| Chip | Window | Notes |
|---|---|---|
| Today | `[today, today]` | Single-day |
| This weekend | `[next Friday, next Sunday]` if today < Friday else `[today, this Sunday]` | Lake Havasu local time |
| This week | `[today, this Sunday]` | |
| Next month | `[start of next month, end of next month]` | |
| Custom date range | `[from, to]` operator-supplied | Date pickers — bounded to 90 days to prevent abusive expansion |

### §3.5 Performance + indexing

At V1 launch with ~200 events (~50 recurring), expansion cost is bounded:

- Pre-filter SQL with `ix_events_status_date` + `ix_events_is_recurring_date`: <5 ms
- Python expansion of ~50 recurring events × ~4-8 occurrences in a 1-month window = <10 ms total
- In-memory sort: <1 ms

Total category-page render budget for events: ~16-20 ms. Comfortable.

At V1.5/V2 (~500 events, ~150 recurring), expansion cost could grow to ~50 ms. Still acceptable. The materialization optimization (§3.1 trade-off) waits for hard data.

### §3.6 RRULE storage examples

Documented in `docs/operations/event_recurrence_examples.md` (new doc Phase 9 ships) — operator-facing reference:

| Real-world recurrence | RRULE string |
|---|---|
| Weekly yoga every Tuesday | `FREQ=WEEKLY;BYDAY=TU` |
| Every other Friday | `FREQ=WEEKLY;INTERVAL=2;BYDAY=FR` |
| Last Saturday of every month | `FREQ=MONTHLY;BYDAY=-1SA` |
| First Friday of every month (e.g. "First Friday" art walk) | `FREQ=MONTHLY;BYDAY=1FR` |
| Annually on July 4 | `FREQ=YEARLY;BYMONTH=7;BYMONTHDAY=4` |
| Weekdays only summer program | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=20260901T000000Z` |
| Daily for 30 days (e.g. "30 days of yoga") | `FREQ=DAILY;COUNT=30` |
| Daily but skip Dec 24, 25 | `FREQ=DAILY` + `exdate=['2026-12-24', '2026-12-25']` |

The operator-edit UI (§7.3) provides a small structured form that emits valid RRULE strings — operator doesn't need to memorize RFC 5545 syntax.

### §3.7 DST + leap-day edge cases

`dateutil.rrule` natively handles:
- **DST transitions:** wall-clock-aware rules ("every Tuesday at 6pm Lake Havasu time") emit occurrences that move with DST. Arizona/Lake Havasu is in `America/Phoenix` which does NOT observe DST, so this is a non-issue locally. But events imported from other timezones (uncommon for LHC; defensive against scraped Vegas/SoCal events) get correct expansion.
- **Leap day Feb 29:** a `FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29` rule emits Feb 29 in leap years, skips non-leap. Documented edge case; not surfaced in operator UI.

Test coverage in `tests/test_phase9_recurrence.py`:
- DST-transition fixture (parameterized for Phoenix tz + non-Phoenix tz)
- Feb 29 leap-year fixture
- Open-ended recurrence + window-bounded expansion
- EXDATE applied correctly
- RDATE additions outside the rule

---

## §4 Capacity / availability OPTIONAL display

### §4.1 The honesty rule

Per master plan §8 OQ #12 + project principle: **only display capacity when venue publishes real data. NO manufactured scarcity** ("Only 3 spots left!" when we don't actually know).

Per §2.2 schema: `Event.capacity: Integer | None` defaults to NULL. The capacity-display rendering branch:

```python
# app/providers/queries.py — extend _event_status_line_for_card
def _event_capacity_label_for_card(event: Event) -> str | None:
    """Return capacity microcopy if event has honest capacity data,
    else None (card omits the capacity row entirely)."""
    if event.capacity is None:
        return None
    if not event.capacity_source:
        # Defensive: invariant violation, capacity set without source
        return None
    return f"Capacity {event.capacity} · via {_capacity_source_label(event.capacity_source)}"


_CAPACITY_SOURCE_LABELS = {
    "eventbrite": "Eventbrite",
    "venue_published": "venue",
    "operator_typed": "operator",
}
```

### §4.2 V1 ships with capacity = NULL everywhere

The only obvious sources of real capacity data are:
- Eventbrite API (deferred to V2 — scope creep into ticketing)
- Direct venue feeds with capacity (rare; LHC venues don't publish this)
- Operator manually types capacity (allowed but explicitly low-priority for V1)

**V1 Phase 9 ships with zero capacity rendering by default.** The schema columns exist; the rendering branch returns None when capacity is NULL; the operator-edit UI shows the field but defaults blank. This is the honest path.

### §4.3 V1.5 / V2 capacity expansion

When V2 lands Eventbrite integration, the scraper writes `capacity` + `capacity_source='eventbrite'`. The render branch lights up automatically. No template change required.

Operator-typed capacity is allowed in V1 for one specific case: events the operator is producing themselves (e.g. "Hava is hosting a community meetup") where capacity is genuinely known. Operator types capacity + sets `capacity_source='operator_typed'`. Honest but rare.

### §4.4 What NOT to display

| Anti-pattern | Why excluded |
|---|---|
| "Limited spots" without a real number | Manufactured scarcity per master plan §8 OQ #12 |
| "Almost full" derived from estimated venue size | We don't have venue capacity data; estimation IS fabrication |
| "X spots left" without a real source | Same problem |
| Sponsor-paid "featured event" pseudo-capacity ("Reserved seating") | Phase 11 sponsor mechanism is unrelated; capacity is a data field, not a marketing surface |

---

## §5 Event scraper subsystem

### §5.1 Five sources

Per master plan §4 Phase 9 deliverable list:

| Source | URL | Layer | Cadence | Existing client? |
|---|---|---|---|---|
| Chamber community calendar (LHC Chamber of Commerce) | https://www.havasuchamber.com/events (TBD; operator confirms exact endpoint in prereq) | Layer 2-3 (web scrape) | Daily 04:00 LHC local | NEW |
| Go Lake Havasu events | https://www.golakehavasu.com/events (TBD; operator confirms) | Layer 2-3 (web scrape) | Daily 04:30 LHC local | NEW |
| RiverScene Magazine event listings | https://riverscenemagazine.com (sitemap discovery) | Layer 2-3 (existing) | Daily 05:00 LHC local | YES — `app/contrib/river_scene.py` + `app/contrib/river_scene_pull.py` |
| City of Lake Havasu library calendar | Mohave County Library system; LHC branch event feed (TBD; operator confirms) | Layer 3 (likely no API; HTML scrape) | Weekly Sunday 03:00 LHC local | NEW |
| City of Lake Havasu parks-and-rec calendar | https://www.lhcaz.gov/parks-recreation (TBD; operator confirms) | Layer 3 | Weekly Sunday 03:30 LHC local | NEW |

**Why daily for Chamber/Go Lake Havasu/RiverScene + weekly for city library/parks-rec:**
- Chamber + Go Lake Havasu are aggregator surfaces with high event-add velocity (tourism + community calendar). Daily catches new events within ~24h of publication.
- RiverScene Magazine has slower velocity but the existing scraper runs daily already — staying with daily preserves the established cadence.
- City library + parks-rec have weekly or slower velocity. Daily scrapes would be wasted work + impolite to small city web infrastructure.
- Per Phase 8 design memo precedent: per-source cadence tuned to source freshness reality.

**Operator prereq:** before Phase 9b dispatches, operator confirms:
1. The 5 exact source URLs (some are inferred above; operator verifies)
2. The HTML structure stability of each (Chamber + Go Lake Havasu are highest-risk for HTML changes)
3. Whether any source has a structured feed (iCal, RSS, JSON) that's stable — prefer over HTML scraping when available
4. Robots.txt compliance — confirm scrape is permitted; identify any nofollow/noindex tags

`outputs/phase_9_operator_prereq_checklist.md` (new doc, separate from this design) captures the operator-side work.

### §5.2 File layout

```
app/events/
  __init__.py
  recurrence.py            # §3.2
  queries.py               # §3.4
  view_model.py            # event-specific view-model extensions (§10)
  scrapers/
    __init__.py
    base.py                # EventIngestClient base — extends BaseIngestClient with event-specific payload
    chamber.py             # Chamber community calendar
    go_lake_havasu.py      # Go Lake Havasu events
    river_scene_v2.py      # NEW thin wrapper around existing app/contrib/river_scene.py
                           # (keeps the existing module untouched; Phase 9 layers EventIngestClient interface on top)
    lhc_library.py         # City library
    lhc_parks_rec.py       # City parks-and-rec
  dedup.py                 # §6 multi-source dedup helpers

scripts/
  scrape_events.py         # entry point — dispatches to per-source scraper
                           # Usage: python -m scripts.scrape_events --source chamber
  expire_past_events.py    # §2.5 — daily status='expired' sweep
  recurrence_smoke.py      # one-off smoke for "expand all live events; surface any cap-exceeded warnings"
```

The `app/events/` path matches the `app/conditions/` (Phase 8) + `app/groups/` (Phase 6.4) + `app/home/` (Phase 6.5) feature-package convention.

### §5.3 EventIngestClient base shape

Extends Phase 4 `BaseIngestClient`:

```python
# app/events/scrapers/base.py
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any
from app.contrib.ingest_base import BaseIngestClient, EnrichedHit, EntityPayload, RawHit


@dataclass
class EventPayload(EntityPayload):
    """EntityPayload specialized for entity_type='event' ingest."""
    entity_type: str = "event"
    start_date: date | None = None
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    venue_name: str | None = None
    venue_entity_id: str | None = None  # populated by reconciler if venue matches existing entity
    rrule: str | None = None
    tags: list[str] = field(default_factory=list)
    event_url: str | None = None
    description: str = ""


class EventIngestClient(BaseIngestClient):
    """Event-source scraper base. Subclasses implement discover/enrich/dedupe_key/to_event_payload."""

    def to_entity_payload(self, hit: EnrichedHit) -> EventPayload:  # type: ignore[override]
        return self.to_event_payload(hit)

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        raise NotImplementedError
```

### §5.4 Per-source script entry point

```python
# scripts/scrape_events.py
# Usage:
#   python -m scripts.scrape_events --source chamber
#   python -m scripts.scrape_events --source go_lake_havasu
#   python -m scripts.scrape_events --source river_scene
#   python -m scripts.scrape_events --source lhc_library
#   python -m scripts.scrape_events --source lhc_parks_rec
#   python -m scripts.scrape_events --all --dry-run  # smoke

SOURCE_REGISTRY = {
    "chamber": ChamberClient,
    "go_lake_havasu": GoLakeHavasuClient,
    "river_scene": RiverSceneV2Client,
    "lhc_library": LhcLibraryClient,
    "lhc_parks_rec": LhcParksRecClient,
}
```

Pattern follows Phase 8's `scripts/fetch_external_conditions.py --source X` structure.

### §5.5 Write path: contributions queue, NOT direct event insert

**Critical decision:** scrapers do NOT write directly to `events` table. They write to the existing `contributions` table (`app/db/models.py:355-413`) with `entity_type='event'`. Operator approval → contribution flow creates the live `Event` row via `app/contrib/approval_service.py`.

**Why this seam:**
- Existing pattern from Phase 4 + RiverScene scraper (already works this way)
- Gives operator a single review queue (no parallel "scraper-staged events" UI)
- Approval flow already supports event-typed contributions (`Contribution.event_date`, `event_end_date`, `event_time_start`, `event_time_end` columns exist)
- Operator overrides post-approval are preserved by the `operator_override` flag (§2.2 + §7)

The `EventIngestClient.run(query)` produces `EventPayload` instances; the script wrapper converts each to a `ContributionCreate` Pydantic schema and inserts via existing contributions API.

### §5.6 Auto-approval for high-trust sources

To avoid operator-review-bottleneck for Chamber + Go Lake Havasu (which collectively will produce 30-50 events/week), Phase 9 ships a simple high-trust auto-approval rule:

```python
# app/contrib/approval_service.py — extend with event-source allowlist
AUTO_APPROVE_EVENT_SOURCES = {"chamber", "go_lake_havasu", "river_scene"}

def should_auto_approve(contribution: Contribution) -> bool:
    if contribution.entity_type != "event":
        return False
    if contribution.source not in AUTO_APPROVE_EVENT_SOURCES:
        return False
    if not contribution.url_title or not contribution.event_date:
        return False  # incomplete; needs review
    return True
```

City library + parks-rec stay manual-review for V1 (lower volume; operator audits the integration). Operator can flip these to auto-approve via env var `EVENT_AUTO_APPROVE_SOURCES` after a 2-week observation period.

### §5.7 Scrape execution + Railway deployment

Two model options:

| Model | Pros | Cons |
|---|---|---|
| **Per-source Railway scheduled service (RECOMMENDED — Phase 8 precedent)** | Failure isolation; per-source observability; cadence-mismatch friendly (daily Chamber vs weekly Library) | 5 Railway services for events; combined with 7 Phase 8 services = 12 background services. Cost negligible per Phase 8 §3.2 analysis. |
| Single all-source scheduled service | One service to manage; simpler dashboard | Failure isolation lost; Chamber outage delays Library scrape |

**Decision: per-source Railway scheduled service.** Matches Phase 8 design precedent + the operator-facing observability win is worth the service count.

### §5.8 Reusing existing RiverScene client

`app/contrib/river_scene.py` + `app/contrib/river_scene_pull.py` already exist (Phase 4.x). Phase 9 does NOT rewrite them. Instead, `app/events/scrapers/river_scene_v2.py` is a thin adapter:

```python
# app/events/scrapers/river_scene_v2.py
from app.contrib.river_scene_pull import run_pull
from app.events.scrapers.base import EventIngestClient, EventPayload


class RiverSceneV2Client(EventIngestClient):
    """Adapter wrapping the existing RiverScene pull into the EventIngestClient
    interface. Preserves the existing Phase 4.x contributions-queue write path."""

    source_name = "river_scene"

    def discover(self, query):  # delegates to existing module
        ...

    # etc — adapter pattern, no behavior change to the existing pull
```

This preserves Phase 4.x test coverage + existing operator approval workflow.

---

## §6 Multi-source dedup

### §6.1 The dedup problem

Chamber lists "Spring Festival 2026" at Aquatic Park on June 7. Go Lake Havasu lists "LHC Spring Festival" at Aquatic Park on June 7. RiverScene also lists it.

Without dedup: three duplicate cards on `/category/events` for the same real-world event.

### §6.2 Dedup key

Per the prompt: **`(venue_entity_id, start_datetime, normalized_title)` tuple as dedup key.** Phase 9 refines this to a fuzzy match:

```python
# app/events/dedup.py
from datetime import datetime, date
from rapidfuzz import fuzz
from app.db.models import Event


DEDUP_DATETIME_WINDOW_MINUTES = 30  # events within 30 min of each other on same day = potential dup
DEDUP_TITLE_FUZZY_THRESHOLD = 85    # token_sort_ratio threshold


def find_duplicate(
    db: Session,
    *,
    venue_entity_id: str | None,
    start_date: date,
    start_time_obj: time | None,
    normalized_title: str,
) -> Event | None:
    """Return existing Event row if a likely duplicate, else None."""
    candidates_q = db.query(Event).filter(Event.date == start_date)
    if venue_entity_id:
        candidates_q = candidates_q.filter(
            or_(
                Event.entity_id == venue_entity_id,
                # Venue link via provider too — defensive against ENTITY vs Provider mismatch
                Event.provider_id == venue_entity_id,
            )
        )
    candidates = candidates_q.all()

    target_dt = datetime.combine(start_date, start_time_obj) if start_time_obj else None

    for cand in candidates:
        # Title fuzzy match
        if fuzz.token_sort_ratio(cand.normalized_title, normalized_title) < DEDUP_TITLE_FUZZY_THRESHOLD:
            continue
        # Time proximity (within 30 min)
        if target_dt and cand.start_time:
            cand_dt = datetime.combine(cand.date, cand.start_time)
            if abs((target_dt - cand_dt).total_seconds()) > DEDUP_DATETIME_WINDOW_MINUTES * 60:
                continue
        return cand

    return None
```

### §6.3 Venue resolution

The `venue_entity_id` lookup uses Phase 4.x's `app/contrib/ingest_reconciler.py` pattern:

```python
def resolve_venue_entity_id(db: Session, venue_name: str, venue_address: str | None) -> str | None:
    """Try to match venue_name (+ optional address) to an existing Entity.
    Returns entity.id if a high-confidence match, else None.

    Uses: exact name match → fuzzy name + address proximity → google_place_id
    Reuses ingest_reconciler matching logic."""
```

If no venue match, the scraper still creates the event (no FK violation — `Event.entity_id` requires an entity, so a "venue placeholder" entity is created OR the event is rejected to contributions queue for operator-assigned venue). Recommend the latter: scraper-emitted events with unmatched venues land in contributions with a flag, operator manually links to the correct entity via dropdown.

### §6.4 On match — merge semantics

When `find_duplicate()` returns an existing Event row, the scraper does NOT overwrite. Instead:

1. Compare scraper-provided fields vs existing fields
2. For fields where scraper has data AND existing is empty (NULL), write the scraper data
3. For fields where existing has data + `operator_override=True`, scraper IGNORES (preserves operator's edit)
4. For fields where existing has data + `operator_override=False`, scraper UPDATES (refreshes from source)
5. Write a `field_history` row for each field changed
6. Bump `scraped_at` regardless (resets freshness band)

This is the "sustainability layer" pattern from Phase 5's manual recovery — the operator's hand-curated overrides survive scraper passes.

### §6.5 Timezone gotchas

Lake Havasu City is in `America/Phoenix` (no DST). All event times scraped are interpreted as Phoenix-local. If a source publishes in UTC (uncommon for community calendars), the scraper's per-source parser normalizes to Phoenix-local at parse time.

The `Event.start_time` column is `Time` (naive — no timezone). Phase 9 establishes the convention: **all `Event.date` + `Event.start_time` values are Phoenix-local wall-clock**. The `app/core/timezone.py` `LAKE_HAVASU_TZ` constant is the conversion source.

Tests in `tests/test_phase9_dedup.py` cover:
- Same event same day same time: match
- Same event same day 5 min apart: match (within 30-min window)
- Same event same day 45 min apart: no match (outside window — assume genuinely different events)
- Same title different venue: no match
- Similar title (token_sort 88) same venue same time: match (above 85 threshold)
- Similar title (token_sort 80) same venue same time: no match (below threshold)

---

## §7 Operator-curated vs scraper-sourced events

### §7.1 The conflict

Operator manually edits a scraper-sourced event ("the chamber spelled the venue name wrong; I'm fixing it"). Next day's scraper pulls the same event from Chamber's calendar with the misspelled venue. Without protection, the scraper would undo the operator's fix.

### §7.2 The mechanism: `operator_override` flag + per-field tracking

Per §2.2, `Event.operator_override: Boolean DEFAULT false`. Plus `field_history` rows (Phase 3 table) track per-field provenance.

**The rule:**

1. Operator edits a field via admin UI → set `operator_override=True` on the event row + write `field_history` with `source='operator'`
2. Next scrape pulls the same event (matched via §6 dedup)
3. Scraper's merge logic (§6.4) checks `operator_override`:
   - If `True`: scraper updates ONLY fields where `field_history` shows the most recent source for that field is NOT `'operator'`
   - If `False`: scraper updates freely (no operator edits to preserve)
4. Scraper always bumps `scraped_at` (freshness band stays green)

**Why a per-event Boolean + per-field history (vs purely per-field history):**
- The per-event flag is a cheap pre-filter: scraper can skip the field-history lookup for events the operator has never touched. ~95% of events stay `operator_override=False` and the merge is fast.
- The per-field history (already exists from Phase 3) handles the granular case for the 5% the operator has edited.

### §7.3 Operator-edit UI surface

New admin route `/admin/events/<id>/edit` mirrors the existing `/admin/contributions` flow:

```
┌─────────────────────────────────────────────┐
│ Edit Event: Spring Festival 2026             │
│ Source: chamber (auto-approved)              │
│ Last scraped: 2 days ago                     │
│                                              │
│ Title:        [Spring Festival 2026     ]    │
│ Date:         [2026-06-07              ]    │
│ Start time:   [10:00 AM               ]    │
│ End time:     [4:00 PM                ]    │
│ Venue:        [Aquatic Park ▼ entity link] │
│ Description:  [...textarea...        ]    │
│ RRULE:        [(none) ▼ pick recurrence ]   │
│ EXDATE:       [+ Add exception date]         │
│                                              │
│ Status:       (•) Live  ( ) Cancelled        │
│ If cancelled, reason:                        │
│   [textarea, only if status=cancelled]       │
│                                              │
│ ☑ Lock my edits — don't let scrapes overwrite │
│   (sets operator_override = true)            │
│                                              │
│ [ Save ]  [ Cancel ]                         │
└─────────────────────────────────────────────┘
```

The "Lock my edits" checkbox is the explicit `operator_override` toggle. Defaults checked when operator edits any field; operator can uncheck to allow scrapes to re-take.

### §7.4 Cancellation as operator action

`status='cancelled'` is an operator-only transition. Scrapers do NOT auto-cancel — a missing event in the next scrape is NOT a signal that the event was cancelled (could be a transient page error, source HTML change, etc.).

The scraper's missing-from-source behavior:
- Event exists in `events` table with `source='chamber'`, `status='live'`
- Tomorrow's Chamber scrape produces a list that doesn't include this event
- Scraper does NOTHING. The event stays live until either (a) operator manually cancels it OR (b) it auto-expires per §2.5 background job.

Rationale: false-positive cancellation (scraper bug → "all events cancelled") is much more harmful than a slightly-stale event lingering. Phase 13 / V1.5 may add a "stale-source" warning chip on the card if scraper consistently fails to refresh an event for >14 days, but auto-cancellation is explicitly out of scope.

---

## §8 "Things to Do" themed group landing

### §8.1 Scope

Per master plan §4 Phase 9: "Themed group landing for 'Things to Do' group (was deferred from Phase 6)."

Phase 6.4 shipped 4 themed groups (`eat-drink-group`, `health-fitness-group`, `on-the-water-group`, `home-auto-group`). Phase 9 adds a 5th: `things-to-do-group`.

### §8.2 Category bundle

**Operator decision-lock at Phase 9 wrapper authoring time. Recommended:**

| Category slug | Category name | Include? | Rationale |
|---|---|---|---|
| `events` (cat-2) | Events | YES | Core: things to do = events |
| `outdoors-parks-trails` (cat-7) | Outdoors, Parks & Trails | YES | Parks + golf + trails are core activities |
| `classes-sports-recreation` (cat-9) | Classes, Sports & Recreation | YES | Recurring classes + pickup sports |
| `on-the-water` (cat-3) | On the Water | NO | Already its own themed group (`on-the-water-group`); double-bundling creates confusion |
| `lodging-vacation-rentals` (cat-10) | Lodging | NO | Lodging is "where to stay", not "what to do" |
| Eat & Drink (cat-1) | Eat & Drink | NO | Already its own themed group |

**Recommended bundle: cat-2 + cat-7 + cat-9.** Operator confirms at dispatch time.

### §8.3 Themed group module extension

`app/groups/themed_groups.py` extended:

```python
THEMED_GROUPS: dict[str, list[str]] = {
    "eat-drink-group": ["eat-drink"],
    "health-fitness-group": ["health-wellness-care", "classes-sports-recreation"],
    "on-the-water-group": ["on-the-water"],
    "home-auto-group": ["home-property-services", "auto-rv-fuel"],
    "things-to-do-group": ["events", "outdoors-parks-trails", "classes-sports-recreation"],
}

_GROUP_LABELS["things-to-do-group"] = "Things to Do"
_GROUP_ONE_LINERS["things-to-do-group"] = (
    "Events, outdoor recreation, and classes — what to do around Lake Havasu."
)
_GROUP_ACCENTS["things-to-do-group"] = "warm"
```

The route `/group/things-to-do-group` is automatically picked up by the Phase 6.4 themed-group routes module (`app/api/routes/themed_groups.py`) — no new route code needed.

### §8.4 Card overlap with health-fitness-group

`classes-sports-recreation` is in BOTH `health-fitness-group` AND `things-to-do-group`. This is intentional + acceptable:
- A user browsing "Health & Fitness" sees fitness classes through the wellness lens
- A user browsing "Things to Do" sees fitness classes through the activities lens
- The same Hava card renders identically in both contexts

The themed-group interleaving in §9 makes this overlap surface different content (event-heavy in things-to-do, place-heavy in health-fitness).

---

## §9 Integrated stream: interleaving events + places

### §9.1 Phase 6.4 baseline

Phase 6.4 shipped themed-group landing pages that render an interleaved-ranked stream of unified Hava cards "across bundled categories". At Phase 6.4 ship time, the stream was entity-typed `commercial` + `place` cards (no events). The interleaving was per-`compute_card_rank` (Phase 6.3 `app/core/ranking.py`).

Phase 9 adds events to the eligible set.

### §9.2 The interleaving change

The themed-group landing route at `app/api/routes/themed_groups.py` (Phase 6.4) queries entities for the bundled categories. Phase 9 extends the query:

```python
def get_themed_group_card_stream(
    db: Session, group_slug: str, *, limit: int = 30
) -> list[HavaCardViewModel]:
    cat_slugs = get_categories_for_group(group_slug)

    # Entities (Phase 6.4 path)
    entity_ids = _entity_ids_for_categories(db, cat_slugs)

    # Events upcoming in the next 30 days (Phase 9 path)
    upcoming = events_in_window(
        db,
        window_start=date.today(),
        window_end=date.today() + timedelta(days=30),
        category_slug=None,  # multi-category via group; filter post-fetch
    )
    upcoming_event_entity_ids = [
        ev.entity_id for ev, _occ_date in upcoming
        if _event_category_in_set(ev, cat_slugs)
    ]

    # Combine + rank
    all_entity_ids = list(set(entity_ids + upcoming_event_entity_ids))
    cards = []
    for eid in all_entity_ids:
        vm = build_card_view_model(db, eid)
        if vm:
            cards.append((vm, _rank_score(db, eid, group_slug)))
    cards.sort(key=lambda pair: -pair[1])
    return [vm for vm, _ in cards[:limit]]
```

### §9.3 Ranking adjustment for interleaved streams

Events ranked alongside places need a fair scoring shape. Phase 9 extends `app/core/ranking.py`:

```python
# app/core/ranking.py extension
def compute_event_card_rank(
    *,
    event: Event,
    occurrence_date: date,
    now_temp_f: float = STUB_CURRENT_TEMPERATURE_F,
    distance_mi: float | None,
    user_in_boat_mode: bool = False,
) -> float:
    """Mirror compute_card_rank for events.

    Bias factors:
    - Imminence: today +30%, tomorrow +15%, this weekend +10%, this week +5%, else 0%
    - Distance (when reference point set): inverse-distance weight
    - Heat-aware (per Phase 6.3): events at indoor venues +20% when temp >= 100°F
    - Boat-mode: events at boat-access venues +10% when boat-mode active
    - Editorial: featured +25%
    """
    days_ahead = (occurrence_date - date.today()).days
    base = 1.0

    if days_ahead == 0:
        base *= 1.30
    elif days_ahead == 1:
        base *= 1.15
    elif days_ahead <= 7 and occurrence_date.weekday() >= 5:
        base *= 1.10
    elif days_ahead <= 7:
        base *= 1.05

    # heat + boat + distance modifiers reuse Phase 6.3 helpers...
    return base
```

This puts "tonight at 6pm" events near the top of a themed-group stream during high-activity hours (the user is likely browsing FOR something to do tonight) while still letting evergreen places (restaurants, etc.) compete for ranking against future-dated events.

### §9.4 Card variety capping

To prevent a single high-velocity event source (e.g. Chamber on a busy weekend) from dominating the stream, Phase 9 caps event cards at 40% of the visible stream:

```python
def _cap_event_share(cards: list[tuple[HavaCardViewModel, float]], max_event_pct: float = 0.40) -> list[...]:
    ranked = sorted(cards, key=lambda p: -p[1])
    output: list = []
    event_count = 0
    place_count = 0
    for vm, score in ranked:
        if vm.entity_type == "event":
            if event_count / max(1, len(output) + 1) >= max_event_pct:
                continue  # skip; preserve variety
            event_count += 1
        else:
            place_count += 1
        output.append((vm, score))
        if len(output) >= 30:
            break
    return output
```

40% threshold operator-tunable via env var `THEMED_GROUP_EVENT_CAP_PCT` (default 0.40).

### §9.5 Per-category page vs themed group

`/category/events` is event-only — no capping needed. `/category/classes-sports-recreation` and `/category/outdoors-parks-trails` are place-primary with event surfacing as a chip filter ("Show classes happening this week"). Themed group landing is the interleaved surface.

---

## §10 Event-specific freshness band + card grammar

### §10.1 Tighter decay curve

Phase 6.1 shipped freshness bands at `app/providers/queries.py:536` (`derive_freshness_band_from_updated_at`) keyed on `Entity.updated_at`:

| Band | Threshold (Phase 6.1) |
|---|---|
| green | < 30 days |
| amber | 30-90 days |
| red | > 90 days |

Per master plan §4 Phase 9: "Freshness anchor on scrape timestamp. Tighter decay curve than the entities default."

Phase 9 adds an event-specific helper:

```python
# app/providers/queries.py extension
EVENT_FRESHNESS_GREEN_DAYS = 7
EVENT_FRESHNESS_AMBER_DAYS = 21


def derive_event_freshness_band(event: Event, *, now: datetime) -> str:
    """Tighter decay curve for scraped events.

    Reads Event.scraped_at when populated (scraper-sourced); falls back to
    Entity.updated_at via the provider link when NULL (operator-curated)."""
    anchor = event.scraped_at
    if anchor is None:
        anchor = event.entity.updated_at if event.entity else event.created_at

    delta_days = (now - anchor).days
    if delta_days < EVENT_FRESHNESS_GREEN_DAYS:
        return "green"
    if delta_days < EVENT_FRESHNESS_AMBER_DAYS:
        return "amber"
    return "red"
```

### §10.2 Integration with `build_card_view_model`

The existing card builder at `app/providers/queries.py:723` reads:

```python
freshness = derive_freshness_band_from_updated_at(entity.updated_at, now=now_dt)
```

Phase 9 extends to:

```python
freshness = derive_freshness_band_from_updated_at(entity.updated_at, now=now_dt)
if entity.entity_type == "event" and event is not None:
    freshness = derive_event_freshness_band(event, now=now_dt)
```

The card's existing freshness dot (green/amber/red color) automatically picks up the new band — template doesn't change.

### §10.3 Status line color (already Phase 6.1)

`_event_status_line_for_card` at `app/providers/queries.py:666` already emits lake-blue status text for upcoming events ("Tonight at 6:00pm" / "This weekend" / etc.). Phase 9 verifies this works end-to-end + extends:

- Cancelled events: status text "Cancelled" in red (status_color = "red")
- Status text already returns red for events >7 days in past per existing logic ("Last week" red)
- For recurring events: status text shows the NEXT occurrence within the current view window, not the master row's date

### §10.4 Card variant: recurring events

Recurring events in the card stream surface their next-upcoming occurrence. The card-builder helper needs the occurrence date:

```python
def build_card_view_model_for_event_occurrence(
    db: Session,
    event_id: str,
    occurrence_date: date,
    *,
    now: Optional[datetime] = None,
) -> HavaCardViewModel | None:
    """Same as build_card_view_model but parameterized on a specific
    occurrence date — supports recurring events surfacing different
    occurrences in different views."""
```

The card itself doesn't structurally change; the status line text reflects the occurrence date.

### §10.5 Sponsor pill (Phase 11 deferred)

The `is_sponsored` field on `HavaCardViewModel` exists from Phase 6.1. For events in V1, `is_sponsored` always returns False (events aren't monetized yet — Phase 11 lands the sponsor mechanism on commercial entities first; event-typed sponsorship deferred to Phase 11.5 / V2). The card grammar already renders zero pill when False; no template change.

---

## §11 "What's on at this venue" region

### §11.1 Phase 6.5 anchor

Per master plan §4 Phase 6 + Phase 6.5 wrapper: `provider_profile.html` ships with an empty region anchor like:

```html
<!-- venue-events-region-anchor -->
{# Phase 9 fills this region with the venue's upcoming events #}
```

Phase 9 replaces the anchor with:

```html
<!-- venue-events-region-anchor -->
{% include 'components/venue_events_region.html' %}
```

### §11.2 The component

New `app/templates/components/venue_events_region.html`:

```jinja
{% if venue_events %}
<section class="venue-events-region">
  <h3 class="venue-events-region__heading">What's on at {{ provider_name }}</h3>
  <ul class="venue-events-region__list">
    {% for card in venue_events %}
      <li>{% include 'components/hava_card.html' with context %}</li>
    {% endfor %}
  </ul>
</section>
{% endif %}
```

If `venue_events` is empty, the section doesn't render — graceful collapse (per Phase 6.1 grammar discipline).

### §11.3 Query path

The provider profile route (`app/providers/router.py`) is extended:

```python
def _venue_events_for_profile(db: Session, provider: Provider, limit: int = 5) -> list[HavaCardViewModel]:
    """Return up to `limit` upcoming event cards tied to this venue."""
    venue_entity_id = provider.entity_id
    horizon_end = date.today() + timedelta(days=60)

    # Pre-filter: events linked to this venue (via Event.entity_id matching
    # the provider's entity OR via Event.provider_id direct link)
    candidates = (
        db.query(Event)
        .filter(Event.status == "live")
        .filter(
            or_(
                Event.entity_id == venue_entity_id,
                Event.provider_id == provider.id,
            )
        )
        .filter(
            or_(
                # non-recurring: future-dated within horizon
                and_(Event.is_recurring == False, Event.date.between(date.today(), horizon_end)),
                # recurring: pre-filter true; expansion handled below
                Event.is_recurring == True,
            )
        )
        .all()
    )

    flat = occurrences_in_window(candidates, window_start=date.today(), window_end=horizon_end)
    seen_event_ids: set[str] = set()
    cards: list[HavaCardViewModel] = []
    for event, occ_date in flat:
        if event.id in seen_event_ids:
            continue  # show recurring event only once (next occurrence)
        seen_event_ids.add(event.id)
        vm = build_card_view_model_for_event_occurrence(db, event.id, occ_date)
        if vm:
            cards.append(vm)
        if len(cards) >= limit:
            break
    return cards
```

### §11.4 Caching

The "What's on at this venue" region adds 1 query per provider-profile-page-render. At V1 traffic levels (~100-500 page views/day), this is acceptable un-cached.

If profiling at V1.5 shows this becomes a bottleneck, the recommended caching pattern is **process-local LRU cache with short TTL**:

```python
from functools import lru_cache
from time import time

# Tuple cache key (venue_entity_id, hour_bucket)
@lru_cache(maxsize=256)
def _cached_venue_events(venue_entity_id: str, hour_bucket: int) -> tuple[str, ...]:
    """Cache event IDs for this venue, bucketed by hour-of-day.
    hour_bucket = int(time() // 3600). New hour = cache miss = re-query."""
    ...
```

This pattern is rejected for V1 — adds complexity without proven need. Phase 13 reassesses.

**Invalidation on event create/update:** when an event's `entity_id` matches a venue's `entity_id`, OR when an event's `provider_id` is set/changed, invalidate the cache. If using LRU above, the invalidation seam is `_cached_venue_events.cache_clear()` on event-write. At V1 scale, the hourly bucket already provides near-realistime freshness.

### §11.5 Empty state

Operator decision: when a venue has zero upcoming events, render nothing (region collapses). The alternative — "No upcoming events at this venue. Add one →" CTA — is rejected for V1; venue claim flow (Phase 11) is the operator-event-add seam, not the profile page.

---

## §12 Category page chip filters + sort dropdowns

### §12.1 `/category/events` filters

Per master plan §4 Phase 9 — "date-aware filters (today / this weekend / next month / by date range)".

The category page module at `app/api/routes/category_pages.py` is extended for `events` slug. The `Chip` dataclass at line 38 + `CategoryPageConfig` at 43 already support chip variants. Phase 9 adds a third chip row for `events`:

```python
# Inside the events config entry
events_config = CategoryPageConfig(
    sub_trade_chips=(
        # Existing sub-trades from Phase 5.8 (event venues, live music, art galleries, etc.)
        Chip("venue", "Venues"),
        Chip("live_music", "Live music"),
        Chip("art_gallery", "Galleries"),
        Chip("museum", "Museums"),
        ...
    ),
    operational_chips=(
        # NEW date-aware chips
        {"slug": "today", "label": "Today"},
        {"slug": "this-weekend", "label": "This weekend"},
        {"slug": "this-week", "label": "This week"},
        {"slug": "next-month", "label": "Next month"},
    ),
    sort_default="chronological",
)
```

Query-string handling: `/category/events?when=today` filters to today's events; `/category/events?when=this-weekend` to Sat+Sun; etc.

### §12.2 `/category/classes-sports-recreation` filters

Per master plan §4 Phase 9 — "recurring schedules + age bands + drop-in vs registration filters".

The Phase 5.9-shipped category gets new chips:

```python
classes_sports_config = CategoryPageConfig(
    sub_trade_chips=(
        Chip("yoga", "Yoga"),
        Chip("pilates", "Pilates"),
        Chip("swim", "Swim"),
        Chip("pickleball", "Pickleball"),
        Chip("childcare", "Childcare"),
        Chip("youth_sports", "Youth sports"),
        Chip("adult_sports", "Adult sports"),
    ),
    operational_chips=(
        {"slug": "drop-in", "label": "Drop-in OK"},
        {"slug": "registration", "label": "Registration required"},
        {"slug": "kids", "label": "Kids (0-12)"},
        {"slug": "teens", "label": "Teens (13-17)"},
        {"slug": "adults", "label": "Adults (18+)"},
        {"slug": "55-plus", "label": "55+"},
    ),
    sort_default="closest_now",  # Phase 5.9 default — closest + drop-in available
)
```

Drop-in vs registration is a new entity attribute. Phase 9 extends `Entity.crowd_notes` JSON shape to optionally carry `{"drop_in_friendly": true|false}` — operator-typed during entity edits.

Age bands derive from the existing `Program.age_min` / `Program.age_max` columns (Phase 1A). Filter logic:

```python
def filter_by_age_band(entities: list, band: str) -> list:
    if band == "kids":
        return [e for e in entities if any(0 <= p.age_min and p.age_max <= 12 for p in e.programs)]
    if band == "teens":
        return [e for e in entities if any(13 <= p.age_min and p.age_max <= 17 for p in e.programs)]
    # etc
```

### §12.3 Sort dropdowns

`/category/events` adds a `chronological` sort option (default) — earliest occurrence first. Other sorts:
- `chronological` (default): next occurrence date ascending
- `closest_now`: nearest venue first (existing Phase 6.3 sort)
- `featured`: editorial picks first

`/category/classes-sports-recreation` inherits Phase 6.3's `closest_now` default, no new sort.

### §12.4 Pagination across virtual occurrences

Recurring events introduce a pagination question: if "weekly yoga" has 4 occurrences in next month, do they take 4 spots in the paginated stream or 1?

**Decision: 1 spot per recurring event in `/category/events`** (shows next-upcoming occurrence). The `/venue/<slug>` page is the surface where multiple occurrences of the same event might appear (V1.5 — V1 ships with deduplicated single-occurrence-per-event).

Pagination math: 50 events per page where each "event" = 1 logical event row (after dedup), not 1 expanded occurrence.

---

## §13 Chat integration

Phase 7 already wires chat tier-2/tier-3 to query the ENTITY catalog. Phase 9 makes events queryable in chat.

### §13.1 What changes in chat

The existing chat modules at `app/chat/tier2_db_query.py` + `tier2_handler.py` query Entity rows. Phase 9's change: `Entity.entity_type='event'` rows become first-class in chat results.

For event-specific queries ("what's happening tonight?"), the tier-2 layer extends with a date-aware predicate:

```python
# app/chat/tier2_handler.py extension
def detect_event_intent(query: str) -> dict | None:
    """Return {'when': 'today' | 'tonight' | 'this_weekend' | None} if
    query is event-flavored, else None."""
    q = query.lower()
    if any(k in q for k in ("tonight", "happening", "events", "what's on")):
        return {"when": "tonight" if "tonight" in q else "today"}
    if "this weekend" in q or "saturday" in q or "sunday" in q:
        return {"when": "this_weekend"}
    return None
```

When detected, the tier-2 query uses `events_in_window` (from §3.4) instead of generic entity search.

### §13.2 Cross-entity queries

Master plan §4 Phase 7 already covers this ("where can I take my dog for breakfast?" → dog-friendly restaurants AND dog parks interleaved). Phase 9 extends to event-mixed: "what's there to do with kids this weekend?" → events with age_band=kids AND parks with age_band=kids interleaved.

The interleaving logic mirrors §9.

### §13.3 Tier-3 LLM prompt

The LLM prompt at tier-3 gets a new preamble when event intent detected:

> "The user is asking about events. We have N upcoming events in the next 7 days. Surface them chronologically; mention venue name + time prominently."

This is a 1-line addition to the existing tier-3 prompt template.

---

## §14 What's NOT in Phase 9

Explicit non-scope list to prevent over-scoping:

| Excluded | Why | When (if ever) |
|---|---|---|
| Eventbrite / Meetup / Facebook Events API integrations | API access requires app review + costs; ticketing-API integration is V2 scope | V2 |
| Twilio SMS event reminders ("Yoga starts in 30 min") | Per Phase 8 §11 — SMS deferred to V1.5 | V1.5 |
| Operator booking flow / ticketing | Out of scope; Hava is a directory, not a marketplace | V2+ (separate strategic decision) |
| Capacity rendering with manufactured data | Per master plan §8 OQ #12 — honest-or-omit | Never |
| Per-event sponsorship (sponsored event cards) | Phase 11 lands sponsor mechanism on commercial entities first | Phase 11.5 / V2 |
| `event_traffic` alert wired (Phase 8 stub) | Was deferred from Phase 8; Phase 9 lands the Events surface so 9.5 can finally wire the alert | Phase 9.5 |
| Multi-day event detail expansion ("see all dates") | Card shows next occurrence; multi-occurrence drill-in is V1.5 | V1.5 |
| Calendar export (.ics file per event) | Reasonable V1.5 addition; out of scope for Phase 9 | V1.5 |
| User RSVP / "I'm going" tracking | Marketplace feature; Hava is directory | V2+ |
| Event detail page (separate URL `/events/<id>`) | The card links to `event_url` (the source URL) by default; dedicated detail page is V1.5 | V1.5 (the existing `_profile_url_for_card` returns `/events/<id>` but the route itself isn't shipped in Phase 9) |
| Operator scrape-monitoring dashboard | Sentry breadcrumbs + Railway service logs are the V1 surface | V1.5 |
| Auto-cancellation when source removes event | False-positive risk too high; operator-only cancel in V1 | Never (intentional design) |
| Row-expansion materialization for recurrence | At-query-time expansion is fast enough at V1 scale; materialize if profiling shows need | Phase 13 / V1.5 |
| Public / Civic Resources events sub-source | Library + Parks-Rec are 2 of the 5 sources already — that covers civic | — |
| Crowdsourced user-submitted events | Existing contributions queue supports this for events already; no new UI in Phase 9 | — |

---

## §15 Risk register

Top 5 risks for Phase 9, with mitigations.

### Risk 1 — Scraper brittleness against HTML structure changes (HIGH severity)

**Threat:** Chamber + Go Lake Havasu + RiverScene are HTML-scrape targets. Any of those sites changes their event-page template and the scraper breaks silently. The next-day cadence means stale event listings within ~24h of breakage; worse, no new events surface for days.

**Mitigation:**
- Sentry breadcrumbs (Phase 4.1 standard) for every scrape: success count, failure count, "parsed 0 events" alarm.
- Operator-facing weekly scrape-health summary email (Phase 9b stretch — or V1.5).
- Per-source `last_successful_scrape_at` field on a new `scraper_health` table (alternative: reuse `external_conditions_cache` shape since it has `last_error` + `error_count` — easier path).
- Robust HTML selector strategy: prefer schema.org `Event` microdata when present (most modern WordPress event plugins emit it); fall back to CSS selector only when microdata absent.
- Polite fail-fast on suspicious results: if scrape returns 0 events when last week returned 30, raise + alert rather than silently writing 0.

**Residual risk:** silent failure window of ~24h is acceptable. Critical failure (3+ days zero events) triggers operator-visible alert.

### Risk 2 — Recurrence math edge cases (MEDIUM severity)

**Threat:** RRULE expansion has well-known corner cases (DST transitions; leap years; BYWEEKDAY semantics across year boundaries; UNTIL vs COUNT exit conditions). A bug in `expand_event` causes wrong dates surfaced on cards → user shows up at "yoga at 6pm Tuesday" that didn't actually happen.

**Mitigation:**
- `dateutil.rrule` is the battle-tested library; we don't roll our own.
- Phase 9 test suite covers DST (parameterized Phoenix vs Pacific), Feb 29, year-boundary, UNTIL+COUNT combos.
- The expansion `cap=100` safety ceiling defends against pathological rules.
- Operator-edit UI emits valid RRULE strings only (no free-text RRULE editing); structured form prevents most error classes.
- Smoke script `scripts/recurrence_smoke.py` runs nightly against all live recurring events; logs any cap-exceeded or parse-error events for operator review.

**Residual risk:** an operator-typed RRULE-form combination we didn't anticipate produces a wrong expansion for a specific event. Mitigation: operator can edit individual occurrences via EXDATE; per-event correction is bounded.

### Risk 3 — Multi-source dedup edge cases (MEDIUM severity)

**Threat:** The `(venue_entity_id, start_datetime, normalized_title)` fuzzy match has both false-positive (merging genuinely different events) and false-negative (failing to merge same event with title drift) modes. False-positives are worse — operator's edits to event A get overwritten by scraper assuming event B is A.

**Mitigation:**
- 30-min datetime proximity window — same-venue same-day same-hour is the merge gate.
- Token-sort fuzzy ratio threshold 85 — tuned conservatively from Phase 5.3 + 5.4 NPI/AZ-ROC reconciler experience.
- All dedup decisions logged with structured breadcrumb; operator can audit weekly.
- Operator override flag (`operator_override=true`) is the safety net — once an operator touches an event, scraper cannot reverse the change.
- Edge case: same event published with venue spelling variant ("Aquatic Center" vs "LHC Aquatic Center"). Mitigation: venue resolution via Phase 4 reconciler with name normalization.

**Residual risk:** ~5% false-positive rate at launch; operator-facing dedup-audit log surfaces these for manual unmerge. Tunable thresholds in env vars `EVENT_DEDUP_TITLE_THRESHOLD` + `EVENT_DEDUP_DATETIME_WINDOW_MINUTES`.

### Risk 4 — Operator overhead per event copy-write / scrape-miss (MEDIUM severity)

**Threat:** Per master plan §7 risk #6: "schedule-heavy expansion refresh burden". If scrapers miss 30% of events, operator must manually add them via contribution queue. At 50-100 events/week target, even 30% miss = 15-30 events/week operator-typed = ~3-5 hours/week. Unsustainable.

**Mitigation:**
- Five sources (cross-pollination): if Chamber misses an event, Go Lake Havasu likely catches it.
- Auto-approval for high-trust sources (§5.6) cuts operator approval time from per-event review to weekly batch audit.
- Operator dashboard: scrape-health weekly summary surfaces which sources are missing the most.
- Manual-entry surface (contribute form for events) exists from Phase 4.x; remains the operator-add path.

**Residual risk:** at launch, expect ~5 hours/week operator-time on event curation. Acceptable per master plan §7 #6.

### Risk 5 — Scope creep into ticketing / event-discovery feature breadth (LOW-MEDIUM severity)

**Threat:** Once events are in the product, the temptation to add RSVPs, calendar export, Eventbrite ticket integration, push notifications, "my events" pages, social sharing — all justifiable individually, all add up to a "feature factory" V1.5 burnout.

**Mitigation:**
- Explicit V1.5/V2 exclusion list in §14.
- Phase 9 SHIP gate: only the four lanes (A + B + C + D) — anything else is V1.5+.
- Operator-facing weekly review with the master plan: any new event-feature ask is a V1.5 ticket, never a Phase 9 amendment.

**Residual risk:** strategic — not technical. Mitigation lives in operator + Cowork discipline, not code.

### Honorable mentions (lower-severity)

- **`scraped_at` race conditions** if 2 scrape services hit the same Event in quick succession. Mitigation: existing dedup catches the second; first-writer wins.
- **Recurring event cancellation surface** when operator wants to cancel a whole recurring series vs. one occurrence. Mitigation: operator-edit UI shows both options ("Cancel this occurrence only" → adds EXDATE; "Cancel entire series" → sets `status='cancelled'`).
- **Venue resolution gaps** when scraper-emitted event names a venue not yet in the Entity catalog. Mitigation: operator-resolution queue (venue-pending events surfaced in admin contributions UI with venue-link dropdown).
- **Alembic-collision risk** per the Phase 6.4 close-out gotcha — if Phase 9a + 9b are dispatched in parallel sessions, both try to chain off the same alembic head. Mitigation: Phase 9a's migration completes + ships before Phase 9b dispatches; sequential only.
- **`dateutil` version pin drift** could change rrule semantics. Mitigation: pin `python-dateutil>=2.8.2,<3` in requirements; pytest fixtures catch behavior changes on upgrade.

---

## §16 Success criteria

Per master plan §4 Phase 9: "Events appear correctly in category pages, themed groups, profile 'what's on' regions, and chat responses. RRULE recurrence handles weekly classes correctly. Schedule freshness band reflects scrape recency."

Concrete pass/fail criteria for Phase 9 close-out.

### §16.1 Event ENTITY + lifecycle acceptance (Phase 9a)

| # | Criterion | How to verify |
|---|---|---|
| E1 | `/category/events` renders ≥15 event cards | Browse `/category/events`; count rendered Hava cards (must use unified card grammar, not custom event chrome) |
| E2 | Event card status line uses lake-blue color per Phase 6.1 grammar | Inspect any event card; status line text e.g. "Tonight at 6:00pm" with `color: var(--lake-blue)` |
| E3 | Recurring weekly event surfaces next occurrence, not master row date | Create recurring yoga event with rrule=WEEKLY;BYDAY=TU; verify card shows "This Tuesday" not the master DTSTART date |
| E4 | EXDATE exception works | Add today to event's exdate; verify card no longer shows "Tonight" status |
| E5 | Cancelled event renders "Cancelled" + red status | Set event status='cancelled'; verify card |
| E6 | Past event auto-expires after 7 days | Trigger `expire_past_events.py` against fixture-dated past event; verify status flips to 'expired' |

### §16.2 RRULE + date-range query acceptance (Phase 9a)

| # | Criterion | How to verify |
|---|---|---|
| R1 | `events_in_window` returns correct events for window | Fixture: 3 events (2 in window, 1 outside); function returns 2 |
| R2 | RRULE expansion correctly produces occurrences | Fixture: weekly Tuesday rrule; query Tuesday-to-Tuesday window; expect 2 occurrences |
| R3 | EXDATE removes expected occurrences | Same fixture + EXDATE one of the Tuesdays; expect 1 occurrence |
| R4 | RDATE adds extra occurrences | Fixture + RDATE for a Wednesday in window; expect Tuesday + Wednesday |
| R5 | Open-ended rrule + window-cap expansion bounded | Fixture: daily rrule, no UNTIL; query 1-year window; expect 365 occurrences, no infinite loop |
| R6 | Cap-exceeded raises ValueError | Fixture: malicious daily rrule for 5 years (1825 occurrences); expansion with cap=100 raises |
| R7 | DST-aware expansion (parameterized Phoenix vs Pacific) | Phoenix tz: no DST; rule emits same wall-clock pre+post spring forward |

### §16.3 Scraper acceptance (Phase 9b)

| # | Criterion | How to verify |
|---|---|---|
| S1 | All 5 scrape services deploy on Railway + run cron schedules | Railway dashboard shows 5 services with cadence per §5.1 |
| S2 | Chamber scrape produces ≥10 events on first run | Dry-run + count `EventPayload` instances |
| S3 | Go Lake Havasu scrape produces ≥10 events on first run | Same |
| S4 | Multi-source dedup merges Chamber + Go Lake Havasu duplicate of same event | Fixture-injected: same event in both source feeds; dedup writes 1 Event row, not 2 |
| S5 | Operator override survives next scrape | Operator edits event title; scrape runs; verify title unchanged + `operator_override=true` preserved |
| S6 | Failed scrape doesn't break other sources | Manually break Chamber URL; verify Go Lake Havasu + RiverScene continue |
| S7 | Scrape writes to contributions queue, not directly to events | Verify scrape output appears in `/admin/contributions` queue for non-auto-approved sources |
| S8 | Auto-approved sources land directly as live events | Chamber + Go Lake Havasu + RiverScene scrape outputs visible immediately on `/category/events` |

### §16.4 Surface acceptance (Phase 9a + 9b)

| # | Criterion | How to verify |
|---|---|---|
| U1 | `/category/events` chip filter "today" works | Add today event + tomorrow event; click "Today"; only today shows |
| U2 | `/category/events` chip filter "this weekend" works | Same, with Saturday/Sunday events; "This weekend" chip surfaces them |
| U3 | `/category/classes-sports-recreation` renders cards with recurring schedule indication | Card status line: "Tuesdays at 6:00pm" for a recurring class |
| U4 | `/category/classes-sports-recreation` age band filter works | Kids chip filters to programs with age_max <= 12 |
| U5 | `/category/classes-sports-recreation` drop-in filter works | Drop-in chip filters to entities with crowd_notes.drop_in_friendly=true |
| U6 | `provider_profile.html` venue-events region renders for venues with events | Venue with 3 upcoming events shows 3 cards in "What's on" region |
| U7 | Venue-events region collapses gracefully when no events | Venue with 0 upcoming events: region not rendered, no empty-state copy |
| U8 | `/group/things-to-do-group` renders interleaved events + places | Cards visible mix `entity_type='event'` + `entity_type='commercial'` + `entity_type='place'` |
| U9 | Themed-group event-share cap honored | Stress-test with 50 events + 10 places; output stream ≤40% event cards |

### §16.5 Freshness band acceptance (Phase 9a)

| # | Criterion | How to verify |
|---|---|---|
| F1 | Scraper-sourced event freshness uses scraped_at, not entity.updated_at | Event with scraped_at = 5 days ago: freshness band = green (per 7-day threshold) |
| F2 | Event green/amber/red thresholds tighter than entity default | Fixture at 8 days old: band = amber (entity default would be green); fixture at 22 days old: band = red |
| F3 | Operator-curated event (NULL scraped_at) falls back to entity.updated_at | Fixture: event.scraped_at = NULL, entity.updated_at = 5 days ago: band = green (entity default 30-day threshold) |

### §16.6 Chat acceptance (Phase 9a)

| # | Criterion | How to verify |
|---|---|---|
| C1 | "what's happening tonight" returns event entities | Ask chat; tier-2 surfaces today/tonight's events |
| C2 | "events this weekend" returns weekend-occurrence events | Same; window correctly applied |
| C3 | Cross-entity query mixes events + places | "what to do with kids" — returns both events with kid age-band + entities like parks |

### §16.7 Operational acceptance

| # | Criterion | How to verify |
|---|---|---|
| O1 | Pytest stays green at +50-75 net-new tests | `pytest -q` exits 0; tests cover §16.1-16.6 + dedup + recurrence + scrapers |
| O2 | Alembic head migrates cleanly (additive migration) | `alembic upgrade head` on staging DB; head moves forward |
| O3 | All 6 new Railway services (5 scrapers + 1 expirer) deploy + run | Railway dashboard green |
| O4 | Sentry breadcrumbs `events.scrape_succeeded` + `events.dedup_match` visible | Inspect Sentry for events-categorized breadcrumbs |
| O5 | No N+1 queries on `/category/events` page render | Pytest fixture with 50 events; SQL count assertion <10 queries per render |

---

## §17 Effort estimate

Master plan §4 Phase 9 estimates "L (12-18 days dispatch). Event scraper subsystem is the longest sub-lane."

### §17.1 Phase 9a engineering (Event ENTITY + RRULE + Events category page + venue-events region)

| Sub-lane | Effort | Notes |
|---|---|---|
| Alembic migration (8 column additions + status CHECK + 4 indexes) | 0.5 day | Pattern from Phase 3.1; smaller than it sounds — all additive |
| `app/events/recurrence.py` (dateutil.rrule wrapper) | 1 day | Plus test coverage for edge cases (DST, EXDATE, RDATE, leap, cap) |
| `app/events/queries.py` (events_in_window + occurrences_in_window) | 0.5 day | Pure-function helpers; SQLAlchemy bog-standard |
| `_event_status_line_for_card` + `derive_event_freshness_band` + `build_card_view_model_for_event_occurrence` extensions | 0.5 day | Reuses Phase 6.1 helpers; small additions |
| `/category/events` chip filters + sort dropdown extensions | 1 day | Anchored edits to `app/api/routes/category_pages.py`; date-window parsing |
| `provider_profile.html` venue-events region + component + query | 1 day | New component + route extension + tests |
| `scripts/expire_past_events.py` + Railway service | 0.5 day | Simple sweep job + cron |
| `scripts/recurrence_smoke.py` + admin event-edit UI (cancellation, EXDATE) | 1 day | Admin form additions + smoke script |
| Tests (~30-45 net-new) | 2 days | Recurrence edge cases + venue-events query + category-page chip filters + freshness band |
| **Total Phase 9a engineering** | **8 days dispatch** | |

### §17.2 Phase 9b engineering (Scraper subsystem + Classes/Sports + Things-to-Do group + interleaving)

| Sub-lane | Effort | Notes |
|---|---|---|
| `app/events/scrapers/base.py` + EventIngestClient + EventPayload | 0.5 day | |
| Chamber scraper | 1 day | HTML-scrape, microdata-preferred; per-source HTTP + retry envelope |
| Go Lake Havasu scraper | 1 day | Same shape |
| RiverScene V2 adapter | 0.25 day | Thin wrapper around existing module |
| LHC library scraper | 1 day | |
| LHC parks-rec scraper | 1 day | |
| `app/events/dedup.py` + multi-source dedup tests | 1 day | rapidfuzz matching + fixture-rich test coverage |
| `scripts/scrape_events.py` + Railway service configs (×5) | 0.5 day | |
| `/category/classes-sports-recreation` chip filter extensions | 0.5 day | Age band + drop-in/registration chips |
| Things-to-Do themed group (`app/groups/themed_groups.py` extension + label dict) | 0.25 day | Trivial — Phase 6.4 routes auto-pick-up |
| Themed-group interleaving (events + places) + event-share cap | 1 day | Extend Phase 6.4 stream-builder; rank events alongside entities |
| Operator scrape-health monitoring (scraper_health table + admin view) | 1 day | Optional — can defer to V1.5; recommend ship V1 |
| Tests (~20-30 net-new) | 1 day | Scrapers + dedup + themed-group + interleaving |
| **Total Phase 9b engineering** | **9 days dispatch** | |

### §17.3 Combined Phase 9 (9a + 9b sequential)

**17 days dispatch.** Aligns with master plan's L (12-18 days). Recommend:
- Phase 9a = M (~8 days) — Event ENTITY + RRULE foundation + categories
- Phase 9b = M (~9 days) — Scrapers + Classes/Sports + Things-to-Do group + interleaving

Sequential dispatch only (no parallel) per the Phase 6.4 alembic-collision gotcha.

### §17.4 Operator-side workload

Beyond the prereq checklist (~2-4 hours documented at `outputs/phase_9_operator_prereq_checklist.md`):

| Activity | Time |
|---|---|
| Confirm 5 event-source URLs + HTML stability | ~1-2 hours |
| Confirm Things-to-Do group category bundle (cat-2 + cat-7 + cat-9 recommended) | ~30 min |
| Per-source robots.txt audit | ~30 min |
| Weekly event-curation post-launch (auto-approve audit + venue-resolution queue) | ~3-5 hours/week sustained |
| Operator edits to ~30-50 highest-priority recurring events (RRULE setup) | ~4-6 hours one-time |
| Cat-2 + cat-9 entity sub-trade taxonomy review | ~1 hour |
| **Total operator work, one-time** | **~8-12 hours** |
| **Total operator work, ongoing** | **~3-5 hours/week** |

The ongoing operator burden is the real cost. Per master plan §7 risk #6 — this IS the schedule-heavy expansion refresh burden the master plan flagged.

---

## §18 Sequencing + dispatch chain

### §18.1 Dependencies that must be true before Phase 9a dispatch

- Phase 6.4 SHIPPED at `96c915d` (themed groups + map view + boat-mode toggle) — CONFIRMED.
- Phase 6.5 SHIPPED (provider profile venue-events region anchor `<!-- venue-events-region-anchor -->` exists) — PENDING; Phase 6.5 wrapper is pre-positioned but not yet dispatched.
- Phase 7 SHIPPED (chat tier-2/tier-3 wired to ENTITY) — PENDING; Phase 7 currently in flight per `outputs/phase_7_recovery_dispatch_note.md`.
- Phase 8a SHIPPED (conditions panel + alerts; provides `current_temperature_f()` for event ranking heat bias) — PENDING; estimated late June 2026.

### §18.2 Dependencies that must be true before Phase 9b dispatch

- Phase 9a SHIPPED.
- Operator confirms 5 event-source URLs + robots.txt + HTML structure (prereq checklist).
- Operator confirms Things-to-Do group bundle.

### §18.3 Phase 9 dispatch wrapper SHA-patch slots

For both Phase 9a + 9b wrappers:

- `<<<PHASE_8_HEAD_SHA>>>` — Phase 8a's SHIP commit (Phase 9a dispatches against this base)
- `<<<PHASE_8_ALEMBIC_HEAD>>>` — alembic head after Phase 8a's migration
- `<<<PHASE_6_5_HEAD_SHA>>>` — venue-events anchor confirmation
- `<<<EVENT_SOURCE_URLS_LOCKED>>>` — operator confirms 5 source URLs (Phase 9b only)
- `<<<THINGS_TO_DO_GROUP_BUNDLE>>>` — operator-locked category list for things-to-do-group (Phase 9b only)
- `<<<EVENT_AUTO_APPROVE_SOURCES>>>` — operator-locked allowlist (default: chamber + go_lake_havasu + river_scene)

### §18.4 Suggested commit batching

Phase 9a likely splits into 4-5 commits:

1. **Schema + lifecycle.** Migration + `Event.status` CHECK extension + indexes + tests.
2. **Recurrence helpers.** `app/events/recurrence.py` + `app/events/queries.py` + tests.
3. **Card grammar extensions.** `_event_status_line_for_card` extensions + `derive_event_freshness_band` + `build_card_view_model_for_event_occurrence` + tests.
4. **Category page chip filters + venue-events region.** Anchored edits to `category_pages.py` + new `venue_events_region.html` component + tests.
5. **Admin event-edit UI + expirer script + close-out.** RRULE-form + EXDATE add UI + `expire_past_events.py` + STATE.md update.

Phase 9b splits into 5-6 commits:

1. **Scraper base + first scraper (Chamber).** `EventIngestClient` + Chamber + tests.
2. **Remaining scrapers (Go Lake Havasu + RiverScene adapter + LHC library + LHC parks-rec).** Per-source modules + tests.
3. **Multi-source dedup.** `app/events/dedup.py` + tests.
4. **Classes/Sports/Recreation chip filters.** Age band + drop-in chips.
5. **Things-to-Do themed group + interleaving.** Themed group registry extension + interleaving extension + event-share cap + tests.
6. **Scrape-health monitoring + close-out.** Optional scraper_health table + admin view + STATE.md update.

---

## §19 Summary

Phase 9 lands the schedule-heavy expansion the master plan §4 deferred from Phase 5 — Events + Classes/Sports/Recreation as first-class ENTITY surfaces with RRULE-based recurrence handling, a 5-source event scraper subsystem, multi-source dedup, operator-curated vs scraper-sourced merge semantics with the manual-recovery + sustainability layer pattern, integrated themed-group streams (Things-to-Do landing), and the "What's on at this venue" region that fills the Phase 6.5-shipped anchor.

Three architectural decisions are load-bearing:

1. **At-query-time RRULE expansion**, not row-expansion, with rule + exdate + rdate stored inline on `Event`. Simpler edit semantics, simpler storage, fast enough at V1 scale; rejects materialization until profiling proves need.
2. **Contributions-queue write path for scrapers**, not direct event-table writes. Reuses the Phase 4.x review surface + auto-approval allowlist for high-trust sources (Chamber + Go Lake Havasu + RiverScene); city library + parks-rec stay manual-review.
3. **Per-event `operator_override` flag + `field_history` per-field provenance** as the sustainability-layer pattern preventing scraper-undo of operator edits.

Two phases recommended (9a + 9b sequential, not parallel — alembic-collision gotcha from Phase 6.4). 9a = Event ENTITY + RRULE + Events category + venue region (~8 days). 9b = scrapers + Classes/Sports + Things-to-Do group + interleaving (~9 days). Combined ~17 days, aligning with master plan's L estimate.

Capacity rendering ships disabled by default per master plan §8 OQ #12 — schema columns exist (`capacity` + `capacity_source`) but render branch returns None when NULL. V1 ships with zero capacity display until V2 lands Eventbrite-class real data sources.

Critical risks: scraper brittleness against source HTML changes (Sentry monitoring + microdata-preferred selectors + fail-fast on zero-event scrapes); recurrence edge cases (dateutil.rrule battle-tested + smoke script nightly); dedup edge cases (operator override safety net); operator overhead (~3-5 hours/week sustained — known risk per master plan §7 #6); scope creep into ticketing (explicit V14 exclusion list).

What Phase 9 explicitly does NOT ship: Eventbrite/Meetup integrations (V2), Twilio SMS reminders (V1.5), booking/ticketing (V2), per-event sponsorship (V2 / Phase 11.5), `event_traffic` alert wiring (Phase 9.5), event detail page route (V1.5), calendar export (V1.5), user RSVPs (V2), row-expansion materialization (Phase 13).

---

*Authored by Cowork plan-agent at the post-`616fd8b` design-pre-position session (2026-05-20). Pre-positioned during Cursor's Phase 6.4 close-out + Phase 7 recovery + alembic-collision gotcha draft work, against an estimated dispatch window of mid-July 2026 after Phase 8a + 8b ship. Input to the future Phase 9a + 9b dispatch wrappers; SHA-patch slots in §18.3 fill at wrapper authoring time. Sequential dispatch only — no parallel sessions per the Phase 6.4 alembic-collision lesson.*

---

### Critical Files for Implementation

- `C:\Users\casey\projects\havasu-chat\app\db\models.py` (lines 166-246 — `Event` table; Phase 9 adds 8 columns + status CHECK + 4 indexes via additive migration)
- `C:\Users\casey\projects\havasu-chat\app\providers\queries.py` (lines 536, 666-696, 723-805 — `derive_freshness_band_from_updated_at` + `_event_status_line_for_card` + `build_card_view_model`; Phase 9 extends with `derive_event_freshness_band` + event-occurrence variant)
- `C:\Users\casey\projects\havasu-chat\app\contrib\ingest_base.py` (BaseIngestClient + EntityPayload; Phase 9 extends to `EventIngestClient` + `EventPayload` at new `app/events/scrapers/base.py`)
- `C:\Users\casey\projects\havasu-chat\app\groups\themed_groups.py` (lines 1-95 — themed group registry; Phase 9 adds `things-to-do-group` entry)
- `C:\Users\casey\projects\havasu-chat\app\api\routes\category_pages.py` (lines 38-101, 245-275 — `CategoryPageConfig` + chip filter dispatch; Phase 9 extends events + classes-sports-recreation chip rows and adds date-window query parsing)

---

### One-paragraph summary

I produced a ~750-line Phase 9 architectural design document covering all 11 requested deliverables — Event ENTITY surface fully wired through the unified Hava card grammar with full lifecycle states ('draft' / 'live' / 'cancelled' / 'expired'), RRULE-based recurrence using `dateutil.rrule` with at-query-time expansion (rejecting row-expansion at V1 scale; rationale + tradeoffs detailed), recurrence exceptions stored as RRULE EXDATE inline on the Event row (rejecting a separate exceptions table; audit via existing `field_history`), a 5-source event scraper subsystem at `app/events/scrapers/` reusing the Phase 4 `BaseIngestClient` pattern with per-source Railway scheduled services (daily for Chamber/Go Lake Havasu/RiverScene; weekly for LHC library/parks-rec), multi-source dedup via fuzzy `(venue_entity_id, start_datetime, normalized_title)` matching with 30-min window + 85 token-sort threshold, operator-curated vs scraper-sourced merge semantics via the `operator_override` flag + `field_history` per-field provenance (Phase 5 manual-recovery + sustainability-layer pattern), tighter event-specific freshness decay (green <7d / amber 7-21d / red >21d) reading from new `scraped_at` column, date-aware chip filters on `/category/events` (today / this weekend / next month / custom range) and age-band + drop-in/registration filters on `/category/classes-sports-recreation`, "What's on at this venue" region filling the Phase 6.5 anchor, integrated themed-group streams interleaving events + places with 40% event-share cap, new Things-to-Do themed group bundling cat-2 + cat-7 + cat-9, capacity rendering NULL-default per master plan §8 OQ #12 (schema columns exist but render branch returns None — no manufactured scarcity), recommended Phase 9a/9b split (RRULE foundation + categories vs scrapers + interleaving; sequential only per Phase 6.4 alembic-collision lesson), top-5 risk register (scraper HTML brittleness, recurrence math edge cases, multi-source dedup false-positives, operator overhead ~3-5 hours/week sustained, scope creep into ticketing), concrete pass/fail acceptance criteria across 6 surfaces, refined effort estimate of 17 dispatch days (9a=8 + 9b=9) aligning with master plan's L estimate plus ~8-12 one-time operator hours, and explicit V1.5/V2 exclusion list (Eventbrite/Meetup APIs, Twilio SMS event reminders, booking/ticketing, per-event sponsorship, `event_traffic` alert wiring to Phase 9.5, event detail page route, calendar export, user RSVPs, row-expansion materialization). Since I was in READ-ONLY planning mode and could not Write the file directly to `outputs/phase_9_architecture_design.md`, the document is delivered above as my reply text for the user to save.
