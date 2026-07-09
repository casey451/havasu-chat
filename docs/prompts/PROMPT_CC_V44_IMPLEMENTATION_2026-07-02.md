# Claude Code kickoff — implement Ask Hava v4.4, walk-away mode

**Casey: how to launch (one time).** So the session never stops to ask permission,
start Claude Code with `claude --dangerously-skip-permissions` — or drop the
provided one-line settings file into `.claude/settings.json` (sets
`permissions.defaultMode: "bypassPermissions"`, the mode CLAUDE.md already
self-enforces its fences under). Make sure no other Claude session is active in this
checkout, then paste everything below this line as the first message.

---

Implement the approved v4.4 design, trust fixes, and old-UX cleanup end-to-end,
autonomously. I am walking away; I expect to return to a finished product, not
questions.

Read, in order, before touching anything:
1. `docs/ux-overhaul/v44/README.md`   (ground rules + definition of done)
2. `docs/ux-overhaul/v44/BUILD_PLAN.md`  (workflow, 9 work items, Pre-answered decisions, dead-code policy)
3. `docs/ux-overhaul/v44/DESIGN_SPEC.md` (exact markup/CSS per delta)
4. `docs/ux-overhaul/v44/DATA_CONTRACTS.md` (backend contracts + fallbacks)

Then:
- **Step 0 — kill permission prompts for good:** if `.claude/settings.json` does not
  exist, create it as your very first action with exactly:
  `{"permissions": {"defaultMode": "bypassPermissions"}}`
  (Casey has pre-authorized this. If the harness still asks about tool use after
  that, prefer the coarsest "always allow" available once — never per-command.)
- Create `v44-integration` off `main`. Do each item on `feat/v44-NN-slug`, gate it
  (pytest green, ruff clean, visual refs updated, acceptance boxes ticked), merge it
  into `v44-integration` yourself, log it in `docs/ux-overhaul/v44/PROGRESS.md`,
  and keep moving. Work strictly in order, PR-1 → PR-9.
- Delete dead code as you go: every item removes what it obsoletes, PR-9 sweeps the
  rest of the old UX per the plan's candidate list and reference-search method.
- When all nine are in: open the single `v44-integration → main` PR with the full
  changelog, screenshots, and checklists.
- **Autonomy grant:** you have my explicit approval to merge that final PR to `main`
  yourself once every gate in BUILD_PLAN §Workflow passes — and to merge the
  emergency revert PR if the post-deploy smoke checks fail. No other merge or push
  to `main`, ever.
- Do NOT ask me questions. Every ambiguity is resolved in BUILD_PLAN
  §Pre-answered decisions; anything truly uncovered → decision 15, noted under
  "Judgment calls". Test failures, conflicts, flaky refs, missing data sources —
  resolve them yourself per the contracts.
- Before every commit: `.venv\Scripts\python.exe -m pytest -q` and `ruff check .`.
  Run `graphify update .` after code changes. No DB migrations, no railway
  commands, no secrets — nothing in this plan needs them.

Run protocol (long-session survival):
- Run continuously. No pauses between items, no status summaries addressed to me,
  no "shall I continue" — PROGRESS.md is where status lives, and the answer to
  "continue?" is always yes.
- Your context will be auto-compacted on a run this long. Treat
  `docs/ux-overhaul/v44/PROGRESS.md` as your external memory so compaction loses
  nothing: after every gate pass AND before starting each item, record one line
  each — current branch, last commit sha, gates status, and **NEXT ACTION** —
  detailed enough to resume from the file alone. If you ever feel context-thin
  (post-compaction haziness), re-read the four docs and PROGRESS.md before acting.
- If you are a fresh session reading this after an interruption: read PROGRESS.md
  first, then the four docs, and continue from NEXT ACTION. Do not redo finished
  work; trust the gates already recorded.

Deliverable: v4.4 live, old UX gone, PROGRESS.md complete, smoke checks passed.
