# Dispatch channels — operator playbook

This document is the *how-to* companion to `docs/maintainability/dispatch_protocol.md` (which covers the 12 working-agreement rules). Use this doc when picking which channel to route a piece of work to and how to write the prompt. Use the protocol doc when you're about to do something with `git`, edit a shared file, or run a smoke test.

---

## The five channels

You (the Cowork primary) have five effective ways to get work done. The first four are paste-based or operator-mediated; the fifth is direct.

### 1. Cursor — focused single-file edits

**Best for:** bounded code changes with precise scope. Single-file or small multi-file lanes. Schema migrations. Operator scripts. Anything where the diff should be small and reviewable.

**Pattern:** you write a self-contained dispatch prompt → operator (Casey) pastes it into a fresh Cursor chat → Cursor returns a text report → Casey pastes the report back to you → you review the diff and propose the commit recipe.

**Strengths:** anchored-Edit-friendly, executes cleanly when scope is well-defined, good at "do exactly this and report back."

**Weaknesses:** occasionally ships pragmatic deviations from the dispatch and reports them at the end (re-read for "deviation" callouts before integrating). Has been observed bundling unrelated working-tree changes into commits despite explicit constraints (the *absorption pattern* documented in `2026-05-10_absorption_forensics.md`). Solution: instruct Cursor to report ship-log entry text rather than editing `BACKLOG.md` directly; you add the entry after the commit lands.

