# Phase 8.0.1.5 — Owner dispositions (2026-04-22)

**Source:** Owner review of `docs/phase-8-0-1-5-housekeeping-plan.md` (Cursor triage). **Status:** Decisions locked below for a follow-up **execute** phase (add/commit/delete + `.gitignore`). No git actions performed in this file.

---

## Inventory note (18 vs 17)

**Accept the 18-file inventory** (the STOP snapshot’s 17 paths **plus** `docs/phase-8-0-2-preflight-stop-2026-04-22.md`). Future pre-flight wording should use **“approximately”** / current `git status`, not **“exactly 17”**, when the inventory record is itself part of the set.

---

## Owner narrative (full read)

### Agree with Cursor without hesitation

- **DELETE #1, #2, #5, #6, #7, #8** — #1–#2 recoverable from git log; #5 strict duplicate of #4; #6–#7 pre-implementation for shipped code; #8 verified duplicate of tracked `docs/phase-6-4-1-cursor-prompt.md`.
- **KEEP #10, #11, #13, #14, #15, #16, #18** — post-deploy smoke, gate/QA, process audit; grep-friendly in a year.
- **KEEP #17 (`t3-24-voice-audit-sample`)** — active for **8.0.2** explicit-rec work. **Note:** After the bypass ships, candidate for **8.0.7** known-issues / doc cleanup (purpose served).

### Push back / judgment

- **#4** — Cursor defaulted **DELETE**; **owner: KEEP.** Rationale: shipped code + verification note capture *what* shipped, not always *why* / trade-offs / owner decisions. Phase 6.1.4 voice-fix prompt is paper-trail worth keeping. **Pair with DELETE #5** (undated duplicate only).
- **#9** — Cursor defaulted **KEEP**; **owner: KEEP (weakly)** — precedence / Windows / test wording useful for future sessions; folded into tracked prompt is also true. **Accept DELETE** for minimal tree if desired.
- **#12** — Cursor defaulted **DELETE**, flagged ambiguous; **owner: DELETE** — overlap with tracked long-form report; “no commit” stale. **KEEP** only if a separate short executive summary is wanted.

### GITIGNORE (owner disagrees with Cursor “0”)

Broad `docs/**/*cursor-prompt*` is wrong — it would ignore intentional canonicals like `docs/phase-6-4-1-cursor-prompt.md`.

**Owner-approved patterns** (exports + scratch reviews only):

```gitignore
# Ignore chat-exported Cursor prompt copies (canonical phase-*-cursor-prompt.md stays committable)
docs/phase-*-cursor-prompt-chat-export.md
docs/phase-*-cursor-prompt-review-*.md
```

Rationale: matches file types that accumulate and get deleted (#8, #9); reduces repeat clutter in Phase 8+.

**Conflict — execute phase must resolve:** **#9 is KEEP** and its path is **`docs/phase-6-4-1-cursor-prompt-review-2026-04-21.md`**, which **matches** `docs/phase-*-cursor-prompt-review-*.md`. Git would treat new copies as ignored (and `git add` may require `-f`). **Pick one:**

1. **Only add the `chat-export` line** (safest with KEEP #9), **or**
2. Keep **both** lines and add an **exception immediately after** the review pattern:  
   `!docs/phase-6-4-1-cursor-prompt-review-2026-04-21.md`  
   (verify order per `.gitignore` negation rules), **or**
3. **Rename** KEEP #9 to something that does not match `*-cursor-prompt-review-*` (e.g. `phase-6-4-1-design-review-2026-04-21.md`) then both ignore lines are safe.

---

## Resolved calls (four decisions — locked for execute prompt)

| # | Question | Decision |
|---|----------|----------|
| 1 | **#4** — KEEP (owner) vs DELETE (Cursor default)? | **KEEP** `docs/phase-6-1-4-cursor-prompt-voice-fixes-2026-04-21.md` |
| 2 | **#9** — KEEP vs minimal-tree DELETE? | **KEEP** `docs/phase-6-4-1-cursor-prompt-review-2026-04-21.md` (owner accepts DELETE alternative for minimal tree) |
| 3 | **#12** — DELETE vs keep short summary? | **DELETE** `docs/phase-6-4-1-implementation-summary.md` |
| 4 | **Gitignore** — add two patterns vs skip? | **ADD** the two lines in `.gitignore` as quoted above |

---

## Final disposition table (owner-approved)

| # | Filename | Disposition |
|---|----------|-------------|
| 1 | `docs/phase-6-1-3-close-status-response-2026-04-21.md` | **DELETE** |
| 2 | `docs/phase-6-1-3-cursor-prompt-commit-close.md` | **DELETE** |
| 3 | `docs/phase-6-1-4-commit-response-2026-04-21.md` | **KEEP** |
| 4 | `docs/phase-6-1-4-cursor-prompt-voice-fixes-2026-04-21.md` | **KEEP** |
| 5 | `docs/phase-6-1-4-cursor-prompt-voice-fixes.md` | **DELETE** |
| 6 | `docs/phase-6-3-implementation-summary.md` | **DELETE** |
| 7 | `docs/phase-6-3-preflight-report.md` | **DELETE** |
| 8 | `docs/phase-6-4-1-cursor-prompt-chat-export.md` | **DELETE** |
| 9 | `docs/phase-6-4-1-cursor-prompt-review-2026-04-21.md` | **KEEP** |
| 10 | `docs/phase-6-4-1-deploy-and-production-smoke-2026-04-22.md` | **KEEP** |
| 11 | `docs/phase-6-4-1-gates-response-2026-04-22.md` | **KEEP** |
| 12 | `docs/phase-6-4-1-implementation-summary.md` | **DELETE** |
| 13 | `docs/phase-6-4-post-deploy-report-2026-04-21.md` | **KEEP** |
| 14 | `docs/phase-6-5-docs-commit-confirmation-2026-04-22.md` | **KEEP** |
| 15 | `docs/phase-6-5-lite-post-deploy-2026-04-22.md` | **KEEP** |
| 16 | `docs/phase-8-0-1-cursor-handback-2026-04-22.md` | **KEEP** |
| 17 | `docs/t3-24-voice-audit-sample.md` | **KEEP** |
| 18 | `docs/phase-8-0-2-preflight-stop-2026-04-22.md` | **KEEP** |
| — | `docs/phase-8-0-1-5-housekeeping-plan.md` | **KEEP** (commit with batch) |
| — | `docs/phase-8-0-1-5-cursor-handback-2026-04-22.md` | **KEEP** (commit with batch; Cursor meta-handback for 8.0.1.5) |
| — | `docs/phase-8-0-1-5-owner-dispositions-2026-04-22.md` | **KEEP** (this file; commit with batch) |

**Counts:** **11 KEEP** from inventory rows #3–#4, #9–#11, #13–#18 + **3** meta docs (`phase-8-0-1-5-housekeeping-plan.md`, `phase-8-0-1-5-cursor-handback-2026-04-22.md`, this `phase-8-0-1-5-owner-dispositions-2026-04-22.md`) = **14 paths** to `git add` for docs, plus **`.gitignore`**. **7 DELETE.**

**`.gitignore`:** append the **two** pattern lines (section above).

---

## Execute phase (placeholder — not run here)

Next step: owner (or Cursor under a dedicated **8.0.1.5-execute** prompt) applies deletes, updates `.gitignore`, stages **KEEP** paths + meta docs, runs `pytest -q`, single commit with agreed message, **hold push** if policy requires.
