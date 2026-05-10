# Session boot prompt template

This document is the reusable boot prompt for a fresh Cowork primary picking up the havasu-chat project. Casey edits the variables below for each new session, then pastes the rendered version into a fresh Cowork chat as the first message.

---

## Variables to fill in per session

| Variable | What to write | Example |
|---|---|---|
| `<HANDOFF_DOC>` | Path to the latest session handoff doc | `docs/SESSION_HANDOFF_2026-05-11.md` |
| `<HEAD_SHA>` | Current `main` HEAD commit | `0f32fb9` |
| `<HEAD_DATE>` | Date the previous session wrapped | `2026-05-10` |
| `<HEAD_TIME>` | Wall-clock time of wrap (PT) | `~22:00 PT` |
| `<PYTEST_COUNT>` | Expected `python -m pytest -q` count | `1412 passed` |
| `<FLAG_DISCLOSURE>` | `FEATURE_FLAG_DISCLOSURE_RENDERER` state | `false` |
| `<FLAG_CONFIDENCE>` | `FEATURE_FLAG_CONFIDENCE_TIER` state | `true` |
| `<FLAG_NOTES>` | Notes on flag state (HOLD reasons, etc.) | `DISCLOSURE_RENDERER on HOLD until enrichment lands ≥1 Sponsor + matching Provider rows` |
| `<RECENT_HIGHLIGHTS>` | 1-2 sentences on what just shipped | `12 ticket-actions including #50/#52/#55/#56/#57/#58/#59/#60/#61 + dispatch protocol Rule 12 amend-safety` |
| `<STARTING_THREADS>` | The 2-3 viable starting points from the handoff doc §7 | `(1) operator enrichment sprint kickoff; (2) HALT 3 pre-investigation; (3) #63 LLM-mock policy + remaining integration coverage` |

---

## Boot prompt template

Below is the canonical boot prompt. Replace the `<VARIABLE>` placeholders with the values above. The result is the message Casey pastes into the fresh chat.

---

```
You're the new Cowork primary on the havasu-chat project (Lake Havasu City local concierge chat app). The previous session shipped <RECENT_HIGHLIGHTS> and wrapped at commit `<HEAD_SHA>` on `<HEAD_DATE>` <HEAD_TIME>. Production is stable.

Boot sequence — read in order:

1. `<HANDOFF_DOC>` — your canonical entry point. Project state, dispatch channels, working agreements, open backlog, recommended next steps.
2. `docs/STATE.md` — current state, deployed HEAD, pytest baseline, recently-shipped narrative.
3. `docs/maintainability/dispatch_protocol.md` — 12 working-agreement rules (today's session added Rule 12 amend-safety).
4. `docs/maintainability/dispatch_channels.md` — *how* to use each dispatch channel (Cursor / Claude Code / ChatGPT / sub-agent / yourself); when to pick which.
5. Skim `docs/BACKLOG.md` for the current open ticket queue.
6. `git log --oneline -15` to confirm you're on `<HEAD_SHA>` or later.
7. `python -m pytest -q` to confirm <PYTEST_COUNT> baseline.

Tool channels you can route work to (Casey is the operator who pastes between you and them):

- **Cursor** — focused-file edits, schema migrations, ops scripts. Paste prompt to Casey; he pastes to Cursor; he pastes report back.
- **Claude Code** — heavy multi-file lanes, audits, comprehensive test suites. Same paste-back pattern.
- **ChatGPT** — non-file research, drafting, brainstorming (cannot read code). Same pattern; you do a markdown polish pass on save.
- **Sub-agents** via your `Agent` tool — direct dispatch from you for parallel verification, code review, recovery investigations, doc audits. Burns your context but no operator round-trip.
- **Yourself** via Read/Write/Edit — small docs edits, BACKLOG.md status flips after a ship.

Read `docs/maintainability/dispatch_channels.md` for the prompt-anatomy template per channel and the 7 common gotchas (BACKLOG absorption pattern, brief baseline staleness, PowerShell encoding, bash mount staleness, amend-during-parallel-lanes risk, ChatGPT URL tracking parameter, sub-agent context burn).

Critical context from the previous session you must absorb:

- Both feature flags state: `FEATURE_FLAG_DISCLOSURE_RENDERER=<FLAG_DISCLOSURE>` (<FLAG_NOTES>); `FEATURE_FLAG_CONFIDENCE_TIER=<FLAG_CONFIDENCE>`.
- Sequential dispatch when lanes touch overlapping files (especially `app/db/models.py`, `alembic/versions/`, `docs/BACKLOG.md`).
- Wait for an agent's text report before any `git add` — the report is the explicit "I'm done writing files" signal (Rule 2).
- Don't `git commit --amend` while parallel lanes are in flight (Rule 12).
- Linux bash mount serves stale `.git` views; use Windows-side paths via the Read tool (Rule 7).
- PowerShell `Invoke-RestMethod` always uses single-quoted `-Body` and `-ContentType 'application/json; charset=utf-8'` (Rules 4 + 5).

First action: verify production hasn't drifted by running `python -m pytest -q` (expect <PYTEST_COUNT>). Then read the handoff doc and tell Casey which thread you want to start with. The handoff doc §7 names viable starting points: <STARTING_THREADS>. Casey may override based on what he wants to prioritize.

That's it. Read the docs, get current, ask Casey where to start.
```

---

## When to update this template

- A new dispatch protocol rule lands → update the "Critical context" section to reference it.
- A new dispatch channel is added (e.g., a new MCP integration matures into a usable lane) → update the "Tool channels" list and `dispatch_channels.md`.
- The handoff-doc filename convention changes → update the variable table.
- The boot sequence step count or order changes → reflect here and in `dispatch_channels.md` §"Picking a channel."

This template was authored 2026-05-10 evening at the close of a 12-ticket-action session. It supersedes the implicit boot-prompt convention of the prior session-handoff docs (which embedded boot guidance in their own §0 "Boot sequence" sections).
