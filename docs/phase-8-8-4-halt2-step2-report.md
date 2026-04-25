# Phase 8.8.4 — HALT 2 report (Step 2: recurring-dedupe + bucketing)

**Date:** 2026-04-25  
**Status:** Ready for owner review before Step 3 (LLM router module).

---

## What changed

**File: `app/chat/tier2_db_query.py`**

- **`_filter_window_span_inclusive`:** Inclusive day span of the *filter* window. Unbounded upper (e.g. `upcoming`) is treated as a very large span so the path is **broad**.
- **`BROAD_EVENT_SQL_LIMIT = 500` / `NARROW_EVENT_SQL_LIMIT = 80`:** Broader windows pull a larger ORM cap before in-memory selection.
- **`_recurring_series_key` / `_dedupe_recurring_preserving_chrono`:**  
  - `is_recurring` **True** → one row per **( `normalized_title`, `start_time` )**, keep **earliest** in window.  
  - `is_recurring` **False** → one row per **event `id`** (no collapse with neighbors).
- **`_upper_bound_for_clustering`:** Uses `win_end` when set; for open-ended upper uses **max** event date in the current candidate list (or no bucketing if empty).
- **`_is_still_clustered_early`:** 8th row by date (index `min(7, len-1)`) is still in the first **30%** of the inclusive day span → “still clustered.”
- **`_time_bucket_first_hits`:** Splits `lower..upper` into `MAX_ROWS` day-subranges, takes the first event in each, then chrono backfills to `MAX_ROWS` if needed.
- **`_query_events`:** If span **≤ 30** days, legacy “first N by `date ASC, start_time ASC`” (no recurring collapse). If **> 30** days: dedupe recurring, then (if still clustered and `len > MAX_ROWS`) time-bucket, else `[:MAX_ROWS]`.

**Heuristic note:** The implementation prompt’s “title + time” fallback is **not** used when `is_recurring` is false; the owner lock was **column-based** first. (Heuristic can be added later for mis-flagged data.)

**File: `tests/test_tier2_db_query.py`**

- Extended **`_evt`** with `is_recurring` and `start`.
- **Three tests** (isolated with unique `category` tokens to avoid cross-test DB pollution):
  1. Broad window + 12 weekly `is_recurring` rows → **one** event in output for that series.
  2. Narrow (≤ 30d) + 8 `is_recurring` daily rows, same series key → **8** event rows (no collapse in narrow path).
  3. Broad + many early, few late, clustered → at least one returned row in **July** (bucketing reaches late window).

---

## Pytest

```text
python -m pytest tests/ -k "schema or db_query" -v
```

**31 passed** (Windows, `.venv`); 833 deselected.

```text
python -m pytest tests/test_tier2_db_query.py -v
```

**17 passed.**

---

## Uncommitted (for Step 5 three-commit plan)

Includes Step 1 + Step 2: `app/chat/tier2_schema.py`, `app/chat/tier2_db_query.py`, `tests/test_tier2_schema.py`, `tests/test_tier2_db_query.py`, and any uncommitted doc files (e.g. HALT reports) unless committed separately.

---

## Next

**Step 3:** `app/chat/llm_router.py`, `prompts/llm_router.txt`, `tests/test_llm_router.py` — then **HALT 3** (full prompt + `RouterDecision` in chat and optional MD).
