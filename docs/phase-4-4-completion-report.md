# Phase 4.4 — completion report

**Status:** No commit; awaiting explicit owner approval to commit and push.

---

## Pre-flight checks

```
Pre-flight checks:
  Check 1 (4.3 commit in history): PASS — subject "Phase 4.3: Routing integration + token split schema + cost analytics" appears in `git log -30` (903032c…).
  Check 2 (routing integration live): PASS — `_handle_ask` calls `try_tier1` → `try_tier2_with_usage`; on Tier 2 text `answer_with_tier3` is used (`unified_router.py`).
  Check 3 (schema has split columns): PASS — `ChatLog` has `llm_input_tokens` / `llm_output_tokens`; `alembic/versions/7a8b9c0d1e2f_add_llm_input_output_token_columns.py` present.
  Check 4 (baseline tests pass): PASS — `526 passed`.
```

---

## Smoke test (before battery)

- **Result:** PASS — `POST https://havasu-chat-production.up.railway.app/api/chat` with JSON `{"query": "what should I do Saturday", "session_id": "<random>"}` returned a non-empty `response` and HTTP 200.
- **Note:** The Phase 4.4 handoff text used `{"message": ...}`; production concierge expects **`query`** (see `ConciergeChatRequest`). The script follows the real API.

---

## Battery script + output

- **Added:** `scripts/run_voice_spotcheck.py` (stdlib HTTP, 1.5s pause between calls, one `session_id` for all 20 turns, `shutil.which("railway")` so Windows resolves `railway.CMD` for DB correlation).
- **Output file:** `scripts/output/voice_spotcheck_2026-04-20T20-34.md` (20 sections; `tier_used` + token columns from `chat_logs` where present; `(unavailable)` for tiers with no LLM split, e.g. `gap_template`, `chat`, Tier 1).
- **Note:** An initial run failed DB correlation when subprocess could not resolve bare `railway` on Windows; fixed with `shutil.which("railway")` and the battery was re-run. The obsolete first-run artifact was removed from `scripts/output/`.

---

## 20-query `tier_used` distribution

(Battery run reflected in `voice_spotcheck_2026-04-20T20-34.md`.)

| tier_used       | Count |
|-----------------|-------|
| `2`             | 6     |
| `3`             | 8     |
| `gap_template`  | 2     |
| `1`             | 2     |
| `chat`          | 2     |

---

## Cost analytics — full production output

Command: `railway run .\.venv\Scripts\python.exe scripts\analyze_chat_costs.py` (or equivalent with venv Python).

