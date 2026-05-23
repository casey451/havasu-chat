# Session handoff — havasu-chat — 2026-05-23 (v9, resume-from-v8 + 5 ships landed + Phase 8b/9 wrappers DISPATCH-READY)

> **What this is:** Boot prompt for the next Cowork-primary session.
> Supersedes `outputs/session_handoff_2026-05-22_v8.md` (v8) and earlier
> (v1–v7). Captures a 5-commit ship arc that closed the v8 §6 STATE.md
> doc lane (both the code-block extension AND the prose narrative refresh)
> + landed structural .gitignore root-level expansion + landed three
> dispatch_channels gotchas + SHA-patched both Phase 8b + Phase 9 Cursor
> wrappers to DISPATCH-READY state.
>
> **Authored:** 2026-05-23, ~04:00Z (≈ 2026-05-22 ~21:00 MST), end-of-session.
>
> **Origin/main tip:** `f448f11` (chore(outputs): SHA-patch Phase 8b + Phase 9 dispatch wrappers — both now DISPATCH-READY)
> **Alembic head:** `d8e9f0a1b2c3` (unchanged; no migrations this session).
> **CI status:** **GREEN through #406** (#406 on `f448f11` completed success at ~03:40Z; **18 consecutive green main CIs since `e21a31d` 2026-05-21 lint recovery**, modulo #400 auto-cancelled by newer push).
> **Pytest baseline at HEAD:** **~2290 + 3 skipped** (unchanged this session; all 5 ships were docs/chore — zero test additions or removals).

---

## §1 What shipped this session

**5 commits to origin/main:**

| SHA | Type | Title |
|---|---|---|
| `73c4273` | docs | STATE.md Recent commits code-block extension (2f87211..1bb8019; 224 lines) + line 13 pytest count fix (~2270 → ~2290 + lhcaz_aquatic note) |
| `b484b63` | chore | gitignore: extend _* scratchpad patterns to repo root (parallel to outputs/-anchored coverage from d4777c0) |
| `de2b70f` | docs | dispatch_channels gotchas #25/#26/#27 — bash mount phantom state + cmd.exe git add multi-path abort + scratchpad .cmd stale-message bugs |
| `6070726` | docs | Recently shipped prose narrative refresh — Phase 4.2 through de2b70f (Sessions 24+ ship arcs) |
| `f448f11` | chore | SHA-patch Phase 8b + Phase 9 dispatch wrappers — both now DISPATCH-READY |

**Per-commit content breakdown:**

