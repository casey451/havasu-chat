# Phase 4.2 — Completion summary (for review)

## Pre-flight checks

| Check | Result | Notes |
|-------|--------|--------|
| Check 1 (`Tier2Filters` schema) | **PASS** | Ten fields only, types/defaults/constraints match 4.1 contract; validators for `time_window` + `day_of_week` unchanged. |
| Check 2 (parser prompt few-shots) | **PASS** | All eight query strings present verbatim in order in `prompts/tier2_parser.txt` (lines 25–46). |
| Check 3 (4.1 commit `9a30909` scope) | **PASS** | Stat shows only the four new files (`tier2_parser.py`, `tier2_schema.py`, `tier2_parser.txt`, `test_tier2_parser.py`), no edits to existing production files. |

---

## Schema discovery (catalog → filters)

**Tables (`app/db/models.py`):**

- **`providers`**: `provider_name`, `category`, `address`, `phone`, `hours` (free text), `description`, flags `draft`, `is_active`, `verified`. No structured age or per-day schedule.
- **`programs`**: `title`, `description`, `activity_category`, `age_min` / `age_max` (nullable ints), `schedule_days` (JSON list of lowercase weekday strings, e.g. `["saturday"]`), `schedule_start_time` / `schedule_end_time` (HH:MM strings), `location_name`, `location_address`, `tags` (JSON list), `provider_id`, `draft`, `is_active`.
- **`events`**: `title`, `description`, `date` (`Date`), `start_time` / `end_time`, `location_name` / `location_normalized`, `tags` (JSON), `status` (`live` used), `provider_id` optional.

**Filter mapping implemented:**

| Filter | Approach |
|--------|----------|
| `entity_name` | `ILIKE` on provider name/description; program title/provider_name; event title/description. |
| `category` | `ILIKE` on typed columns where present; plus Python pass on JSON `tags` and free-text fields. |
| `age_min` / `age_max` | Overlap logic on program `age_min`/`age_max`; programs with no age pass through; providers excluded when any age bound set (no age columns). |
| `location` | `ILIKE` on provider `address`; program `location_name` / `location_address`; event `location_name`. |
| `day_of_week` | Events: Python filter by weekday name of `Event.date`. Programs: intersection with `schedule_days`. Providers: excluded when only day-of-week is set (no structured hours). |
| `time_window` | Resolved with server `date.today()` via `tier2_db_query._today()` (patchable in tests): `today`, `tomorrow`, `this_week`, `this_weekend`, `this_month`, `upcoming` (from today, no upper bound). Events filtered on `Event.date`. Programs/providers omitted when **only** `time_window` is set (no other dimensions) — date-centric queries stay on events. |
| `open_now` | **Unmapped:** logs a warning and returns **no rows** so Tier 3 handles it. |

**Row dict shape:** Each dict has `type` (`provider` \| `program` \| `event`), `id`, `name`, plus a small set of extra keys (dates, location, truncated description, tags, schedule snippet, etc.) kept short for formatter context.

**Tests:** `monkeypatch` / `pytest.MonkeyPatch` on `tier2_db_query._today` for deterministic windows (no `conftest.py` change).

---

## Verification

- **Pytest:** `python -m pytest -q` — **521 passed** (493 baseline + 28 new Tier 2 tests).
- **Track A battery:** `python scripts/run_query_battery.py` — **116 / 120** matches.

---

## Files created (Phase 4.2)

| File | Role |
|------|------|
| `app/chat/tier2_db_query.py` | `query(filters) -> list[dict]` (cap 8, `SessionLocal` per call). |
| `app/chat/tier2_formatter.py` | `format(query, rows) -> Optional[str]` (Haiku, temp 0.3, max_tokens 400, ephemeral system cache, token log line). |
| `app/chat/tier2_handler.py` | `answer_with_tier2(query)` + `TIER2_CONFIDENCE_THRESHOLD = 0.7` and distinct fallback logs. |
| `prompts/tier2_formatter.txt` | Role + compressed voice rules (Option B / Option 3, length, no conditional prompts, gap / external delegation, plain text). |
| `tests/test_tier2_db_query.py` | 14 DB-layer tests (+ open_now warning). |
| `tests/test_tier2_formatter.py` | 7 formatter tests (mocked SDK). |
| `tests/test_tier2_handler.py` | 7 orchestrator tests (mocked parser/formatter/query as specified). |

**No existing production files outside this set were modified** (only new `tier2_*` modules, new prompt, new tests, this doc).

---

## Token / cost notes

- Formatter **system** prompt: ~1,125 characters (~**280** tokens at ~4 chars/token).
- Mocked formatter tests reported **input_tokens=120**, **output_tokens=40** on the stub usage object (illustrative only).
- Typical **user** block = query line + compact `json.dumps(rows, separators=(",", ":"))`; with ≤8 slim rows, system + user stays in a much smaller band than Tier 3’s large context block. Exact live totals depend on row payload size.

---

## STOP-and-ask

None. `open_now` is explicitly handled as “warn + empty → Tier 3 fallback” per spec.

---

## Commit

Planned message (verbatim):

`Phase 4.2: Tier 2 DB query layer + formatter + orchestrator`
