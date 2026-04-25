# Phase 8.8.6 step 0 — Confabulation Eval Harness Spec

Status: Draft for owner review (HALT 0 closed)
Date: 2026-04-25
Scope: Spec only (no implementation changes in this phase)
Predecessor: 8.8.5 reverted (`d1fef0f`, `c3562c9` revert `f8afb81`, `297086d`)
Successor: 8.8.6 step 1+ (rich-row formatter fix, drafted after this harness produces a baseline measurement)

---

## 1) Problem statement

8.8.5 attempted to suppress Tier 2 formatter confabulation via a richness classifier plus a tightened prompt. The 12-query validation set passed sparse-row probes but the rich-row failure mode (Aqua Beginnings: `"private heated outdoors"` extrapolation; Grace Arts Live: `"indoor air-conditioned family-friendly"` extrapolation) persisted deterministically across 6/6 runs (3 flag-on, 3 flag-off). The approach was rolled back per 8.8.5 spec §5.3.

Two diagnoses follow from that outcome:

1. **The fix was wrong.** Prompt-level guardrails on rich rows do not suppress extrapolation reliably. A deeper formatter or grounding change is needed (8.8.6 step 1+).

2. **Our measurement was wrong.** A 12-query sample missed the rich-row mode. Catching it required deploying to staging and reading transcripts. Every future formatter / prompt change has the same exposure: confabulation that doesn't appear in the canonical battery ships unnoticed.

This phase addresses (2) before attempting (1) again. We build a systematic confabulation eval harness that sweeps the full catalog, runs each query in both router-flag states with N repetitions, and emits per-row + per-extrapolation-word reports against a deterministic detector. The harness is the measurement instrument for 8.8.6 step 1+ and every subsequent formatter / prompt phase.

### 1.1 Verbatim failure cases the harness must catch (regression anchors)

These are the canonical fixtures the v1 detector must flag at high confidence in unit tests and in full-sweep output:

1) **Aqua Beginnings** — Provider row.
   - Row description: `"Max 3 swimmers per group. Free initial assessment. Coach Rick (Swim America® certified)."`
   - Confabulated response excerpt: `"private heated outdoor pool sessions, though you'd need to book directly through their site."`
   - Invented content: `private`, `heated`, `outdoor`, `book directly through their site`.

2) **Grace Arts Live** — Provider row.
   - Row description: `"Nonprofit. Affiliated with ACPA. established: 2006."`
   - Confabulated response excerpt: `"indoor option, air-conditioned, family-friendly, youth theatre production."`
   - Invented content: `indoor`, `air-conditioned`, `family-friendly`. Note: `youth theatre` may be derivable from related Event rows — detector must scope evidence to all rows the formatter saw on that turn, not just the primary Provider row (see §3.5.1).

3) **London Bridge Beach** — not in catalog as Provider during 8.8.5 validation.
   - Confabulated response excerpt: `"shade from the bridge structure."`
   - Invented content: an entire entity surface. Out of v1 detector scope (entity-invention is v2); included here so it isn't forgotten.

---

## 2) Goals and non-goals

### 2.1 Goals

1. Measure per-row confabulation rate across the full curated catalog of Provider and Program rows.
2. Run each probe under both `USE_LLM_ROUTER=false` and `USE_LLM_ROUTER=true`.
3. Aggregate over N runs per (query, flag-state) to absorb Tier 3 stochasticity.
4. Emit human-readable per-row, per-extrapolation-word, and per-run reports.
5. Be the validation instrument for 8.8.6 step 1+ and every later formatter / prompt phase. Reusable, repeatable, version-controlled.
6. Detect the regression-anchor cases in §1.1 deterministically.

### 2.2 Non-goals (locked)