**Prompt anatomy:**
1. Context (1-2 paragraphs — what's the ticket, what's the production state, what's blocked elsewhere)
2. Scope (numbered steps, files to touch, files to leave alone)
3. Constraints (anchored Edit only, don't run `git add -A`, don't push, don't amend)
4. Report format (files modified, tests added, pytest before/after, SHA, ship-log text)

**Recent example dispatches** (look at the corresponding ship-log entry in `BACKLOG.md` for the executed result):
- `#50` (matcher floor) — single-file edit
- `#56` (UTF-8 wire test) — single new test file
- `#57 + #59` bundle — two related tickets in one prompt

### 2. Claude Code — heavy multi-file lanes

**Best for:** multi-file refactors, audit lanes, comprehensive test-suite generation, architectural investigations. Anything where "investigate first, then ship" is the right shape.

**Pattern:** same paste-based as Cursor.

**Strengths:** handles multi-file scope without losing the thread. Strong at "investigate this and propose a fix" lanes. Comprehensive test coverage. Proactive about halt-and-report when scope is unclear (this is good behavior — encourage it explicitly in your prompts).

**Weaknesses:** can over-investigate when given an unbounded prompt. Brief-baseline-staleness pattern: pytest counts and SHAs in dispatch briefs go stale during execution; CC has flagged this 4+ times. Mitigation: instruct CC to run `git pull && pytest -q --collect-only | tail -1` as brief step 0 to confirm the actual baseline at execution time.

**Prompt anatomy:** same as Cursor, plus:
- Multi-phase scope: investigation → design → implementation → tests → commit
- Halt-and-report etiquette: tell CC explicitly when to stop. Investigation phases should always allow stopping if scope is bigger than expected. The session 2026-05-10 #51 and #56 ships are good models — both halted appropriately.

**Recent example dispatches:**
- `#51` (UTF-8 charset patches) — investigation + halt-and-report (turned out to be smoke-harness encoding artifact, not an app bug)
- `#58` (delegating-entry floor coverage) — investigation + ship
- chat-route integration test — halted with 4 scoping decisions, shipped reduced scope

### 3. ChatGPT — pure prose, no codebase access

**Best for:** anything that doesn't need codebase access. Cold-email drafts, FAQ writing, operator-facing documentation, brainstorming, market research, copy editing.

**Pattern:** you write the prompt → Casey pastes to ChatGPT → ChatGPT returns text → you write to file via the Write tool, polishing markdown structure on the way in.

**Strengths:** fast, no file-access overhead. Good at structured creative work when given clear voice/format anchors.

**Weaknesses:**
- Cannot read codebase, cannot verify product reality. Use `[CASEY: confirm <fact>]` placeholders in prompts for facts ChatGPT can't ground.
- Tends to skip markdown structure (no `#`/`##`/`---`) — always do a polish pass on save.
- Auto-appends tracking parameters to URLs (e.g., `?utm_source=chatgpt.com`) — strip them.
- Drifts toward marketing speak ("amazing," "thrilled," "excited") — explicitly ban these in the prompt.

**Prompt anatomy:**
1. Context (1-2 sentences — what's this for, who reads it)
2. Voice anchor — paste an excerpt of existing prose that matches the target voice; tell ChatGPT to match it exactly
3. Output requirements (sections, length, tone)
4. Constraints (no exclamation points, no marketing speak, sign-off conventions, fact-check placeholders)

**Recent example dispatches:**
- Three new cold-email variants (restaurants, boat repair, auto repair) — voice-matched against existing variants
- Reply handlers (yes/no/questions/follow-up) — operator-facing email templates
- End-user FAQ — first content under `docs/user_facing/`
- Lake Havasu seasonality calendar — operator reference for sprint pacing

### 4. Sub-agents — your Agent tool

**Best for:** parallel verification, code review, voice-battery / adversarial testing, doc audits, recovery investigations, forward-looking forensics.

**Pattern:** you dispatch directly via your `Agent` tool with a self-contained prompt. The agent runs in its own context window and returns a text report. **No operator round-trip needed.**

**Strengths:** parallel work that doesn't block the main conversation. Has full file tools + bash. Good at "go investigate X and report back." Can write files, but should be instructed not to (the operator's commit workflow expects deliberate staging).

**Weaknesses:**
- Burns YOUR context (the agent's report comes into your context). For long sessions this adds up.
- Parallel commits can race the operator's git workflow. Always instruct sub-agents not to run any git operations.
- Multiple sub-agents in parallel can race each other on shared files. Stay in non-overlapping file domains.

**Prompt anatomy:**
1. Context (current production HEAD, pytest baseline, what's already in flight elsewhere)
2. Scope (file domain — explicit allowlist of files the agent may touch)
3. What NOT to touch (every other file, especially files other in-flight lanes are using)
4. Constraints (no git operations, use Read with Windows-side paths preferred, anchored Edit only)
5. Report format (what to return as text)

**Recent example dispatches:**
- Cross-`docs/` reference audit (subsumed `#54`) — read-only forensics
- Post-enrichment smoke catalog draft — forward-looking artifact
- HALT 3 close-out template — forward-looking artifact
- Absorption-pattern forensics + Rule 13 candidate — recommendation was DON'T add Rule 13

### 5. Yourself — direct file tools

**Best for:** small docs edits, `BACKLOG.md` status flips after a ship lands, anchored Edits to known files, writing prose ChatGPT just produced.

**Pattern:** Read first if needed, then Edit/Write directly.

**Strengths:** zero operator burden, immediate feedback.

**Weaknesses:** burns your context if reading large files. The bash mount is unreliable for `git` operations (Rule 7 of dispatch protocol — Linux mount serves stale views; Windows-side Read is authoritative).

---

## Picking a channel

| Work shape | Channel |
|---|---|
| Single-file edit, code | Cursor |
| Multi-file lane / audit / heavy investigation | Claude Code |
| Pure prose, no codebase needed | ChatGPT |
| Parallel verification or read-only forensics | Sub-agent |
| Tiny doc edit / `BACKLOG.md` status flip / append a paragraph | Yourself |

**When in doubt:** start with a sub-agent investigation lane. Read-only investigation reveals the right channel for the actual ship.

---

## Multi-channel parallel dispatch

You can run multiple sub-agents in parallel by sending a single message with multiple `Agent` tool calls — they execute concurrently. Casey-paste channels (Cursor, Claude Code, ChatGPT) run sequentially via Casey's keyboard; he pastes one prompt at a time.

**Realistic parallel topology** (proven on session 2026-05-10):
- 1 Cursor lane in flight + 1 Claude Code lane in flight + 1 ChatGPT prompt awaiting paste + 1-4 sub-agents running concurrently from your message.

**Constraints when running multiple lanes:**
- Each lane in a different file domain (no two lanes touching the same file).
- Each lane instructed not to touch `BACKLOG.md` (you consolidate ship-log entries after commits land).
- Sub-agents instructed not to run git operations.
- Casey's commit boundaries are sequential — he commits one lane at a time as reports come in.

---

## Common gotchas

**1. `BACKLOG.md` absorption.** Agents instructed not to touch `BACKLOG.md` sometimes commit it anyway when their `git add` stages working-tree changes implicitly. Substance is correct (the entries are right), history is messy. Mitigation: instruct agents to *report* ship-log entry text rather than editing `BACKLOG.md`; you add it after their commits land. Forensic memo: `docs/maintainability/2026-05-10_absorption_forensics.md`.

**2. Brief baseline staleness.** Dispatch briefs say "pytest baseline 1391, HEAD `f990488`" but by the time the agent runs, other lanes have committed. Pytest count and HEAD have moved. Mitigation: instruct the agent to confirm baseline at execution time with `git pull && pytest -q --collect-only | tail -1`.

**3. PowerShell encoding.** `Invoke-RestMethod -Body` defaults to ISO-8859-1. Always include `-ContentType "application/json; charset=utf-8"` in PowerShell smoke calls. See dispatch protocol Rule 4 + Rule 5.

**4. Bash mount staleness.** The Linux bash mount serves stale `.git` views — `git log`, `git status`, `wc -l` on `/sessions/.../havasu-chat/...` all unreliable. Use the Read tool with Windows-side paths (`C:\Users\casey\projects\havasu-chat\...`) — those are authoritative. See dispatch protocol Rule 7.

**5. `git commit --amend` while parallel lanes are in flight.** Don't. The amend will rewrite the most recent commit, which may not be yours. Dispatch protocol Rule 12 — added 2026-05-10 after the `#50`/`#51` git wrinkle.

**6. ChatGPT URL tracking parameter.** ChatGPT auto-appends `?utm_source=chatgpt.com` when it inlines URLs. Always strip on save.

**7. Sub-agent context burn.** Each sub-agent report comes back into your context window. After 4-5 sub-agent runs, your context is meaningfully fuller. Plan accordingly — for long sessions, prefer Cursor/CC/ChatGPT (whose contexts don't burn yours) over sub-agents.

**8. PowerShell `$` interpolation hits commit subjects too.** Dispatch protocol Rule 4 scopes the single-quote rule to `Invoke-RestMethod -Body`, but the same interpolation bites `git commit -m "..."`. Session-13's commit `11b248f` lost the `$79` from the intended subject `Verified Presence ($79/mo) cold-pitch scripts` — PowerShell read `$79` as a variable inside the double-quoted `-m` argument and the committed subject reads `(/mo)`. Cure: single-quote any `git commit -m '...'` whose subject contains `$`, `` ` ``, or other PowerShell-interpolable sigils. Cosmetic this time; would be a real semantic problem if a future subject embedded a variable-looking string that the shell silently emptied.

**9. Local ruff must match the `dev-requirements.txt` pin.** Session-13's schema-commit push surfaced 4 pre-existing ruff failures in three unrelated test files because the Cowork primary's local ruff was older than CI's pinned `ruff==0.15.12`. Newer ruff has stricter I001 (isort) behavior; older locals pass clean while CI fails. Cure: `python -m pip install ruff==0.15.12` (or whatever the pin currently reads) before any pre-commit lint check. CI is the source of truth; local must match.

**10. `alembic current` `(mergepoint)` label is a chain-walk diagnostic, not a multi-head alarm.** Session-13's schema-commit pre-push cycle: Casey's local SQLite dev DB reported `1a2b3c4d5e6f (mergepoint)` on `alembic current`, which Cowork primary initially read as a multi-head conflict and held back the push. Chain-walking `down_revision` values via `Grep ^down_revision alembic/versions/` revealed `1a2b3c4d5e6f` was a long-resolved merge living 6 revisions earlier in the linear chain — Casey's local DB was just stale; production was unaffected. Cure: when `alembic current` shows an unexpected revision with a `(mergepoint)` label, walk the chain forward via Grep before raising an alarm. False-alarm rate on this signal is high.

**11. "Done" with no chat output may still have written the file.** Session-13's first attempt at the rate-limiter §8 decisions memo went to Claude Code; Casey reported "CC errored or refused" because no chat-side output appeared. Sub-agent recovery later revealed CC had actually written the memo to `docs/maintainability/phase2_5_rate_limiter_decisions_memo.md` — the sub-agent saw a Claude Code header in the existing file and overwrote it. The fix path was correct (sub-agent recovery worked), but the detection was wrong: Casey assumed refusal from missing chat-side output rather than checking the filesystem. Cure: when any channel reports "done" but the chat-side output is missing or partial, check the target file path directly before concluding the channel failed. Applies to CC, Cursor, and sub-agents equally.

**12. Session sandbox `outputs/` doesn't persist; save artifacts under the workspace path.** Session-12's prior-session artifacts (`cc_prompt_rate_limiter_decisions_memo.md`, `chatgpt_prompt_provider_profile_ux.md`, etc.) lived in the session sandbox path (`local-agent-mode-sessions/.../outputs/`) and were gone by session-13. The handoff implicitly expected those files to be available; reauthoring was required. Cure: anything the next session needs to reference must be saved under the workspace `outputs/` path (`C:\Users\casey\projects\havasu-chat\outputs\`), not the session-scratch path. The workspace `outputs/` folder is not gitignored, so artifacts get committed alongside their associated ship-logs as durable records of the dispatch.

**13. PowerShell command chaining: `;` is universal; `&&` only works in pwsh 7+.** Session-16 surface: Cowork primary suggested `git add ...; git status; git commit ...; git push` blocks using `&&` between commands; Casey's PowerShell rejected the `&&` operator. Windows PowerShell 5.1 (the default on most Windows installs) doesn't support `&&` / `||` as command-chaining operators — those landed in pwsh 7+. The semicolon (`;`) is universally safe across both shells. Tradeoff: `;` doesn't short-circuit on failure (each command runs regardless of the previous one's exit code), so for any chain where you genuinely need stop-on-failure semantics, run the commands as separate lines instead. Cure: use `;` (or newline-separated commands) in any PowerShell chain unless you've confirmed Casey is on pwsh 7+. Same lesson scope as gotchas #3 + #8 — PowerShell's syntax surprises catch agents that default to bash-shaped command chains.

**14. The reflog (`.git/logs/HEAD`) is NOT the commit ancestry — walk parent links instead.** Session-17 boot surface: Cowork primary needed to verify origin/main top-5 matched the boot prompt's expected SHAs (`dcf2f7a → 4bb74bc → 03f7160 → ...`). Bash mount git was broken per Rule 7, so the primary fell back to grepping `.git/logs/HEAD`. None of the expected SHAs matched, AND the reflog tail showed subjects from a completely different work stream (`tier2 category filter`, `feat(home+chat): editorial home + voice/component chat refactor`, `Add stale aquatic event pruner`, `merge redesign/phase-1-hero-and-palette`) — all from abandoned branches the repo's HEAD had visited historically. The primary false-alarmed Casey, claiming "none of the boot prompt SHAs exist in this repo." Wrong: the reflog is the chronological record of every commit HEAD has ever pointed at — including checkouts to other branches, dead experiments, and reset/rebase-orphaned commits — NOT the parent ancestry of the current HEAD. The decisive verification of "is commit X in the current ancestry of main?" is to walk parent links from HEAD via the commit objects. From the bash sandbox: `python3` + `zlib.decompress` on `.git/objects/<sha[:2]>/<sha[2:]>` reads a commit body and exposes its `parent` line; chain that walk and you have the ancestry. Cure: when verifying ancestry from the sandbox, walk parent links from HEAD via commit-object reads, don't grep the reflog. Reflog forensics are valid for "what has HEAD pointed at over time" (investigating force-pushes, accidental resets, branch experiments) — wrong tool for "is SHA X currently reachable from HEAD." Sample walker:

```python
import zlib, os
def read_obj(sha):
    p = f'.git/objects/{sha[:2]}/{sha[2:]}'
    with open(p, 'rb') as f: raw = zlib.decompress(f.read())
    return raw[raw.index(b'\0')+1:].decode('utf-8', errors='replace')
sha = open('.git/refs/heads/main').read().strip()
for _ in range(20):
    body = read_obj(sha)
    parents = [ln.split()[1] for ln in body.splitlines() if ln.startswith('parent ')]
    subject = body[body.index('\n\n')+2:].splitlines()[0]
    print(f'{sha[:10]} :: {subject}')
    if not parents: break
    sha = parents[0]
```

Same lesson scope as Rule 7 — Windows-side reads are authoritative when the Linux mount is unreliable, AND the right verification mechanism matters as much as the right side of the mount.

**15. Bash mount `git` operations leave a `.git/index.lock` that Linux can't unlink — Windows `git` then refuses to commit.** Session-18 close-out surface: Cowork primary ran `git status -s` + `git diff --stat HEAD` from the bash sandbox during spot-check of an incoming Cursor return — output was substantively correct (right modified-files list, right untracked-files list) but accompanied by two warning lines: `error: cache entry has null sha1` and `warning: unable to unlink '/sessions/.../havasu-chat/.git/index.lock': Operation not permitted`. Primary surfaced the warnings to Casey but didn't act on them. Casey then ran `git commit` from PowerShell on the same working tree and hit a hard fatal: `fatal: Unable to create 'C:/Users/casey/projects/havasu-chat/.git/index.lock': File exists. Another git process seems to be running in this repository, e.g. an editor opened by 'git commit'. Please make sure all processes are terminated then try again. If it still fails, a git process may have crashed in this repository earlier: remove the file manually to continue.` Root cause: the bash sandbox is a different filesystem layer with restricted permissions on the workspace mount; Linux `git` correctly acquires the index lock at start of operation but the sandbox permission model blocks the close-time unlink (`Operation not permitted`), leaving a stale `.git/index.lock` that Windows `git` then correctly refuses to step on. Both halves are doing the right thing — the failure is the seam between them. Cure: `Remove-Item .git\index.lock` from PowerShell, sanity-check with `git status`, retry the commit (clean — Windows status will also reveal that the bash-side "extra modified files" Cowork primary saw, like phantom changes in `tests/voice_battery/reports/static_review.md` or a botched-quote-named file, are Linux-mount-only artifacts; Windows is the source of truth). Scope: **bash mount `git` is not safe even for read-only operations in mixed-OS sessions.** This extends gotcha #4 (bash mount staleness) — #4 covered the unreliability of bash-side `git log` / `status` reads; #15 covers the side-effect harm those reads can do to Windows-side operations. From session-18 forward in any mixed-OS session, do NOT run `git ...` from the bash sandbox against the working tree; use the Read + Grep + Glob tools (Windows-authoritative, don't touch git internals) for everything: directory listings, file diffs, status surveys. The only safe bash-side git-adjacent operations against the working tree are pure object reads via `python3` + `zlib.decompress` on `.git/objects/...` (per gotcha #14's parent-walk pattern) — those bypass the index lock entirely. Session-19 extended the scope: even read-only plumbing commands like `git ls-tree` for commit-content inspection should be replaced with the parent-walk pattern. One slip in session-19 left a `.git/index.lock` on the Linux mount that did NOT propagate to Casey's Windows filesystem (Remove-Item returned path-not-found) — harm was theoretical only that time, but the rule from session-20 forward is zero `git ...` from the bash sandbox against the working tree.

**16. Embedded `"..."` inside `-m '...'` bodies on PowerShell break the commit.** Session-19 docs-commit surface: Cowork primary proposed a commit subject that read approximately `docs: Phase 3 brief + 3.1 dispatch prompt artifacts (pre-positioned for "SHIPPED 2026-05-12" Phase 2 close-out)` and wrapped the full message in single quotes — `git commit -m 'docs: Phase 3 brief + 3.1 dispatch prompt artifacts (pre-positioned for "SHIPPED 2026-05-12" Phase 2 close-out)' -- docs/maintainability/master_build_plan.md docs/STATE.md` — expecting PowerShell's single-quote rule to make the entire body a single literal argument the way bash + zsh would. PowerShell didn't. The command failed with `error: pathspec 'Phase' did not match any file(s) known to git` (subsequent words from the body interpreted as pathspecs). Root cause: PowerShell's native-command argument re-tokenizer (the layer that translates PowerShell arguments into Win32 `argv[]` for non-PowerShell executables like `git.exe`) treats embedded `"..."` as quote-state changes EVEN inside an outer single-quoted body. The single quotes correctly suppress `$variable` interpolation and most metacharacter expansion, but the embedded double-quote pair causes the tokenizer to split the argument: what was supposed to be one `-m` argument becomes `docs: Phase 3 brief + 3.1 dispatch prompt artifacts (pre-positioned for `, then `SHIPPED 2026-05-12`, then ` Phase 2 close-out)` — three positional args. Git takes the first as the `-m` body and treats the rest as pathspecs, which then don't match. Consequence in session-19: the docs files stayed in the staging index from the prior `git add`, the next `git add` for outputs picked them up, and the chore commit at `3d89e58` bundled all four files. Subject mislabel; Rule 12 (no amend after push) meant we live with it. Cure: **avoid embedded `"..."` entirely in `-m '...'` bodies on PowerShell.** Use plain text (no quotes needed for emphasis — most subjects work fine with bare phrases). If emphasis is genuinely needed, use Unicode curly quotes (`"..."` U+201C / U+201D) which the re-tokenizer treats as regular characters. Backtick-escaping (`` `" ``) also works but is harder to read. Heredoc-style multi-line commits via stdin (`git commit -F -` with piped input) sidestep the issue entirely for long messages. Same lesson scope as gotchas #3 + #8 + #13 — PowerShell quoting/parsing surprises catch any agent that defaults to bash-shaped command shapes. Bash + zsh do NOT have this problem because they respect single-quote literalness for the entire argument body; this gotcha is PowerShell-specific.

---

## Working agreements

The 12 hard-won rules live in `docs/maintainability/dispatch_protocol.md`. Read them once, then reference them by number in dispatch prompts when relevant. Today's session added Rule 12 (amend-safety); the `2026-05-10_absorption_forensics.md` memo includes a Rule 13 candidate that was *not* added (verdict: N=1, low severity, cure already implicit in Rule 2).

---

## When to escalate to a fresh chat

You're a Cowork primary running a long session. Eventually context burn matters. Heuristic:
- After 4-5 sub-agent dispatches, your context is meaningfully fuller.
- After 10+ paste-channel round-trips, you've absorbed a lot of state.
- When a fresh handoff doc has just been authored, that's a natural starting point for a new agent — using it validates the handoff actually works.

When you escalate: write a fresh handoff doc capturing today's work (or update the existing one), then tell Casey the new chat should boot from `docs/SESSION_BOOT_PROMPT.md` + the latest `docs/SESSION_HANDOFF_<date>.md`.
