# UPDATE — 2026-05-09 late evening: Phase 2 first-week dispatch FULLY SHIPPED

**The session that wrote this handoff continued past the original wrap point and shipped two more lanes (Lane 3 + Lane 4) plus a HALT 3 definition recovery.** The body of this doc below is preserved as-written, but the "remaining work" section is superseded — Phase 2 first-week is now complete.

## Final commits (in chronological order):

- `dd484a0` — Lane 1 substantive (#47/#48/#49 fix bundle)
- `db718ac` — Lane 1 STATE close-out
- `8c5d008` — Lane 2: P2.HOME.1 DISCLOSURE_WORD on /home + filed #50/#51/#52/#53
- `489915f` — Original session handoff doc (this file)
- `d6cd782` — HALT 3 definition recovery → `docs/maintainability/halt3_definition.md` + #53 status update
- `e725717` — **(REVERTED)** Lane 3 + partial Lane 4; alembic multi-head broke production
- `913e790` — Revert of `e725717` to restore known-good state
- `130f8ad` — Phase A: Phase 8.8.6 spec restore from git history (`731d551c`) + cold email variants + BACKLOG #54
- `1749675` — Lane 3 (clean re-dispatch): P2.BL.45 expand `verification_method` CHECK → migration `c5d6e7f8a9b0`
- `3c40ff4` — BACKLOG #55 (extend `confidence_tier._KNOWN_METHODS`)
- `24abe82` — Lane 4 (clean re-dispatch): P2.OBS.1 disclosure-renderer observability → migration `d6e7f8a9b0c1`

## Final state at session close:

- **Pytest:** 1348 passed, 6 subtests passed (1341 baseline + 7 net new from Lane 4 tests).
- **Alembic head:** `d6e7f8a9b0c1` (Lane 4); clean linear history (no multi-head merge needed because we sequenced Lane 3 before Lane 4 on the second pass).
- **Feature flags:** `FEATURE_FLAG_DISCLOSURE_RENDERER=false` (HOLD until enrichment); `FEATURE_FLAG_CONFIDENCE_TIER=true` (verified mid-session).
- **Production verified:** `chat_logs` has the four new `disclosure_*` columns post-deploy of `24abe82` (Railway web SQL confirmed, columns nullable, table currently empty).

## Backlog adds this session:

- `#50` single-char query matches short entity prefix (LOW; pre-existing matcher behavior)
- `#51` accent-bearing queries return HTTP 400 (LOW; pre-existing preprocessing)
- `#52` trade-superlative queries return null where real entities exist (LOW; #47 over-conservatism)
- `#53` HALT 3 undefined on-tree → recovered via `docs/maintainability/halt3_definition.md`; gates Phase 2.5
- `#54` dangling `relay/halt1-closure-final-lexicons.md` doc references (LOW; cosmetic doc-hygiene)
- `#55` extend `confidence_tier._KNOWN_METHODS` for Lane 3's new operator vocab (LOW; should ship before enrichment sprint completes)

## What's left for the next session:

- **Operator enrichment sprint** (Casey-driven; toolchain ready at `templates/enrichment/` + `scripts/ingest/*`)
- **Phase 2.5 / P2.PREM.1** gated on HALT 3 close (multi-week; sequenced work-to-close in `docs/maintainability/halt3_definition.md` §6)
- **Phase 2 mid-week** lanes per `docs/maintainability/phase2_lane_decomposition.md`
- **Three small follow-ups (#50/#51/#54)** that can roll into any future code-hygiene lane
- **#55 should ship before enrichment** so confidence-tier classifier doesn't under-rank operator-vocab rows

## Critical lesson learned (read before dispatching parallel agents):

Mid-session, we dispatched Cursor (Lane 3) + Claude Code (Lane 4) in parallel. Both wrote files to the same working tree on overlapping schedules. Casey ran `git add -A` mid-flight, capturing partial Lane 4 work in a Lane 3 commit. The result was a multi-head alembic state that broke Railway's deploy and 1351 pytest errors locally. Recovery required `git revert e725717`, sequential replay of all the work, ~75 minutes of cleanup.

**The protocol now**: dispatch lanes **sequentially** when they touch overlapping files (especially `app/db/models.py` and `alembic/versions/`). Wait for the agent's **text report** before any `git add` — the report is the explicit "I'm done writing files" signal. Working-tree state alone isn't reliable when an agent is mid-flight.

Sequential dispatch (Cursor for Lane 3 → land it → Claude Code for Lane 4 → land it) was what worked the second time. The alembic head sequencing was clean: Lane 3's `c5d6e7f8a9b0` became Lane 4's `down_revision`, no merge migration needed.

---

# Session Handoff — Lane 1 close + Lane 2 close + HALT 3 audit (2026-05-09 evening)

**Audience:** A fresh Cowork / Claude / Cursor session continuing where this evening session left off.
**Read time:** 4 minutes for the bootstrap.
**Companion docs:** `docs/SESSION_HANDOFF_2026-05-09.md` (this morning's bootstrap — Phase 1 close + Phase 2 kickoff), `docs/STATE.md` (canonical project state), `docs/maintainability/phase2_first_week_dispatch.md` (dispatch playbook for Lanes 2-5).

---

## §0 — For the next agent: start here

You're picking up after this evening's session. **Most of the Phase 2 first-week leaderboard is done:** Lane 1 (#47/#48/#49 fix bundle) shipped and verified live with CT flag re-enabled, and Lane 2 (P2.HOME.1 `DISCLOSURE_WORD` consistency on `/home`) shipped and visually verified. **Lane 3 (P2.BL.45) and Lane 4 (P2.OBS.1) are next on the playbook.**

**Recommended boot sequence:**

1. Read this doc end-to-end (~4 min).
2. Skim this morning's `docs/SESSION_HANDOFF_2026-05-09.md` §0, §3.1, §4 for deeper Phase 1 context — the rest is largely covered here.
3. Read `docs/maintainability/phase2_first_week_dispatch.md` §6 (Lane 3 dispatch prompt for P2.BL.45) and §7 (Lane 4 dispatch prompt for P2.OBS.1).
4. Verify pytest baseline: `python -m pytest -q` should show **1341 passed**. If different, `git log --oneline -10` to see what changed since.
5. Check Railway env vars: `FEATURE_FLAG_DISCLOSURE_RENDERER` should be **false** (still HOLD until enrichment); `FEATURE_FLAG_CONFIDENCE_TIER` should be **true** (re-enabled this evening, verified clean).
6. Ask the operator (Casey) which lane to dispatch first.

## §1 — One-paragraph summary

This session shipped Phase 2 first-week Lanes 1 and 2 to production (Lane 1 substantive `dd484a0` + STATE `db718ac` + Lane 2 `8c5d008`), closed Backlog #47, #48, #49, ran the full 39-query Lane 1 smoke catalog cleanly, re-enabled `FEATURE_FLAG_CONFIDENCE_TIER` and verified the hedge fires correctly under CT-on (Tier 2/3 LOW-confidence rows produce hedge in LLM voice via Lane CT2.B; #48 negation skip suppresses incorrect hedges; #49 raw-cache contract works across flag-flip), filed four new follow-up tickets (#50 single-char query match, #51 accent handling 400, #52 trade-superlative over-conservative matching, #53 HALT 3 undefined on-tree), conducted a parallel HALT 3 audit that revealed HALT 3 is undefined on-tree (not just unverified) and gates Phase 2.5 / P2.PREM.1, and **recovered the HALT 3 definition + close-criteria framework from the off-tree strategy doc into `docs/maintainability/halt3_definition.md`** — critical finding from the recovery is that the three acceptance bands are set during HALT 3 close from baseline measurements, NOT pre-stated in the strategy doc.

## §2 — What landed this evening

| Lane | Owner | Files | Tests | SHA |
|---|---|---|---|---|
| Lane 1 — #47/#48/#49 fix bundle | Cursor | `app/chat/entity_matcher.py` (cross-category guard with trade-cluster taxonomy), `app/chat/tier2_formatter.py` (negation-aware skip in `_enforce_low_tier_phone`), `app/chat/tier3_handler.py` + `app/chat/llm_cache.py` (raw cache storage + serve-time post-process), 3 new test files | 13 net new (5 + 6 + 2) | `dd484a0` |
| Lane 1 — STATE close-out | Cowork primary | `docs/STATE.md` Production block + new top entry | n/a | `db718ac` |
| Lane 2 — P2.HOME.1 `DISCLOSURE_WORD` consistency on `/home` | Cursor | `app/home/router.py` (import + context inject), `app/templates/home.html` (subtitle + 3 card badges), `tests/test_home_disclosure_word.py` (new) | 1 net new | `8c5d008` |
| BACKLOG: 4 new follow-up tickets filed (#50, #51, #52, #53) + Lane 2 ship-log | Cowork primary | `docs/BACKLOG.md` | n/a | included in `8c5d008` |
| HALT 3 audit | General-purpose agent | (read-only investigation) | n/a | finding filed as #53 |
| HALT 3 definition recovery | Cowork primary | new `docs/maintainability/halt3_definition.md` (recovered from `ask-hava-detailed-plan.docx` §1.1 + Phase 1 close criteria + Decision #37); BACKLOG #53 status update appended | n/a | follow-up commit |

**Combined:** 1341 tests passing; both feature-flag states correct (`DISCLOSURE_RENDERER=false`, `CONFIDENCE_TIER=true`); production verified across 39-query Lane 1 smoke catalog + 4 adversarial smoke checks + cache-hit/miss across flag-flip + Lane 2 visual verification.

### Specs and docs that landed
- `docs/BACKLOG.md` — Lane 1 ship-logs (3 entries) + Lane 2 ship-log (1 entry) + 4 new OPEN tickets (#50/#51/#52/#53).
- `docs/STATE.md` — Production block refreshed (Slice 71b → Lane 1 close, 921 → 1341); new top entry under "Recently shipped (high signal)" capturing Lane 1 close.

## §3 — Production state at session close

- **Repo `main` HEAD:** `8c5d008` (Lane 2 + 4 follow-up tickets) on top of `db718ac` (Lane 1 STATE close-out) on top of `dd484a0` (Lane 1 substantive). All deployed to Railway and verified live.
- **Pytest:** 1341 passed (Lane 1 baseline 1340 + Lane 2's 1 new test).
- **Feature flags:**
  - `FEATURE_FLAG_DISCLOSURE_RENDERER = false` (intended; HOLD until enrichment populates Sponsor + Provider rows).
  - `FEATURE_FLAG_CONFIDENCE_TIER = true` (re-enabled this evening after Lane 1 unblocked it; verified clean across 39-query smoke catalog + cache-hit/miss verification).
  - Audience-signal persistence: AUTOMATIC (column-gated, working).
- **Cache state:** `LlmResponseCache` flushed twice this session (pre-deploy via Railway web SQL `DELETE FROM llm_response_cache;` returned 0 rows; post-deploy via same path). Entries written this evening are in the new raw-text format per #49 contract.
- **Live `/api/chat` smoke results:** all four adversarial checks pass (`phone for addrss` → null; `sloane number` → null; `what is the best plumber...` → null with no BMX false positive, no phone+hedge tail; `hours for All Seasons Plumbing` → entity matches via Tier 1). Cache-test pair (cache miss + cache hit on identical query) confirms #49 raw-storage contract works across flag-flip. CT-on verification (`tell me about All Seasons Plumbing`) confirms hedge appears in LLM voice via Lane CT2.B; CT-on negation case (`what is the best plumber...` cache hit) confirms #48 suppresses hedge under cache-hit path with CT enabled.

## §4 — Open backlog at session close

### Phase 2 first-week — remaining

- **Lane 3 — P2.BL.45 `verification_method` CHECK constraint expansion** — small Cursor lane (30-45 min); dispatch prompt in `phase2_first_week_dispatch.md` §6.
- **Lane 4 — P2.OBS.1 disclosure-renderer observability instrumentation** — heavy Claude Code lane (45-75 min, 7+ files: schema migration + renderer instrumentation + handler wiring + tests + spec update); dispatch prompt in `phase2_first_week_dispatch.md` §7. **Now safe to dispatch since CT is on.**
- **Lane 5 — Operator enrichment sprint** — operator-driven, parallel to engineering lanes; toolchain ready (`templates/enrichment/`, `scripts/ingest/validate_enrichment_csv.py`, `scripts/ingest/ingest_enrichment_csv.py`).

### NEW filed this session — low-priority Phase 2 follow-ups

- **#50 — Single-char queries match short entity prefix** (LOW). Surfaced from Class C2 of smoke catalog: query `"a"` → entity `A & A Electronics Assembly`. Recommended fix: ≥3-char minimum-length floor at matcher entry points.
- **#51 — Accent-bearing queries return HTTP 400** (LOW). Surfaced from Class E3: query `múdshärk bréwery` → 400. Recommended fix: NFD-normalize at chat-route boundary OR return 422 with friendly_errors message.
- **#52 — Trade-superlative queries return null where real entities exist** (LOW). Surfaced from Class B5 + Lane 1's "best plumber" → null observation. Recommended fix: trade-aligned bypass in `_category_guard_skips_row` when query and row tag the same trade.

### NEW filed this session — strategic, gates Phase 2.5

- **#53 — HALT 3 undefined on-tree; close-out blocked on definition recovery** (gates Phase 2.5 / P2.PREM.1). HALT 3 is referenced in 5+ docs as a Phase 1 deliverable but is DEFINED nowhere on-tree. Strategy doc (`ask-hava-detailed-plan.docx` Decision #37) is off-tree. Multi-week work-to-close: recover definition → author spec with numeric thresholds → ≥1 week production traffic dwell → run confabulation harness → close-out doc → P2.PREM.1.

### Carried forward from morning session

- #39 — thread audience signal into placement-regime selection (DEFERRED to Phase 2; precondition: 4-6 weeks of `chat_logs.audience_signal` data).
- Backlog #2 — `_time_bucket_first_hits` and broad `span` (Phase 2 candidate, pre-Phase-1).
- Backlog #18 — Repo hygiene & documentation hierarchy (PM phases A-D, pre-Phase-1).

## §5 — HALT 3 audit findings (strategic — read before any Phase 2.5 conversation)

**Headline: HALT 3 isn't unverified — it's undefined on-tree.** Full details in `docs/BACKLOG.md` #53.

The audit traced HALT 3 references through `confabulation-eval-runbook.md`, `phase1_deploy_runbook.md` §9, `phase2_lane_decomposition.md`, `phase2_first_week_dispatch.md` §9, and `STATE.md`:215. Only on-disk artifact: `relay/halt3-step1-runs-excerpts.txt` (raw confabulation-harness probe captures, no §Outcome). No HALT 3 spec on disk. No HALT 1 or HALT 2 closure docs (`relay/halt1-closure-final-lexicons.md` is referenced from code but missing from disk — orthogonal concern). Phase 8.8.6 spec was pruned per `STATE.md`:215, possibly recoverable from git history.

**Implication:** "Audit HALT 3" cannot mean "verify the close criteria are met." The criteria are not on-tree. HALT 3 must first be DEFINED before it can be closed. Multi-week sequence: recover definition → author spec with numeric thresholds → run harness → close-out → unblock P2.PREM.1.

**Status update (2026-05-09 evening — definition recovery completed):** The HALT 3 definition was recovered from the off-tree `ask-hava-detailed-plan.docx` into `docs/maintainability/halt3_definition.md`. **Critical finding from the recovery:** the strategy doc explicitly states the three bands (gating-rate, anchor-regression, catalog-flagging) are *set during HALT 3 close from baseline measurements*, not pre-stated. So "definition recovery" yielded the framework + sequencing constraints + Decision #37's role (renderer Premier-gate), but NO specific numbers — by design. The next gate is the enrichment sprint completion, then ≥1 week production traffic dwell, then the harness baseline run, then the bands get set from baseline output.

**Operational implication for Phase 2 timeline:** Phase 2.5 (Premier inventory open) is genuinely "month 2+" not "week 3." Lanes 2-4 and the enrichment sprint can proceed normally — they don't depend on HALT 3. The full sequenced work-to-close is in `docs/maintainability/halt3_definition.md` §6.

## §6 — What Phase 2 should consider first (next session)

The recommended first-week lane order from `phase2_first_week_dispatch.md` §3 still holds, with Lane 1 + Lane 2 already shipped:

1. ~~Lane 1: #47/#48/#49 fix bundle~~ — SHIPPED.
2. ~~Lane 2: P2.HOME.1~~ — SHIPPED.
3. **Lane 3: P2.BL.45** — verification_method CHECK constraint expansion (Cursor, 30-45 min). Dispatch prompt: `phase2_first_week_dispatch.md` §6.
4. **Lane 4: P2.OBS.1** — disclosure-renderer observability instrumentation (Claude Code, 45-75 min, multi-file). Dispatch prompt: `phase2_first_week_dispatch.md` §7. **Highest leverage** — every downstream Phase 2 decision depends on having structured per-render telemetry.
5. **Lane 5: Operator enrichment sprint** — parallel to engineering lanes; toolchain ready.

**Optional sequencing tweaks:**

- **HALT 3 definition recovery** can happen any time. 15 min of Casey reading the `.docx` and copying into a new `.md` unblocks multi-week downstream work. Worth doing before any other strategic conversation about Phase 2.5.
- **Lane 3 vs Lane 4 ordering** — playbook lists Lane 3 first (smaller), but Lane 4 is higher leverage. If the operator's energy is high, dispatch Lane 4 first; if low, Lane 3 first as a confidence-building small ship.

## §7 — Things that look broken but aren't

- **`relay/halt1-closure-final-lexicons.md` referenced from code but missing from disk** — orthogonal concern surfaced by HALT 3 audit. `app/eval/confabulation_detector.py` and `confabulation_query_gen.py` reference this file. Confabulation harness may still work (lexicons could be hardcoded in code or read from a different location) but the dangling reference is worth filing as a separate ticket if it bites.
- **STATE.md "Recent commits" block is stale** — last refreshed at Slice 71b; should be updated via `git log --oneline -30` in a future STATE close-out. Not blocking.
- **Single-char query "a" matching "A & A Electronics Assembly"** — pre-existing matcher behavior, filed as #50. Not Lane 1 regression.
- **Accent-bearing query 400 error** — pre-existing preprocessing concern, filed as #51. Not Lane 1 regression.
- **"What is the best plumber" → null** — Lane 1 dispatch acceptance allowed null; ideal-case behavior would surface a real plumber. Filed as #52. Not a regression.
- **The `<aside class="sponsor">` "This slot is open" widget on /home** — that's the existing sponsor-fallback path, not the Lane 2 spotlight cards. Working as expected (different mechanism — Sponsor model fallback when no eligible row exists, separate from `DISCLOSURE_WORD`).

## §8 — Topology and protocol that worked

Same as morning session, with confirmed practice:

- **Cowork primary** orchestrates and integrates; Cursor handles focused-file edits and small-to-medium lanes; general-purpose agents handle parallel investigation lanes (HALT 3 audit was the protocol-rule-5 voice-battery analog for this session).
- **Anchored Edit over full-file Write** held throughout this session — no truncation collisions across ~5 doc files.
- **Production cache purge via Railway web SQL** is the operator-friendly path (no `DATABASE_URL` env-var fiddling required); proven across two purges this session. Filed as the canonical operational pattern in this handoff.
- **PowerShell single-quoted JSON bodies** for `Invoke-RestMethod` (no `$body` interpolation issues) — confirmed on the 39-query smoke loop.
- **Voice-battery / 30-query smoke catalog as protocol-rule-5 verification** — proven; the catalog caught zero regressions on Lane 1's matcher changes.

## §9 — Final test count + cache state

```
$ python -m pytest -q
1341 passed in ~6min

$ alembic heads
b4c5d6e7f8a9 (head)   # unchanged from morning session — Lane 1 + Lane 2 are TypeDecorator/code-only changes, no migrations
```

Cache state: `LlmResponseCache` flushed twice this session; current entries are in #49 raw-text format (post-`strip_soft_suggest`, no phone+hedge baked in). Serve-time `_enforce_low_tier_phone` runs on cache hits, gated on `FEATURE_FLAG_CONFIDENCE_TIER`.

---

*This handoff captures Lane 1 close + Lane 2 close + HALT 3 audit + 4 follow-up tickets. The morning handoff (`docs/SESSION_HANDOFF_2026-05-09.md`) remains the broader Phase 1 / Phase 2 context. Next session picks up Lane 3, Lane 4, or HALT 3 definition recovery — operator's call.*
