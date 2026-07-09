# v4.4 implementation package — READ THIS FIRST

**Written 2026-07-02 by the Cowork design session. Audience: a Claude Code session
implementing this WITHOUT asking Casey anything.**

Casey approved the v4.4 direction (mock: `ask-hava-premium-v4.4.html`, delivered via
Cowork outputs; he may drop a copy into `design-exploration/` — his convention, same as
the v4 mock). **Implementation does NOT require the mock file** — every delta is fully
specified in these docs, with exact markup and CSS.

## The three documents

1. **BUILD_PLAN.md** — mission, the PR sequence (8 small PRs, each independently
   shippable), acceptance criteria per PR, the git/test protocol, and — critically —
   **§Pre-answered decisions**: every judgment call already made. If you think you need
   to ask Casey something, check that section first; the answer is there.
2. **DESIGN_SPEC.md** — component-by-component visual deltas with exact markup/CSS
   lifted from the approved mock. Includes the guardrails (the 12-lesson feedback log
   distilled into hard rules).
3. **DATA_CONTRACTS.md** — backend contracts: gas single-source + grades + honest label
   tiers, the counting service, date-keyed caching, water temp + sunset sources with
   fallbacks, directory counts, day-activity for the date strip.

## Ground rules (non-negotiable, from CLAUDE.md — repeated here because they matter)

- `main` auto-deploys to production. Work happens on `v44-integration` (yours to
  merge into freely) via `feat/v44-<nn>-<slug>` branches. Exactly ONE thing ever
  touches `main`: the final `v44-integration → main` PR, merged under the explicit
  autonomy grant in the kickoff prompt once every gate passes (see BUILD_PLAN
  §Workflow, including the post-deploy smoke + revert protocol). Never any other
  push or merge to main.
- Remove dead code as you go: every PR deletes what it obsoletes, and PR-9 is the
  backstop sweep of the old UX (BUILD_PLAN §Dead code policy).
- Before every commit: `python -m pytest -q` green AND `ruff check .` clean.
  (PowerShell: use `.venv\Scripts\python.exe -m pytest -q`.)
- No production DB writes, no `railway` commands, no secrets. **No alembic migrations
  are needed anywhere in this plan** — if you find yourself writing one, you've
  misread a spec; re-read DATA_CONTRACTS (everything is config or computed).
- One session per working directory. Run from Casey's machine (Claude Code CLI),
  not a Cowork sandbox — sandbox git/mounts are unsafe in this repo (see CLAUDE.md).
- After code changes, run `graphify update .`.
- Update `tests/visual/refs/*` in the same PR as any visual change, and add the new
  gas-page refs when PR-6 lands.

## Order of work

Trust fixes first (PR-1..3), then visual deltas (PR-4..7), shell consolidation last
(PR-8). Do not reorder: later PRs consume services built in earlier ones, and the
sequencing mirrors Casey's stated priority (data honesty before visible change).

## Definition of done (whole package)

- All 9 work items merged into `v44-integration`, gates green at every step.
- The single `v44-integration → main` PR merged under the grant (or, if Casey
  removed the grant line, open and one click away), smoke checks passed.
- Old-UX dead code gone (PR-9 checklist), zero questions asked of Casey.
- `docs/ux-overhaul/v44/PROGRESS.md` complete (one line per item: branch, status,
  merge/PR link) so any future session can resume cold.