- **Not a fix for confabulation.** That is 8.8.6 step 1+.
- No formatter prompt changes, router changes, schema changes, or model changes.
- No retrieval / selection correctness measurement. Wrong-row-picked is a separate problem (see Aquatic Center known issue).
- No Tier 3 LLM-judge harness in v1. Documented as a v2 extension.
- No entity-invention detection in v1. London Bridge Beach class of failure is logged but not gated.
- No pass/fail threshold defined in this phase. Threshold lives in 8.8.6 step 1+ once we have a baseline.
- No bulk-catalog (Phase 8.11 / 4,574 row) sampling strategy in v1. Scoped to curated catalog. Sampling deferred to a later phase once bulk ingest is closer.
- No intent-style probes (`"kids on a hot day"`, `"a quiet weekend morning"`) in v1. Per-row probes only. Intent queries deferred to v2 because they couple confabulation detection with retrieval correctness.

---

## 3) Approach

### 3.1 Architecture

Three modules plus a CLI runner. Detection logic lives behind importable APIs so it is unit-testable and reusable from anywhere (CI, ad-hoc, future phases).

```
scripts/confabulation_eval.py            # CLI runner
app/eval/__init__.py
app/eval/confabulation_query_gen.py      # catalog -> probe queries
app/eval/confabulation_invoker.py        # in-process or HTTP invocation, returns response + evidence set
app/eval/confabulation_detector.py       # detection layers, returns hits per response
app/eval/confabulation_report.py         # JSONL/MD/CSV emission
tests/test_confabulation_query_gen.py
tests/test_confabulation_detector.py
tests/test_confabulation_invoker.py
docs/confabulation-eval-runbook.md       # operator guide
```

Reports written to `scripts/confabulation_eval_results/<utc-timestamp>/` (gitignored except for committed baselines).

### 3.2 Query generation

For every live Provider row in the catalog, emit three probe queries:

1. `tell me about <n>`
2. `what does <n> offer`
3. `where is <n>`

For every live Program row, emit three probe queries:

1. `tell me about <n>`
2. `when does <n> meet`
3. `what is <n>`

Templates are locked at HALT 1 (§3.7). `<n>` substitution uses the row's display name verbatim. No fuzzing in v1.

### 3.3 Run mode

**Default: in-process.** The runner imports the unified router and calls it directly with each probe. It captures both the assistant response *and* the full set of rows the formatter received for that turn (`evidence_set`). In-process is the default because (a) row-level introspection is required for the primary detection layer (§3.5.1), and (b) it removes network and deploy latency from the loop.

**Opt-in: HTTP mode** (`--mode=http --base-url=<url>`). For staging validation. Skips evidence-set introspection and falls back to wordlist + number-invention layers only (degraded detection). Documented; not the default path.

### 3.4 Determinism strategy

- N runs per (query, flag-state). Default N=3. Configurable via `--runs`.
- Tier 3 calls are stochastic; per-run confabulation is binary, but per-(query,flag-state) confabulation rate is meaningful at N=3 and tightens at larger N.
- Each run is logged with a stable `(query_id, flag_state, run_index)` tuple for reproducibility.
- Seed is logged but not enforced — Tier 3 doesn't accept a seed today and we don't want to fork the prod path.

### 3.5 Detection layers (v1)

Three layers. Each emits hits with row context, layer label, and matched span. The detector is content-only — it does not score voice, length, formality, or any other axis.

#### 3.5.1 Layer 1 — Per-row scoped extrapolation diff (PRIMARY)

The point of this layer: catch confabulation in vocabulary we have not seen before. This is what the wordlist alone cannot do.

For each turn:

1. Capture the `evidence_set` = union of all content tokens from every row the formatter received on that turn (Provider rows: name + description + featured_description + category + address + phone + hours + website. Program rows: name + activity_category + schedule + cost + description.). Tokens normalized: lowercased, lemmatized, stripped of punctuation.
2. Tokenize the response. Filter to content words via a stoplist + POS tag (NOUN / ADJ / VERB excluding generic verbs). Numbers handled by Layer 3.
3. Subtract: `response_content_tokens − evidence_set_tokens − safe_framing_vocabulary`.
4. Any remainder is a candidate hit. Each hit records the token, its sentence-of-occurrence in the response, and the row IDs in scope.

