# HALT 3 brief — full-catalog sweep + step 1+ baseline

**Phase:** 8.8.6 step 0 → step 1+ transition
**Predecessor:** HALT 2 close at `9172b3b` (5-row dry-run, off 19.4% / on 4.0%)
**Successor:** 8.8.6 step 1+ (rich-row formatter fix; design informed by this baseline)
**Companion docs:** `docs/phase-8-8-6-step-0-eval-harness-spec.md`, `docs/confabulation-eval-runbook.md`, prior handoff doc (HALT 2 close)

---

## 1. Purpose

Produce the stable confabulation-rate baseline that 8.8.6 step 1+ improvement will be measured against. Surface novel confabulation patterns for Layer 2 wordlist governance. Confirm the gating signal differentiates clean vs confabulating rows at full-catalog scale. Capture catalog data-quality candidates as input to the step 1+ audit-vs-model-fix scoping decision.

This is the first run that produces a reference snapshot. Step 1+ work will mutate the catalog (audit pass is on the table); this snapshot will not be regenerable post-mutation. That informs the commit plan in §7.

---

## 2. HALT 3 / HALT 4 structure

The full-catalog sweep is ~10× the work of v5's dry-run iterations. Splitting at the natural data-generation/analysis seam scales better and surfaces tripwire failures or mid-run errors before committing to full review authoring.

| HALT | Owner | Scope | Output |
|---|---|---|---|
| HALT 3 | Cursor | Pre-state verification, run sweep, capture outputs, mechanical sanity checks, anchor diagnostic count | Halt artifact: tripwire band readings, run counts, Aqua Tier 3 inclusion count, file paths to outputs |
| HALT 4 | Claude + Casey | Review artifact authoring, qualitative judgment, close decision, baseline commit authorization | `relay/halt4-close.md` review artifact + commit of baseline files |

If HALT 3 sanity is clean, HALT 4 is largely artifact authoring against generated data. If HALT 3 trips a band or the Aqua re-run threshold fires, the response routes through chat before HALT 4 starts.

---

## 3. HALT 3 parameters

### Catalog scope

- All Provider rows in the curated catalog (~24)
- All Program rows in the curated catalog (~28)

If the actual row counts deviate materially from these estimates, Cursor reports the actuals in the HALT 3 sanity output and proceeds without adjustment.

### Probe generation

Per existing harness defaults (see `confabulation_query_gen.py`):
- 3 templates per Provider row (tell-me-about / what-offer / where-is)
- 3 templates per Program row (tell-me-about / when-meet / what-is)

Estimated probes: ~72 Provider + ~84 Program = ~156 probes per flag state.

### Run parameters

- Both flag states (`USE_LLM_ROUTER=false` and `USE_LLM_ROUTER=true`): ×2
- N=3 runs per (probe, flag-state): ×3

**Estimated total invocations: ~936**

### Runtime / cost

- Runtime: 60-90 minutes (handoff §7 estimate)
- API cost: <$10 (handoff §7 estimate)

---

## 4. HALT 3 mechanical sanity checks

Cursor performs these without judgment calls. Output goes in the HALT 3 halt artifact for Casey + Claude review.

### 4.1 Pre-state verification

- `git status` clean on `main`
- Eval harness files present at expected paths (`app/eval/`, `scripts/confabulation_eval.py`)
- Baseline directory does not yet exist (avoid clobbering): `scripts/confabulation_eval_results/baselines/8-8-6-step-0/` should be absent before run

### 4.2 Tripwire bands (off-flag gating rate)

Diagnostic-only. Do not gate close. Cursor reports which band the off-flag rate falls into:

| Band | Range | Meaning |
|---|---|---|
| A (sanity floor) | < 5% | Possible silent detector regression. Investigate before HALT 4. |
| B (sanity ceiling) | > 50% | Possible calibration regression or new lexicon noise. Investigate before HALT 4. |
| C (advisory window) | 10-30% | Expected band based on v5's 19.4%. Proceed to HALT 4. |
| (between bands) | 5-10% or 30-50% | No sanity flag, but worth Claude noting in HALT 4 review. |

### 4.3 Run count verification

