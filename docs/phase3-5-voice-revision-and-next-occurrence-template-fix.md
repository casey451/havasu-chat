# Phase 3.5 — Voice revision + NEXT_OCCURRENCE template fix (completion report)

## Summary

**Baseline:** 465 tests passed before changes; **465** after.

**Commit:** `80be9e8` — `Phase 3.5: Voice revision + NEXT_OCCURRENCE template fix` — pushed to `main`.

---

## Task 1 — `prompts/system_prompt.txt`

**Structure (unchanged):** Intro → **Hard rules** → **Response style** (3.2.1) → **Handling gaps** (3.2.2) → closing line. **Response style** and **Handling gaps** were not rewritten.

**What changed (Hard rules only):**

| Topic | Before (conceptually) | After |
|--------|------------------------|--------|
| Sentence cap | Single bullet: 1–3 sentences | Same, plus: “Hold the line at three — if a fourth sentence sneaks in, cut it.” |
| Follow-up questions | “No follow-up questions unless…” | Same, plus ask-mode period rule, no preference prompts, BAD/GOOD example (Altitude). |
| Say so and stop | Only “context block” / invent nothing | New bullets: can’t answer → say once, stop; BAD/GOOD “tomorrow’s date” example. |
| Option 3 / §2.2 | (not spelled out) | New bullet: explicit triggers + pick one + BAD/GOOD (farmers market example uses **London Bridge** / farmers market — real recurring surface in seed/context, not a fake venue name). |

**Verbatim modified block (lines 3–16):**

```text
Hard rules:
- Answer in 1–3 short sentences. Use contractions ("it's", "they're", "what's"). Hold the line at three — if a fourth sentence sneaks in, cut it.
- No filler ("Certainly", "Great question", "I'd be happy to").
- No follow-up questions unless the user explicitly asked one. In ask mode, end with a period — not a question mark — unless the user asked a question. Do not prompt for preferences ("what kind of…", "what interests you").
  BAD: "Altitude is open 9am–9pm Saturday. What kind of activity interests you?"
  GOOD: "Altitude's open 9am–9pm Saturday — 90-minute open jump runs $19 if the kids need to burn energy."
- Lead with the useful answer, then stop.
- If the context block does not contain enough information, say so plainly and stop — do not invent venues, times, or prices.
- If you cannot answer what they asked (e.g. you don't have that date, or the catalog has no row), say that once and stop. Do not pivot to listing other events, months, or venues they didn't ask for.
  BAD: "I don't have tomorrow's date, so I can't tell you what's happening tomorrow. The catalog shows upcoming events in May and June 2026 (dance showcases, recitals, and theater), but nothing closer than that."
  GOOD: "I don't have tomorrow's date locked in — I can't tell you what's on yet."
- Explicit recommendation triggers (Option 3 — pick and commit): when the user says things like "what should I do," "pick one," "which is best," "worth it," "your favorite," or "what would you do," choose one concrete option from the Context and stand behind it. Do not open with "that depends," do not list unprompted alternatives, and do not ask what they want.
  BAD: "That depends what you're into! You could check out Altitude, or a dance studio. What kind of activity interests you?"
  GOOD: "Hit the Saturday farmers market at London Bridge — it's the main weekend draw if you want something local and low-key."
```

*(Lines 17+ unchanged from prior 3.2.1 / 3.2.2.)*

---

## Task 2 — `app/chat/tier1_templates.py` (NEXT_OCCURRENCE / DATE_LOOKUP path)

**Note:** There is **no** separate `NEXT_OCCURRENCE` template key. `tier1_handler` calls `render("DATE_LOOKUP", …)` for both `DATE_LOOKUP` and `NEXT_OCCURRENCE`. The fix is: **natural spoken dates for ISO `YYYY-MM-DD`** + **clearer variants** (still `DATE_LOOKUP`).

**Before — `DATE_LOOKUP` variants:**

- `"{program} is {date}."` / `"It's {date}."` / `"Date: {date}."`

**After — `DATE_LOOKUP` variants:**

- `"{program} is {date}."`
- `"The next {program} is {date}."`
- `"{program}'s on {date}."`

**New helper:** `_naturalize_iso_date_slot()` — if `date` is exactly `YYYY-MM-DD`, format as `Weekday, Month D, YYYY`; otherwise unchanged (e.g. `April 20–27`).

**OPEN_NOW:** Implemented in **`tier1_handler`** as fixed strings, **not** in `TEMPLATES`. No ISO date dump; wording is already conversational. **No code change** (per scope). Same “flat template” issue as DATE_LOOKUP does **not** apply.

---

## Tests

- No test files changed.
- **465** passed before and after; **no failures.**

---

## Divergences

1. **Separate `NEXT_OCCURRENCE` template key** — Not added; **`tier1_handler` must not be edited** per scope, and it always uses `render("DATE_LOOKUP", …)` for that branch. Fix is **shared `DATE_LOOKUP` templates + ISO → spoken date**.
2. **Initial prompt typo** — First draft said “more than **four** sentences,” which conflicted with 1–3; corrected to **hold the line at three** and cut a fourth.
3. **Worked GOOD example** — Uses **Saturday farmers market at London Bridge** (real, generic Havasu fixture) instead of inventing a BMX line that would need event times from Tier 1 data.
