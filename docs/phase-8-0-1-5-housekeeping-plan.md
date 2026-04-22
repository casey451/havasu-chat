# Phase 8.0.1.5 — Docs housekeeping plan (uncommitted)

**Date:** 2026-04-22  
**Purpose:** Triage untracked `docs/*` artifacts before Phase 8.0.2 pre-flight can pass. **No git operations executed** in this pass.

---

## Pre-flight checks

### 1. `git log --oneline -5`

```text
69e1a75 Phase 8.0.1: bug-fix track triage report
7a12022 docs: Phase 6 close — all sub-phases shipped, Phase 8 next
35194af Phase 6.5-lite: local voice plumbing (empty, ready to grow)
a9dca4d docs: Phase 6.5 deferral plan and correct-and-grow workflow
3b6315e Phase 6.4.1: recommended-entity capture for prior_entity
```

**Result:** **PASS** — **HEAD is `69e1a75`** (8.0.1 triage report). Branch **ahead of `origin/main` by 1 commit** (local 8.0.1 not pushed, or equivalent).

### 2. `git status` (untracked set vs STOP report)

The Phase 8.0.2 STOP doc (`docs/phase-8-0-2-preflight-stop-2026-04-22.md`) lists **17** paths. **Current** untracked set = those **17** **plus** the STOP doc itself:

| # | Path | In STOP list? |
|---|------|---------------|
| 1–16 | (same filenames as rows 1–16 in STOP doc) | Yes |
| 17 | `docs/t3-24-voice-audit-sample.md` | Yes |
| 18 | `docs/phase-8-0-2-preflight-stop-2026-04-22.md` | **No** (this file is the inventory record, not part of the original 17) |

**Result:** **FAIL** as written (“exactly the 17 listed”) — actual count **18** untracked housekeeping candidates **before** this plan file. **No modified tracked files.**

**Owner resolution:** Approve **18-file inventory** (recommended), or delete `docs/phase-8-0-2-preflight-stop-2026-04-22.md` and re-run pre-flight for strict 17-match.

### 3. `.\.venv\Scripts\python.exe -m pytest -q`

```text
742 passed in 480.93s (0:08:00)
```

**Result:** **PASS**

---

## STOP-and-ask (pre-flight)

- **Pre-flight 2 failed** under literal wording. Triage table below covers **all 18** current untracked files (including `phase-8-0-2-preflight-stop`). Awaiting owner **explicit OK** to treat that as the scoped set before any `git clean` / `git add`.

---

## Triage table (all untracked candidates)

