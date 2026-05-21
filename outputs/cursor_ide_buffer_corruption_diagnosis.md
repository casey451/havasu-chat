# Cursor diagnostic dispatch — IDE buffer corruption pattern (recurring)

> **What this is:** Investigation + durable preventive recommendation. The havasu-chat working tree has been corrupted three times by what appears to be an IDE editor-buffer collision. Each time: tracked files get truncated mid-line (e.g., `tier2_handler.py` ends with `fi, fo =` no newline; `ranking.py` ends with bare `re`), new files survive intact, but modifications to existing tracked files get silently regressed.
>
> **Your job:** diagnose root cause + recommend durable preventive workflow. **Read-only investigation** — do NOT modify any source files; the recovery work lives in a separate dispatch at `outputs/cursor_recovery_phase_7_7_1_plus_8a_0.md`.
>
> **Time-box:** ~45-60 min. Report findings; do not implement.

---

## §0 Boot prereqs

```powershell
cd C:\Users\casey\projects\havasu-chat
git log --oneline -5
```

Expected origin/main tip at dispatch time: at or after `d2e3867`. The actual tip may have advanced if recovery patches landed concurrently — verify and note.

```powershell
git status --short
```

If the tree is dirty with M files on tracked files (especially `tier2_handler.py`, `unified_router.py`, conditions fetchers, conftest.py) — corruption is currently active. Note that as part of your §1 evidence.

---

## §1 The pattern

Three confirmed corruption events this session:

### Event #1 — initial Phase 8a Cursor dispatch (2026-05-20 evening)

- Cursor terminal session ran `python -m pytest` + wrote files for Phase 8a deliverables (~53 files)
- New files (`app/conditions/`, `app/alerts/`, `alembic/versions/d1e2f3a4b5c6_*`, etc.) wrote correctly
- Modifications to EXISTING tracked files were corrupted: `app/chat/tier2_handler.py` ended with `fi, fo =` (no newline), missing 64 lines vs HEAD
- Cursor's §12 report claimed success — test counts + ruff clean. The §12 disagreed with disk state.
- Casey caught it pre-commit via `git diff HEAD --stat` showing -637 line deletions across files Phase 8a should not have touched
- Operator stashed at `8a-collision-corrupted-tree-2026-05-20`

### Event #2 — Phase 8a re-dispatch (2026-05-20 evening)

