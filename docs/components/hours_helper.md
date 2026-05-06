# hours_helper

`app/contrib/hours_helper.py` (~144 lines)

## Purpose

Bridge **Google Places `regular_opening_hours.periods`** JSON into a **Tier-2–friendly structured hours dict** (`providers.hours_structured`) and expose **`is_open_at`** for **OPEN_NOW–style** queries using **Lake Havasu City local wall time** (`America/Phoenix`, fixed UTC−7 fallback when **`zoneinfo`** unavailable).

## Public surface

**`LAKE_HAVASU_TZ`** — **`ZoneInfo("America/Phoenix")`** when **`tzdata`** is present; otherwise **`timezone(timedelta(hours=-7))`** (no DST; matches Phoenix policy).

**`places_hours_to_structured(places_regular_opening_hours: dict) -> dict`** — Converts Places periods into:

```python
{"monday": [{"open": "HH:MM", "close": "HH:MM"}, ...], ...}
```

Weekday keys match Tier 2 / program schedule naming (**`monday` … `sunday`**). Returns **`{}`** on malformed input, missing periods, or empty periods.

**`is_open_at(hours_structured: dict, as_of: datetime) -> bool`** — **`True`** iff **`as_of`** (naive interpreted as Phoenix, aware converted to Phoenix) falls **inclusive** inside any segment for that weekday.

## Inputs and outputs

**`places_hours_to_structured`**

- Walks **`periods`** list; each period must have **`open`** dict with integer **`day`** (Google convention 0=Sunday … 6=Saturday).
- **Same open/close day:** single segment **`open_s`–`close_s`** on that weekday key.
- **Open without close:** treated as **`00:00`–`23:59`** on open day (“24/7 anchor” heuristic).
- **Different open/close day:** **overnight split** — segment **`open_s`–`23:59`** on open day, **`00:00`–`close_s`** on close day (docstring rationale: keep each weekday bucket same-day only).

**`is_open_at`**

- Resolves weekday via **`datetime.weekday()`** Monday=0 mapping to lowercase keys.
- Compares **`cur = f"{hour:02d}:{minute:02d}"`** string-wise to segment bounds (**lexicographic HH:MM works for 00–23 hours**).

## Internal structure

- **`_GOOGLE_DAY_TO_KEY`** / **`_PYTHON_WEEKDAY_TO_KEY`** — Static translation tables.
- **`_hm(point)`** — Extract **`hour`/`minute`** from Places point dict → **`HH:MM`** string.
- **`_append_segment`** — Append-open-list pattern on output dict.

## Conventions

**Inclusive close minute.** Module docstring states closing time is **inclusive** (`open <= cur <= close`). Changing this affects Tier 2 OPEN_NOW semantics.

**Fallback timezone.** Arizona no-DST assumption baked into timedelta fallback — acceptable for Lake Havasu product scope.

## Known limitations

**String clock comparison** — No explicit parsing to minutes-since-midnight; ambiguous if future adds seconds (current contract is HH:MM only).

**Places malformed periods skipped silently** — Invalid dicts **`continue`** the loop; partial conversion possible.

**No holiday / special-hours exceptions** — Purely periodic weekly structure.

## Configuration

None at module level; **`tzdata`** presence affects **`LAKE_HAVASU_TZ`** quality on exotic hosts.

## Related

**Direct callers:**

- **`app/contrib/approval_service.py`** — **`places_hours_to_structured`** when approving providers with Places JSON.
- **`app/chat/tier2_db_query.py`** — **`is_open_at`** on **`providers.hours_structured`** for OPEN_NOW gating (see module docstring reference).

**Tests:** **`tests/test_hours_helper.py`**.

**Cross-ref:** **`docs/components/places_client.md`** — supplies **`regular_opening_hours`** blobs consumed here.
