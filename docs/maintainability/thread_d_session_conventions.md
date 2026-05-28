# Thread D — concurrent session conventions

Adopted **2026-05-28** (v47 parallel session). Full session notes live under
`outputs/v47_threadd_decision.md` and `outputs/v47_coordination.md` (gitignored
scratchpad; this file is the durable record).

## Decision

| Option | Name | Verdict |
| ------ | ---- | ------- |
| **1** | Worktree-per-session / per-agent | **Adopt** when two or more automated agents touch the repo concurrently |
| **2** | Session-owns-branch register | **Reject** |
| **3** | Harden-and-accept-chaos (preflight) | **Adopt always** — see `preflight_safe_commit.md` |

**Hybrid:** isolate concurrent agents with worktrees; never skip preflight on commit-shaped flows.

## When to use worktrees

- **Yes:** v47-style parallel agents (runtime baseline, product profiling, FUSE repro, Thread D doc) — Casey runs `outputs/_v47_setup_worktrees.cmd` once from cmd.exe.
- **No (default):** single-agent session with a clean tree and no overlapping Casey ship window — main checkout on `main` is fine.
- **Re-evaluate** at v47 close whether worktree ceremony should become the default or stay parallel-only.

## Cowork / FUSE exception

Cowork mounts `C:\Users\casey\projects\havasu-chat` only. During parallel work that checkout stays on a **feature branch** (e.g. `v47/thread-d-decision`), not `main`. Other agents use sibling paths:

- `havasu-chat-v47-runtime` → `v47/runtime-baseline`
- `havasu-chat-v47-product` → `v47/product-work`
- `havasu-chat-v47-fuse` → `v47/fuse-investigation`

## Parallel-Casey (not solved by worktrees)

Human cmd.exe / IDE windows can still front-run prepared Cowork steps or mutate branches mid-session. Mitigations:

1. Re-verify from Windows before each prepared apply step (`git status`, `git log origin/main..HEAD`, `gh pr list`).
2. Do not trust sandbox `git status` / `wc -l` / `git show HEAD` for load-bearing tree state — use Read tool + cmd.exe.

## Boot checklist (any agent)

1. `git status --porcelain` and `git diff HEAD --stat` both empty (unless intentionally continuing WIP).
2. Confirm branch and PR state from cmd.exe before claiming a prepared step is still needed.
3. For commits: `call outputs\_preflight_safe_commit.cmd` with `PREFLIGHT_EXPECTED_BRANCH` set.

## Teardown (end of parallel session)

```cmd
cd /d C:\Users\casey\projects\havasu-chat
git switch main
git pull
git worktree remove ..\havasu-chat-v47-runtime
git worktree remove ..\havasu-chat-v47-product
git worktree remove ..\havasu-chat-v47-fuse
git branch -D v47/thread-d-decision v47/fuse-investigation v47/runtime-baseline v47/product-work
git worktree prune
```

## Background reading

- Options tradeoffs: `outputs/thread_d_session_conventions_proposal.md`
- Evidence memo: `outputs/thread_d_recommendation_memo.md`
