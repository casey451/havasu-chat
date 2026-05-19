# Phase 7 Close-Out — Lane E SHIPPED at `0a305e0` (with HALT 3 flag-flip deferred to Phase 7.5)

> **What this is:** the durable close-out for Phase 7 (chat ENTITY wiring + boat-mode + conditions awareness + HALT 3 close-out + cross-entity + snowbird-return view). Instantiated from `outputs/lane_d_e_post_ship_close_out_template.md` post-Cursor-§12-report 2026-05-20. Captures Cursor's §12 findings, acceptance-gate verification, the substantive deviations, and the HALT 3 validator initial-run outcome (12/22 PASS) with the operator-locked decision to defer iteration to a Phase 7.5 polish lane.
>
> **Author:** Cowork primary, 2026-05-20 post-`0a305e0`.
>
> **Ship SHA:** `0a305e0` (`feat(phase7): chat ENTITY wiring + boat-mode + conditions awareness + HALT 3 close-out + cross-entity + snowbird-return view`).
>
> **Alembic head post-ship:** `c9d0e1f2a3b4` (Phase 7's `users.last_active_at` migration; chains from `f6a7b8c9d0e1`; revision ID chosen to avoid prior-session collision attempts `a7b8c9d0e1f2` / `b8c9d0e1f2a3` per 2026-05-20 alembic-collision gotcha).
>
> **Companion docs:**
> - `outputs/cursor_dispatch_prompt_phase_7.md` — original dispatch wrapper Cursor consumed (post-recovery via `outputs/phase_7_recovery_dispatch_note.md` amendment)
> - `outputs/phase_7_recovery_dispatch_note.md` — Phase 7 recovery post-6.4-collision; the actual re-dispatch context
> - `outputs/phase_7_halt3_initial_run_report.md` — raw HALT 3 validator output (12/22 PASS); per-query interpretation; Phase 7.5 input
> - `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md` — Phase 7.5 scope + Cursor approach for the failure-triage + flag-flip closure
> - `outputs/dispatch_channels_alembic_collision_gotcha_draft.md` — gotcha that Phase 7's migration ID choice (`c9d0e1f2a3b4`) operationalized

---

## §1 Cursor §12 final report summary (received 2026-05-20)

**Baseline verification (observed, not assumed):**

| Check | Observed |
|---|---|
| Pytest collect (pre-work) | 2060 |
| Alembic current (dev DB, pre-work) | `f6a7b8c9d0e1` |
| Pytest collect (post-work) | 2135 (+75 vs baseline; includes Phase 6.4's +25 carried in addition to Phase 7's +50) |
| Pytest final run | 2133 passed + 2 skipped |
| Alembic head (script) | `c9d0e1f2a3b4` (post Phase 7 migration; single head — multi-head trap avoided) |
| Alembic current (dev DB) | `f6a7b8c9d0e1` initially → `c9d0e1f2a3b4` after `alembic stamp` (operator action 2026-05-20) |
| Ruff | Clean on Phase 7 Python paths |

**Files created:** 15 (9 new code files + 1 alembic migration + 6 new test files; total ~1,100 lines of new code + ~50 new tests).

**Files modified (anchored edits):** 13 (8 chat module + 1 route + `models.py` + `home.html` + `home/router.py` + 3 test files).

---

## §2 Acceptance-gate verification

| Gate | Status | Notes |
|---|---|---|
| (a) Chat tier 2/3 wired to ENTITY table | ✅ SHIPPED | New `app/chat/entity_catalog_query.query_entities()` + `prefers_entity_catalog()` gate. Replaces pre-pivot River Scene events catalog query at `tier2_db_query.py:33+`. Legacy events/programs path preserved for `open_now` + `entity_name-only` queries (compat layer documented in §3 Finding #2). |
| (b) Chat boat-mode awareness | ✅ SHIPPED | New `ChatRequestContext` reads `?boat=1` + `X-Boat-Mode: 1` header + `users.preferred_mode` column (Phase 3.1 reuse, same column Phase 6.4 wires). Tier 2 filters `Entity.boat_access IS NOT NULL`. Tier 3 LLM preamble. |
| (c) Chat conditions awareness via STUB reuse | ✅ SHIPPED | Reuses `STUB_CURRENT_TEMPERATURE_F` + `HEAT_BIAS_*` constants + `compute_card_rank` from `app/core/ranking.py` per design. Tier 3 heat preamble. Phase 8 will swap `STUB_CURRENT_TEMPERATURE_F` → `read_current_temperature_f()` cleanly. |
| (d) HALT 3 close-out | ✅ INFRA SHIPPED; **validator initial run = 12/22 PASS; flag flip BLOCKED — see §3 Finding #1** | `app/chat/halt3_eval_set.yaml` (22 queries within 20–30 band) + `app/chat/halt3_validator.py` shipped + runs. Operator-manual `FEATURE_FLAG_DISCLOSURE_RENDERER` flip remains deferred (this was always operator-out-of-band, but with validator failures the flip is now blocked on Phase 7.5 polish-lane closure). |
| (e) Cross-entity queries | ✅ SHIPPED | New `app/chat/entity_intent.detect_multi_domain_category_slugs()` + multi-slug ENTITY query interleaved by `compute_card_rank`. |
| (f) Snowbird-return view | ✅ SHIPPED | New `app/chat/snowbird_query.py` + `app/home/snowbird_panel.py` + `app/templates/components/snowbird_panel.html`. Oct 1 – Apr 30 window + `last_active_at` heuristic. `home.html` anchored at `<!-- snowbird-panel-include -->` below the hero (preserves Phase 6.4's `<!-- search-bar-include -->` at hero; gotcha #18 home.html anchor coordination held). |
| Tests | ✅ 50 new (target +50–80; met) | 2133 passed + 2 skipped of 2135 collected. |
| Ruff | ✅ clean | |
| Migration | ✅ `c9d0e1f2a3b4` ships cleanly | Chains from `f6a7b8c9d0e1`. Avoided collision with `a7b8c9d0e1f2` / `b8c9d0e1f2a3` per 2026-05-20 gotcha. |

**5 of 6 deliverables fully met; deliverable (d) HALT 3 — infrastructure shipped + validator runs + initial run reveals 10 failures requiring triage (Phase 7.5 polish lane).**

---

## §3 Substantive findings + deviation triage

### Finding #1 — HALT 3 validator initial run: 12/22 PASS; flag flip BLOCKED; Phase 7.5 polish lane required

The HALT 3 validator runs cleanly (infrastructure works) and produces a per-query report. Initial run against `halt3_eval_set.yaml` (22 queries):

```
cited_coverage=42% (target 100%)
missing_confab_max=0.50 (target 0.0)
all_passed=False
12 PASS / 10 FAIL
```

**Failure breakdown:**

| Category | Count | Queries | Severity | Likely cause |
|---|---|---|---|---|
| Confabulation: chat fabricated citation when should be `i_dont_know` | 1 | q07 (cited + 0.50 confab) | **P0 — the original sin HALT 3 was built to prevent** | Chat hallucinating entity citation for query about entity not in catalog. Smoking gun. |
| Expected `cited`, got `i_dont_know` | 6 | q03, q10, q14, q16, q17, q21 | Medium | Chat returning "I don't know" when entity may actually be in catalog. ENTITY catalog query missing matches OR disclosure renderer too conservative OR eval set expects entities not actually present. |
| Expected `i_dont_know`, got `uncited` | 2 | q06, q22 | Medium-high | Chat producing uncited responses on missing-data cases. Disclosure renderer not catching these. |
| Tier + disclosure mismatch | 1 | q02 (expected tier=2/cited, got tier=3/i_dont_know) | Low | Tier classification differs from eval expectation. Could be eval set too strict. |

**Disposition:** **Defer iteration to Phase 7.5 polish lane** (operator decision 2026-05-20). Phase 7 ships with HALT 3 infrastructure complete + validator functional + 22-query eval set authored + initial-run failure surface documented. Phase 7.5 polish lane:
1. Triages each of the 10 FAILs per-query: real-bug-needs-fix vs eval-set-too-strict
2. Fixes the real bugs (q07 confabulation is the priority)
3. Updates the eval set if any expectations were wrong
4. Re-runs validator to acceptance (100% cited coverage + 0.0 confabulation max)
5. Then operator flips `FEATURE_FLAG_DISCLOSURE_RENDERER=true` out-of-band on Railway

Phase 7.5 dispatch artifacts: `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md` (scope + Cursor approach) + `outputs/phase_7_halt3_initial_run_report.md` (raw report + per-query interpretation).

**Phase 6.5 + Phase 8 NOT blocked by Phase 7.5.** The HALT 3 flag flip is independent of those lanes' scopes. Phase 7.5 can dispatch in parallel with Phase 6.5 / Phase 8 IF file-scope disjoint (app/chat/halt3_* + eval set + possibly disclosure_render.py for 7.5; Phase 6.5 = templates/static/routes; Phase 8 = app/conditions/ + app/alerts/ + new routes — disjoint). The 2026-05-20 alembic-collision gotcha still applies if Phase 7.5 ships any migration (unlikely — HALT 3 polish is code-side).

### Finding #2 — `prefers_entity_catalog()` compat gate (sensible deliberate compromise)

The `prefers_entity_catalog()` gate function returns `False` for `open_now` and `entity_name-only` queries, falling back to the legacy events/programs SQL path. This kept the pre-existing tier2 tests green AND explains why Phase 6.4's full-suite saw 42 tier2 failures (Phase 6.4's working tree had Phase 7's WIP without this gate yet authored). Cursor's `tests/test_tier2_db_query.py` monkeypatches `prefers_entity_catalog → False` for the synonym-map regression test, with explicit narrative that this documents legacy SQL as the authority for that assertion.

**Disposition: ACCEPT.** Sensible compatibility layer.

**Implication for Phase 8:** when Phase 8 swaps `STUB_CURRENT_TEMPERATURE_F` → `read_current_temperature_f()`, the chat path will read live conditions ONLY through the ENTITY catalog path (where `prefers_entity_catalog()` returns True). `open_now` + `entity_name-only` queries don't get heat-bias applied. This is documented in Phase 7's commit body + the Phase 8 dispatch wrapper acknowledges it.

### Finding #3 — `User.last_active_at` re-added (recovery from Phase 6.4 collision-cleanup)

Cursor: "Phase 6.4 collision reverted User.last_active_at from ORM while chat code still referenced it — restored in app/db/models.py this session."

**Disposition: ACCEPT.** Exactly the right recovery move. Phase 6.4's collision-cleanup was aggressive enough to remove the ORM column declaration; Phase 7's recovery dispatch re-added it cleanly via the new unique-revision migration. Closes the collision wound.

### Finding #4 — Tier 2 row shape: `type: "provider"` when commercial Provider exists

Cursor documents formatter-compat: row shape uses `type: "provider"` when a commercial Provider record exists for the entity, otherwise the ENTITY shape. Sensible backward-compat layer.

**Disposition: ACCEPT.** Worth a one-line note here (just noted).

### Finding #5 — hint_extractor token-budget warnings (secondary signal; perf carry)

The HALT 3 validator run logged 22 warnings: `hint_extractor: token usage exceeds soft budget (inp=~378 out=8)` — one per query. Hint extractor is being invoked with longer-than-expected input. Not a HALT 3 pass/fail concern, but a perf carry to track.

**Disposition: V1.5 polish candidate.** Not Phase 7 scope; not blocking the close-out. Worth noting in `outputs/v1_5_carry_inventory_triage.md` as a new carry.

### Finding #6 — Dev DB drift on `users.last_active_at` (operator action resolved 2026-05-20)

Cursor's initial `python -m alembic upgrade head` failed with "duplicate column name: last_active_at" — column already existed in dev SQLite DB from prior partial work (the pre-6.4-collision Phase 7 Cursor session), but alembic version table was still stamped at `f6a7b8c9d0e1`. Operator ran `python -m alembic stamp c9d0e1f2a3b4` to reconcile; `python -m alembic current` now returns `c9d0e1f2a3b4 (head)`.

**Disposition: RESOLVED operator-side 2026-05-20.** No code change needed. Railway production has never had the partial state and will upgrade cleanly via `alembic upgrade head` at next deploy.

---

## §4 Commit batch landed

| # | SHA | Subject |
|---|---|---|
| 1 | `0a305e0` | `feat(phase7): chat ENTITY wiring + boat-mode + conditions awareness + HALT 3 close-out + cross-entity + snowbird-return view` |

27 files changed, 2040 insertions(+), 26 deletions(-). 15 new files (1 alembic migration + 8 chat module files + 1 home/ panel + 1 component template + 6 test files; ~1,100 lines of new code + ~50 new tests).

**To follow (separate commits per Rule 8):**
- `docs(phase7): close-out + master plan §4 Phase 7 SHIPPED line + STATE.md prepend + Phase 8 wrapper SHA-patch`
- `chore(outputs): Phase 7 HALT 3 initial run report + Phase 7.5 polish-lane dispatch note (validator triage queue)`

---

## §5 Carries forward

- **Phase 7.5 polish lane** — see `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md` for scope + Cursor approach. Triages 10 HALT 3 failures + closes flag-flip gate. Can dispatch in parallel with Phase 6.5 / Phase 8 (file-scope disjoint per gotcha #18; no migration expected).
- **Phase 6.5 dispatch** — wrapper at `outputs/cursor_dispatch_prompt_phase_6_5.md`. SHA slots resolve to `<<<PHASE_6_4_HEAD_SHA>>>` = `96c915d` and `<<<PHASE_6_4_ALEMBIC_HEAD>>>` = `f6a7b8c9d0e1` (Phase 6.4's alembic head — unchanged since 6.4 shipped no migration). **Important:** Phase 6.5 wrapper was authored against Phase 6.4 head and Phase 6.4's home.html shape. Phase 7's home.html anchor for snowbird-panel-include is now also in place. Phase 6.5 wrapper instructs Cursor to preserve BOTH anchors (`<!-- search-bar-include -->` at hero + `<!-- snowbird-panel-include -->` below hero).
- **Phase 8 dispatch** — wrapper at `outputs/cursor_dispatch_prompt_phase_8.md` is now READY to dispatch. SHA slots SHA-patched to `0a305e0` + `c9d0e1f2a3b4` in the same commit batch as this close-out doc.
- **`FEATURE_FLAG_DISCLOSURE_RENDERER` flip** — remains operator-deferred until Phase 7.5 validator goes 22/22 PASS.
- **HALT 3 validator hint_extractor token-budget perf warnings** — 22 instances of `token usage exceeds soft budget (inp=~378 out=8)`. Not blocking; V1.5 polish candidate. Add to V1.5 carry inventory triage doc.
- **Phase 6.4 + Phase 7 alembic-collision gotcha** — drafted at `outputs/dispatch_channels_alembic_collision_gotcha_draft.md`; fold into `docs/maintainability/dispatch_channels.md` at next docs checkpoint.

---

## §6 What Phase 7 unblocks (post-close-out)

| Lane | Status |
|---|---|
| Phase 6.5 (homepage rebuild + 8 themed group tiles + venue-events region hook) | UNBLOCKED — wrapper ready at `outputs/cursor_dispatch_prompt_phase_6_5.md` |
| Phase 7.5 (HALT 3 polish lane) | UNBLOCKED — dispatch note at `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md` |
| Phase 8a (conditions + alerts) | UNBLOCKED — wrapper SHA-patched at `outputs/cursor_dispatch_prompt_phase_8.md`; operator prereqs all RESOLVED (AirNow + USGS + Nixle agency 3726) |
| Phase 8b (cat-13 expansion) | Deferred; micro-dispatch after 8a |
| Phase 9 (events + RRULE + Things to Do) | Architectural design at `outputs/phase_9_architecture_design.md`; wrapper to be authored later |

Three lanes can dispatch in parallel post-Phase-7 if file-scope-disjoint:
- Phase 6.5 = `app/templates/home.html` + `app/templates/components/themed_tile.html` + `app/static/styles/components/` + `app/api/routes/home.py` + `app/templates/provider_profile.html` (venue-events anchor)
- Phase 7.5 = `app/chat/halt3_*` + `app/chat/disclosure_render.py` + chat module touches as needed
- Phase 8a = `app/conditions/` + `app/alerts/` + `app/api/routes/conditions.py` + `app/api/routes/alerts.py` + `app/templates/components/conditions_strip.html` + `app/static/js/conditions_strip.js` + STUB swap in `app/core/ranking.py`

**Alembic concern:** only Phase 8 ships a migration (verify dirty Phase 3.1 schema first). Phase 6.5 + 7.5 = no migration. So no alembic-collision risk in this triple-parallel posture.

---

## §7 Pre-Phase-8 verification commands

When the operator is ready to dispatch Phase 8 (any time after this close-out commits + pushes):

```powershell
git log --oneline -5
# Expected newest: <docs commit> + 0a305e0 feat(phase7) + 616fd8b + e3a5a59 + ...

python -m alembic current
# Expected: c9d0e1f2a3b4 (post Phase 7)

python -m alembic heads
# Expected: c9d0e1f2a3b4 (single head — multi-head trap avoided)

python -m pytest --collect-only -q | tail -3
# Expected: 2135 collected (Phase 7 ship state)
```

Then patch the Phase 8 wrapper clipboard pipeline + paste to fresh Cursor.

---

*Authored by Cowork primary at the post-`0a305e0` Phase 7 close-out session (2026-05-20). Lives at `outputs/phase_7_close_out.md`. Companion docs: `outputs/phase_7_halt3_initial_run_report.md`, `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md`. Phase 7 shipped; HALT 3 flag-flip deferred to Phase 7.5; Phase 6.5 + Phase 8 + Phase 7.5 all dispatch-ready.*
