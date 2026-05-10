# HALT 3 close-out

**Status at template draft (2026-05-10):** TEMPLATE ONLY — to be filled in when steps 1-7 of `halt3_definition.md` §6 complete. Production HEAD at template draft: `21c2e08`. Pytest baseline at draft: 1385.

**Status at close-out:** [FILL: pending | in-progress | RESOLVED] [FILL: completion date]

HALT 3 is the closure milestone for the confabulation harness at `app/eval/confabulation_*.py` and the gating artifact for Phase 2.5 / P2.PREM.1 (Premier inventory open). This close-out exists because the strategy doc explicitly defers the three acceptance bands (gating-rate, anchor-regression, catalog-flagging) to the close itself — they are calibrated from baseline measurements rather than pre-stated. The framework, sequencing constraints, and rationale live in `docs/maintainability/halt3_definition.md`; harness invocation and output schema live in `docs/confabulation-eval-runbook.md`. This artifact records the actual measurements and the bands set against them.

---

## §1 — Preconditions verified

Confirms steps 1-3 of `halt3_definition.md` §6 completed before harness baseline.

- **Operator enrichment sprint:** [FILL: status — sprint commit SHA reference, verified business count (target: ≥50 across restaurants/plumbers/HVAC/pool service/boat repair/urgent care/auto repair), Sponsor row count (target: ≥1), matching Provider row count]
- **`FEATURE_FLAG_DISCLOSURE_RENDERER` flag flip:** [FILL: date flipped from `false` → `true`, deployer, Railway env-var change reference, post-flip smoke result reference per `phase1_deploy_runbook.md`]
- **CT flag status:** confirmed ON since 2026-05-09 evening per BACKLOG #47/#48/#49 close — [FILL: re-confirm still ON at close-out date]
- **Production traffic dwell:** [FILL: dwell start date (= flag-flip date), dwell end date (≥7 days later), `chat_logs` row count over window, distinct session count, % rows with non-null `disclosure_regime`]
- **Earliest meaningful baseline run gate:** per `halt3_definition.md` §3, no earlier than 2026-05-16 — [FILL: confirm baseline run date ≥ this floor]

---

## §2 — Harness baseline run

Records what running the confabulation harness produced under the post-flip post-dwell conditions.

- **Command run:** `python scripts/confabulation_eval.py --mode=inprocess --runs=3 --flags=both --rows=both --output-dir=scripts/confabulation_eval_results/halt3-baseline`
- **Run timestamp:** [FILL: ISO-8601 start; harness took ~[FILL] minutes]
- **Run duration:** [FILL: total wall-clock seconds]
- **Output artifacts** (paths per `confabulation-eval-runbook.md` §Artifacts):
  - `scripts/confabulation_eval_results/halt3-baseline/summary.md` — gating rate by flag, top offenders, top gating tokens (L2+L3), Layer 1 advisory section, tier split, regression anchors (gating only)
  - `scripts/confabulation_eval_results/halt3-baseline/per_row.csv` — `row_id`, `row_name`, `total_runs`, `included_runs`, `gating_runs_with_hit`, `advisory_token_count`, `top_3_gating_tokens`
  - `scripts/confabulation_eval_results/halt3-baseline/runs.jsonl` — per-run probe / response / evidence / split hits / latency / tier / exclusion flags
- **Mirrored to relay** (for cross-reference from this artifact): [FILL: confirm whether copies were also placed at `relay/halt3-baseline-summary.md` etc., or whether the canonical paths above are the only copy]
- **Run-environment notes:** [FILL: alembic head SHA at run time, Python version, harness git SHA, any `--include`/`--exclude`/`--limit` overrides (none expected for baseline), env-var overrides]
- **Inclusion-policy reminder** (per runbook §v1 summary inclusion policy): denominator is **Tier 2 always + Tier 3 only when at least one Layer 2 hit fires**. Tier 1 runs are excluded (`tier_1_no_formatter`). Tier 3 runs with no Layer 2 hits are excluded (`tier_3_no_layer2_hits`). Layer 1 is advisory and does not feed the headline. — [FILL: confirm `excluded_reason` distribution from `runs.jsonl` matches expectations]

---

## §3 — The three bands

Each band: definition, baseline measurement, threshold set during this close, pass/fail logic. Thresholds are NOT pre-stated; they are derived here from the baseline distribution per `halt3_definition.md` §2.

### §3.1 — Gating rate (Tier 2 + Tier 3-with-L2)

