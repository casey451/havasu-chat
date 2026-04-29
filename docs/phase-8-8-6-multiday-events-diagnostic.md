# Multi-day events diagnostic — read-only

**Context:** Phase 8.8.6 step 1+ session. Catalog populated on deployed (114 events including 71 RiverScene). User concern: multi-day events may not register properly. This document diagnoses storage, approval, retrieval, and deployed data — no code changes or fix proposals.

**Check 3 note:** The embedded query used the same SQLAlchemy logic as the original inline `railway run python -c` snippet; where PowerShell made inline `-c` unreliable, a temp script under `%TEMP%` was used with `PYTHONPATH` set to the project root. Output was non-empty.

---

## Check 1 — Parser and `normalize_to_contribution`

### 1) `RiverSceneEvent` for multi-day

`RiverSceneEvent` is a dataclass with explicit `start_date` and `end_date` (plus times, description, etc.):

```33:48:app/contrib/river_scene.py
@dataclass
class RiverSceneEvent:
    """Normalized event parsed from a RiverScene event detail HTML page."""

    title: str
    url: str
    start_date: date
    end_date: date
    start_time: time_type
    end_time: time_type
    description_html: str
    venue_name: str | None
    venue_address: str | None
    organizer: str | None
    category_slugs: list[str]
    raw: dict[str, Any] = field(default_factory=dict)
```

`fetch_and_parse_event` sets `end_d` from the table’s “End Date”, or falls back to `start_d`:

```285:299:app/contrib/river_scene.py
    labels = _table_label_map(table)
    start_raw = labels.get("Start Date")
    start_d = _parse_us_date(start_raw or "")
    ...
    end_raw = labels.get("End Date")
    end_d = _parse_us_date(end_raw) if end_raw else start_d
    if end_d is None:
        end_d = start_d
    if end_d < start_d:
        end_d = start_d
```

### 2) `normalize_to_contribution` → `ContributionCreate`

- There is **one** contribution per parsed page.
- `event_date` is **`rse.start_date` only**; there is no `event_end_date` on the create payload.
- The multi-day range is only reflected in **`submission_notes`**, via `_format_date_heading` (e.g. “June 10–12, 2026”).

Relevant code:

```336:386:app/contrib/river_scene.py
def normalize_to_contribution(rse: RiverSceneEvent) -> ContributionCreate:
    """
    Map a :class:`RiverSceneEvent` to :class:`ContributionCreate` for the review queue.

    The ``event_date`` / ``event_time_start`` / ``event_time_end`` fields mirror the source;
    the multi-day range is also spelled out in ``submission_notes`` for operators.
    """
    ...
    date_line = _format_date_heading(rse.start_date, rse.end_date)
    ...
    return ContributionCreate(
        entity_type="event",
        submission_name=rse.title[:200],
        submission_url=su,  # type: ignore[arg-type]
        submission_notes=notes,
        event_date=rse.start_date,
        event_time_start=rse.start_time,
        event_time_end=et_end,
        source="river_scene_import",
        unverified=False,
    )
```

**Summary:** Not one row per day from the parser; not a DB column for end date on the contribution; the end date is in **notes text**, not in structured `event_date` / approval fields.

### 3) Tests in `tests/test_phase8_10_river_scene.py`

- `test_fetch_and_parse_multi_day_event`: asserts `start_date` / `end_date` on `RiverSceneEvent` (e.g. Desert Storm Apr 22–25).
- `test_normalize_multi_day`: asserts the notes line contains a range like `Date: June 10–12, 2026` (en-dash in source).
- `test_normalize_single_day`: asserts a single-day `Date:` line has no “–” in that line.

---

## Check 2 — Approval path and `Event`

### 1) `Event` model date fields

Single calendar **`date`**, not an end date or list:

```82:90:app/db/models.py
class Event(Base):
    __tablename__ = "events"
    ...
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
```

### 2) `approve_contribution_as_event`

Builds `EventCreate` with **`date=edited_fields.date`** (one day). No multi-day handling:

```192:207:app/contrib/approval_service.py
    ec = EventCreate(
        title=edited_fields.title.strip(),
        date=edited_fields.date,
        start_time=edited_fields.start_time,
        end_time=edited_fields.end_time,
        location_name=edited_fields.location_name.strip(),
        description=edited_fields.description.strip(),
        event_url=edited_fields.event_url.strip(),
        contact_name=None,
        contact_phone=None,
        tags=list(tags or []),
        is_recurring=is_rec,
        source=event_source,
        status="live",
        created_by=created_by,
    )
```

### 3) `EventApprovalFields`

Only **`date`** (singular) — no end-date field:

