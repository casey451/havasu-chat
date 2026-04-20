# Phase 4.5 — completion report (Tier 2 row payload cleanup)

**Status:** No commit; awaiting explicit owner approval to commit and push.

---

## Pre-flight checks

```
Pre-flight checks:
  Check 1 (4.4 commit in history): PASS — `16038ca Phase 4.4: Voice battery script + baseline run` in last 20 commits.
  Check 2 (voice battery script): PASS — `scripts/run_voice_spotcheck.py` present and runnable (smoke + 20 queries + DB correlation).
  Check 3 (row-dict builders present): PASS — `_event_dict`, `_program_dict`, `_provider_dict`, `_truncate` present; caps updated per Phase 4.5 (event/program/provider description 120; hours still 120).
```

---

## Files changed

| File | Change |
|------|--------|
| `app/chat/tier2_db_query.py` | Removed `id` from event/program/provider row dicts; program `location_name` + `location_address` → single optional `location` via `_program_location_display`; description caps 180/160/160 → **120** for events/programs/providers; `_merge_simple` dedupe now uses `_row_dedupe_key` (no `id`). |
| `tests/test_tier2_db_query.py` | `test_location_sara_park`: assert `"Sara"` appears in `location_name` **or** `location` (programs use `location` only). |

**Change 2 note:** Provider row dicts already exposed only `name` (from `provider_name`); there was no duplicate `provider_name` key on providers, so nothing to remove there.

---

## Tests

- **`pytest`:** **526 passed** (full suite).
- **`scripts/run_query_battery.py`:** **120 total, 116 matches** (unchanged vs prior Track A bar).

---

## Voice battery (production)

- **Output:** `scripts/output/voice_spotcheck_2026-04-20T21-09.md`
- **Smoke:** OK; **0× `HTTP ERROR`** across 20 queries (20/20 successful).
- **Tier distribution (this run):** tier **`2`:** 6 · **`3`:** 8 · **`gap_template`:** 2 · **`1`:** 2 · **`chat`:** 2 (same pattern as Phase 4.4 baseline).

### Token delta (important)

**Railway production was still running the pre–Phase 4.5 build** at the time of this battery (changes not yet deployed). The run therefore shows **the same Tier 2 `llm_input_tokens` as before** (e.g. Q1 **2566**, Q3 **2352**, Q10 **2366**, Q11 **1363**, Q9-style row **1303**, Q19 **1324**).

**Local payload shrink** (same filters / `events.db`, compact JSON as the formatter uses):

| Sample filter | Rows | JSON UTF-8 bytes (before → after) | Δ |
|---------------|------|-------------------------------------|---|
| Saturday `day_of_week` | 8 | 4675 → **3984** | **−691 (~14.8%)** |
| Sara Park `location` | 8 | 3533 → **3045** | **−488 (~13.8%)** |
| Rotary + age 8 | 1 | 573 → **489** | **−84 (~14.7%)** |

That is **~14–15% less row JSON** on these samples. After deploy, a **rough** expectation is **on the order of ~10–15% lower combined Tier 2 input tokens** (row JSON is only part of parser + formatter input), not the full 14% of total billing unless remeasured on live traffic.

---

## Anomalies / notes

1. **Deploy gate:** Re-run `scripts/run_voice_spotcheck.py` (or `railway run … scripts/analyze_chat_costs.py`) **after** shipping this change to confirm live Tier 2 means.
2. **Formatter prompt** was not edited; it does not hard-code `location_name` for programs, so the new `location` field should be fine, but owner should still skim a few Tier 2 replies post-deploy.

---

## Commit workflow

Per Phase 4.5 instructions: **nothing was committed or pushed** pending explicit owner approval. If approved, use commit message **verbatim**:

```text
Phase 4.5: Tier 2 row payload cleanup
```

Then `git push` to `main` once; leave `Made-with: Cursor` trailer alone; no amend, no force push, no hook bypass.
