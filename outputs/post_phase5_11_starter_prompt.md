# Post-Phase-5.11 Starter Prompt

> Short paste-into-new-Cowork-chat prompt. The comprehensive branch-point
> boot prompt lives at `outputs/post_phase5_11_next_session_boot_prompt.md`
> (228 lines) -- this is the lightweight kickoff that points to it +
> sets context in ~40 lines. Paste everything below the `---` line.

---

You're picking up the havasu-chat project after **Phase 5 (Tier 1 data gathering) COMPLETED 2026-05-17** at Phase 5.11 SHIP. All 13 Tier-1 categories now populated; 1,314 active entities across 12 active Tier-1 slugs; `origin/main` top is `309f8b4` (boot-prompt commit on top of the 5.11 SHIP chain).

Working directory: `C:\Users\casey\projects\havasu-chat`.

**Read these in order before doing anything else:**

1. **`outputs/post_phase5_11_next_session_boot_prompt.md`** -- authoritative branch-point boot prompt. Covers: 5.11 lane chain on origin, all-13-Tier-1 entity counts, **3 dispatchable lanes** (A: Phase 6 amend5-to-11 ledger dispatch via Claude Code [LOW-FRICTION, recommended first]; B: Phase 6.3 Cursor UI lane; C: Phase 7 with scope reconciliation caveat), V1.5 carry inventory pointer, **sandbox FUSE-mount unlink-block workaround pattern** (critical for any future sandbox-driven repo work in this Cowork session), cleanup carry, and 7-item pre-flight checklist.

2. **`outputs/phase5_11_session_closeout.md`** -- 5.11 SHIPPED state index. 6-gate scorecard, full lane chain (sustainability `1dd443a` -> SHIP `dcf3dd4` -> SHA-cleanup `6b8ba50` -> ruff-fix `6adfc05` -> framing-correction `54f17e6` -> boot prompt `309f8b4`), V1.5 carries from 5.0-5.11 (~20 items), and the FUSE-mount gotcha narrative.

3. **`docs/maintainability/master_build_plan.md`** -- 4 Phase 6 (~line 311) + 4 Phase 7 (~line 345) + 5 dependency graph (~line 509). Authoritative on phase sequencing; cross-reference Phase 7's "Tier 2 categories" list against what Phase 5 actually populated (the Phase 7 hand-off note is pre-Phase-5-restructure stale on this point -- noted in the boot prompt 2 Lane C caveat).

4. **`docs/STATE.md`** -- current state of record. NOTE: STATE.md "Recently shipped" currently tops at Phase 5.4. The 5.5-5.11 SHIPPED ledger entries are queued for **Lane A** (amend5-to-11 dispatch via Claude Code; paste-ready docs at `outputs/claude_code_dispatch_phase6_amend5_to_8.md` + `outputs/claude_code_dispatch_phase6_amend9_to_11.md`). Reading STATE.md, treat 5.5-5.11 as "shipped but ledger-debt-pending."

**After reading the 4 docs, surface a short context-discovery report to the operator covering:**
- Which of the 3 lanes (A / B / C) you propose to pursue + why
- Any ambiguities surfaced by the boot prompt or master plan reads (esp. the Phase 7 scope-staleness question)
- Confirmation that the FUSE-mount workaround pattern is internalized for any sandbox-driven work this session

Then **await operator confirmation** before any DB-write apply-script, scrape, commit cadence, or dispatch. Cadence: operator confirms each step before dispatch.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.11 session 1 (2026-05-17) post-Phase-5-COMPLETE. Companion to `outputs/post_phase5_11_next_session_boot_prompt.md`; this starter prompt is the lightweight paste-in-fresh-chat artifact, the comprehensive boot prompt is the full state index.*
