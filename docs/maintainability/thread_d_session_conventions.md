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

## FUSE wedge when Windows switches branch on the Cowork mount

v47 reproduced issue [#62932](https://github.com/anthropics/claude-code/issues/62932) on
`.git/HEAD`: after a Windows-side `git switch` on the path Cowork has mounted, sandbox
bash can see a **truncated stale** `HEAD` (e.g. `ref: refs/heads/v47/t` instead of the
full branch name). `stat` mtime/size on `.git/HEAD` can stay stale even when content
recovers. The same bug class can wedge `.git/index` independently of `.git/HEAD`.

**Content-length-sensitive wedge (v47 hypothesis):** short → long rewrites truncate at
the cached page boundary; long → short rewrites may appear correct because the new
content fits the stale cache. Example: `git switch -c v47/thread-d-decision main` left
sandbox `.git/HEAD` at 21 bytes (`ref: refs/heads/v47/t`) while Windows held 38 bytes
(`ref: refs/heads/v47/thread-d-decision`). Merging PR #24 (38 → 21 bytes) cleared the
wedge coincidentally, not because FUSE recovered.

**Until wedge clears or session reboots**, avoid these sandbox git ops (they resolve
`HEAD` through the stale view):

| Broken in sandbox | Use instead |
| ----------------- | ----------- |
| `git rev-parse HEAD` | Read tool on `.git/HEAD`; or explicit branch ref / cmd.exe |
| `git status` | cmd.exe `git status` (or `--porcelain`) |
| `git show HEAD:*` | `git show <sha>:path` with a known SHA or branch ref |
| `git diff HEAD` | `git diff <sha>..<sha>` or `git diff <branch>..<branch>` |
| `git ls-files` | cmd.exe `git ls-files` |

Commit / push: Windows `apply_*.cmd` + preflight only (see
`docs/maintainability/preflight_safe_commit.md`).

**Convention:** multi-agent setup may switch the main checkout off `main` once; treat
that as expected FUSE friction on agent A, not a reason to skip worktrees. Prefer
**not** switching the Cowork-mounted checkout mid-session when avoidable; do code edits
in sibling worktrees when another agent needs a different branch.

Full repro notes: `outputs/v47_fuse_findings_A.md` (gitignored).

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