`safe_framing_vocabulary` is a curated list of generic concierge-voice tokens that appear in responses but aren't confabulation: `nice, decent, good, worth, check, head, go, stop, place, spot, place-name aliases (the bridge, the channel, McCulloch, Sara Park), pronouns, articles, prepositions, modal verbs, common time/quantity hedges (usually, sometimes, often)`. Owner-reviewed at HALT 1.

This layer is the workhorse. It catches `private`, `heated`, `outdoor`, `air-conditioned`, `family-friendly` against Aqua Beginnings / Grace Arts Live evidence sets — and equally catches future confabulation in vocabulary we haven't yet seen.

#### 3.5.2 Layer 2 — Curated extrapolation wordlist (SECONDARY)

Cheap regression check. A literal wordlist of known confabulation vocabulary, scoped to category-extrapolation patterns:

- Facility / amenity invention: `heated, indoor, outdoor, private, air-conditioned, climate-controlled, shaded, covered`
- Audience-fit invention: `family-friendly, kid-friendly, kid-appropriate, romantic, upscale, casual, cozy, intimate, quiet, lively`
- Procedural invention: `book directly, reservation required, walk-ins welcome, no reservations`

For each hit, we flag any wordlist member appearing in the response but not in the evidence set. Owner-reviewed and locked at HALT 1; allowed to grow during operation as new patterns surface, similar to the implementation-lexicon governance from 8.8.5 §3.1.3.

This layer is partially redundant with Layer 1 by design — it gives us a clean per-pattern frequency report (which extrapolation words confabulate most often) that Layer 1's diff doesn't produce as cleanly.

#### 3.5.3 Layer 3 — Number / quantity invention (SECONDARY)

For each turn:

1. Extract digit sequences and quantity nouns (`several, multiple, dozen, dozens, handful, few, many, most`) from both the response and the evidence set.
2. **Normalize before diff.** Both sides are passed through a canonicalizer that:
   - strips currency symbols (`$19` → `19`),
   - normalizes time formats (`8am`, `8:00 AM`, `08:00`, `8 a.m.` → `08:00`),
   - normalizes duration variants (`90 min`, `90 minute`, `90-minute`, `90 minutes` → `90min`),
   - normalizes day-of-week abbreviations (`Mon`, `Monday`, `mon` → `monday`),
   - normalizes price-range variants (`$10-15`, `$10 to $15`, `10-15 dollars` → `10-15`).
3. Diff response canonical-numbers against evidence-set canonical-numbers. Any remainder is a candidate hit.

The normalization step is required, not optional. Without it, the layer produces high false-positive rates on every catalog row that lists hours, prices, or schedule durations in formats the response then re-renders (e.g. row says `"8:00 AM"`, response says `"8am"` — same fact, different surface form). Canonicalizer rules are owner-reviewed at HALT 1 alongside the lexicons.

Catches invented hours, capacities, prices, recurrence counts. Cheap; high precision once normalized; covers a failure class wordlists miss.

#### 3.5.4 Out of v1 — documented as v2 extensions

- **Layer 4 — entity invention.** Flag mentions of provider / place / program names not in the evidence set or the catalog. Catches London Bridge Beach class of failure.
- **Layer 5 — LLM judge.** A separate Haiku call: *"Given these rows and this response, list any factual claims in the response that are not supported by the rows."* Useful for catching what cheap detectors miss; expensive enough to be opt-in.

### 3.6 Reporting

Each run emits three artifacts under `scripts/confabulation_eval_results/<utc-timestamp>/`:

1. **`runs.jsonl`** — one record per (query, flag_state, run_index): query text, query template, row IDs probed, flag state, run index, response text, evidence set, detector hits per layer, response latency, tier classification of the response.

