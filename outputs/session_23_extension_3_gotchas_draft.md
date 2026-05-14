# Session-23-extension-3 Gotchas Draft

> Captured during session-23-extension-3 (2026-05-13) Phase 6 build kickoff. Two new patterns worth folding into `docs/maintainability/dispatch_channels.md` as gotchas. Numbering left as `<<<NEXT>>>` — operator confirms whether to slot as #18 / #19 (depending on whether the kickoff's referenced "gotcha #18 file-scope disjointness" has been formally added to dispatch_channels.md yet; if not, this session's items may be #18 and #19, or the file-scope rule lands as #18 and these become #19 and #20).
>
> Both items emerged in the session-23-extension-3 setup phase (before Phase 6.1 Cursor dispatch). Both have concrete operator action that worked; documenting so future sessions don't burn time on the same diagnosis.

---

## Gotcha #<<<NEXT>>>: Linux mount staleness persists through Windows-side `git restore` — the mount caches file CONTENT, not just stat() metadata.

**Session-23-extension-3 surface:** Cowork primary inspected working tree from the Linux sandbox after a chain of state-restoration steps and saw 29 modified files with destructive content truncations (master_build_plan.md showing 280 lines vs HEAD's 615; models.py 1475 vs 1539; multiple test files truncated; scripts/places_load.py losing 78 lines from mid-function). Recommended PowerShell sequence `Remove-Item .git\index.lock; git restore --staged .; git restore .` to revert all working-tree drift. Operator ran the sequence; Windows-side `git status --short` after the restore returned only ONE line (the staged deletion of a busted-quote filename). But Cowork primary's Linux-side `git status` returned the same 29 modified files with the same truncated content — `wc -l` from Linux STILL reported master_build_plan.md at 280 lines after the Windows `git restore .` should have restored it to 615.

**Root cause:** the Linux mount of the Windows workspace folder caches file CONTENT, not just stat() metadata. When operator's PowerShell `git restore .` updated file content on the Windows filesystem, the Linux mount's content cache was not invalidated. Linux-side reads (including `git status` which hashes file content to detect changes) saw the stale pre-restore content and reported the files as still modified. Windows-side `git status` and `git diff` saw the real (restored) content and reported clean.

**Disambiguation method used:** Cowork primary asked operator to run `git diff --stat` from PowerShell side; output returned a clean single-line result (only the garbled file deletion). That confirmed the Linux mount was the unreliable side, not the Windows working tree. The operator's `git status --short` returning clean was the authoritative answer.

**Scope:** this extends gotcha #4 (bash mount staleness) — #4 covered the unreliability of `.git`-internal reads from Linux. Today's pattern adds: **working-tree file content reads from Linux are also stale after Windows-side mutations**, and the staleness persists beyond just the immediate next read. The Linux mount holds the cache across an entire session — `sync`, `cat`, re-running `wc -l`, none of those invalidate it. Only force-touching the file from Windows side (e.g., editing + saving in a Windows-side editor, or `Set-Content` overwrites) flushes the cache.

**Cure:**
1. **Trust the Windows-side `git` output** for working-tree status; the Linux mount is best-effort for context-building but unreliable for stateful operations.
2. **Use `git show HEAD:<path>`** when reading file content from Linux side — this reads from `.git/objects` (which the mount caches consistently) rather than the working tree.
3. **When Linux and Windows views diverge on file content**, treat Windows as authoritative without further investigation. The mount's content cache can stay stale for the duration of the session.

**Companion lesson:** when proposing a multi-step PowerShell sequence with a `git status --short` sanity-check at the end, always ALSO ask operator to run `git diff --stat` (which checks content) — `git status --short` alone shows only the file-level state (modified/staged/untracked) but `git diff --stat` shows content deltas, and the two can diverge if working tree appears modified due to mount staleness vs real content drift. Today's setup phase had a 15-minute false-alarm cycle that `git diff --stat` from PowerShell resolved in two seconds.

---

## Gotcha #<<<NEXT+1>>>: Pasting Cowork message text into Cursor's chat input causes Cursor to EXECUTE embedded shell commands.

**Session-23-extension-3 surface:** after Cowork primary primed the operator's clipboard with the Phase 6.1 dispatch prompt body via `Get-Content outputs\cursor_dispatch_prompt_phase_6_1.md | Select-Object -Skip 17 | Select-Object -SkipLast 31 | Set-Clipboard`, operator opened a fresh Cursor session and pasted... not the clipboard (with Ctrl+V), but **the entire Cowork message text** containing the explanation + the PowerShell pipeline as a code block. Cursor parsed the message, saw the `Get-Content` command in a code fence, and **ran it in its own terminal** — producing a near-identical-sounding confirmation message ("Running the PowerShell pipeline to copy the selected lines to the clipboard. The command finished successfully (exit code 0)..."). Cursor's response read so similarly to Cowork primary's that the operator initially didn't realize the dispatch prompt itself was never actually sent to Cursor — only the wrapper message about the dispatch prompt.

**Root cause:** Cursor's chat input accepts free-form text. When the input contains a triple-backtick PowerShell code block, Cursor's agent interprets the block as an instruction to execute the command (because it has terminal access). The agent's response style — confirming command execution with similar prose conventions to Cowork primary — masks the disconnect.

**Three things were happening simultaneously:**
1. Operator pasted Cowork primary's response message (intent: pass info to Cursor)
2. Cursor parsed embedded PowerShell command and ran it (intent: helpfully execute commands)
3. Operator's clipboard got re-primed with the dispatch prompt body (side-effect of Cursor running the pipeline) — meaning the system clipboard state was correct, just not what Cursor itself had received

**Disambiguation:** operator surfaced "that was in cursor" with a screenshot. Cowork primary spotted the Cursor agent's response in the screenshot and recognized the wording was Cursor's (not Cowork's earlier message reproduced), which meant Cursor had executed something. Identified the issue: Cursor never received the dispatch prompt; the operator needs to actually paste from clipboard into Cursor's chat input (separate paste action — not the same as pasting the explanatory message).

**Cure:**
1. **When priming the clipboard for paste into Cursor**, give the operator EXPLICIT instruction to: (a) click Cursor's chat input field, (b) Ctrl+V to paste, (c) Send. Don't bury the action inside a longer explanation.
2. **Distinguish "this clipboard content goes to Cursor's chat input"** from "this PowerShell command runs in your terminal." Make the destination explicit per action.
3. **If the Cowork message must contain a PowerShell snippet AND something that should go into Cursor**, separate them visually — put the PowerShell in a non-code-fenced inline form (or label it clearly as "run in PowerShell, NOT Cursor") so Cursor doesn't auto-execute if the operator accidentally paste-routes the whole message.
4. **As a Cursor recipient**: if a chat message contains both an explanation AND a code block that LOOKS like a command, ask the operator before executing — don't run the command and silently produce confirmation prose that reads like the explanation's continuation.

**Scope:** multi-tool workflows where the operator routes the SAME copy-pasted text through Cowork (clarify intent) + PowerShell (run command) + Cursor (dispatch task) are prone to this pattern. Per dispatch_protocol Rule X (channel-pick playbook), the cleanest path is: Cowork generates a paste-ready dispatch prompt as a separate file; operator copies that file's content into clipboard via `Get-Content | Set-Clipboard`; operator pastes from clipboard directly into Cursor's chat input (NOT pasting any wrapper messages). The session-23-extension-3 incident burned ~10 minutes resolving a confused "what did Cursor actually receive" state.

**Companion lesson:** when verifying that Cursor has actually been dispatched, ask operator to confirm: (a) what they pasted (the literal first few lines as Cursor sees them), and (b) Cursor's first response (which should be its baseline-values report per the dispatch prompt's §0). If Cursor's first response is anything other than `git log` + pytest + alembic baseline output, something else got pasted.

---

## How to fold these into dispatch_channels.md

Both items follow the existing gotcha-format pattern (`**N. Title.** Session-XX surface: ... Root cause: ... Cure: ... Scope: ...`). Suggest:

1. **Confirm the kickoff's "gotcha #18 file-scope disjointness" status.** The kickoff references it by number; if it's already in dispatch_channels.md, then today's items become #19 and #20. If not yet committed (it's a session-23 extension lesson), file-scope disjointness lands as #18, mount-staleness-extension as #19, paste-routing-confusion as #20.
2. **Append to dispatch_channels.md after gotcha #17** with the new numbered entries.
3. **Update gotcha #4** with a cross-reference: "See gotcha #<<<N>>> for the post-`git restore` content-cache extension."
4. **Commit as a small docs chore** alongside the Phase 6.1 close-out docs commit (so it lands with related session work).

---

*Authored at session-23-extension-3 (2026-05-13) pre-positioned during Phase 6.1 in-flight execution. Lives at `outputs/session_23_extension_3_gotchas_draft.md`. Operator reviews + commits to dispatch_channels.md with appropriate numbering.*
