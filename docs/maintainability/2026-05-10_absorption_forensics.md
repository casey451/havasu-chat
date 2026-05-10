# 2026-05-10 Absorption-Pattern Forensics

**Range investigated:** `24abe82..54a56b1` (29 commits, ~16-hour window 2026-05-09 19:13 → 2026-05-10 10:46).
**Author:** sub-agent (forensic memo, read-only investigation).
**Scope:** identify commits whose `git log --stat` shows files outside the scope advertised by the commit message; classify the staging-side mechanism that produced each absorption; draft a Rule 13 candidate for `dispatch_protocol.md` if the pattern is strong enough to warrant it.

---

## §1 — Pattern summary

The session shipped 29 reachable commits across 4 dispatch channels (Cursor, Claude Code, ChatGPT-via-operator, sub-agents). Inspection of `git show --stat` for each commit, cross-referenced against the lane prompts that triggered them, finds **two genuine absorption events** plus **one already-documented Rule 12 wrinkle** (the #50 amend that swept #51's tree, which was the very incident that produced Rule 12 in the first place — not a new pattern).

The substance of every absorbed file was correct and was content the operator intended to ship in the same session. What violated working agreement #8 was the *bundling*: the absorbed bytes landed in a commit whose message advertises only the agent's lane work, so future `git log --grep` searches for "BACKLOG.md history" or "smoke catalog edits" will miss them. The signal is real but small (2 events / 29 commits ≈ 7%), and severity is low because no production code or migrations were affected — every absorption was a docs-side BACKLOG.md status flip or ship-log paragraph that the operator was already planning to commit minutes later anyway.

---

## §2 — Forensic table

| Commit SHA | Intended scope (per message) | Files actually touched (per stat) | Absorbed files | Severity | Notes |
|---|---|---|---|---|---|
| `f1625259` | docs(handoff): SESSION_HANDOFF_2026-05-10.md | SESSION_HANDOFF_2026-05-10.md | — | clean | — |
| `847f79a9` | feat(confidence_tier): #55 code + tests | confidence_tier.py, BACKLOG.md, test_confidence_tier.py | **docs/BACKLOG.md** (status flip OPEN→SHIPPED + ship-log paragraph) | **low** | Cursor-lane prompt was code+test only. Operator had pre-staged BACKLOG flip. |
| `cbcf713b` | docs: handoff addendum + dispatch protocol | SESSION_HANDOFF_2026-05-09_evening.md, dispatch_protocol.md | — | clean | Both files in scope. |
| `63d257fb` | docs(outreach): cold-email variants | cold_email_variants_2026-05-09.md | — | clean | — |
| `f9e9b067` | feat(matcher): #50 minimum-length floor | entity_matcher.py, test_entity_matcher.py | — | clean | — |
| `b361526a` | fix(docs): #51 PowerShell UTF-8 patch | BACKLOG.md, backlog_46_smoke_check_queries.md, phase1_deploy_runbook.md, phase2_first_week_dispatch.md | — | clean (orphaned by amend; not in main ancestry) | All four files in lane scope. Now unreachable from 54a56b1. |
| `79f73961` | (amend) feat(matcher): #50 ≥3-char floor | BACKLOG.md, backlog_46_smoke_check_queries.md, phase1_deploy_runbook.md, phase2_first_week_dispatch.md | **all four** (the amend inherited #51's tree, not #50's) | **already documented** | This is the canonical Rule 12 case. Tree advertises #50 code, holds #51 docs. Skip — Rule 12 covers it. |
| `5730f8a5` | docs(outreach): reply handlers | reply_handlers.md | — | clean | — |
| `10b2f5d2` | docs(backlog,dispatch): #50 ship-log + Rule 12 | BACKLOG.md, dispatch_protocol.md | — | clean | Both in scope. |
| `df612d4c` | docs(outreach): post-launch sponsor comms | post_launch_comms.md | — | clean | — |
| `817987fc` | fix(docs,eval): close #54 dangling refs | confabulation_detector.py, confabulation_query_gen.py, BACKLOG.md, components/confabulation_detector.md, components/confabulation_query_gen.md, confabulation-eval-runbook.md, halt3_definition.md | — | clean | BACKLOG flip is part of "close #54" scope. Borderline. |
| `ba139b57` | docs(state,handoff): refresh bootstrap docs | SESSION_HANDOFF_2026-05-10.md, STATE.md | — | clean | — |
| `d40c020f` | docs(deploy-runbook) | phase1_deploy_runbook.md | — | clean | — |
| `edfe1c63` | docs(phase2): SUPERSEDED first-week dispatch | phase2_first_week_dispatch.md, phase2_lane_decomposition.md | — | clean | lane_decomposition status banner in scope. |
| `9efec365` | docs(outreach): enrichment sprint runbook | enrichment_sprint_runbook.md | — | clean | — |
| `8c8ecdb9` | docs(audit): coverage audit | phase2_midweek_coverage_audit.md | — | clean | — |
| `d060240f` | fix(matcher): #52 trade-aligned bypass | entity_matcher.py, test_entity_matcher_trade_superlative.py | — | clean | — |
| `e1eafe0d` | docs(backlog): #52 SHIPPED + #56-#62 file | BACKLOG.md | — | clean | — |
| `0d566b3d` | docs(maintainability): post-enrichment smoke catalog | post_enrichment_smoke_catalog.md | — | clean | Sub-agent honored prompt; nothing else swept in. |
| `6c6ca021` | feat(test): #56 chat-route UTF-8 | test_chat_route_utf8.py | — | clean | — |
| `21c2e086` | docs(user-facing): Hava FAQ | hava_user_faq.md | — | clean | — |
| `f9904887` | test(matcher): #58 direct floor coverage | test_entity_matcher.py | — | clean | Despite #58 being the lane that flagged a stash race; commit itself is clean. |
| `710487a1` | docs(maintainability): HALT 3 close-out template | halt3_closeout.md | — | clean | Sub-agent honored prompt. |
| `ddc2b133` | docs(backlog): #56 + #58 SHIPPED | BACKLOG.md | — | clean | — |
| `9db35121` | docs(handoff): SESSION_HANDOFF_2026-05-11 | SESSION_HANDOFF_2026-05-11.md | — | clean | — |
| `3e5d2aa3` | docs(outreach): sponsor quick-reference card | sponsor_quick_reference.md | — | clean | — |
| `9fff5c21` | test(confidence_tier): #57 + #59 | test_confidence_tier.py | — | clean | — |
| `9460f69a` | test+docs: #60 mtb invariant + #61 E3 layer | test_entity_matcher.py, backlog_46_smoke_check_queries.md | — | clean | Both in scope. |
| `439ee5d9` | docs(backlog): #57 + #59 SHIPPED | BACKLOG.md | — | clean | — |
| `54a56b1a` | docs(backlog): #57 + #59 + #60 + #61 SHIPPED | BACKLOG.md | — | clean | HEAD. |

**Tally:** 29 commits in range. **1 novel absorption** (`847f79a9`), low severity. **1 pre-existing Rule 12 case** (`79f73961`), already documented. **27 clean.**

---

## §3 — Mechanism analysis

The user's task description hypothesized three mechanisms:

1. **Operator pre-stages BACKLOG.md, then commits agent's file with prior staging carry-over.** The agent's `git add <agent's file>` should produce a clean commit, but if the operator had already run `git add docs/BACKLOG.md` earlier and forgot to commit it, the next `git commit` (with no `--only` flag and no path argument) sweeps everything currently staged.
2. **Operator runs `git add <agent's file>` while their own working-tree edits are dirty, then `git status` shows mixed state.** If operator then runs `git commit` without explicit pathspecs, the staged BACKLOG hunk goes along for the ride.
3. **The `git stash` / `git stash pop` race CC flagged in their #58 report.** A pop after an agent's write can re-introduce dirty content into the next staging operation.

Reviewing the single novel absorption (`847f79a9`, the #55 commit that swept the BACKLOG status flip):

- The BACKLOG hunk in `847f79a9` is a `OPEN, low priority follow-up` → `SHIPPED #55` flip plus a multi-line ship-log paragraph. That paragraph reads as operator-authored prose ("Pytest before: 1348 passed; pytest after: 1369 passed") — written *after* the Cursor lane reported test counts. So the operator clearly authored the BACKLOG edit *between* Cursor's text report and the operator's `git commit`.
- Cursor's lane prompt for #55 explicitly says "code + test only; do not edit BACKLOG.md — operator handles ship-log in a follow-up commit". Cursor honored that — `entity_matcher.py` and `test_confidence_tier.py` are exactly what Cursor's text report mentioned.
- The `git status` at commit time would have shown three modified files (Cursor's two + operator's BACKLOG hunk). The operator's `git add` likely used `git add -u` or `git add .` rather than `git add app/chat/confidence_tier.py tests/test_confidence_tier.py`. That's **mechanism 2**: a path-broad `git add` while the working tree was mixed.

Mechanism 1 (carry-over from prior staging) is unlikely here because nothing was staged before the agent reported — between #54 close and #55 dispatch the operator had committed cleanly. Mechanism 3 (stash race) doesn't fit the timing — #58's stash race was in the afternoon (`f9904887`, 09:47), well after #55 (19:41 the prior evening).

**Best-fit mechanism: #2 — broad `git add` against a mixed working tree.** The `79f73961` Rule 12 case is mechanically distinct (amend re-pointing HEAD) and is already covered.

The cure is operator-side: stage with explicit pathspecs (`git add app/chat/confidence_tier.py tests/test_confidence_tier.py`) rather than `git add -u` / `git add .` whenever any file the agent did *not* report is dirty.

---

## §4 — Rule 13 candidate text

Format matches Rules 1–12 exactly. Ready to paste into `dispatch_protocol.md` between Rule 12 and the closing summary paragraph.

```markdown
## 13. Stage with explicit pathspecs when the working tree is mixed

**Rule** — When the agent reports completion and the operator's own working tree also has dirty edits, stage the agent's files by exact path (`git add <path1> <path2>`). Do not use `git add -u`, `git add .`, or `git add -A` until `git status` shows nothing else outstanding.

**Why** — Agents honor the "do not touch X" half of their prompt: their text report lists exactly the files they wrote. But the commit boundary is the operator's `git add` + `git commit`, not the agent's report. A broad `git add` sweeps anything else dirty in the tree — typically operator-authored ship-log edits to `docs/BACKLOG.md` or sub-agent drafts staged earlier — into a commit whose message advertises only the agent's lane. Substance is correct; the commit is mis-labelled. Future `git log --grep` searches against the absorbed file lose precision, and working agreement #8 (one substantive lane per commit) is silently violated. Established 2026-05-10 (commit `847f79a9`, where the #55 confidence-tier code commit absorbed the operator's pre-authored BACKLOG ship-log hunk).

**Example**

```text
Cursor reports #55 complete: app/chat/confidence_tier.py + tests/test_confidence_tier.py.
Operator has separately edited docs/BACKLOG.md (status flip + ship log).
git add app/chat/confidence_tier.py tests/test_confidence_tier.py
git commit -m "feat(confidence_tier): #55 …"
git add docs/BACKLOG.md
git commit -m "docs(backlog): #55 SHIPPED ship-log entry"
```

**Counterexample**

```text
Cursor reports #55 complete.
Operator's docs/BACKLOG.md is also dirty.
git add -u
git commit -m "feat(confidence_tier): #55 …"
# Commit's tree now contains the BACKLOG flip too.
# git log --stat shows three files; message advertises one lane.
```
```

---

## §5 — Recommendation

**Verdict: leave as a forensic note; do not promote to Rule 13 yet.**

Reasoning:

- **Frequency is too low to justify a rule.** One novel absorption in 29 commits (3.4%) is below the threshold that earned existing rules. Rule 1 (Anchored Edit) was forged from multiple full-file overwrite incidents in a single day. Rule 11 (force-stop agents) came from repeated re-corruption events. Rule 12 (no amend with parallel lanes) came from the explicit #50/#51 wrinkle plus near-misses. A single low-severity sweep does not yet meet that bar.
- **Severity is the lowest of any rule's founding incident.** No production code, no migrations, no rollback impact, no debugging time lost. The absorbed content was material the operator was committing in the next 60 seconds anyway.
- **Cure is mechanical and obvious once articulated** — explicit pathspecs — and is already implicit in Rule 2 ("only then stage files intentionally"). Rule 2 covers the *timing* (after agent reports), and the natural reading of "intentionally" already implies pathspecs over `-u`/`-A`. Adding Rule 13 would be slightly redundant with Rule 2.
- **Counter-argument for promotion.** The pattern is mechanistically distinct from Rule 2 (Rule 2 is about *when*, Rule 13 candidate is about *how*). If a second instance shows up in the next session, that second data point would justify codification. For now, this memo serves as the citation if/when it recurs.

If a second absorption event occurs in the next dispatch session, paste the §4 candidate into `dispatch_protocol.md` as Rule 13 with both incidents cited in the **Why** paragraph. Until then, this memo lives at `docs/maintainability/2026-05-10_absorption_forensics.md` as the on-the-record analysis, and operator vigilance on staging during mixed-tree moments is the informal mitigation.

---

**End of memo.**