2. **`summary.md`** — human-readable: per-flag-state aggregate confabulation rate; top-20 offending rows with sample responses; top-20 most-confabulated tokens (across Layer 1 and Layer 2 combined); per-tier breakdown; regression-anchor sanity check (did §1.1 cases get flagged?).

3. **`per_row.csv`** — row × extrapolation-token matrix for spreadsheet review on mobile. Columns: row_id, row_name, total_runs, runs_with_hit, top_3_tokens.

A baseline result directory will be committed (one per quarter or per significant phase) so progress is comparable across runs. Day-to-day result directories are gitignored.

### 3.7 HALT checkpoints

Three HALTs. None should bend on second testing.

- **HALT 1 — pre-implementation lexicon, template, and hook review.** Before classifier code is locked, owner reviews and approves: (a) per-row probe template list (§3.2), (b) safe_framing_vocabulary stoplist (§3.5.1), (c) Layer 2 wordlist (§3.5.2), (d) Layer 3 quantity-noun list and canonicalizer rules (§3.5.3). Lexicon governance follows 8.8.5 §3.1.3 model: conceptual classes locked, literal lists implementation-owned and may evolve post-deploy with owner review. **HALT 1 also reports back from Cursor's read of `app/chat/unified_router.py` to determine whether evidence-set introspection requires a hook to that file (§8 decision #9). If a hook is needed, the proposed diff is shown at HALT 1 before implementation.**

- **HALT 2 — dry-run on 5-provider subset.** Before full-catalog sweep, run the harness against a hand-picked 5-provider subset that includes both regression anchors (Aqua Beginnings, Grace Arts Live) and at least three rows that should produce zero hits (a rich, well-described provider; a sparse provider that gets handled correctly today). Owner reviews report shape and detector calibration.

- **HALT 3 — first full-sweep report.** Owner reviews the full-catalog baseline before harness is declared 8.8.6-ready. Confirms the detector signal is signal, not noise. May trigger lexicon adjustments under HALT 1's governance rule.

---

## 4) Implementation file list

### 4.1 Files to create

1. `scripts/confabulation_eval.py` — CLI runner. Flags: `--mode={inprocess,http}`, `--runs N`, `--flags={off,on,both}`, `--rows={providers,programs,both}`, `--output-dir`, `--limit` (for HALT 2 subset), `--include` / `--exclude` (row filters).
2. `app/eval/__init__.py`
3. `app/eval/confabulation_query_gen.py` — `generate_probes(session) -> list[Probe]`. Returns one Probe per (row, template). Probe carries query text, row reference, template id.
4. `app/eval/confabulation_invoker.py` — `invoke(probe, flag_state) -> InvocationResult`. Two implementations behind a strategy interface: `InProcessInvoker` and `HttpInvoker`. Returns `InvocationResult(response_text, evidence_set, tier_used, latency_ms, raw_log)`.
5. `app/eval/confabulation_detector.py` — `detect(invocation_result) -> list[DetectorHit]`. Hits carry layer, token, sentence_index, row_ids_in_scope. Includes the Layer 3 canonicalizer per §3.5.3.
6. `app/eval/confabulation_report.py` — `write_jsonl`, `write_summary_md`, `write_per_row_csv`.
7. `tests/test_confabulation_query_gen.py`
8. `tests/test_confabulation_detector.py` — fixture cases for §1.1 anchors plus negative fixtures (clean responses) plus Layer 3 normalization fixtures (e.g., `"$19"` vs `"19"`, `"8am"` vs `"8:00 AM"`, `"90 min"` vs `"90-minute"` all match).
9. `tests/test_confabulation_invoker.py` — in-process invoker integration test against a 1-provider stub catalog.
10. `docs/confabulation-eval-runbook.md` — how to invoke, how to read each artifact, how to interpret hits, how to expand lexicons under HALT 1 governance.

