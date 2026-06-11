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

## Sandbox (Cowork) sessions: the mount lies — hard rules (2026-06-10/11)
Three parallel sandbox sessions (Tracks B, C, D) independently rediscovered the
same failure modes in one night. They share ONE Linux VM (one small disk, one
/tmp), and the virtiofs mount of this checkout is unreliable in both directions:
- **Mount READS lie**: files modified during the VM's lifetime are served stale,
  size-padded with trailing NULs, or truncated. A sandbox session "discovering"
  corrupted/NUL'd files in this tree is usually describing its own mount view,
  not the Windows disk. Verify via Windows-side tools (Read/pytest/CI) before
  alarming anyone.
- **Mount WRITES corrupt for real**: bash/python writes through the mount have
  silently truncated files ON DISK (trades.py lost its final bytes). Never
  write repo files via the mount shell; use the Windows-side file tools only.
- **Never run git against this checkout from a sandbox**: stale reads mean git
  would hash and commit garbage, and lock files race Casey's own commands
  (.git/index.lock, config.lock — three collisions in one night). Working
  patterns that survived end-to-end: Casey runs all git in his terminal; or an
  isolated in-sandbox clone with `--separate-git-dir` off-mount handed back as
  git bundles (Track D); fresh content travels INTO a sandbox via a newly
  created zip of the tree (new files propagate; modified ones don't).

## Backstop (recommended, ask Casey to enable)
GitHub branch protection on `main`: require a PR + review, block direct pushes.
That makes the "never push to main" rule physically enforced, not just honored —
the right safety floor for bypass-permissions sessions.

## Dynamic workflows
Reserve for genuinely large, parallelizable jobs (the 5k intent phrase dataset, a
repo-wide audit). Don't spin up fan-out workflows for small sequential tasks —
they burn tokens for no speedup.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
