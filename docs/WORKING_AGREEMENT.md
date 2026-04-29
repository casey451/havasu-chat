# Working agreement

This document defines how Casey, Claude, and Cursor collaborate on havasu-chat. It exists so any fresh Claude or Cursor session can be up to speed without rediscovering rules through chat.

## Roles

**Casey** — Project owner. Approves designs, ships work, runs production touches that aren't delegated to Cursor. Final authority on go/no-go decisions.

**Claude** — Reviews and plans. Reads code via tools or via Cursor's reports. Drafts Cursor bootstraps, reviews Cursor's output at each gate, recommends approvals or fixes. Does not execute code changes directly. Does not approve work on Casey's behalf.

**Cursor** — Implements. Writes and edits code based on Claude's bootstraps and Casey's approvals. Reports back at each gate. Does not chain across gates without approval.

## Discipline

**Halt-and-report between steps.** Each step in a multi-step task ends with a halt. Cursor reports what was done, Casey relays Claude's review, Claude approves or asks for fixes. Cursor does not advance to the next step without explicit approval.

**No commits or pushes without approval.** Even when Cursor has written and verified code, the commit step is its own gate. Same for the push step.

**Empty output is a finding.** If a command returns nothing, that's reported explicitly, not glossed.

**No new files under `scripts/` without approval.** Cursor doesn't create new tooling or scripts unilaterally.

**If output doesn't match what was asked, say so and retry.** Don't claim success when it didn't happen. Surface the mismatch and the cause.

## Cursor permissions

**Cursor can:**
- Read any file in the repo
- Edit any file with explicit approval
- Run local commands (`python -m pytest`, `git status`, `git diff`, etc.)
- Run `git push origin main` after announcing intent and waiting ~30 seconds for halt
- Run read-only SQL against production via Railway dashboard or equivalent
- Run read-only HTTP requests against production endpoints (`/health`, `/api/chat` for verification)

**Cursor cannot:**
- Run database WRITE operations against production (schema changes, data changes, deletions)
- Force-push, delete branches, modify tags, rotate secrets
- Decide ship vs. don't-ship when verification is ambiguous — that's Casey's call

## Commit discipline

**Subject under 73 characters.** Match recent project style (e.g., `Tier2 query: include event_url in event row payload`).

**Commit messages must be UTF-8 without BOM.** Write the message to a temp file using a method that does not emit a BOM. Two reliable methods:

- Python: `pathlib.Path('msg.txt').write_text(content, encoding='utf-8')`
- PowerShell: `[System.IO.File]::WriteAllText('msg.txt', $content, [System.Text.UTF8Encoding]::new($false))`

**Byte-verify commits.** Pre-commit and post-commit, the first three bytes of the subject must be the actual ASCII letters of the subject (e.g., 84, 105, 101 for "Tie..."), not 239, 187, 191 (the BOM).

**Use `python -m pytest -q`** as the test command. Bare `pytest` does not resolve in this PowerShell environment.

## Output formatting

**Render diffs in fenced code blocks** (triple backticks). Markdown rendering outside code blocks strips diff markers (`+`/`-` prefixes) silently. This was a recurring issue and the fix is unconditional code-block usage.

**Render commit messages in fenced code blocks** for the same reason.

## Verification

**For features that touch user-visible behavior**, production verification is required after deploy. Acceptable verification depends on what shipped:

- LLM-mediated behavior: multi-sample to characterize flakiness, programmatic ground-truth comparison against SQL where applicable. Single-sample verification is not sufficient (a single happy roll on a flaky LLM produces false confidence).
- Deterministic behavior: hash-equality check across multiple runs of the same query proves determinism. Catalog fingerprint check before and after the run sequence rules out drift.

**For features that don't touch user-visible behavior** (test additions, payload-shape changes, internal refactors), test coverage may be sufficient verification with a deferred-verification note in the backlog if production sampling isn't feasible.

**Failure handling**: any verification failure is a halt. Don't paper over by altering criteria post-hoc. Decide between revert and follow-up explicitly.

## Session structure

Each working session typically follows this shape:

1. **Briefing** — Casey opens with project state and the session's target. For continuity, this is now grounded in the canonical docs (`STATE.md`, `WORKING_AGREEMENT.md`, `BACKLOG.md`) rather than reconstructed in chat.
2. **Design pass** — Claude reviews scope, identifies design questions, drafts a Cursor bootstrap with gated steps.
3. **Implementation** — Cursor executes step-by-step, halting between steps. Claude reviews each step's output, recommends approval or fixes.
4. **Verification** — Production verification per the criteria above.
5. **Close-out** — STATE.md and BACKLOG.md updated to reflect what shipped.

## Evolving the agreement

This document is updated when the working agreement actually changes — not during normal sessions. Changes require explicit Casey approval and are committed as their own change. Examples of past changes: granting Cursor `git push` permission, granting Cursor read-only production access, adopting BOM-free commit verification.