| SHA | Files | Notes |
|---|---|---|
| `73c4273` | docs/STATE.md (+225/-1) | Line 13 ~2270 → ~2290 with lhcaz_aquatic note (reconciles with line 17 Health-block figure). Lines 31-254 extend the newest-first commit ledger with the 224-commit gap from `2f87211` (Phase 4.3) through `1bb8019` (today's HEAD); covers Phase 4.4 / Phase 5.0-5.11 / Phase 6.1-6.5 / Phase 7 / Phase 7.5-7.7.1 / Phase 8a + 8a.0-8a.4 / Lane H flag-flip / lhcaz_aquatic arc / e21a31d lint recovery / today's 4 v8-session commits. Largest doc-staleness gap in STATE.md now closed at the ledger level. |
| `b484b63` | .gitignore (+12/0) | Adds bare `_*.cmd` / `_*_result.txt` / `_*_result.json` / `_*_msg.txt` patterns at root-level scope alongside d4777c0's `outputs/`-anchored patterns. `git check-ignore -v` confirms all 6 untracked workspace-root scratchpad .cmds (`_disable_aquatic_*`, `_flag_flip_close_out_*`, `_state_md_*`) now match line 67 `_*.cmd`. Structural cure complete: ephemeral scratchpad invisible to git at ANY depth. |
| `de2b70f` | docs/maintainability/dispatch_channels.md (+6/0) | Adds 3 new gotcha paragraphs at lines 212/214/216 (single substantial paragraph each, matching the prose convention of existing #15/#17/#18/#19/#20/#22/#23/#24 entries). #25 bash mount can invent filesystem state (phantom modifications, control-character filenames, fake truncations); extends #4/#7/#15. #26 cmd.exe git add multi-path abort on first non-existent path (canonical example: 8c19490). #27 scratchpad .cmd accumulation causes stale-commit-message bugs (canonical example: 786936a); cites d4777c0 + b484b63 as the structural cure. Highest gotcha number advances #24 → #27. |
| `6070726` | docs/STATE.md (+2/0) | Inserts a second giant flat prose paragraph after the existing session-23 paragraph at line 28. New paragraph narrates the Phase 4.2 → de2b70f arc in flat-prose style with SHA-anchored per-phase summaries: Phase 4 completion (4.2-4.4) / Phase 5 data lane COMPLETE / Phase 6 UI build COMPLETE / Phase 7 chat + HALT 3 + hardening / Phase 8a conditions + alerts subsystem + hardening / maintainability surfacing / lhcaz_aquatic carry / 2026-05-22 7-commit hygiene arc. Closes the LARGER v8 §6 STATE.md doc lane: previously the prose narrative ended at Phase 4.1, leaving sessions 24+ undocumented in narrative form. Master plan §4 confirmed already-current; no separate refresh needed there. |
| `f448f11` | outputs/cursor_dispatch_prompt_phase_8b.md (+13/-13) + outputs/cursor_dispatch_prompt_phase_9.md (+18/-16) | Phase 8b: 2 SHA slots filled globally (`<<<PHASE_8A_HEAD_SHA>>>` → `8a905c6`, `<<<PHASE_8A_ALEMBIC_HEAD>>>` → `d8e9f0a1b2c3`) + SHA-PATCH-APPLIED header at line 3. Phase 9: 4 SHA slots filled globally (`<<<PHASE_8_HEAD_SHA>>>` → `8a905c6`, `<<<PHASE_8_ALEMBIC_HEAD>>>` → `d8e9f0a1b2c3`, `<<<PHASE_6_5_HEAD_SHA>>>` → `bdca0bd`, `<<<PHASE_7_5_HEAD_SHA>>>` → `b701759`) + SHA-PATCH-APPLIED header + historical DISPATCH-NOT-YET-READY framing preserved for audit. `<<<SKIP_N>>>` + `<<<SKIPLAST_N>>>` (clipboard-pipeline offsets) intentionally left TBD — operator computes from actual line counts at paste time. Both wrappers are now paste-ready in a fresh Cursor chat. |

**4 root-cause discoveries this session:**

1. **File Explorer address-bar coords are display-dependent and drift mid-session.** Started the session with `(320, 47)` working twice for the address-bar empty-area click on the Built-in Display landscape layout. Then `(320, 47)` STOPPED working when File Explorer's window appeared on a different display (1456×819 → 754×1600 portrait viewport). Recovery: body-click in the file-list area (around `(300, 250)`) to give File Explorer keyboard focus, then `Ctrl+L` to force address-bar focus, then type and Enter. The body-click → `Ctrl+L` pattern is the durable recovery when coords drift. Address-bar location varies by File Explorer window position + screen orientation; clicks targeting the breadcrumb chevron at `~(250, 47)` open a dropdown menu instead of entering edit mode. **Lesson**: don't assume address-bar pixel coords are stable across a session; the body-click → Ctrl+L fallback is the universal recovery.

2. **Edit tool `replace_all` will replace the same string in YOUR newly-inserted text.** When I added a SHA-PATCH-APPLIED header to the Phase 8b wrapper referencing `<<<PHASE_8A_HEAD_SHA>>>` and `<<<PHASE_8A_ALEMBIC_HEAD>>>` as plain-text labels, then ran two `replace_all` Edits to substitute those placeholders globally, my header's literal references got mangled: "`<<<PHASE_8A_HEAD_SHA>>>` → `8a905c6`" became "`8a905c6` → `8a905c6`". Fixed by re-editing the header to describe the placeholders verbally ("the Phase-8a HEAD-SHA placeholder is filled with...") rather than typing them literally. **Lesson**: when you're about to do `replace_all` on a token, don't leave that token in the file in any descriptive/documentation context — it'll get rewritten too. For Phase 9 I did the replacements FIRST then added the header (with verbal descriptions only), which avoided the issue.

3. **AskUserQuestion tool can error mid-session.** Got "Tool permission request failed: Error: Tool permission stream closed before response received" when trying to surface V1.5 wave options. One-off; tool recovered later. **Lesson**: if AskUserQuestion errors, fall back to plain-text presentation of the options + ask Casey to reply in chat. Don't retry the tool repeatedly.

4. **Parallel sub-agent fan-out is fast + cheap for recon.** Launched 4 `Explore` sub-agents in parallel via a single Agent-tool-block invocation: Phase 8b dispatch readiness / Phase 9 dispatch readiness / V1.5 inventory triage with top-3 wave recommendations / master plan + STATE.md prose-narrative structure scoping. All 4 returned within minutes with substantial structured reports that informed the next 3 ships. The parallel pattern is the right shape when you have multiple independent recon questions about a large codebase. **Lesson**: when next steps depend on understanding 3+ areas of the codebase, fan out — don't serialize. Single Agent-tool-block call with N sub-agents is one round trip; N serial calls is N round trips.

---

## §2 End-to-end prod validation evidence

**Per-ship prod smoke evidence:**
- After `73c4273` (~00:08Z): /health 200, event_count=214; /api/conditions all 4 sources fresh, `aqi_source_distance_mi=61.7` invariant intact, `current_aqi=43` (O3), `current_temp_f=95.0`, `lake_is_stale=false`, `lake_gauge_ft=49.18`.
- After `de2b70f` (~03:23Z): CI #404 green; Railway redeployed (docs-only no-op for runtime).
- After `6070726` (~03:35Z): CI #405 green; same docs-only no-op.
- After `f448f11` (~03:45Z): /health 200, event_count=214; /api/conditions `aqi_source_distance_mi=61.7` ✅, all 4 sources fresh ("Updated 28 min ago" on AQI), `lake_is_stale=false`. Parks-rec-scrapes cron #66 fired at 07:11Z on f448f11 and completed success (~6h after #65 on 1bb8019).

**CI evidence:**
- #402 on `73c4273`: completed success ✅
- #403 on `b484b63`: completed success ✅
- #404 on `de2b70f`: completed success ✅
- #405 on `6070726`: completed success ✅
- #406 on `f448f11`: completed success ✅
- #66 parks-rec-scrapes on `f448f11`: completed success ✅ (5 consecutive green cron runs since the 24f4aa1 lhcaz_aquatic rewrite landed)
- **18 consecutive green main CIs since `e21a31d` 2026-05-21** (counting all completed-success runs)

---

## §3 Closed carries vs v8 baseline

| v8 carry | v9 status |
|---|---|
| STATE.md "Recently shipped" per-commit entries refresh (line 28+) | **FULLY CLOSED via `73c4273` (code-block extension; 224 commits) + `6070726` (prose narrative refresh; Phase 4.2 through de2b70f arc)**. Both the SHA ledger AND the narrative paragraph are now current as of `de2b70f`. |
| dispatch_channels.md gotcha additions (low-priority v8 NEW carry) | **CLOSED via `de2b70f`** — gotchas #25/#26/#27 all landed with full prose write-ups matching the existing entry style. |
| .gitignore workspace-root scratchpad coverage (implicit from gotcha-#27 cure) | **CLOSED via `b484b63`** — bare `_*.cmd` / `_*_result.txt` / `_*_result.json` / `_*_msg.txt` patterns cover root-level scratchpad alongside d4777c0's `outputs/`-anchored patterns. `git check-ignore` confirms all 6 untracked root .cmds now matched. |
| Phase 8b cat-13 expansion dispatch-readiness | **CLOSED via `f448f11`** — wrapper SHA-patched (`<<<PHASE_8A_HEAD_SHA>>>` → `8a905c6`, `<<<PHASE_8A_ALEMBIC_HEAD>>>` → `d8e9f0a1b2c3`); SHA-PATCH-APPLIED header added; PASTE-READY in a fresh Cursor chat. Operator framing reduced to: paste, audit return, commit. |
| Phase 9 dispatch-readiness | **CLOSED via `f448f11`** — wrapper SHA-patched (4 slots filled with `8a905c6` / `d8e9f0a1b2c3` / `bdca0bd` / `b701759`); SHA-PATCH-APPLIED header added; historical DISPATCH-NOT-YET-READY framing preserved as audit. Phase 9a is PASTE-READY in a fresh Cursor chat. Phase 9b waits for 9a HALT + operator confirms on scrapers cadence (3 daily + 2 weekly) + Things-to-Do bundle (cat-2 + cat-7 + cat-9). |
| V1.5 prioritization wave | Still **DEFERRED** — 3 candidate waves identified by recon agent (Validator+Ops hardening / Trust-Signal Verifier bundle / Conditions Data-Source upgrade); operator picks. See §6 for the menu. |

**NEW carries surfaced this session:**

| Carry | Why | Priority |
|---|---|---|
| 12 untracked .md/.txt files in outputs/ (handoff docs + diagnostic reports + status files; not scratchpad — these are durable artifacts the operator may want to retain or share) | These have been untracked for many sessions; not blocking anything. Could be added to .gitignore if intentionally durable scratchpad, or `git add` if they should be tracked as session artifacts. Operator-decide. | Low |
| 6 untracked root .cmd files (the v8-vintage scratchpad: `_disable_aquatic_*`, `_flag_flip_close_out_*`, `_state_md_*`) — physically still on disk | b484b63 made them gitignored so they're invisible to git, but they remain on disk and could still be accidentally double-clicked. Optional cleanup: `del C:\Users\casey\projects\havasu-chat\_*.cmd` from PowerShell or just leave (they're harmless once gitignored). | Low / cosmetic |
| Address-bar coords portability across display orientations | Already documented in §1 root-cause #1; future verify/commit .cmds could use `Win+R` Run dialog instead of File Explorer address bar — but Win+R requires `systemKeyCombos` grant. Or stick with body-click → Ctrl+L as the universal recovery. | None (already documented) |
| File Explorer multi-display behavior | When the user has 2+ monitors, File Explorer can open on a different display than the previous screenshot's coordinate space. `mcp__computer-use__switch_display` can help, but it's faster to just take a fresh screenshot after any open_application call and recompute coordinates. | None (already documented) |

---

## §4 Pattern wins — durable operational insights

1. **Parallel sub-agent recon is the right shape when 3+ independent questions need answering.** This session launched 4 `Explore` sub-agents in a single Agent-tool-block: Phase 8b readiness, Phase 9 readiness, V1.5 triage, master_plan + STATE.md scoping. All 4 returned in parallel with substantial structured reports. Total wall time ≈ longest single agent (~1-2 min); total context cost ≈ sum of returns. Compare to N serial calls (N × round trip). **Discipline**: any time you find yourself thinking "I need to investigate A, B, C, and D before I can ship anything substantive," fan out via a single Agent-tool-block with N sub-agents.

2. **Multi-file commits via single-path `git add` (one path at a time) work cleanly.** `f448f11` staged `outputs/cursor_dispatch_prompt_phase_8b.md` then `outputs/cursor_dispatch_prompt_phase_9.md` in two sequential `git add` calls (per v8 §1 #2 lesson + v8 boot prompt's NEW HARD RULE for cmd.exe multi-path abort). Pre-commit `git diff --cached --stat` confirmed exactly 2 paths staged. Clean ship. **Discipline carries forward**: every multi-file commit uses one `git add <path>` per path, with explicit error-code log between calls, then a `git diff --cached --stat` gate before the actual commit.

3. **Edit tool `replace_all` is dangerous when used WITH descriptive headers referencing the same token.** The pattern that bit me: write a SHA-PATCH-APPLIED header that says "`<<<PHASE_8A_HEAD_SHA>>>` → `8a905c6`" as documentation, THEN run `replace_all` on `<<<PHASE_8A_HEAD_SHA>>>`. The header's literal reference gets rewritten too, producing "`8a905c6` → `8a905c6`". Cure: either (a) do the `replace_all` FIRST then add the header with verbal descriptions of the placeholders rather than literal placeholder strings, OR (b) use `replace_all=false` and target each occurrence individually (verbose but safe). For Phase 9 I used pattern (a) and it landed clean. **Discipline**: when about to `replace_all` on a token, scan the file for any descriptive/audit/documentation references to that same token and either rewrite them first or add them after the replace.

4. **AskUserQuestion is fast but can fail; plain-text presentation is the durable fallback.** AskUserQuestion errored once mid-session with a permission-stream-closed error. The fallback (presenting the options as plain numbered bullets in chat) works fine — it's slower for the user to reply but no fancier tooling needed. **Discipline**: if AskUserQuestion errors, don't retry; present the options as plain text and let the user reply with the option number or label.

5. **Computer-use coords are display-and-window-position-dependent and shift mid-session if window moves between monitors.** A click that worked perfectly at the start of the session may miss its target when the same window appears on a different monitor or display orientation. The universal recovery pattern is body-click in a safe area (file list, empty desktop area) → `Ctrl+L` to force keyboard focus to the address bar. This works regardless of display orientation or window position because keyboard shortcuts target the focused app, not pixel coordinates. **Discipline**: before any address-bar click, if it's been > 5 minutes since the last screenshot OR the file count in the status bar has changed, take a fresh screenshot first and recompute coords. If the click misses, fall back immediately to body-click → `Ctrl+L`.

6. **STATE.md doc lane can split cleanly into code-block-refresh (mechanical, large diff) + prose-narrative-refresh (substantive, small diff).** The two STATE.md ships this session (`73c4273` 225-line code-block extension + `6070726` 2-line prose narrative addition) each have a single clean concern and minimal cross-coupling. Treating them as TWO separate ships rather than one mega-commit kept each commit's diff scannable and made the "what changed" question trivially answerable from git log. **Discipline**: when a doc lane has both mechanical-ledger AND substantive-narrative work, ship them as separate commits even if the underlying file is the same.

---

## §5 Tool state — what carries to next session

**Persists (no action):**
- 5 new commits on origin/main (`73c4273`, `b484b63`, `de2b70f`, `6070726`, `f448f11`) + Railway auto-deployed each (docs/chore changes are runtime no-ops).
- `.gitignore` now blocks `_*.cmd` / `_*_result.txt` / `_*_result.json` / `_*_msg.txt` at BOTH root-level AND `outputs/`-scoped patterns. Future ephemeral scratchpad invisible to git regardless of which directory it lands in.
- `docs/maintainability/dispatch_channels.md` highest gotcha number is now **#27**.
- `docs/STATE.md` line 13 pytest count now reads `~2290 + 3 skipped` (was `~2270`); line 28 prose paragraph followed by a second paragraph at line 30 narrating sessions-24+ ship arcs; code-block lines 31-254 fully current with the SHA ledger through `f448f11`.
- `outputs/cursor_dispatch_prompt_phase_8b.md` — DISPATCH-READY; paste in a fresh Cursor chat to ship Phase 8b.
- `outputs/cursor_dispatch_prompt_phase_9.md` — DISPATCH-READY for Phase 9a; Phase 9b paste after Phase 9a HALT + operator confirms.
- 18 consecutive green CIs since `e21a31d` 2026-05-21.

**Needs one-click re-grant in new session:**
- Computer-use access for File Explorer via `request_access` — today's grant was instant on first try.
- Claude in Chrome browser pairing not used this session.

**Bash mount status:**
- **STABLE for HTTP smokes + GitHub API queries this session** — no phantom-state firings observed. The gotcha-#25 risk remains for filesystem/git-state queries; default to Read tool or Windows-side .cmd-result for any FS/git question. Bash is fine for `curl` + `python3` + anything that doesn't touch the mount.

**Verify .cmd discipline carrying forward:**
- 18 consecutive green CIs since whole-repo `ruff check .` discipline landed at `e21a31d`. Every .cmd this session ran the whole-repo ruff.
- All 5 operational .cmd pairs (verify + commit) this session redirected stdout+stderr to `outputs/_<topic>_*_result.txt`. The pattern survived even when File Explorer launches were finicky — Read tool always pulled the result file cleanly afterward.
- Multi-file commit (`f448f11`) used single-path `git add` per file with explicit error checks between calls. Clean ship; no abort.

---

## §6 First N actions in the new chat

1. Read this v9 doc.
2. Smoke prod `/api/conditions` — expect all 4 sources fresh, `aqi_source_distance_mi=61.7` invariant intact (Phase 8a.4).
3. Smoke prod `/health` — expect HTTP 200, `event_count` near 214 (or higher if more aquatic data flowed in overnight).
4. Check CI status via `curl https://api.github.com/repos/casey451/havasu-chat/actions/runs?branch=main&per_page=5` — expect #406 on `f448f11` as the last main CI run, all green. Any newer runs should also be green.
5. **Confirm parks-rec-scrapes cadence still green**: `curl https://api.github.com/repos/casey451/havasu-chat/actions/workflows/272943770/runs?per_page=5`. Expected: a stream of completed/success runs on `f448f11` or later (~6h cadence). If any FAILED, drop into log fetch via Chrome MCP.
6. **Ask Casey which lane to ship.** The queue (ordered by friction):
   - **V1.5 wave pick (Casey-input lane)**: 3 candidate waves recommended by the v9 recon. Casey picks one:
     - **(a) Validator + Ops Hardening (~1 wk, S/M)** — F6 `near_match` fail-open fix + F7 over-broad regex tighten + post-deploy smoke automation. Pure backend confidence + risk mitigation. Smallest, safest, no operator-side prereqs. The post-deploy smoke automation would have caught all 3 Phase 7.5 prod bugs.
     - **(b) Trust-Signal Verifier Bundle (~1.5 wk, M)** — AZDHS childcare verifier (cat-12) + AZDOR lodging verifier (cat-10) + AZRE vacation rentals verifier (cat-10). Unlocks 70-90% coverage in Havasu's two friction categories (kids + tourism). Pure database + query layer; no UX churn. Highest leverage per the V1.5 triage.
     - **(c) Conditions Data-Source Upgrade (~1 wk, M)** — water-temp alt-source (USGS 09426630 Bill Williams or Bureau of Reclamation) + Nixle replacement (Mohave County SO / `ein.az.gov` / `lhcaz.gov` RSS) + tighter AirNow (PurpleAir / AZDEQ state monitors). Removes the "from Blythe CA 60mi away" disclaimer. Needs operator feasibility research async per source.
   - **Phase 8b cat-13 expansion dispatch (Cursor paste)**: wrapper at `outputs/cursor_dispatch_prompt_phase_8b.md` is DISPATCH-READY. Operator opens a fresh Cursor chat, pastes the wrapper, awaits Cursor's return, audits against §12 + §13 criteria, then Cowork primary recommends commit batch.
   - **Phase 9a dispatch (Cursor paste)**: wrapper at `outputs/cursor_dispatch_prompt_phase_9.md` is DISPATCH-READY for Phase 9a (substantial — Events as ENTITY + RRULE + 3-source scraper subset). Phase 9b waits for 9a HALT. Operator computes SKIP_N + SKIPLAST_N at paste time per the inline clipboard pipeline.
   - Optional cosmetic: cleanup of 12 untracked outputs/*.md files (operator-decide whether to gitignore or track them).

---

## §7 Boot prompt for next chat

```
Resume havasu-chat.

REQUIRED READING (in order, before any action):
1. outputs/session_handoff_2026-05-23_v9.md — 5 commits shipped last session (73c4273 STATE.md code-block extension + b484b63 .gitignore root-level _* patterns + de2b70f dispatch_channels gotchas #25/#26/#27 + 6070726 STATE.md prose narrative refresh + f448f11 Phase 8b/9 wrapper SHA-patches). v8's STATE.md doc lane FULLY CLOSED (both code-block AND prose narrative now current). Phase 8b + Phase 9 wrappers both DISPATCH-READY in fresh Cursor chats. 18 consecutive green main CIs since e21a31d. Parks-rec-scrapes cron #66 GREEN on f448f11.

2. (skim) docs/STATE.md — all 4 staleness blocks now current as of 2026-05-23T~04:00Z. Line 10 staleness sentence still reads "none currently". Line 28 prose paragraph + line 30 prose paragraph together narrate Phase 1 → de2b70f. Code-block at lines 31-254 is the current SHA ledger.

3. (skim) outputs/cursor_dispatch_prompt_phase_8b.md — DISPATCH-READY; paste in fresh Cursor chat to ship Phase 8b cat-13 expansion.

4. (skim) outputs/cursor_dispatch_prompt_phase_9.md — DISPATCH-READY for 9a; paste in fresh Cursor chat. SKIP_N + SKIPLAST_N clipboard offsets are TBD by design — operator computes at paste time from actual line counts.

TOOL RE-GRANTS UPFRONT:
- mcp__computer-use__request_access for File Explorer (today's grant was instant on first try).
- Claude in Chrome not needed for routine boot.

FIRST 5 ACTIONS:
1. Smoke prod /api/conditions — expect all 4 sources fresh, aqi_source_distance_mi=61.7. If null, Phase 8a.4 regressed.
2. Smoke prod /health — expect 200, event_count ≥ 214 (or higher if more aquatic data flowed in overnight).
3. Check CI status — expect #406 on f448f11 green plus any newer runs green.
4. Check parks-rec-scrapes cron via workflow 272943770 — expect a stream of completed/success runs on f448f11 or newer (~6h cadence). If ANY failed, drop into log fetch via Chrome MCP.
5. Ask Casey which v9 §6 lane to ship next. The queue (ordered by friction):
   - V1.5 wave pick — 3 candidate waves recommended; Casey picks (a) Validator + Ops Hardening, (b) Trust-Signal Verifier Bundle, or (c) Conditions Data-Source Upgrade.
   - Phase 8b cat-13 expansion dispatch — wrapper PASTE-READY in fresh Cursor chat.
   - Phase 9a dispatch — wrapper PASTE-READY in fresh Cursor chat.

POSTURE:
- Confirm-each-step for new directions; blanket approval for the proven ship pattern (Edit-tool inline edits → _topic_verify.cmd launched via computer-use → result.txt read from disk → _topic_commit.cmd with push). 22 ships proven across seven sessions now (12 v5/v6 + 1 v7 + 4 v8 + 5 v9).
- For Railway env-var changes: hand the save click to Casey explicitly even though the action is reversible.
- For destructive Railway dashboard ops, pause for explicit click confirmation.
- Use TaskCreate/TaskUpdate liberally so progress shows in the widget.

HARD RULES (carried forward from v8):
- Bash mount is UNRELIABLE for filesystem/git state (gotcha #25 in dispatch_channels.md). Trust Read tool + Windows-side .cmd → result.txt for any FS/git query. Bash is fine for curl + GitHub API + HTTP smokes.
- Never open Cursor IDE. Edit-tool only for code changes.
- When telling Casey to double-click a .cmd, ALSO note that any .py file next to it (if present) will open Cursor — do NOT click that one.
- Every verify .cmd runs `ruff check .` (whole-repo scope), not just `ruff check <touched files>`. 18 consecutive green CIs since this discipline landed at e21a31d.
- When Chrome MCP hangs on `document_idle` timeout twice in a row, fall back to GitHub API / curl rather than retrying the browser. EXCEPTION: for GH Actions LOGS (vs metadata), Chrome MCP IS the primary path because the GH logs REST endpoint is admin-only (returns 403 anonymously).

NEW HARD RULES from v9:
- File Explorer address-bar coords drift mid-session when window moves between monitors. Universal recovery: body-click in a safe area (file list, empty desktop) → Ctrl+L to force keyboard focus to the address bar → type and Enter. Don't trust a previously-working coordinate after a screen change.
- Edit-tool `replace_all` will rewrite the same token in your newly-inserted header/documentation text. Either do `replace_all` FIRST then add headers with verbal descriptions of placeholders (not literal placeholder strings), OR use `replace_all=false` and target each occurrence individually.
- AskUserQuestion can error mid-session with permission-stream-closed. If it errors, fall back to plain-text presentation of the options and ask the user to reply by option number or label. Don't retry.
- Parallel sub-agent fan-out via single Agent-tool-block: when 3+ independent recon questions about the codebase need answering before the next ship, launch them all in parallel rather than serializing. Each sub-agent returns a substantial report; total wall time ≈ longest single agent.

If anything looks weird (sandbox shows surprising diffs, file appears truncated, .cmd "opens and instantly closes", Chrome MCP wedged, flag value differs from expected, etc.) STOP and ask Casey before proceeding.
```

---

*Authored 2026-05-23 end-of-session by Cowork primary. Saved to `outputs/session_handoff_2026-05-23_v9.md`. Supersedes v1–v8 for next-session boot.*
