# Pre-flight Safe Commit helper

`outputs\_preflight_safe_commit.cmd` is a small batch file lifted out of
`outputs\apply_thread_a_fix.cmd` after the v43 session (2026-05-27). It
runs three cheap checks before any state-mutating git operation and
aborts with a non-zero exit code if the working tree is not in a state
where a commit or push would be safe.

## When to use it

Call it from the top of any apply / commit / push script — anything
whose failure mode includes "the wrong content gets committed" or "a
commit gets made on the wrong branch." A typical wrapper:

```cmd
@echo off
call outputs\_preflight_safe_commit.cmd
if errorlevel 1 exit /b 1

REM ... your real work here: apply patch, run tests, stage, commit ...
```

The helper is idempotent and has no side effects beyond writing
`outputs\_preflight_staged.txt` (the snapshot it inspects). It runs in
well under a second on a clean tree.

## What each check guards against

| Check | What it inspects | Failure mode it catches |
|---|---|---|
| 1. `.git\HEAD` matches `ref: refs/heads/main` | Reads the first line of `.git\HEAD` | `.git\HEAD` silently truncated or null-byte-extended by a concurrent process. v43 hit this three times during read-only work; if a commit had run while HEAD was `ref: refs/heads/fix/t<NUL><NUL>...` the commit would have landed on a corrupt detached ref. |
| 2. `.git\index.lock` does not exist | File existence check | Another git operation is in flight, or a prior op crashed and left a stale lock. Either way, mutating the index right now is unsafe. |
| 3. `git diff --cached --name-only` is empty | Reads the staged index | Phantom staged content from a concurrent Cowork session, an IDE git extension, or a virtiofsd write-coherency artifact. v43 caught a complete revert of merged PR #18 sitting in the index while the session was doing read-only investigation. Without this check the next `git commit` would have silently reverted that PR. |

The checks are deliberately conservative: they refuse to proceed rather
than auto-repair. The error messages include a repair recipe so the
human can decide whether the precondition violation is benign (e.g.
they intentionally staged something else and ran the wrong script) or
malign (the FUSE / concurrent-session class of bugs documented in
`outputs\cowork_upstream_bug_report_fuse_stale_inode.md`).

## What it does NOT check

- **`.git\config` integrity.** v43's handoff mentions null-byte
  extension of `.git\config` as a possible failure mode, but we have
  no documented case where it caused a wrong commit (git tends to
  ignore trailing nulls in the config). Skipped to keep the script
  small.
- **`.git\HEAD` SHA matches a specific commit.** The helper verifies
  the *branch ref* is what you expect; it does not pin to a specific
  HEAD SHA. If you need that (e.g. you're applying a patch designed
  against a specific base), add a follow-up check in the caller:

  ```cmd
  for /f %%a in ('git rev-parse HEAD') do set HEAD_SHA=%%a
  if not "!HEAD_SHA!"=="6483a229a7a3c0e39d8266171af572fae4c14607" (
      echo Wrong base commit. Aborting.
      exit /b 1
  )
  ```

- **Working tree is unmodified.** The helper checks only the *index*
  (`--cached`), not the working tree. Modified-but-unstaged files are
  fine and don't trip the check — that's the usual mid-edit state.
  If your caller wants a strict "tree must be pristine" precondition,
  add `git status --porcelain` against an expected allowlist.
- **Sandbox-side FUSE staleness.** This script runs on Windows; it
  doesn't try to defend against the bash-sandbox stale-view bug
  (which is real but produces obviously-wrong output rather than
  silent wrong commits — see the FUSE bug report for the asymmetry).

## Customizing the expected branch

Default is `main`. Override by setting `PREFLIGHT_EXPECTED_BRANCH`
before the call:

```cmd
set PREFLIGHT_EXPECTED_BRANCH=fix/my-branch
call outputs\_preflight_safe_commit.cmd
if errorlevel 1 exit /b 1
```

## Provenance

- Extracted from `outputs\apply_thread_a_fix.cmd` (steps 1 and 2) in
  the v44 session (2026-05-27).
- Pattern proven in v43 — the two checks caught both the HEAD
  corruption and the phantom-revert incidents that session.
- Session handoff: `outputs\session_handoff_2026-05-27_v43_thread_a_fixed.md`.
- Upstream bug report (the underlying causes): `outputs\cowork_upstream_bug_report_fuse_stale_inode.md`.

## A note on tracking

The helper lives at `outputs\_preflight_safe_commit.cmd`. The leading
underscore matches the v43 handoff's suggested filename and **is
gitignored** by the `outputs/_*.cmd` rule in `.gitignore`. The helper
is therefore not version-controlled: it persists in your local
`outputs/` directory on disk, but a fresh checkout will not get it.

This doc is the durable record. If the helper file is ever missing,
the body of `outputs\apply_thread_a_fix.cmd` steps 1–2 plus this doc
contain enough to reconstruct it. If you want a tracked version,
rename it to drop the leading underscore (`outputs\preflight_safe_commit.cmd`)
or move it to a tracked location like `tools\preflight_safe_commit.cmd`,
and update this doc.