- **Definition:** percentage of harness probes (within the inclusion denominator above) that hit the safety-net gate — Layer 2 wordlist hit on Tier 2, Layer 2 + Layer 3 canonicalizer hits on Tier 2, or Layer 2 hit on Tier 3 — rather than producing a clean response. Source: `summary.md` "gating rate by flag" section.
- **Baseline measurement:** [FILL: <gating count> / <included probes> = <percentage>; break out by `--flags` arm if relevant]
- **Per-category breakdown** (per strategy doc — emergency / high-stakes warrants tighter band): [FILL: gating rate per category — emergency, plumbers, HVAC, urgent care, auto repair, restaurants, etc.]
- **Threshold set:** global ≤ [FILL: percentage]; emergency / high-stakes categories ≤ [FILL: tighter percentage]. Above these, FAIL.
- **Threshold rationale:** [FILL: 1-2 sentences on why this band, derived from baseline distribution shape — e.g., "baseline gating rate was X% on a probe set designed to surface confabulation risk; threshold set at Y% to allow Z% headroom for normal drift, with emergency categories held tighter at W% per strategy doc §1.1."]
- **Result:** [FILL: PASS | FAIL]

### §3.2 — Anchor regression

- **Definition:** percentage of curated anchor probes (queries with known correct answers in the post-enrichment catalog) that produce wrong-entity, null-where-correct, or gating-where-correct responses. Source: `summary.md` "regression anchors (gating only)" section. Per strategy doc §1.1, this is **per-category** with tighter thresholds for emergency / high-stakes categories.
- **Anchor set composition:** [FILL: count of anchor probes; source file — likely `app/eval/confabulation_query_gen.py::_PROBES_PROVIDER` (and program/event variants) or a curated `relay/halt3-anchor-set.txt` if separately maintained — verify which is canonical at close time]
- **Anchor set governance note:** anchor set is governed by HALT 1 (owner-reviewed, append-only, no silent drift) per `confabulation-eval-runbook.md` §Lexicon Governance. — [FILL: confirm no anchor-set churn between baseline and close]
- **Sequencing precondition** (per `halt3_definition.md` §3): anchor regression cannot be calibrated against an empty `Provider` table; enrichment sprint must have populated rows. — [FILL: confirm enrichment §1 above passed]
- **Baseline measurement:** [FILL: <regressions> / <anchors> = <percentage> overall; per-category table below]

| Category | Anchors | Regressions | Rate | Threshold set | Result |
|---|---|---|---|---|---|
| Restaurants | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| Plumbers (emergency) | [FILL] | [FILL] | [FILL] | [FILL: tighter] | [FILL] |
| HVAC | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| Pool service | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| Boat repair | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |
| Urgent care (emergency) | [FILL] | [FILL] | [FILL] | [FILL: tighter] | [FILL] |
| Auto repair | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |

- **Threshold rationale:** [FILL: per-category derivation; emergency categories rationale per strategy doc "wrong emergency plumber recommendation at 11pm is not [recoverable]"]
- **Result:** [FILL: PASS | FAIL]

### §3.3 — Catalog flagging

- **Definition:** percentage of catalog rows (from the top-50 enriched businesses set per Phase 1 close criteria) that the harness flagged as confabulation-prone via repeated gating hits. Source: `per_row.csv`.
- **Per-row offender ranking source:** column `gating_runs_with_hit` in `per_row.csv` (per `confabulation-eval-runbook.md` §Artifacts); `top_3_gating_tokens` provides the qualitative signal per row. — [FILL: confirm column name still matches at close time, in case runbook updated]
- **Flagging cutoff used:** [FILL: e.g., "any row with `gating_runs_with_hit` ≥ 2 of 3 runs is flagged" — verify with runbook or set at close]
- **Baseline measurement:** [FILL: <flagged rows> / <top-50 enriched rows> = <percentage>]
- **Top 5 flagged rows:** [FILL: row_name + gating_runs_with_hit + top_3_gating_tokens for each]
- **Threshold set:** ≤ [FILL: percentage cap on top-50 enriched]. Above this, FAIL.
- **Threshold rationale:** [FILL: derived from baseline distribution; strategy doc calls for "below acceptable band" without a specific number]
- **Result:** [FILL: PASS | FAIL]

---

## §4 — Negative-set extension

Per `halt3_definition.md` §6 step 6 + strategy doc §1.1: a curated set of queries whose correct answer is "I don't know" or "no current match" — closed businesses, cancelled events, services Havasu does not have. Confabulation rate on the negative set is a sharper signal than gating rate alone.

- **Negative-set source:** [FILL: file path or generation mechanism — e.g., `relay/halt3-negative-set.txt` or a `--include` invocation against a curated probe list; if newly authored, record commit SHA]
- **Negative-set composition:** [FILL: ~30-50 queries per strategy doc; breakdown by closed-business / cancelled-event / nonexistent-service]
- **Probe count:** [FILL]
- **Pass/fail criterion:** [FILL: e.g., "100% of negative-set probes return null, 'don't have' framing, or fall to safety-net gate; any false-positive entity match (Tier 1 hit on a closed business, Tier 2/3 fabricated entity) triggers FAIL"]
- **Result:** [FILL: PASS | FAIL with details — per-probe failures listed if any]

