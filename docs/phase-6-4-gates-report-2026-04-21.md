# Phase 6.4 gates report — 2026-04-21

Report from post–`.env` key population run (**no commit**).

## Step 1 — keys

`OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are both visible after `ensure_dotenv_loaded()` (`True` / `True`).

## Step 2a — integration

```text
5 passed in 9.34s
```

**Pass rate: 5/5** (meets the 4/5+ bar).

## Step 2b — hint extractor tokens

```text
n=12
mean_prompt_tokens=378.08
mean_completion_tokens=10.58
max_prompt_tokens=383 max_completion_tokens=17
```

**Means: ~378 input, ~11 output per call.**

**STOP (token gate):** mean **input ~378** is **above** the **~300** ceiling. Mean output is **below** ~100.

## Step 2c — local voice spot-check

- **Server:** `uvicorn` on `http://127.0.0.1:8765` (HTTP 200 before the run).
- **Report:** `scripts/output/voice_spotcheck_2026-04-21T20-56.md`
- **Note:** Report still shows `expected 20 chat_logs rows, got 0` (local logging/DB vs production); not used as a query-level FAIL here.

### Voice gate (explicit)

**Verdict: PASS**  
**Numeric score: 20/20** (0 FAIL, 0 MINOR by the rubric used)

**Rubric used:** Each query **PASS** unless it breaks scope, misuses tier, or **hedges the calendar** when Tier 3 + `Now:` should anchor time. **Q20** “not in the catalog” / thin schedule wording is **PASS** (including owner note: no prompt broadening). **Q6** anchors “Saturday–Sunday, April 25–26” and separates empty weekend events from Altitude hours. **Q9** anchors “Wednesday, April 22” for “tomorrow” from `Now` on 2026-04-21 (Tuesday) — weekday/date consistent.

**MINOR / FAIL query list:** none.

## Step 3 — three numbers (summary)

| Gate | Result |
|------|--------|
| **Integration** | **5/5** passing |
| **Hint extractor means** | **~378 in / ~11 out** → **STOP** on input vs ~300 max |
| **Local voice** | **PASS — 20/20** (0 MINOR, 0 FAIL) |

## Surprise / follow-up

With a real key, integration is green, but the **measured mean prompt size for hint extraction is still meaningfully above the ~300 target**, so the **hint token gate should block ship** until that is tuned or the threshold is explicitly revised.

**No commit** until explicit **approved, commit and push**.