Cursor reports:
- Total invocations (expected ~936)
- Tier 1 excluded count
- Tier 2 included count
- Tier 3 included count (Layer 2 hits) and Tier 3 excluded count (no Layer 2 hits)
- Aqua Beginnings flag-on Tier 3 included count (the anchor diagnostic count)

### 4.4 Aqua Tier 3 anchor re-run trigger

**Pre-committed threshold:** if Aqua Beginnings flag-on Tier 3 invocations land in the included set fewer than **3 times**, Cursor flags this in the HALT 3 halt output. Cursor does **not** auto-trigger a re-run. Casey + Claude decide the response in chat — either authorize a targeted Aqua-only re-run (3 templates × additional N) or proceed to HALT 4 with the gap noted.

This is the §1.1 anchor diagnostic from spec amendment 5: "when Aqua Beginnings flag-on Tier 3 invocations occur in the included set, they exhibit the §1.1 anchor pattern (Layer 2 hit on facility-claim or invented-domain tokens)." A sample size below 3 is too noisy to support that claim.

---

## 5. HALT 4 close criteria

Sharpened from handoff §7. Qualitative review with explicit owner+Claude judgment.

### 5.1 Anchor diagnostic (sharpened)

When Aqua Beginnings flag-on Tier 3 invocations occur in the included set, they exhibit the §1.1 anchor pattern (Layer 2 hit on facility-claim tokens or invented-domain tokens). Sample size ≥ 3 in the included set, or augmented by a targeted re-run if §4.4 fired.

Grace Arts Live is **not** a regression criterion in HALT 4. The synthetic-fixture detector test still asserts the regression behavior. Live model output is informational only — recorded as advisory note in the review artifact ("Grace Arts Live live output — model produced clean output across all probes" / or note if anchor returned).

### 5.2 Top gating tokens reflect real confabulation

Top-20 gating tokens (Layer 2 + Layer 3 combined) are dominated by real confabulation vocabulary plus invented numerical content. Detector noise / artifacts are absent or rare.

### 5.3 Per-row differentiation

Per-row gating-hit rate distribution shows meaningful differentiation. Clean rows near 0%. Confabulating rows substantially above. Distribution shape is interpretable, not flat.

### 5.4 Layer 1 advisory is reviewable

Top-50 global advisory tokens (post distinctness filter — see §6.3) plus per-row top-3 advisory views are scannable. Not so noisy that surfacing novel confabulation-class candidates is impractical.

### 5.5 Lexicon governance

Any new wordlist additions flagged by HALT 4 review go through HALT 1 lexicon governance. Not in scope for HALT 4 close — HALT 4 produces the candidate list; governance happens in step 1+ planning.

### 5.6 Tripwire bands

Bands A and B (§4.2) did not fire, **or** if they fired, the cause was diagnosed and is not a silent regression. Band C is informational; falling outside it (5-10% or 30-50%) is recorded as advisory note.

---

## 6. HALT 4 review artifact spec

The HALT 4 deliverable is `relay/halt4-close.md`, structured as below.

### 6.1 Headline

Per-flag rate (off / on), total included runs per flag, exclusion breakdowns. One paragraph of interpretation.

### 6.2 Per-row breakdown

Table: row_id, included_runs, gating_hits, gating_rate, top_3_gating_tokens. Sorted by gating_rate descending. The clean-row / confabulating-row distribution becomes legible from this view.

### 6.3 Advisory token review (filtered)

**Global view:** top-50 advisory tokens across full catalog, **filtered to tokens appearing across ≥3 distinct rows** (distinctness filter). Separates pattern from single-row artifact.

**Per-row view:** top-3 advisory tokens per row. Captures what's distinctive per row (washed out by the global view).

Reviewer (Claude + Casey) sorts global-view survivors into:
- Likely scaffolding → candidate for `safe_framing` list expansion
- Likely novel confabulation class → candidate for Layer 2 wordlist
- Ambiguous → leave; revisit at next baseline

Output: candidate lists, not committed lexicon changes. Lexicon changes go through HALT 1 governance in step 1+ planning.

### 6.4 Catalog data-quality candidates

Manual review pass during HALT 4. Pattern: rows whose advisory tokens substantially overlap with row content from non-description fields (address, phone, hours, schedule). Aqua Beginnings' address-field prose is the canonical case (handoff §6.1).

