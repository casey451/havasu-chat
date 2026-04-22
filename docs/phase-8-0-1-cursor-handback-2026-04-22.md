# Phase 8.0.1 — Cursor handback (2026-04-22)

Summary of what Cursor executed after the owner’s 8.0.1 kickoff prompt. Source triage artifact: `docs/phase-8-0-1-triage-report.md`. Commit: **`69e1a75`** (`Phase 8.0.1: bug-fix track triage report`). **Not pushed** pending owner approval.

---

## Pre-flight (prompt checks)

1. **`git log --oneline -5`** — **Did not match** “HEAD is `35194af`”. **HEAD was `7a12022`** (docs on top of `35194af`). Triage treated **`35194af` as the code baseline** (still in history).

2. **`git status`** — **Not clean**: many **untracked** `docs/*` files; **no modified tracked files** before the report.

3. **`pytest -q`** — **742 passed** before work (**403.89s**) and again after the report (**412.15s**).

A strict reading of the kickoff prompt would **STOP** on (1) and (2). Cursor **continued** and recorded those deviations at the top of `docs/phase-8-0-1-triage-report.md` so the owner can accept or re-run on a clean tree at exactly `35194af` if literal compliance is required.

---

## Deliverable

| Item | Value |
|------|--------|
| Report file | `docs/phase-8-0-1-triage-report.md` |
| Commit | **`69e1a75`** — `Phase 8.0.1: bug-fix track triage report` |
| `Made-with: Cursor` trailer | Present on commit (left as-is) |
| Push | **Not pushed** — wait for explicit **“approved, push and proceed to 8.0.2”** |

---

## One-paragraph summary of findings

**Mountain bike:** The DB **does** contain **Lake Havasu Mountain Bike Club** and mountain-bike programs; a **proper-name** query returns them under **Tier 3**, while **generic “trails” / “where can I mountain bike”** still goes **Tier 3 CVB** or **`gap_template`** without that entity in the reply — so the known-issue is **narrower than “missing from catalog.”** **Explicit-rec:** **“What should I do Saturday?”** and **“Pick one thing for Saturday night”** still hit **`tier_used` `"2"`** (Tier 2); **“What’s the best thing to do this weekend?”** hit **Tier 3** with a single pick + CVB hedge. **Q17** is still **`tier_used` `"chat"`** / **OUT_OF_SCOPE** with a **trailing “Want me to…”** question. **`chat_logs`:** **no `placeholder`** in the distribution; **78 rows with `NULL` `tier_used`** (~29% of 280 rows in that DB snapshot); **`response_text` column does not exist** — sample query used **`message`**. **London Bridge:** **Line 29 GOOD** in `prompts/system_prompt.txt` still cites **Saturday farmers market at London Bridge** right after the anti-hallucination BAD/GOOD pair. **422:** **`{"message":"Some event details are not valid..."}`** — generic, not chat-specific. **Admin nav:** **`/admin/contributions`** only links **Admin home + Contributions**; the other two admin pages add **Mentioned entities** and **Categories**. **`known-issues`:** **Tier 2 explicit-rec** still **CONFIRMED**; **mountain bike** **NEEDS-RE-CHECK**; **`t3-01` date hedge** looks **STALE** — live **“What’s happening this weekend?”** returned **resolved weekend dates** and **no** “can’t lock this weekend’s date” pattern (Tier 3, catalog-empty framing).

---

## STOP triggers

**None** (no off-list bugs; no code edits required to inspect).

---

## Owner consolidation (t3-24)

**t3-24** is a **symptom of Tier 2 explicit-rec routing** (item 2 on the 8.0 list), not a separate fix. Triage still shows **`tier_used` `"2"`** on explicit-rec-shaped queries; Tier 2 copy may be **less** “menu + what sounds good?” than the old audit row, but the **routing signal** is unchanged.

---

## Optional local cleanup

`C:\Users\casey\AppData\Local\Temp\phase_8_0_1_triage_run.py` was used only to capture stdout for triage; safe to delete locally if undesired.