### 4.2 Files explicitly NOT to modify

- `app/chat/llm_router.py`
- `app/chat/unified_router.py`
- `app/chat/tier2_db_query.py`
- `app/chat/tier2_formatter.py`
- `app/chat/tier3_handler.py`
- `app/chat/tier2_schema.py`
- `prompts/*.txt`
- `app/db/models.py`
- `app/main.py`

The harness is read-only against the system. The only acceptable touch to the above list is adding an evidence-set hook to the in-process invocation path *if and only if* such a hook cannot be built externally — and that touch is its own HALT 1 decision per §8 #9.

### 4.3 `.gitignore` additions

```
scripts/confabulation_eval_results/*
!scripts/confabulation_eval_results/baselines/
```

---

## 5) Test plan

### 5.1 Unit tests

1. `test_confabulation_query_gen`: given a stub catalog of 2 providers + 1 program, generate_probes returns 9 probes with expected templates and row references.
2. `test_confabulation_detector_layer1`: against the Aqua Beginnings fixture (row + confabulated response), Layer 1 flags `private`, `heated`, `outdoor`. Against a clean Aqua Beginnings response that stays within the row, Layer 1 flags nothing.
3. `test_confabulation_detector_layer2`: wordlist members in a response without row support are flagged; same words present in row description are NOT flagged.
4. `test_confabulation_detector_layer3_invented`: invented hours / prices / capacities flagged; row-supported numbers not flagged.
5. `test_confabulation_detector_layer3_normalization`: `"$19"` in response matches `"19"` in row (no hit); `"8am"` matches `"8:00 AM"` (no hit); `"90-minute"` matches `"90 min"` (no hit); `"Mon"` matches `"Monday"` (no hit). Negative side: `"$25"` in response when row says `"$19"` IS flagged.
6. `test_confabulation_detector_safe_framing`: tokens in the safe_framing_vocabulary stoplist do not produce Layer 1 hits even when not in the evidence set.
7. `test_confabulation_detector_grace_arts_live`: the multi-row evidence-set scoping works — `youth theatre` is NOT flagged when an associated Event row in the evidence set contains it; `air-conditioned` IS flagged.
8. `test_confabulation_report`: JSONL / MD / CSV emission produces parseable artifacts.

### 5.2 Integration tests

1. `test_inprocess_invoker_smoke`: against a 1-provider stub catalog, in-process invoker returns a populated `InvocationResult` with non-empty evidence_set.

### 5.3 Validation gate (for the harness itself)

The harness ships when:

1. Full unit + integration suite passes.
2. HALT 2 dry-run on the 5-provider subset produces a clean report.
3. HALT 3 full-sweep report flags both §1.1 regression anchors at >0 confabulation rate per (query, flag-state).
4. Full-sweep report does not produce so many false positives on rich, well-described rows that the signal is unusable. "Unusable" is owner-judged at HALT 3.

### 5.4 Not a gate this phase

This phase does NOT define a confabulation-rate threshold for shipping a formatter change. That threshold belongs in 8.8.6 step 1+ once we have a measured baseline. The harness produces numbers; 8.8.6 step 1+ decides what "good enough" means.

---

## 6) Risk and rollback

### 6.1 Risks

