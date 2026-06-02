# Working rules for Claude Code in this repo (havasu-chat)

These rules govern every session, including when `permissions.defaultMode =
"bypassPermissions"` is set. Bypass mode means the tool won't *prompt* you — it
does NOT relax these fences. Self-enforce them.

## The one thing that matters most
**`main` auto-deploys to production on Railway** (preDeploy runs `alembic upgrade
head`). So **pushing or merging to `main` = a live production deploy.** Treat it
that way.

## Never do these without Casey's explicit approval in chat
- Push or merge to `main` (it deploys to prod). Open a PR and stop.
- Any production DB write — backfills, loads, migrations applied to prod. Always
  `--dry-run` first, show the counts, and wait for approval before the real run.
- `railway` writes/deploys, or anything that reads/prints secrets or
  `railway variables`.
- Destructive git: force-push, history rewrite, or `reset --hard` that could drop
  commits that aren't already on a pushed branch.
- Destructive DB: drop/truncate/delete.
- Handling/typing API keys, tokens, passwords; solving CAPTCHAs; financial actions.

## Always
- Work on a **feature branch off `main`**, never directly on `main`. Commit freely
  there; merging is Casey's gate.
- Before every commit: `python -m pytest -q` green **and** `ruff check .` clean.
  (PowerShell: bare `pytest` doesn't resolve — use `.venv\Scripts\python.exe`.)
- Keep commits scoped; update tests in the same commit as behavior changes.
- Prod data ops follow: dry-run → show counts → Casey approves → apply.
- On a genuine judgment call (e.g. the #63 river_scene reconcile), STOP and ask —
  don't guess.

## One session per working directory
Do not operate concurrently with another session in this directory — parallel
sessions repeatedly moved git HEAD and tangled state. If another session may be
active here, confirm it's stopped before doing git work. For unavoidable
parallelism, use a separate `git worktree`, never the same checkout.

## Backstop (recommended, ask Casey to enable)
GitHub branch protection on `main`: require a PR + review, block direct pushes.
That makes the "never push to main" rule physically enforced, not just honored —
the right safety floor for bypass-permissions sessions.

## Dynamic workflows
Reserve for genuinely large, parallelizable jobs (the 5k intent phrase dataset, a
repo-wide audit). Don't spin up fan-out workflows for small sequential tasks —
they burn tokens for no speedup.
