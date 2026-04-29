# Multi-day events + parser prompt fix (Option γ) — Step 1 design

**Context:** Design-only pass (Step 1). No code changes, no commits, no server, no Railway. Protocol: no deploy writes without explicit approval; no commit/push without approval; local reads only for this document’s authoring.

---

## A. Parser prompt updates

**What’s wrong today**

`prompts/tier2_parser.txt` only documents `day_of_week`, `time_window` (a short allow-list), and related fields. It does **not** list `date_exact`, `date_start` / `date_end`, `month_name`, or `season`, which are first-class fields on `Tier2Filters` in `app/chat/tier2_schema.py` (lines 56–78) with validation and a **mutual-exclusion rule**: at most one of `time_window`, `month_name`, `season`, `date_exact`, or `date_start`/`date_end` (see `_temporal_non_overlap`).

**What to add in the schema section (conceptual, not the final copy)**

1. **`date_exact`**  
   - Type: `string` in **ISO-8601 date** form, e.g. `"2026-05-08"`.  
   - Use when the user names a **specific calendar day** (“May 8, 2026”, “5/8/26”, “Friday, May 8, 2026” when the intent is that calendar day, not a generic “Friday this week”).

2. **`date_start` / `date_end`**  
   - Inclusive range; same ISO `YYYY-MM-DD` strings.  
   - Use for explicit ranges (“between June 1 and June 7”, “from the 1st to the 7th” with clear month/year if needed).

3. **`month_name`**  
   - Lowercase full month per validator (`january` … `december`).  
   - Use for “in July”, “events in August” **without** a specific day, when the ask is a whole month (not a `time_window` like “this month”).

4. **`season`**  
   - `spring` | `summer` | `fall` | `winter` (lowercase, per schema).

5. **Alignment with `time_window` and disambiguation**  
   - Instruct: when a **concrete** calendar day or range (or month/season) is the primary time constraint, prefer **`date_*` / `month_name` / `season`** and set **`time_window` to null** so `_temporal_non_overlap` is satisfied.  
   - `time_window` remains for: today / tomorrow / this week / this weekend / this month / **upcoming** / and (if documented) **`next_week` / `next_month`** — see **Gap note** below.

**Gap note — `time_window` allow-list**

`tier2_schema._TIME_WINDOWS` includes `next_week` and `next_month`, but the current prompt only lists a subset. The design should either: (1) add those two to the prompt’s allow-list, or (2) omit them from the prompt and accept occasional validation failures if the model invents them. (1) is safer and matches the schema.

**Structure**

Keep the existing “Schema (all keys optional except …)” block; add a **Temporal (structured calendar)** bullet group after `day_of_week` and in sync with `time_window`. A short “**Do not mix**” line mirroring the schema (one temporal group) will help the model avoid invalid JSON.

---

## B. Few-shot examples

**Keep** existing few-shots; **add** new query/output pairs, each valid under `Tier2Filters`:

| Intent | Proposed example shape (illustrative) |
|--------|----------------------------------------|
| Single calendar day | “What events are on May 8, 2026?” → `date_exact: "2026-05-08"`, `parser_confidence` high, `time_window` absent/null |
| Date range | “Events between June 1 and June 7, 2026” → `date_start: "2026-06-01"`, `date_end: "2026-06-07"`, no `time_window` |
| Month without day | “What’s in July 2026?” or “events in July” → `month_name: "july"` (and a note: assume current or stated year) |
| Season | “summer events” (when not “this month”-style) → `season: "summer"` |
| “Friday” alone | “What’s on Friday?” → `day_of_week: ["friday"]` and an appropriate `time_window` (e.g. this week / upcoming) — **no** `date_exact` unless a calendar date is given |
| “Friday, May 8, 2026” | `date_exact: "2026-05-08"`; **do not** also set `day_of_week` if it would violate the one-group rule; the exact date wins. (Schema allows only one group — the prompt should state that **full calendar date takes precedence** over weekday-only.) |

**Edge copy (for the prompt, not a test):** “If both a weekday and a full date appear, use `date_exact` and omit `day_of_week`.”

---

## C. Test approach

**Existing pattern**

`tests/test_tier2_parser.py` always **mocks** `anthropic.Anthropic` and feeds synthetic JSON as the “LLM” response (`_parse_with_mock`), then validates `parse()` + `Tier2Filters`. It does **not** call the live API.

**Recommendation**

- **`tests/test_tier2_parser_date_extraction.py`:** follow the same pattern (mock the client, pass JSON strings for each scenario).  
- The session goal (“parser extracts date fields for natural-language queries”) is **LLM-behavioral**. In-repo options:  
  1. **Mock payloads** matching the **target** post-prompt behavior (regression guard for schema + `parse()`) — matches current `test_tier2_parser.py` style.  
  2. **Optional** opt-in **live** tests (env guard) — not required for deterministic CI; existing pattern is **mock only**.