1. **Detector noise.** Layer 1's scoped diff produces false positives on legitimate concierge framing (`"worth a stop"`, `"head over to"`). Mitigated by safe_framing_vocabulary stoplist owner-reviewed at HALT 1.
2. **Detector entrenches today's failure modes.** Wordlist-only would do this; the layered design with Layer 1 as primary mitigates. Wordlists can be expanded post-deploy under HALT 1 governance.
3. **In-process mode masks HTTP-layer behavior.** Mitigated by HTTP mode being available for staging validation. Does not affect detector correctness.
4. **Tier 3 stochasticity makes per-run findings unstable.** Mitigated by N-runs aggregation. Per-(query, flag-state) rate is the unit of analysis, not per-run pass/fail.
5. **Cost creep at bulk-import scale.** Curated catalog is ~24 providers + ~28 programs. v1 sweep is (24+28) × 3 templates × 3 runs × 2 flag states = 936 invocations. Mostly Tier 1/Tier 2 (free) for direct lookups. Estimated <$5 in API cost worst case. Bulk-catalog scale (~4,574 providers post-8.11) requires sampling strategy — out of v1 scope, documented for v2.
6. **Evidence-set introspection requires hooking the formatter call site.** If the unified_router doesn't already expose the rows it passed to the formatter, we may need to add an external hook or accept a small touch to `unified_router.py`. Resolved at HALT 1 once Cursor reads the call site. Hook constraints: logged side-effect only, no signature change, no behavior change, no-op when harness isn't running.
7. **Layered detector adds maintenance burden.** Three layers, three lexicons, three sets of edge cases, plus the Layer 3 canonicalizer rules. Mitigated by clear lexicon governance (HALT 1) and by Layer 1 carrying most of the load.
8. **Layer 3 normalization rules mis-canonicalize an edge case.** Required mitigation: §5.1 test 5 covers the canonical pairs. Owner reviews canonicalizer rules at HALT 1 before code locks.

### 6.2 Mitigations summary

- Layered detection (Layer 1 primary, generalizes; Layers 2/3 secondary, regression coverage).
- Layer 3 canonicalization required, not optional, with owner-reviewed rules.
- HALT 1 owner-reviewed lexicons, templates, canonicalizer rules, and evidence-set hook diff.
- HALT 2 dry-run sanity check.
- HALT 3 full-sweep review before declaring harness ready for 8.8.6 step 1+.
- N-runs default 3.
- In-process default for full detector fidelity; HTTP opt-in for staging.

### 6.3 Rollback

- Pure tooling. No production code changed. No prompts, no schema, no router.
- Rollback = revert harness commits + delete result artifacts + drop `.gitignore` entries.
- No dependency on harness from any production code path. Trivial removal if the approach turns out to be wrong.
- If HALT 1 determines an evidence-set hook in `unified_router.py` is required, the hook is its own commit and can be reverted independently of the harness modules.

This phase is the lowest-risk phase since 8.8.0 by a clear margin.

---

## 7) Phase ledger and docs

- **Phase number:** 8.8.6 step 0. Step 0 = build the eval. Step 1+ of 8.8.6 = use it to fix rich-row confabulation.
- **Sequence (revised pre-launch):**
  ```
  8.8.3 [done]
    -> 8.8.4 [done, dormant via flag]
    -> 8.8.5 [reverted]
    -> 8.8.6 step 0 [THIS PHASE — eval harness]
    -> 8.8.6 step 1+ [rich-row formatter fix, baseline informed by step 0]
    -> 8.9 (event ranking)
    -> 8.10 (River Scene event pull)
    -> 8.11 (Google bulk import)
    -> 8.12 (voice regression v2)
    -> 8.13 (Tier 3 retrieval tuning)
    -> dogfood
    -> launch
  ```

Docs to update during implementation (not in this spec phase):

- `docs/START_HERE.md` — add 8.8.6 step 0 to current sequence; refresh tip pointer; note that doc was stale through 8.8.2 closeout and needs a sweep.
- `HAVA_CONCIERGE_HANDOFF.md` §5 — phase ledger update.
- `docs/known-issues.md` — note that "Tier 2 formatter rich-row confabulation" is now measured by the harness, with a baseline rate captured at HALT 3.
- `docs/pre-launch-checklist.md` — add harness as a pre-launch tool.

Known-issues entries this phase touches (listed for context, not all closed by it):

