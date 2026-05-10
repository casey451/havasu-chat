# Dispatch Protocol — Working Agreements

This document is for the next agent picking up work on havasu-chat. Read it before any dispatch, branch work, smoke testing, cleanup, or commit activity. Every rule below was learned the hard way during the 2026-05-09 marathon session after collisions, truncations, stale mounts, broken migrations, and recovery work that burned hours unnecessarily.

## 1. Anchored Edit over full-file Write on shared files

**Rule** — Use Anchored Edit for existing shared files. Do not full-file rewrite them.

**Why** — Full-file writes caused truncation and overwrite incidents. Anchored edits held stable through the entire 2026-05-09 session with zero collisions.

**Example**

```text
Edit only the specific function in app/chat/router.py.
Patch the exact validator block.
Leave the rest of the file untouched.
```

**Counterexample**

```text
Agent rewrites the entire router file for a 6-line fix.
Another lane modifies adjacent logic.
One write silently destroys the other lane's work.
```

## 2. Wait for the text report before any git add

**Rule** — Do not run `git add` until the agent explicitly reports completion in text.

**Why** — Working-tree state is unreliable while agents are still writing files. Mid-flight staging captured incomplete work and broke production migrations.

**Example**

```text
Agent finishes edits.
Agent reports tests passed, files modified, final SHA.
Only then stage files intentionally.
```

**Counterexample**

```text
git add -A runs while Cursor is still writing Lane 4.
Partial alembic state gets committed with unrelated work.
Railway deploy breaks with multi-head migrations.
```

## 3. Dispatch sequentially when lanes touch overlapping files

**Rule** — If two lanes touch overlapping files, run them sequentially.

**Why** — Parallel work against shared files creates race conditions, silent overwrites, and invalid migration states.

**Example**

```text
Lane A modifies app/db/models.py.
Lane B waits until Lane A commits and reports complete.
```

**Counterexample**

```text
Two agents edit alembic/versions simultaneously.
One migration disappears.
Database history becomes unrecoverable.
```

## 4. Use PowerShell single-quoted bodies with Invoke-RestMethod

**Rule** — In PowerShell, use single-quoted request bodies for `Invoke-RestMethod`.

**Why** — Double quotes interpolate `$variables` and corrupt payloads, especially Railway credentials and URLs.

**Example**

```powershell
Invoke-RestMethod `
  -Uri 'https://example.com/api/chat' `
  -Method POST `
  -ContentType 'application/json; charset=utf-8' `
  -Body '{"query":"pizza"}'
```

**Counterexample**

```powershell
-Body "{\"query\":\"pizza\"}"
$password inside the payload gets interpolated.
Request body becomes invalid JSON.
```

## 5. Do not use curl.exe --data-binary for chat API smoke tests

**Rule** — Use `Invoke-RestMethod` for chat API smoke testing. Avoid `curl.exe --data-binary`.

**Why** — `curl.exe` mangled JSON payloads repeatedly and created false-negative debugging sessions.

**Example**

```powershell
Invoke-RestMethod `
  -Uri 'http://localhost:8000/api/chat' `
  -Method POST `
  -ContentType 'application/json; charset=utf-8' `
  -Body '{"query":"mudshark brewery"}'
```

**Counterexample**

```powershell
curl.exe --data-binary $body ...
JSON encoding breaks.
Team wastes 45 minutes debugging the wrong layer.
```

## 6. Anchored Edit for existing files, Write only for new files

**Rule** — Use the Write tool only when creating brand-new files.

**Why** — Existing-file writes increase overwrite risk dramatically in multi-agent sessions.

**Example**

```text
New docs/maintainability/dispatch_protocol.md → Write is fine.
Existing app/chat/router.py → Anchored Edit only.
```

**Counterexample**

```text
Agent uses Write on an existing 700-line file.
Another lane's changes vanish completely.
```

## 7. Treat Windows-side reads as authoritative over Linux mounts

**Rule** — Trust Windows-side file reads over Linux bind mounts when they disagree.

**Why** — The Linux-mounted workspace occasionally serves stale or truncated file contents.

**Example**

```text
Use:
C:\Users\casey\projects\havasu-chat\...

Verify with Read tool from the Windows path.
```

**Counterexample**

```text
bash cat on /mnt/havasu-chat shows truncated file.
Agent assumes corruption and "fixes" a healthy file.
New corruption gets introduced.
```

## 8. Keep commits isolated per lane

**Rule** — One substantive lane per commit.

**Why** — Mixed-lane commits destroy rollback clarity and make recovery work much harder.

**Example**

```text
Commit 1:
fix(chat): scorer regression

Commit 2:
docs: smoke catalog updates
```

**Counterexample**

```text
One commit contains:
- matcher rewrite
- migration change
- caching fix
- docs cleanup

Rollback becomes impossible without collateral damage.
```

## 9. Purge production cache through Railway SQL only

**Rule** — Purge `llm_response_cache` using Railway's SQL console.

**Why** — Direct `DATABASE_URL` handling created credential and environment mistakes repeatedly.

**Example**

```sql
DELETE FROM llm_response_cache;
```

Path:

```text
Railway → Postgres → Data → Query
```

**Counterexample**

```text
Manual DATABASE_URL exports.
Wrong environment targeted.
Cache remains stale or production data gets hit accidentally.
```

## 10. Run adversarial smoke verification after matcher/scorer changes

**Rule** — Every matcher, scorer, or classifier change gets an adversarial smoke pass.

**Why** — "Looks correct" changes repeatedly failed under real-world phrasing.

**Example**

```text
Run:
docs/maintainability/backlog_46_smoke_check_queries.md

Verify all 39 queries.
```

**Counterexample**

```text
Matcher tweak ships without smoke testing.
Cross-category leakage returns.
Production answers degrade immediately.
```

## 11. Force-stop agents before cleanup operations

**Rule** — Stop Cursor, Claude Code, and CC agents before any working-tree reset.

**Why** — Active agents continue writing after cleanup and silently re-corrupt files.

**Example**

```text
Stop all agents.
Then run:
git checkout -- .
git clean -fd
```

**Counterexample**

```text
Cleanup runs while Cursor is still active.
Files immediately reappear or re-corrupt.
Operator thinks git is malfunctioning.
```

---

If you only remember three things: use Anchored Edit on shared files, wait for the explicit text report before staging anything, and never run overlapping lanes in parallel against the same files. Almost every catastrophic failure from the 2026-05-09 session came from violating one of those three rules. The rest of this protocol exists to reinforce them.