| # | Filename | 1-line content summary | Class | Proposed disposition | Reasoning |
|---|----------|------------------------|-------|----------------------|-----------|
| 1 | `docs/phase-6-1-3-close-status-response-2026-04-21.md` | Meta note that 6.1.3 eight-file commit `c899bfb` is already on `main`; points at sibling prompt files. | Process scratch | **DELETE** | Status is **recoverable from `git log` / `origin/main`**. No unique audit data not in committed `docs/phase-6-1-3-*.md` set. |
| 2 | `docs/phase-6-1-3-cursor-prompt-commit-close.md` | Cursor agent prompt: how to commit exactly eight 6.1.3 artifacts; “do not stage” self-file. | Process scratch | **DELETE** | Phase **closed**; same workflow can be reconstructed from committed artifacts. Intentionally excluded from 6.1.3 commit per its own scope. |
| 3 | `docs/phase-6-1-4-commit-response-2026-04-21.md` | Post-commit log: SHA **`10b251b`**, files touched, cleanup note (four untracked prompts left), `known-issues` follow-up note. | Delivery artifact | **KEEP** | **Permanent audit trail** for what shipped in 6.1.4 vs what was deliberately excluded; complements `docs/phase-6-1-4-verification-note-2026-04-21.md` (tracked). |
| 4 | `docs/phase-6-1-4-cursor-prompt-voice-fixes-2026-04-21.md` | Dated canonical copy of 6.1.4 Cursor prompt (owner decisions, tasks, verification, cost note). | Process scratch | **DELETE** | Phase **complete**; content intent is captured in **tracked** code + `phase-6-1-4-verification-note`. Optional **KEEP** if owner wants a **paste-ready prompt archive** in-repo — default **DELETE** to reduce duplication. |
| 5 | `docs/phase-6-1-4-cursor-prompt-voice-fixes.md` | Same 6.1.4 Cursor prompt body as #4 (undated duplicate). | Process scratch | **DELETE** | **Strict duplicate** of #4; if #4 kept, still delete this; if #4 deleted, delete this. |
| 6 | `docs/phase-6-3-implementation-summary.md` | Post-`proceed` summary of onboarding API, Tier 3 user-context line, UI chips; says **no commit yet**, 688 tests. | Process scratch | **DELETE** | Phase 6.3 is **shipped on `main`** (`f6d423f` lineage); summary is **stale** and **superseded** by code + tests. |
| 7 | `docs/phase-6-3-preflight-report.md` | Read-only preflight: session model, `index.html` patterns, `context_builder` / `tier3_handler` notes. | Process scratch | **DELETE** | **Superseded** by implemented 6.3; no unique facts not in repo code / committed docs. |
| 8 | `docs/phase-6-4-1-cursor-prompt-chat-export.md` | Full **Phase 6.4.1** implementation prompt (recommended-entity capture) exported from chat. | Process scratch | **DELETE** | **Duplicate** of tracked **`docs/phase-6-4-1-cursor-prompt.md`** (verified `git ls-files`). |
| 9 | `docs/phase-6-4-1-cursor-prompt-review-2026-04-21.md` | Claude/owner review notes: precedence contradiction fix, Windows `grep` note, test 7e wording. | Process scratch | **KEEP** (optional **DELETE**) | **Default KEEP:** short **design-review record** not fully duplicated in `phase-6-4-1-cursor-prompt.md`. If owner wants minimal tree, **DELETE** — corrections are already folded into tracked prompt. |
| 10 | `docs/phase-6-4-1-deploy-and-production-smoke-2026-04-22.md` | Deploy/push note for **`3b6315e`**, Railway wait, prod `POST /api/chat` smoke Run A vs B, pronoun binding PASS on retry. | Delivery artifact | **KEEP** | **Unique post-deploy evidence** for 6.4.1; not redundant with `phase-6-4-1-recommended-entity-capture-report.md` alone. |
| 11 | `docs/phase-6-4-1-gates-response-2026-04-22.md` | Voice spotcheck 19/1/0 summary, MINOR on “What should I do Saturday?”, manual scenarios, commit pointer. | Delivery artifact | **KEEP** | **Gate / QA record** for 6.4.1 ship; cross-links `scripts/output/voice_spotcheck_*.md`. |
| 12 | `docs/phase-6-4-1-implementation-summary.md` | Code/test list for 6.4.1, 726 tests note, voice spotcheck path, “no commit” footer (superseded by later commit). | Delivery artifact | **DELETE** | **Overlaps** tracked **`docs/phase-6-4-1-recommended-entity-capture-report.md`** and #10–#11; “no commit” section is **out of date**. Reduces clutter. **Ambiguous** — owner may **KEEP** if they want a **short** executive summary separate from the long delivery report. |
| 13 | `docs/phase-6-4-post-deploy-report-2026-04-21.md` | 6.4 session memory: commit **`4c5c7cb`**, Railway SUCCESS, prod voice Q6/Q9, manual smoke **pronoun FAIL** on “it” prior to 6.4.1. | Delivery artifact | **KEEP** | **Historically significant** deploy smoke showing **gap that motivated 6.4.1**; not duplicated elsewhere. |
| 14 | `docs/phase-6-5-docs-commit-confirmation-2026-04-22.md` | Confirms **`a9dca4d`** docs commit (`PHASE_6_5_LOCAL_VOICE_HANDOFF.md`, handoff §5 note), pushed to `origin`. | Delivery artifact | **KEEP** | **Small permanent record** of 6.5 docs-only ship. |
| 15 | `docs/phase-6-5-lite-post-deploy-2026-04-22.md` | **`35194af`** push, Railway CLI note, prod smoke `tier_used` `"2"` for Saturday night query. | Delivery artifact | **KEEP** | **Post-deploy verification** for 6.5-lite. |
| 16 | `docs/phase-8-0-1-cursor-handback-2026-04-22.md` | Cursor summary of 8.0.1 triage execution, preflight deviations, findings paragraph, `69e1a75`, no push. | Delivery artifact | **KEEP** | Pairs with committed **`docs/phase-8-0-1-triage-report.md`**; explains **process context** for Phase 8. |
| 17 | `docs/t3-24-voice-audit-sample.md` | Consolidated **t3-24** query/response/auditor FAIL / “deferred at root” for explicit-rec routing. | Owner-authored reference (via Cursor) | **KEEP** | **Active input** to **8.0.2** / explicit-rec bypass; referenced in owner notes. |
| 18 | `docs/phase-8-0-2-preflight-stop-2026-04-22.md` | Records **8.0.2 STOP** on unclean tree; lists 17 paths + pytest. | Delivery artifact | **KEEP** | **Process audit** for pre-flight discipline; should remain until 8.0.2 completes or is archived. |

---

## Proposed disposition counts (default recommendations)

| Disposition | Count | Files |
|-------------|------:|-------|
| **KEEP** | **10** (or **9** minimal) | **Default KEEP:** #3, #9, #10, #11, #13, #14, #15, #16, #17, #18. **Minimal tree:** drop #9 → **9 KEEP**. |
| **DELETE** | **8** (or **9** minimal) | #1, #2, #4, #5, #6, #7, #8, #12 — plus **#9** if owner chooses minimal tree. |
| **GITIGNORE-PATTERN** | **0** | No recurring transient file type identified that should never be tracked via a pattern (prompt files are sometimes committed intentionally). |

**Optional pattern (owner only if recurring clutter returns):**

```gitignore
# NOT recommended by default — only if owner standardizes “never commit Cursor exports”:
# docs/**/*-cursor-prompt-chat-export.md
```

---

## Ambiguous / owner-judgment rows

1. **`#9` vs `#8`:** #8 is strict duplicate of tracked prompt → **DELETE**. #9 is **review-only** → default **KEEP**, flag if owner wants one less file.

2. **`#12` vs tracked `phase-6-4-1-recommended-entity-capture-report.md`:** Overlap on “what shipped”; **DELETE** recommended for lean repo, **KEEP** if owner wants a **short** summary distinct from the long report.

3. **`#4` / `#5`:** If owner values **paste-ready 6.1.4 prompt** in git, flip #4 to **KEEP** and still **DELETE** #5 (dedupe).

---

## After this plan file is saved

**Expected:** Previous **18** untracked + **`docs/phase-8-0-1-5-housekeeping-plan.md`** → **19** untracked markdown files (until owner deletes/commits per approved plan).

---

## Completion checklist (for owner after approval)

1. Confirm **18-file** inventory (or trim to 17 per strict STOP list).
2. Approve per-row **KEEP** / **DELETE** (and optional gitignore).
3. Follow-up commit (separate phase): e.g. `git add` on **KEEP** list only, then `git clean -f` or manual delete for **DELETE** list — **not performed in 8.0.1.5**.

---

## Tests

`742 passed` (see pre-flight §3). **No code or tracked files modified** during plan authoring.