1. Tier 2 formatter rich-row confabulation — measurement instrument exists post-this-phase; fix lands in 8.8.6 step 1+.
2. Tier 2 formatter sparse-row confabulation — 8.8.5's sparse rule worked in validation; the harness will detect any regression when 8.8.6 step 1+ ports the rule forward.
3. Tier 3 confabulation observations from 8.8.4 validation — harness measures these too; remediation deferred per prior decision.
4. London Bridge Beach class of entity-invention — flagged for v2 detector layer.
5. Aquatic Center selection misses for "kids on a hot day" — separate retrieval concern; harness does not measure retrieval correctness.

---

## 8) Resolved decisions (owner-approved at HALT 0)

All nine open decisions resolved 2026-04-25.

1. **Phase number:** 8.8.6 step 0. Eval harness is foundation, fix is step 1+.
2. **v1 detector layer set:** Layer 1 (per-row scoped extrapolation diff, primary) + Layer 2 (wordlist, secondary) + Layer 3 (number/quantity invention with canonicalization, secondary). Layer 4 (entity invention) and Layer 5 (LLM judge) deferred to v2.
3. **v1 catalog scope:** curated Provider + Program rows (current live catalog ≈ 24 providers + 28 programs). Bulk-catalog sweep (Phase 8.11 scale) deferred. Sampling strategy is a separate v2 phase once bulk ingest is closer.
4. **Run mode default:** in-process (required for evidence-set introspection). HTTP opt-in for staging validation.
5. **N runs default:** N=3. Configurable via `--runs`.
6. **Pass/fail gate placement:** NOT in this phase. Threshold defined in 8.8.6 step 1+ informed by the baseline this phase produces. Gate placement is the most disciplined decision in §8 — defining a threshold before measuring would repeat the 8.8.5 mistake.
7. **Disposition of `docs/phase-8-8-5-halt5-followup-baseline-verification-and-staging.md`:** kept and committed with a status-update header noting the 8.8.5 rollback. Methodology in §1 of that doc is reusable for any future baseline-verification work.
8. **Probe template lock:** templates in §3.2 approved as decision shape; concrete templates locked at HALT 1 alongside lexicons.
9. **In-scope evidence-set hook:** if exposing the formatter's evidence set requires a touch to `app/chat/unified_router.py`, allowed as a minimal hook with the following constraints: logged side-effect only (e.g. thread-local context or structured logger), no function signature change, no response shape change, no behavior change, no-op or near-zero overhead when the harness isn't running. HALT 1 reports the proposed hook diff before implementation; if the diff exceeds ~5–10 lines or touches control flow, that's a flag. If the call site already exposes evidence rows in a consumable form, no hook needed.

---

## 9) Code-reading references

Authoritative context for HALT 1 implementation reading:

- `app/chat/unified_router.py` — entry point for in-process invoker; identify where the formatter receives row payloads. **Primary read for §8 #9 hook decision.**
- `app/chat/tier2_db_query.py` — `_provider_dict`, `_program_dict`, query/merge flow. Source of evidence-set construction.
- `app/chat/tier2_formatter.py` — formatter call site; receives row JSON.
- `app/chat/tier3_handler.py` — Tier 3 path; harness must record tier classification for reporting.
- `app/db/models.py` — `Provider`, `Program`, `Event` field shape for evidence-set extraction.
- `app/main.py` — `/api/chat` endpoint contract for HTTP mode.
- `prompts/tier2_formatter.txt` — current formatter prompt (informational; harness does not change it).
- `docs/phase-8-8-5-formatter-grounding-spec-v2.md` — the spec that failed; lineage and rationale.
- `docs/phase-8-8-5-halt5-followup-baseline-verification-and-staging.md` — baseline-verification methodology, reusable for any future phase that needs to confirm a test failure is pre-existing.
- `docs/persona-brief.md` §6.7 — voice spec the harness measures against (factually-descriptive at per-provider level for bulk; firsthand at landscape level).

---

## End of spec