- Casey opened a FRESH Cursor chat (per Cowork-primary's instruction)
- Re-dispatched the same Phase 8a wrapper
- **Same corruption pattern reproduced** — identical byte-position truncations on identical files
- Cursor's §12 claimed identical success (27 Phase 8a tests pass, 2251 collected)
- Diagnosis at the time: multi-window IDE editor-buffer collision. The first Cursor IDE window still had stale buffers from event #1 open. When the new chat's terminal Cursor finished its writes, the IDE's autosave / focus-change clobbered the freshly-written files with in-memory truncated content from the first session.
- Recovery: "Lane Z" surgical sub-agent using the Edit tool (writes through agent's filesystem API, not the IDE buffer chain). Worked.

### Event #3 — Phase 7.7.1 + Phase 8a.0 patch loss (2026-05-21)

- After Phase 8a shipped + Phase 7.7.1 (q10/q12 disclosure widening) was applied via Edit tool + Phase 8a.0 (fetcher signature hotfix) was applied via Edit tool, the working tree showed:
  - Validator code edits PERSISTED (`_coerce_disclosure_path`, `_disclosure_matches`, `_expected_includes_cited` all present in `app/chat/halt3_validator.py`)
  - YAML widening at `app/chat/halt3_eval_set.yaml:61-66` (q10) and `:74-79` (q12) was REVERTED to singular `cited`
  - Fetcher hotfix at `app/conditions/airnow.py:38`, `nws.py:30`, `usgs.py:38` was REVERTED
  - `tests/conftest.py` (which was already committed at `d2e3867`) showed as M with -20 LOC vs HEAD
- The validator full eval surfaced the regression: q10 FAILed with "disclosure expected cited, got i_dont_know" — proving the YAML widening was lost
- The fetcher signature bug re-emerged when `railway run python -m scripts.fetch_external_conditions --all` was attempted: all 6 sources failed with the same `RuntimeError: fetch exhausted for <source>` pattern from earlier diagnosis

---

## §2 Hypotheses to investigate

Rank-ordered by plausibility based on Event #2 + #3 evidence.

### H1 — Multi-window Cursor IDE editor-buffer collision (most likely)

Multiple Cursor IDE windows (or one Cursor + one VS Code, etc.) had the corrupted/stale file buffers from Event #1 still open. Each subsequent edit (via agent Edit tool or terminal write) succeeds momentarily; then when the IDE window gains focus or autosave fires, the IDE writes its in-memory stale buffer to disk, clobbering the fresh content.

**Investigation:**

1. Check whether Cursor IDE has an autosave feature + what triggers it. Read Cursor's settings docs.
2. Check if Cursor IDE persists open-file state across "close window" → "reopen later" — if yes, stale buffers can survive a fresh chat dispatch.
3. Inspect `C:\Users\casey\AppData\Roaming\Cursor\` for any state files indicating multi-window persistence.
4. Look at process tree:
   ```powershell
   Get-Process -Name "Cursor" -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime
   ```
   If multiple Cursor PIDs are running, each is potentially editing files.

### H2 — Cursor agent itself has a buggy write path

The Cursor agent's terminal write commands may have a bug where successive writes within one session truncate. Less plausible because the diagnostic in Event #1 showed truncation at consistent byte positions across files — which suggests a buffer-state hazard, not a write-truncation bug.

**Investigation:**

1. In a controlled environment with NO other IDE windows open, run a small Cursor dispatch that modifies a single tracked file. Verify the result.
2. Inspect Cursor agent logs for any "write incomplete" or "partial flush" warnings.

### H3 — File watcher / formatter race condition

Some tool (ruff, black, isort, prettier) configured as on-save formatter is running concurrently with the agent's writes and clobbering them.

**Investigation:**

1. Check `pyproject.toml` for ruff / black format-on-save hooks.
2. Check `.vscode/settings.json` if present.
3. Check `.git/hooks/` for any pre-commit / post-checkout hooks that touch files.

### H4 — Git index lock interference

The cross-mount workspace (Linux bash VM accessing Windows-owned `.git/`) leaves `.git/index.lock` artifacts. While the user has clean ownership, the lock can interfere with git ops mid-write.

**Investigation:**

1. Check if `.git/index.lock` exists right now.
2. Look at `git reflog` for unusual reset / checkout / restore activity around the corruption events.
3. Cross-reference timestamps: did `git restore` or `git stash` run during the corruption window?

### H5 — Antivirus / Windows Defender / Dropbox-style sync stripping content

A background sync agent might be observing file changes and reverting them.

**Investigation:**

1. Check if the repo is inside a Dropbox / OneDrive / Google Drive sync folder (it shouldn't be — should be `C:\Users\casey\projects\havasu-chat\`).
2. Windows Defender's Controlled Folder Access feature can block app writes silently.
3. Check Windows Event Log for any "file modification reverted" or similar entries.

---

## §3 Diagnostic protocol

For each hypothesis, run a discrete probe:

### Probe 1 — Process inventory (~5 min)

```powershell
Get-Process -Name "Cursor", "Code", "Code - Insiders" -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime, MainWindowTitle
Get-Process | Where-Object {$_.ProcessName -match "cursor|vscode|code"} | Select-Object Id, ProcessName, Path
```

Report: how many Cursor/VS Code/Code processes are running RIGHT NOW.

### Probe 2 — Cursor settings inspection (~10 min)

Read:
- `C:\Users\casey\AppData\Roaming\Cursor\User\settings.json`
- `C:\Users\casey\AppData\Roaming\Cursor\User\keybindings.json`

Report any settings related to:
- `files.autoSave`
- `editor.formatOnSave`
- `editor.formatOnSaveMode`
- Any `*.python.*` settings that include formatting

### Probe 3 — Project-level config (~5 min)

Read:
- `pyproject.toml`
- `.vscode/settings.json` (if exists)
- `.editorconfig` (if exists)

Report any format-on-save / file-watcher configuration.

### Probe 4 — Git state forensics (~10 min)

```powershell
git reflog --date=iso | Select-Object -First 20
```

Report any unusual `reset`, `checkout`, `restore`, `stash` operations in the last 24 hours.

```powershell
Test-Path .git\index.lock
```

Report whether the lock exists right now.

### Probe 5 — Sync folder check (~5 min)

```powershell
$repo = "C:\Users\casey\projects\havasu-chat"
$parent = (Get-Item $repo).Parent.FullName
Write-Host "Repo parent: $parent"
Write-Host "Repo is in Dropbox: $(Test-Path "$repo\.dropbox")"
Write-Host "Repo is in OneDrive: $((Get-Item $repo).FullName -match 'OneDrive')"
```

Report any sync folder enclosure.

### Probe 6 — Reproduce in isolation (~15 min)

In a freshly-opened PowerShell window (NO Cursor IDE running):

```powershell
cd C:\Users\casey\projects\havasu-chat
git status --short  # should be clean
echo "# test marker for IDE corruption diagnostic" >> README.md
Start-Sleep -Seconds 10
$content = Get-Content README.md -Raw
if ($content -match "test marker for IDE corruption diagnostic") {
  Write-Host "PERSIST: marker survived 10s" -ForegroundColor Green
} else {
  Write-Host "CLOBBERED: marker was wiped" -ForegroundColor Red
}
git checkout -- README.md  # clean up
```

If the marker survives → no active corruption. If wiped → corruption is mechanistic and ongoing.

---

## §4 Recommended preventive measures

Based on whatever the §3 probes surface, recommend a durable workflow. Examples (don't recommend blindly — base on evidence):

- **If H1 confirmed:** Document a "Pre-Cursor-Dispatch Checklist": close all IDE windows, kill stray processes via Task Manager, then verify with `Get-Process` before dispatching.
- **If H2 confirmed:** Open a Cursor bug report; document the workaround (use Edit tool exclusively for tracked-file modifications during multi-session work).
- **If H3 confirmed:** Disable format-on-save during Cursor sessions, OR ensure formatter config doesn't conflict with the agent's writes.
- **If H4 confirmed:** Don't run cross-mount bash + Windows git ops simultaneously; document the workflow split.
- **If H5 confirmed:** Move repo out of sync folder; add Windows Defender exclusions if needed.

---

## §5 Documentation deliverable

Author a new doc at `outputs/ide_buffer_corruption_diagnostic_report.md` with:

1. **§1 Pattern summary** — paraphrase the three events from §1 above.
2. **§2 Diagnostic evidence** — paste the output of all 6 §3 probes verbatim.
3. **§3 Root cause verdict** — which hypothesis is confirmed (with evidence) vs ruled out (with evidence).
4. **§4 Preventive workflow** — concrete pre-dispatch checklist + workflow recommendations.
5. **§5 What to do if corruption reoccurs** — recovery playbook (mirroring the Lane Z surgical Edit-tool pattern from Phase 8a).

The doc should be ~150-250 lines, narrative + tables where helpful, no padding.

---

## §6 Out-of-scope hard rules

- **Do NOT modify any source files.** This is diagnostic only.
- **Do NOT commit.** The doc itself is a new artifact — the operator commits when ready.
- **Do NOT recommend a fix for the validator or fetchers.** Those are scoped to the parallel recovery dispatch at `outputs/cursor_recovery_phase_7_7_1_plus_8a_0.md`.
- **Do NOT speculate beyond evidence.** If a probe is inconclusive, say so. Bail on a hypothesis when evidence rules it out.

---

## §7 Final report

When done, summarize:

1. Hypothesis verdict (which H1-H5 confirmed/refuted/inconclusive).
2. Confidence level (HIGH / MEDIUM / LOW).
3. Single most-important preventive action the operator should take.
4. File path of the new diagnostic doc.
5. Time spent.

---

*Authored 2026-05-21 post-IDE-corruption-replay-#3. Saved to `outputs/cursor_ide_buffer_corruption_diagnosis.md`. Companion to recovery dispatch at `outputs/cursor_recovery_phase_7_7_1_plus_8a_0.md`.*
