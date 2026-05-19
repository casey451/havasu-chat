# Phase 7 HALT 3 Validator Initial Run Report — 2026-05-20

> **What this is:** the raw output and per-query interpretation of the HALT 3 validator's initial run against the 22-query eval set immediately post-Phase-7-ship (commit `0a305e0`). Captured because the operator pasted the validator output into the terminal but it wasn't persisted to any file — this artifact preserves it as durable input for the Phase 7.5 polish-lane dispatch (`outputs/phase_7_5_halt3_polish_lane_dispatch_note.md`).
>
> **Author:** Cowork primary, 2026-05-20 post-`0a305e0`.
>
> **Run context:** operator ran `python -m app.chat.halt3_validator app/chat/halt3_eval_set.yaml` from the post-`0a305e0` working tree against the local dev SQLite database (alembic head `c9d0e1f2a3b4` post-stamp).

---

## §1 Raw validator output (preserved verbatim)

```
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=380 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=381 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=377 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=373 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=385 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=381 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=381 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=382 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=376 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=381 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=378 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=378 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=373 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=377 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=380 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=375 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=377 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=379 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=377 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=374 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=376 out=8)
WARNING:root:hint_extractor: token usage exceeds soft budget (inp=380 out=8)
PASS q01 tier=2 disc=cited
FAIL q02 tier=3 disc=i_dont_know
  - tier expected tier2, got 3
  - disclosure expected cited, got i_dont_know
FAIL q03 tier=1 disc=i_dont_know
  - disclosure expected cited, got i_dont_know
PASS q04 tier=chat disc=uncited
PASS q05 tier=gap_template disc=i_dont_know
FAIL q06 tier=chat disc=uncited
  - disclosure expected i_dont_know, got uncited
FAIL q07 tier=3 disc=cited
  - disclosure expected i_dont_know, got cited
  - confabulation 0.50 > 0.0
PASS q08 tier=1 disc=i_dont_know
PASS q09 tier=2 disc=cited
FAIL q10 tier=gap_template disc=i_dont_know
  - disclosure expected cited, got i_dont_know
PASS q11 tier=2 disc=cited
PASS q12 tier=2 disc=cited
PASS q13 tier=chat disc=uncited
FAIL q14 tier=3 disc=i_dont_know
  - disclosure expected cited, got i_dont_know
PASS q15 tier=gap_template disc=i_dont_know
FAIL q16 tier=1 disc=i_dont_know
  - disclosure expected cited, got i_dont_know
FAIL q17 tier=3 disc=i_dont_know
  - disclosure expected cited, got i_dont_know
PASS q18 tier=gap_template disc=i_dont_know
PASS q19 tier=3 disc=cited
PASS q20 tier=chat disc=uncited
FAIL q21 tier=gap_template disc=i_dont_know
  - disclosure expected cited, got i_dont_know
FAIL q22 tier=chat disc=uncited
  - disclosure expected i_dont_know, got uncited
cited_coverage=42% missing_confab_max=0.50 all_passed=False
```

---

## §2 Aggregate metrics

| Metric | Observed | Target | Gap |
|---|---|---|---|
| `cited_coverage` (100% disclosure-pipeline coverage on cited responses) | **42%** | 100% | -58 pp |
| `missing_confab_max` (0 confabulation on missing-data cases) | **0.50** | 0.0 | +0.50 |
| `all_passed` | **False** | True | (gates) |
| PASS count | 12 / 22 | 22 / 22 | -10 |
| FAIL count | 10 / 22 | 0 / 22 | +10 |

**Aggregate hint_extractor token-budget warnings:** 22 instances (one per query) at `inp=~378 out=8`. Not a HALT 3 pass/fail signal but a perf carry — hint extractor is being invoked with longer-than-expected input. V1.5 polish candidate.

---

## §3 Per-FAIL categorization

| Query | Observed | Expected | Failure mode | Likely cause |
|---|---|---|---|---|
| q02 | tier=3 / i_dont_know | tier=2 / cited | tier mismatch + disclosure mismatch | Tier classifier may be routing to tier 3 when tier 2 would suffice; OR eval set assumed tier 2 reachability that isn't there. |
| q03 | tier=1 / i_dont_know | (any) / cited | expected cited, got i_dont_know | Entity not surfaced via tier 1 or tier 2; could be ENTITY catalog query miss, OR eval set expected an entity that's been DRAFT'd / removed, OR entity exists but matching failed. |
| q06 | tier=chat / uncited | (any) / i_dont_know | expected i_dont_know, got uncited | Disclosure renderer not catching missing-data; chat producing uncited response on a query that should have been a clean "I don't know". Slightly concerning — uncited responses can drift into confabulation. |
| **q07** | **tier=3 / cited** + **0.50 confab** | (any) / i_dont_know + 0.0 confab | **CONFABULATION** | **The smoking gun.** Chat fabricated citations on a query about an entity NOT in catalog. 50% confabulation rate means half the cited entities don't match the query meaningfully OR don't exist. This is the exact failure mode HALT 3 was built to prevent. P0 priority for Phase 7.5. |
| q10 | tier=gap_template / i_dont_know | (any) / cited | expected cited, got i_dont_know | Same as q03 — tier=gap_template suggests the renderer fell into a missing-data path when it should have found + cited an entity. |
| q14 | tier=3 / i_dont_know | (any) / cited | expected cited, got i_dont_know | Same as q03 — but tier=3 route engaged (LLM-driven path), so chat is acknowledging the LLM-fallback but landing on i_dont_know instead of citing. |
| q16 | tier=1 / i_dont_know | (any) / cited | expected cited, got i_dont_know | Same pattern as q03; tier 1 route engaged but landed on i_dont_know. |
| q17 | tier=3 / i_dont_know | (any) / cited | expected cited, got i_dont_know | Same as q14. |
| q21 | tier=gap_template / i_dont_know | (any) / cited | expected cited, got i_dont_know | Same as q10. |
| q22 | tier=chat / uncited | (any) / i_dont_know | expected i_dont_know, got uncited | Same as q06 — uncited on missing-data, should be i_dont_know. |

