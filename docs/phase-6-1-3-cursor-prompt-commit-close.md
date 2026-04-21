# Cursor prompt — Phase 6.1.3 close (commit artifacts only)

**Goal:** One commit that lands all Phase 6.1.3 **process and audit artifacts** in the repo. **No voice/code fixes** — those are 6.1.4.

---

## Task

1. `git status` — confirm the untracked set matches (or is a subset of) the list below. If unexpected untracked files appear, **STOP** and report.

2. **Stage exactly these files** (adjust paths only if `git status` shows renames):

   - `scripts/voice_audit_results_2026-04-21.json`
   - `docs/phase-6-1-3-voice-audit-report.md`
   - `docs/phase-6-1-3-execution-transcript-2026-04-21.txt`
   - `docs/phase-6-1-3-env-inspection-2026-04-21.md`
   - `docs/phase-6-1-3-kickoff-status-2026-04-21.md`
   - `docs/phase-6-1-3-execution-summary-2026-04-21.md`
   - `docs/phase-6-1-3-voice-audit-report-paste-for-owner-2026-04-21.md`
   - `docs/phase-6-1-3-owner-review-6-1-4-plan-2026-04-21.md`
   - `docs/phase-6-1-3-cursor-prompt-commit-close.md`
   - `docs/phase-6-1-4-cursor-prompt-voice-fixes.md`

3. **`git diff --cached --stat`** — should show additions for the staged docs + JSON only.

4. **Commit message** (verbatim):

   ```
   Phase 6.1.3: voice audit execution + report
   ```

5. **`git push origin main`**

6. **Report back:** commit SHA, `git log --oneline -3`, and confirm push succeeded.

---

## Scope fence

- **In scope:** Committing listed artifacts + owner review doc.
- **Out of scope:** `tier1_templates.py`, `system_prompt.txt`, `tier2_formatter.txt`, `context_builder.py`, `known-issues.md`, runner changes, re-running the audit.

---

## Acceptance

- Single commit on `main` with message above.
- Remote updated (`origin/main`).