Each entry: row_id, suspect field, sample response excerpt, prose pattern echoed. Output is input to the step 1+ catalog audit scoping decision (open question §8.2 below). Not a defect of the harness or the model.

If this pattern turns out to be common (>5 rows), flag for v2 detector consideration — formalized address-field-echo detection. For HALT 3+4, manual flagging is sufficient.

### 6.5 Comparison to v5 dry-run subset

For the 5 rows that overlap with v5 (Aqua Beginnings, Grace Arts Live, Lake Havasu City Aquatic Center, Flips for Fun Gymnastics, Open Jump – 90 Minutes): per-row gating-rate comparison v5 → HALT 3. Sanity check that the v5 subset extrapolated reasonably and that no row dramatically diverged.

### 6.6 Tripwire band readings

Recorded for the snapshot. Diagnostic-only role (per §4.2). Future baselines compared against this reading.

### 6.7 Anchor diagnostic note

Aqua Beginnings flag-on Tier 3 inclusion count + summary of whether §1.1 pattern manifested. Grace Arts Live live-output note (§5.1).

---

## 7. Output / commit plan

### Output directory

`scripts/confabulation_eval_results/baselines/8-8-6-step-0/`

### Files generated by harness run (HALT 3)

- `runs.jsonl` — full per-invocation record
- `summary.md` — human-readable summary
- `per_row.csv` — per-row aggregation

### Files committed (HALT 4 close)

Force-added past `.gitignore`:
- `summary.md`
- `per_row.csv`
- `runs.jsonl.gz` (gzipped — estimated 300-500 KB compressed)

The uncompressed `runs.jsonl` is **not** committed; only the gzipped form.

**Why gzipped jsonl is committed (not just summary + csv):** step 1+ work will change the catalog (audit pass is one of the open questions). This jsonl snapshot is not regenerable once catalog state moves. Per-invocation diagnostic affordance against this baseline is needed for step 1+ comparison work — the v4→v5 canonicalizer fix was caught by per-invocation comparison, not summary-level.

### Repo size budget

If baseline storage grows beyond ~5 MB across multiple baseline snapshots over the life of step 0+1+, revisit the policy. Current single snapshot ~300-500 KB compressed is well under threshold.

### Companion artifact

`relay/halt4-close.md` — the HALT 4 review artifact (§6). Force-added past gitignore consistent with `relay/halt2-close.md` precedent.

---

## 8. Open questions deferred to step 1+

These are **not** HALT 3 or HALT 4 work. Listed for context — HALT 4 review may sharpen them, but resolution belongs to step 1+ planning.

### 8.1 What's the actual fix?

Prompt-level guardrails already failed (8.8.5). HALT 3 baseline informs which direction is most promising — formatter input restructuring, richness classifier with separate prompts, schema changes (separate amenity field from address field), or retrieval changes.

### 8.2 How much is catalog data quality vs model behavior?

The §6.4 catalog data-quality candidates output directly informs this. If the candidates list is substantial, a catalog audit pass is the cheapest first move before model-side work.

### 8.3 What threshold defines "good enough" for step 1+?

Spec §5.4 explicitly defers this. HALT 3 baseline rate sets the reference. Probably "gating rate < X% per flag state, where X is some meaningful fraction of the baseline."

### 8.4 Tier 3 anchor pattern scope

HALT 3 will surface whether Aqua's flag-on Tier 3 facility-claim confabulation is row-specific or a general Tier 3 phenomenon. Drives whether Tier 3 work needs separate scoping.

### 8.5 Layer 5 LLM judge as v2

Whether Layer 1 advisory needs to become gating signal via an LLM judge. Depends on what step 1+ uncovers about whether prompt/schema fixes are sufficient or whether the residual confabulation requires sharper detection.

---

## 9. Process notes

- HALT discipline holds: no chaining HALTs without explicit "proceed to HALT N" approval per handoff §1.
- No production file modifications during HALT 3 or HALT 4. All harness work stays within `app/eval/`, `scripts/`, `tests/`, `docs/`, `relay/`, `scripts/confabulation_eval_results/`.
- Bounded iteration: if HALT 3 sanity trips and the response requires a fix-and-rerun cycle, this becomes a HALT 3a / 3b sequence with explicit close-or-escalate at each step. Pattern follows G/G1/G2/G3 from HALT 2 if needed.

---

**End of HALT 3 brief.**