```87:96:app/schemas/contribution.py
class EventApprovalFields(BaseModel):
    """Operator-edited fields when approving an event contribution."""

    title: str = Field(min_length=3)
    description: str = Field(min_length=20)
    date: date
    start_time: time
    end_time: time | None = None
    location_name: str = Field(min_length=3)
    event_url: str = Field(min_length=1)
```

End-date capability in the approval struct is **not present**.

---

## Check 3 — Deployed DB (read-only query)

### Raw output

```
=== RiverScene events with duplicate titles ===
  2x: Charlie And The Chocolate Factory At Grace Arts Live
  5x: Legends Tattoo Show 2026 Hosted by Lakeside Tattoo Art Collective
  37x: Lake Havasu Farmers Market

=== Sample 5 RiverScene events with their dates ===
  2026-04-24 | Charlie And The Chocolate Factory At Grace Arts Live
  2026-04-25 | Havasu 95 Speedway Night of Destruction!!! Get it In Gear St
  2026-04-25 | Lake Havasu Farmers Market
  2026-04-26 | Charlie And The Chocolate Factory At Grace Arts Live
  2026-04-26 | Mommy and Me, Mother's Day Tea

=== Known multi-day event lookup: Won Bass Havasu ===
  id=edd1b709 | 2026-05-07 | Won Bass Havasu

=== Pro Watercross (multi-day per RiverScene calendar) ===
  id=5d34f3ac | 2026-05-08 | Pro Watercross Road to Havasu
```

### Observations

- **Won Bass Havasu:** a **single** `events` row dated **2026-05-07** (no May 8 / May 9 rows from this title probe).
- **Pro Watercross:** a **single** row on **2026-05-08**.
- **Duplicate `title` groups** (2x / 5x / 37x): multiple `Event` rows share the same title (weekly market, repeated listings, re-imports, etc. — not by itself “multi-day as one row per day” without further joins).

---

## Check 4 — Chat retrieval (Tier 2 + search base query)

### Effective window and `WHERE` in `_query_events`

Window resolution maps `date_exact` to a single day `[d, d]`:

```253:265:app/chat/tier2_db_query.py
def _resolve_effective_event_window(
    filters: Tier2Filters, ref: date
) -> tuple[date | None, date | None]:
    """Inclusive event date window. ``(ref, None)`` means from ``ref`` forward (unbounded)."""
    if filters.date_start is not None or filters.date_end is not None:
        return filters.date_start, filters.date_end
    if filters.date_exact is not None:
        d = filters.date_exact
        return d, d
    ...
```

Core filter: **`Event.date` between `lower` and `win_end` (inclusive)** — no `end_date` on the model, and no “event spans this day” logic:

```523:525:app/chat/tier2_db_query.py
    q = select(Event).where(Event.status == "live", Event.date >= lower)
    if win_end is not None:
        q = q.where(Event.date <= win_end)
```

### `_base_future_events_query` in `app/core/search.py`

Same idea: `Event.date` in `[date_context["start"], date_context["end"]]` or `Event.date >= today`:

```416:424:app/core/search.py
def _base_future_events_query(db: Session, date_context: dict[str, date] | None) -> Any:
    today = date.today()
    if date_context:
        query = db.query(Event).filter(
            and_(Event.date >= date_context["start"], Event.date <= date_context["end"])
        )
    else:
        query = db.query(Event).filter(Event.date >= today)
    return query
```

For a **single-day** user query, the event must land with **`Event.date` inside that day’s window**. An event stored only on the **start** day of a real multi-day run is **not** returned for a query scoped to a **middle** day.

The `a <= e.date <= b` logic in `_time_bucket_first_hits` (same file) still keys off the single `Event.date` per row when bucketing broad windows; it does not parse span from `description`/`submission_notes`.

---

## Summary answers

1. **Storage shape for multi-day events (RiverScene path)**  
   - Parser: one `RiverSceneEvent` with `start_date` and `end_date`.  
   - Contribution: one row, `event_date` = start only; range in `submission_notes`.  
   - `Event`: one row, `date` = that start day; no catalog `end_date` column.  
   - Not one structured row per calendar day in the current ingest/approval path. Duplicate same-title rows on deployed can come from other causes (e.g. recurring market).

2. **Is there a real bug?**  
   **Yes, as a retrieval / product issue:** with single-day `Event.date` and no span in the query, a true multi-day event represented only on its **start date** will be **missed** for user intents that target a **middle** (or, depending on end semantics, end) day. Deployed **Won Bass Havasu** (single row **2026-05-07**) is consistent with missing May 8–9 **if** the product expectation is that those days return that festival.

3. **What deployed data looked like**  
   - Duplicate-title clusters exist (2 / 5 / 37).  
   - **Won Bass:** one row, **2026-05-07**.  
   - **Pro Watercross:** one row, **2026-05-08**.

---

*Diagnostic only. No code changes or fix proposals in this document.*