**Minimum cases for regression (mock payloads)**

- May 8, 2026 → `date_exact` only.  
- June 1–7 range → `date_start` + `date_end`, no `time_window`.  
- July (month) → `month_name`.  
- summer → `season`.  
- “Friday” generic → `day_of_week` + `time_window`, no `date_exact`.  
- Optional: one case — ensure not both `date_exact` and `time_window` in the same object (or expect validation error if the test supplies bad JSON).

**Note:** `parse()` does not inject “reference date”; the model must infer year. Few-shots should use explicit years (e.g. 2026) to match the backlog examples.

---

## D. Surgical commit plan (Commit B vs held past-date work)

Categorization from `git diff` of the four files (working tree vs `HEAD`):

### `app/chat/tier2_db_query.py`

| Change | Category |
|--------|----------|
| `from sqlalchemy import func, or_, select` | **Multi-day** |
| `_event_covers_any_weekday` and use in `day_of_week` filtering | **Multi-day** |
| `_event_dict` optional `end_date` in output | **Multi-day** |
| `_upper_bound_for_clustering` using `end_date` in `max` | **Multi-day** |
| `has_explicit_date_bounds` and new `lower` logic in `_query_events` | **Past-date retrieval** (explicit calendar bounds, including `date_exact`, not clamped to `today`) |
| `select(Event).where(..., func.coalesce(Event.end_date, Event.date) >= lower)` and existing `Event.date <= win_end` | **Multi-day** (interval overlap) |
| `_sample_mixed` `coalesce(end_date, date) >= today` | **Multi-day** |

**Surgical risk:** `lower` and the `coalesce` `WHERE` are in the **same** function. Commit B can include the **coalesce** SQL and the rest, while **excluding** the `has_explicit_date_bounds` / `lower` remapping block. The test `test_explicit_past_date_exact_not_clamped_to_today` depends on the **past-date** hunk; it should **not** be staged in Commit B. The test `test_multi_day_event_surfaces_on_middle_day_date_exact` + `_evt(..., end_date=...)` is **multi-day** and should go in B.

**If hunks are intermingled:** use `git add -p` (or a patch file). If the index cannot split cleanly, **halt and report** — do not guess.

### `app/core/search.py`

| Change | Category |
|--------|----------|
| `_base_future_events_query`: `date_context` and unbounded “future” using interval overlap and `func.coalesce(Event.end_date, Event.date) >= today` (or `>=` `start` with `<=` `end`) | **Multi-day** (overlap + “still running” / middle-day in window) |
| `_event_card` date range when `end_date` > `date` | **Multi-day** |

**Note:** If other uncommitted “past-only” search edits exist outside this diff, re-verify at staging time. **The snapshot reviewed:** the visible `search.py` diff is safe to treat as **Commit B (multi-day)** as shown.

### `tests/test_phase5.py`

| Addition | Category |
|----------|----------|
| `test_explicit_past_date_context_is_honored` | **Past-date** — **exclude from B** |
| `test_date_context_includes_event_when_multi_day_spans_single_day_window` | **Multi-day** — **B** |
| `test_ongoing_multi_day_surfaces_without_date_context` | **Multi-day** — **B** |

### `tests/test_tier2_db_query.py`

| Change | Category |
|--------|----------|
| `_evt(..., end_date=...)` on `Event` | **Multi-day** — **B** |
| `test_explicit_past_date_exact_not_clamped_to_today` | **Past-date** — **not B** |
| `test_multi_day_event_surfaces_on_middle_day_date_exact` | **Multi-day** — **B** |

---

## E. Readiness for steps 5–11 (11-step plan)

- Step 1 (this report) matches the work: prompt, few-shots, tests, and surgical B vs past-date.  
- **Step 2+** still apply: parser prompt + new test file; mock pattern like `test_tier2_parser.py`. Step 3 manual chat on local server is operator-driven. Steps 4–6: two commits, surgical staging for B. Step 7: push (approval). Steps 8–10: migration, backfill, production verification (operator runs commands; read-only production checks per protocol).  
- **Divergences:** Plan’s “10” vs session “11” steps: Step 11 is backlog doc update; explicitly in scope.  
- **`tier2_schema` one-group rule** must be reflected in the prompt, or the model may emit invalid JSON and `parse()` returns `None` (validation failure).

---

*Generated for Option γ, Step 1. Implementation begins after explicit approval for Step 2+.*
