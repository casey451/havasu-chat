# Phase 4.6 — completion report (voice cleanup)

**Status:** Implementation complete — **no commit** pending explicit owner approval.

---

## Pre-flight checks

```
Pre-flight checks:
  Check 1 (4.5 commit in history): PASS — `67f5bf4 Phase 4.5: Tier 2 row payload cleanup` in `git log -20`.
  Check 2 (HOURS_LOOKUP routing intact): PASS — `tests/test_phase38_gap_and_hours.py` classifies `"Is altitude open late on friday?"` as `HOURS_LOOKUP`; Tier 1 path uses provider hours in DB.
  Check 3 (system prompt + external-delegation): PASS — `prompts/system_prompt.txt` exists; prior text had an external-delegation **anti-**pattern (forbid pivot); Phase 4.6 **replaced** that block with a catalog-gap pointer rule (see Change 2).
```

---

## Change 1 — Day-aware HOURS_LOOKUP

**Where:** `app/chat/tier1_templates.py` (helpers + `render` branch), `app/chat/tier1_handler.py` (passes `normalized_query` into `render` data for `HOURS_LOOKUP` and the `TIME_LOOKUP` path that reuses `HOURS_LOOKUP`).

**Mechanism:**

- **`normalized_query`** is passed in the `data` map (not a `{placeholder}` in templates — extra keys are ignored by `.format`).
- **`_weekday_index_from_query`:** full English weekday names only (`monday` … `sunday`), word-boundary match on normalized query.
- **`_hours_focus_for_weekday`:** splits provider `hours` on `|`; requires **at least two** segments so combined strings like `Mon–Sun 9–5` still use the **full-week** templates.
- **`_first_token_weekday_index`:** maps the first token of each segment (`Sun`, `Friday`, `fri` via `full.startswith(t)` for 3-letter tokens) to a weekday index.
- **Closed day:** segment body contains `closed` (e.g. `Tue CLOSED`) → templates `HOURS_LOOKUP_DAY_CLOSED`.
- **Open day:** uses rest of segment after the day token as the time window (e.g. `11am–8pm`).
- **`_short_provider_display_name`:** text before `—`, else full name; if longer than 36 chars, first word only (keeps “Altitude”-style voice).

**New template keys:** `HOURS_LOOKUP_DAY`, `HOURS_LOOKUP_DAY_CLOSED` (one–two short sentences, contractions, no pipe dump).

**Example target shape:** `"Altitude's open 11am–8pm on Friday."` (variant may use “runs” instead of “open”).

**Fallback:** no weekday in query, or fewer than two `|`-separated segments, or no matching day segment → existing `HOURS_LOOKUP` / `Hours: …` behavior unchanged.

---

## Change 2 — External delegation (Tier 3)

**Where:** `prompts/system_prompt.txt` (Hard rules block).

**What changed:** Removed the Phase 3.6 lines that **forbade** adding venue/search/CVB pointers after a gap acknowledgment (the BAD/GOOD pair that praised ending at “locked in” alone). **Replaced** with a short rule: catalog-gap replies should state the gap honestly, then **one clause** with a concrete pointer (CVB **https://www.golakehavasu.com/**, a venue site, or a tight search phrase). Added BAD/GOOD examples aligned with Q20-style “live music tonight.”

**Approach:** Broadened / reframed the old “external delegation” bullet (option **A**-style) rather than adding a separate duplicate section.

---

## Test updates (one line each)

| Test | Note |
|------|------|
| `tests/test_tier1_templates.py` | Added `test_hours_lookup_weekday_with_pipe_hours_focuses_day`, `test_hours_lookup_weekday_non_pipe_hours_keeps_full_dump`, `test_hours_lookup_closed_day_segment`. |
| `tests/test_tier1_handler.py` | Added `test_hours_lookup_day_focus_with_pipe_hours` for end-to-end `try_tier1` + `normalized_query`. |

---

## Verification

| Check | Result |
|--------|--------|
| `pytest` | **530 passed** (+4 tests) |
| `scripts/run_query_battery.py` | **120 total, 116 matches** |
| `scripts/run_voice_spotcheck.py` | **20/20** successful (smoke OK; no `HTTP ERROR` in output) |
| Output path | `scripts/output/voice_spotcheck_2026-04-20T21-34.md` |

**Tier distribution (pre-deploy sanity run):** tier **2** ×6, **3** ×8, **gap_template** ×2, **1** ×2, **chat** ×2 (same shape as prior batteries; **not** validation of 4.6 until Railway has deployed this commit).

---

## Anomalies

- None in tests or battery run. **Token means** in the battery file are still from **production code pre–4.6** until deploy — expect Q14/Q20 behavior to shift only after deploy + rerun.

---

## Commit workflow (when you approve)

Message, verbatim:

```text
Phase 4.6: Voice cleanup - day-aware hours + external delegation
```

Files to include in that commit:

- `app/chat/tier1_templates.py`
- `app/chat/tier1_handler.py`
- `prompts/system_prompt.txt`
- `tests/test_tier1_templates.py`
- `tests/test_tier1_handler.py`
- (optional) this report: `docs/phase-4-6-completion-report.md` — **not** staged unless you want it in the same commit.

**Do not commit on Cursor’s initiative** until you reply with explicit approval.