```
=== Chat log cost / usage analytics ===
Window: last 30 days (created_at >= cutoff UTC)
Total queries (rows): 104
Date range (rows): 2026-04-19T23:23:46.914570 -> 2026-04-20T20:32:21.900723

--- Tier distribution (tier_used) ---
  3: 68 (65.4%)
  chat: 10 (9.6%)
  1: 8 (7.7%)
  2: 8 (7.7%)
  (null): 6 (5.8%)
  gap_template: 2 (1.9%)
  placeholder: 2 (1.9%)

--- llm_tokens_used ---
  NULL (no LLM billable row): 28
  non-NULL: 76
  Note: Tier 1 / gap_template rows typically have NULL tokens. Tier 2/3 store ``llm_tokens_used`` as input+output (and split columns when migrated).

--- Tier 3 token usage (tier_used == '3', llm_tokens_used NOT NULL) ---
  Rows with tokens: 68
  Total tokens: 166478
  Mean per query: 2448.21
  Median per query: 2372.00
  Min: 1719  Max: 3656
  Estimated USD (Haiku 4.5 list rates; combined token field only):
    Worst-case if all tokens billed as output: $0.8324
    Worst-case if all tokens billed as input:   $0.1665
    50/50 input-output split (illustrative):      $0.4994

--- Per-tier input/output split + estimated cost (Haiku 4.5 rates) ---
  Rows missing llm_input_tokens/llm_output_tokens are excluded from mean/cost sums (typically pre-migration data or tiers with no LLM call). ``n_with_split`` counts rows used for averages; ``n_tier`` is all rows for that tier_used in the window.
  tier_used='3'  rows=68  with_split=7  pre_split_or_null=61
    mean llm_input_tokens:  2595.57
    mean llm_output_tokens: 54.43
    estimated cost (sum):     $0.0201
  tier_used='chat'  rows=10  with_split=0  pre_split_or_null=10
    (no split-token rows for this tier in window)
  tier_used='1'  rows=8  with_split=0  pre_split_or_null=8
    (no split-token rows for this tier in window)
  tier_used='2'  rows=8  with_split=8  pre_split_or_null=0
    mean llm_input_tokens:  2023.50
    mean llm_output_tokens: 161.88
    estimated cost (sum):     $0.0227
  tier_used='(null)'  rows=6  with_split=0  pre_split_or_null=6
    (no split-token rows for this tier in window)
  tier_used='gap_template'  rows=2  with_split=0  pre_split_or_null=2
    (no split-token rows for this tier in window)
  tier_used='placeholder'  rows=2  with_split=0  pre_split_or_null=2
    (no split-token rows for this tier in window)

--- Mode distribution ---
  ask: 88 (84.6%)
  chat: 10 (9.6%)
  (null): 6 (5.8%)

--- Top sub_intent (tier_used == '1' only) ---
  NEXT_OCCURRENCE: 4 (50.0% of Tier-1 rows)
  PHONE_LOOKUP: 3 (37.5% of Tier-1 rows)
  HOURS_LOOKUP: 1 (12.5% of Tier-1 rows)
```

**Timing note:** This capture was taken during the 4.4 session; totals may omit the very latest rows if the cost script is re-run after more traffic. Re-run the same command for an up-to-the-minute window.

---

## Flagged anomalies (interpretation checks)

1. **Tier 2 combined tokens vs the Phase 4 target (below 700 combined):** For rows with split columns, analytics reports mean **input 2023.5 + output 161.9 ≈ 2185** combined — **well above 700**. Spot-check rows show similar large inputs (e.g. 2566+199 for Q1). Flag for owner + Claude review (prompt/context size vs expectation).
2. **Tier 3 split coverage in the 30-day window:** Only **7** Tier 3 rows have `llm_input_tokens`/`llm_output_tokens`; **61** are pre-split/null — consistent with data logged before the 4.3 migration; means for Tier 3 split are over `n_with_split=7` only.
3. **Tier 3 mean from legacy `llm_tokens_used`:** **~2448** combined — aligns with historical ~2400 expectation.
4. **Tier 2 adoption:** Window shows **8** Tier-2 rows (7.7%); this battery had **6/20** Tier 2 — not near zero; still a minority vs Tier 3 on open-ended queries.

---

## Verification table

| Step | Result |
|------|--------|
| `pytest` | **526 passed** (after script change) |
| `scripts/run_query_battery.py` | **120 total, 116 matches** — script still targets `https://web-production-bbe17.up.railway.app` per repo (not `havasu-chat-production`); count is for that host as written |
| `scripts/run_voice_spotcheck.py` | End-to-end OK; report **`scripts/output/voice_spotcheck_2026-04-20T20-34.md`** |
| Cost script | Completed with exit 0 (output above) |

---

## Git / scope

- **New file:** `scripts/run_voice_spotcheck.py`.
- **`scripts/output/voice_spotcheck_*.md`:** gitignored — do not commit.
- **No changes** to `app/`, routing, Tier 2 modules, tests, or `.gitignore` for this phase (beyond the new script).

---

## STOP-and-ask

None required for this run: pre-flight passed, smoke passed, battery completed, cost script succeeded, pytest 526, query battery 116/120.

---

## Commit workflow

Per Phase 4.4 instructions: **nothing was committed or pushed** pending explicit owner approval. If approved, use commit message **verbatim**:

```text
Phase 4.4: Voice spot-check battery + post-migration cost analytics
```

Then `git push` to `main` once; leave `Made-with: Cursor` trailer alone; no amend, no force push, no hook bypass.
