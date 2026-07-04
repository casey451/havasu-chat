# v4.6 implementation package — the finish line

**Written 2026-07-04 after the live QA sweep of deployed v4.5 (main @ `b82078b1`).
Audience: a Claude Code session implementing this WITHOUT asking Casey anything.**

v4.4 rebuilt the core surfaces; v4.5 migrated the interior. v4.6 finishes: three
polish items found in live QA, the last seven surfaces still on `base_lake`, and
then the old shell gets deleted for good. After this there is ONE shell.

## Documents

1. **BUILD_PLAN.md** (this folder) — 3 work items + §Pre-answered decisions.
2. **Inherited, still the law:** `../v44/DESIGN_SPEC.md` (§0 guardrails +
   components), `../v44/DATA_CONTRACTS.md`, `../v44/BUILD_PLAN.md` decision 15.
3. **Read the previous runs' memory:** `../v44/PROGRESS.md` and `../v45/PROGRESS.md`
   ("Fixed facts" — worktree-locked main, files never to stage, gate commands,
   the RISE gauge fix, what was deliberately kept).

## Ground rules (identical to v4.4/v4.5 — two clean runs prove them)

- `v46-integration` off `origin/main`; items on `feat/v46-NN-slug`; self-merge
  gated items into the integration branch; ONE final PR to `main` merged under
  the kickoff autonomy grant after all gates + post-deploy smoke.
- Gates: `.venv\Scripts\python.exe -m pytest -q` green, `-m ruff check .` clean,
  mypy, `graphify update .`; refs captured from the local render per v45 §Refs.
- `docs/ux-overhaul/v46/PROGRESS.md` from the first commit; judgment calls logged.
- Dead code dies with its replacement; PR-2 is the terminal sweep.
- No DB migrations, no railway commands, no secrets. Zero questions to Casey.