---

## §5 — Pass/fail summary

| Band | Baseline | Threshold | Result | Notes |
|---|---|---|---|---|
| §3.1 Gating rate (global) | [FILL] | [FILL] | [FILL: PASS \| FAIL] | [FILL] |
| §3.1 Gating rate (emergency) | [FILL] | [FILL] | [FILL: PASS \| FAIL] | [FILL] |
| §3.2 Anchor regression (worst category) | [FILL] | [FILL] | [FILL: PASS \| FAIL] | [FILL: name worst category] |
| §3.3 Catalog flagging (top-50) | [FILL] | [FILL] | [FILL: PASS \| FAIL] | [FILL] |
| §4 Negative-set | n/a | 100% null/gate | [FILL: PASS \| FAIL] | [FILL] |

**Overall HALT 3 verdict:** [FILL: RESOLVED — all bands passed | OPEN — band X failed, see §6 remediation]

**Cross-reference Phase 1 close criteria** (per `halt3_definition.md` §4): this close-out satisfies the rows "Confabulation rate on negative-set evals" and "Catalog data-quality flag rate on top-50 enriched businesses." Other Phase 1 close-criteria rows (disclosure compliance 100%, tone-rule violations zero, event sources ≥5 weekly, Tier 1 hit rate >25%, UI-data-correctness audit) are tracked separately and not re-litigated here. — [FILL: confirm no overlap with parallel close-criteria work or note where each is owned]

---

## §6 — Remediation (only if any band failed)

If all bands passed, this section reads: "All bands passed; no remediation required. P2.PREM.1 unblocked."

If any band failed:

- **Failing band:** [FILL]
- **Root-cause hypothesis:** [FILL]
- **Remediation tickets filed:** [FILL: BACKLOG numbers, owners, expected re-run date]
- **Re-run gating:** P2.PREM.1 dispatch is blocked until re-run shows PASS on the failing band (and no regression on others). — [FILL: re-run date]

---

## §7 — Phase 2.5 / P2.PREM.1 dispatch readiness

Final checklist before dispatching Premier inventory open. Each item must be checked before P2.PREM.1 starts.

- [ ] All bands PASS per §5
- [ ] No remediation outstanding per §6
- [ ] BACKLOG #53 marked RESOLVED with reference to this artifact
- [ ] STATE.md "Recently shipped" entry added (HALT 3 close + bands recorded)
- [ ] `halt3_definition.md` cross-link added pointing to this close-out
- [ ] Decision #37 condition met: disclosure renderer in production AND §4 harness green
- [ ] P2.PREM.1 dispatch prompt drafted (see `phase2_lane_decomposition.md` row P2.PREM.1)

---

## §8 — Filed by

[FILL: operator name + agent attribution if any agents contributed to the close-out — e.g., "Casey Solomon; close-out drafted with Cowork agent on <date>"]

---

## §9 — Related artifacts

- `docs/maintainability/halt3_definition.md` — recovered framework (§1 what HALT 3 is, §2 three bands, §3 sequencing, §4 Phase 1 close criteria, §6 work-to-close) this close-out validates against.
- `docs/confabulation-eval-runbook.md` — harness invocation, artifact schema, inclusion-policy semantics, lexicon governance.
- `docs/maintainability/disclosure_renderer_spec.md` — what the deterministic renderer does that HALT 3 measures (regime gating, tone allowlist, observability columns on `chat_logs`).
- `docs/BACKLOG.md` #53 — original "HALT undefined" audit ticket; gets marked RESOLVED on close-out.
- `docs/STATE.md` — gets a new top "Recently shipped" entry on close-out.
- `scripts/confabulation_eval_results/halt3-baseline/{summary.md,per_row.csv,runs.jsonl}` — harness outputs (canonical location per runbook).
- `relay/halt3-step1-runs-excerpts.txt` — earlier raw-probe captures (predecessor artifact, no §Outcome).
- [FILL: `relay/halt3-anchor-set.txt` or `relay/halt3-negative-set.txt` if curated outside the harness `_PROBES_*` constants]
- `app/eval/confabulation_query_gen.py`, `app/eval/confabulation_detector.py` — harness components (probes, Layer 2 wordlist, Layer 3 canonicalizer).
- `phase1_deploy_runbook.md` — `FEATURE_FLAG_DISCLOSURE_RENDERER` flip procedure referenced in §1.
- `phase2_lane_decomposition.md` — P2.PREM.1 row dispatched after this close.