### Failure pattern groupings

| Pattern | Count | Queries | Priority |
|---|---|---|---|
| **Confabulation (cited when should be i_dont_know with >0 confab)** | 1 | q07 | **P0 — fix first** |
| **i_dont_know expected, got uncited (missing-data leakage)** | 2 | q06, q22 | **P0 — disclosure renderer regression risk** |
| **Cited expected, got i_dont_know (chat being conservative OR missing matches)** | 6 | q03, q10, q14, q16, q17, q21 | P1 — likely fixable via better entity matching OR eval set adjustment |
| **Tier + disclosure mismatch** | 1 | q02 | P2 — could be eval set too strict |

---

## §4 Possible root causes (Phase 7.5 hypotheses to test)

### Hypothesis A: ENTITY catalog matching gap

For the 6 "expected cited, got i_dont_know" cases, the ENTITY catalog query may not be finding entities that the eval set expects to be present. Possible causes:
- Entity exists in catalog but `prefers_entity_catalog()` gate routes the query to the legacy events/programs path which doesn't find it
- Entity exists but `query_entities()` filters it out (e.g., `is_active=False`, `draft=True`, EntityCategory join misses)
- Entity exists but the LLM prompt construction doesn't surface it to the user-facing renderer
- Eval set expects an entity that's been DRAFT'd or soft-deleted

### Hypothesis B: Disclosure renderer over-conservatism

The disclosure renderer may be returning `i_dont_know` more aggressively than designed. Spec at `docs/maintainability/disclosure_renderer_spec.md` is the source of truth — Phase 7.5 should re-read and verify behavior matches.

### Hypothesis C: Confabulation in q07 — bug in entity_intent OR cross-entity query

q07's 0.50 confabulation rate suggests the chat is fabricating citations. Possible sources:
- `entity_intent.detect_multi_domain_category_slugs()` returning categories that the query didn't actually intend
- Cross-entity interleaving surfacing entities loosely related to query keywords without checking semantic fit
- Tier 3 LLM hallucinating entity names (this would be the worst — and the original sin HALT 3 was built to prevent)

q07's "tier=3" routing suggests the LLM-driven path is engaged. If the chat reaches tier 3 and the LLM hallucinates entities, that's a P0 bug; HALT 3's whole point is to catch + prevent this.

### Hypothesis D: Eval set too strict (some FAILs are eval-set-wrong)

Phase 7.5 should examine each query in `app/chat/halt3_eval_set.yaml` and verify:
- The entity the eval expects to be cited is actually IN the catalog (with `is_active=True` + `draft=False`)
- The query phrasing is unambiguous about what entity it's asking for
- The expected tier matches actual tier classification

If 3 of the 6 "expected cited, got i_dont_know" cases turn out to be eval-set-wrong (operator-DRAFT'd entities the eval expected to find, or ambiguous queries), the real bug count drops from 10 to 7.

### Hypothesis E: Race with ENTITY catalog state at validator-run time

The validator ran against the operator's local dev SQLite DB. If that DB's catalog state differs from production (e.g., DRAFT entities, missing seasonal hours, missing categories), some FAILs are environment-specific, not code-bugs. Phase 7.5 should validate against a known-good catalog state OR seed the validator with fixtures.

---

## §5 Phase 7.5 input — what this report enables

Phase 7.5 polish-lane dispatch (`outputs/phase_7_5_halt3_polish_lane_dispatch_note.md`) uses this report as its primary input. Specifically:
- The per-query categorization (§3) tells Cursor 7.5 which queries to investigate in which order
- The hypothesis list (§4) gives Cursor 7.5 a structured investigation framework
- The aggregate metrics (§2) define the pass-criteria Cursor 7.5 is iterating against (`cited_coverage` 42% → 100%; `missing_confab_max` 0.50 → 0.0)
- The raw output (§1) is preserved as a baseline diff target — if Phase 7.5's re-run shows different FAILs, that's progress

---

## §6 Operator path forward

1. **Don't flip `FEATURE_FLAG_DISCLOSURE_RENDERER`.** Stay `false` until Phase 7.5 closes the failures.
2. **Dispatch Phase 7.5** when convenient — can be parallel with Phase 6.5 + Phase 8a per gotcha #18 (Phase 7.5 = `app/chat/halt3_*` + `app/chat/disclosure_render.py` + possibly `app/chat/entity_catalog_query.py` for matching fixes; disjoint from Phase 6.5 templates / Phase 8 conditions module). Use `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md` as the Cursor brief.
3. **Track the hint_extractor token-budget perf carry** in `outputs/v1_5_carry_inventory_triage.md` as a new V1.5 entry (22 warnings per validator run; hint extractor invoked with longer-than-expected input; tighten the prompt OR raise the budget — both V1.5 polish).
4. **After Phase 7.5 ships with validator going 22/22 PASS**, flip `FEATURE_FLAG_DISCLOSURE_RENDERER=true` out-of-band on Railway production. STATE.md "Recently shipped" entry should note both Phase 7.5 ship AND the flag flip date.

---

*Authored by Cowork primary at the post-`0a305e0` Phase 7 close-out session (2026-05-20). Lives at `outputs/phase_7_halt3_initial_run_report.md`. Companion artifacts: `outputs/phase_7_close_out.md`, `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md`. Preserves the raw HALT 3 validator output for Phase 7.5 reference.*
