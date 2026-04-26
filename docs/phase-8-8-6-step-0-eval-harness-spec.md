# Phase 8.8.6 step 0 — Confabulation Eval Harness Spec

Status: HALT 0 closed (2026-04-25). Amendments applied 2026-04-25 (HALT 1 finding), 2026-04-25 (HALT 2 finding), 2026-04-25 (HALT 2 dry-run finding). See §10.
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

1. Measure per-row confabulation rate across the full curated catalog of Provider and Program rows. Rate metric is computed from Layer 2 + Layer 3 hits only — Layer 1 is advisory (see §3.5).
2. Run each probe under both `USE_LLM_ROUTER=false` and `USE_LLM_ROUTER=true`.
3. Aggregate over N runs per (query, flag-state) to absorb Tier 3 stochasticity.
4. Emit human-readable per-row, per-extrapolation-word, and per-run reports.
5. Be the validation instrument for 8.8.6 step 1+ and every later formatter / prompt phase. Reusable, repeatable, version-controlled.
6. Detect the regression-anchor cases in §1.1 deterministically across at least one of Layer 2, Layer 3, or Layer 1 advisory output.

### 2.2 Non-goals (locked)

- **Not a fix for confabulation.** That is 8.8.6 step 1+.
- No formatter prompt changes, router changes, schema changes, or model changes.
- No retrieval / selection correctness measurement. Wrong-row-picked is a separate problem (see Aquatic Center known issue).
- No Tier 3 LLM-judge harness in v1. Documented as a v2 extension.
- No entity-invention detection in v1. London Bridge Beach class of failure is logged but not gated.
- No pass/fail threshold defined in this phase. Threshold lives in 8.8.6 step 1+ once we have a baseline.
- No bulk-catalog (Phase 8.11 / 4,574 row) sampling strategy in v1. Scoped to curated catalog. Sampling deferred to a later phase once bulk ingest is closer.
- No intent-style probes (`"kids on a hot day"`, `"a quiet weekend morning"`) in v1. Per-row probes only. Intent queries deferred to v2 because they couple confabulation detection with retrieval correctness.
- **Layer 1 (per-row scoped diff) is not a gating signal in v1.** It runs and is reported, but the headline confabulation rate is computed from Layer 2 + Layer 3 only. See §3.5.1 for rationale.

---

## 3) Approach

### 3.1 Architecture

Three modules plus a CLI runner. Detection logic lives behind importable APIs so it is unit-testable and reusable from anywhere (CI, ad-hoc, future phases).

```
scripts/confabulation_eval.py            # CLI runner
app/eval/__init__.py
app/eval/confabulation_query_gen.py      # catalog -> probe queries
app/eval/confabulation_invoker.py        # in-process or HTTP invocation; installs evidence-set monkeypatch (in-process only)
app/eval/confabulation_evidence.py       # ContextVar definition + monkeypatch install/restore helpers
app/eval/confabulation_detector.py       # detection layers, returns hits per response
app/eval/confabulation_report.py         # JSONL/MD/CSV emission
tests/test_confabulation_query_gen.py
tests/test_confabulation_detector.py
tests/test_confabulation_invoker.py
tests/test_confabulation_evidence.py
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

Templates locked at HALT 1. `<n>` substitution uses the row's display name verbatim. Display name is normalized at filter time (en-dash and em-dash mapped to ASCII hyphen; lowercased) so operator include/exclude lists work regardless of dash style — see §3.7. No fuzzing in v1.

### 3.3 Run mode

**Default: in-process.** The runner imports the unified router and calls it directly with each probe. It captures both the assistant response *and* the full set of rows the formatter received for that turn (`evidence_set`) via a harness-only monkeypatch on `app.chat.tier2_formatter.format` (see §3.5.1a and §8 #9). In-process is the default because (a) row-level introspection is required for Layer 1's advisory output (§3.5.1), and (b) it removes network and deploy latency from the loop.

**Opt-in: HTTP mode** (`--mode=http --base-url=<url>`). For staging validation. The monkeypatch is not installed in HTTP mode (it's a different process). HTTP mode therefore skips evidence-set introspection and falls back to wordlist + number-invention layers only (degraded detection — see §3.5.2 caveat). In HTTP mode, Layer 1 advisory output is unavailable. Documented; not the default path.

### 3.4 Determinism strategy

- N runs per (query, flag-state). Default N=3. Configurable via `--runs`.
- Tier 3 calls are stochastic; per-run confabulation is binary, but per-(query,flag-state) confabulation rate is meaningful at N=3 and tightens at larger N.
- Each run is logged with a stable `(query_id, flag_state, run_index)` tuple for reproducibility.
- Seed is logged but not enforced — Tier 3 doesn't accept a seed today and we don't want to fork the prod path.

### 3.5 Detection layers (v1)

Three layers with distinct roles. **Layer 2 and Layer 3 are gating** (contribute to the headline confabulation rate). **Layer 1 is advisory** (runs and is reported, but does not contribute to the rate). Each layer emits hits with row context, layer label, and matched span. The detector is content-only — it does not score voice, length, formality, or any other axis.

The role split was not the original design. HALT 2 dry-run iterations (G, G1, G2) demonstrated that Layer 1's per-row scoped diff produces a long-tail of conversational-scaffolding false positives that no reasonable safe_framing list can absorb without bleeding into real confabulation territory. Each round of safe_framing expansion silenced the top 10 offenders only to surface the next 10. Layer 1 retains real value as a *candidate-token surface* for human review during 8.8.6 step 1+ — it produces the "novel words the response used that aren't in the row" signal. But it cannot serve as a primary measurement metric in v1 without poisoning the baseline. Layer 2 + Layer 3 produce clean enough signal to gate on; Layer 1 reports for review. See §10 amendment changelog (2026-04-25 HALT 2 dry-run amendment) for the lineage.

#### 3.5.1 Layer 1 — Per-row scoped extrapolation diff (ADVISORY)

The point of this layer: surface candidate tokens that appear in the response but not in the evidence set. **In v1 this is advisory output for human review, not a gating metric.** The diff produces a list of "things the response said that the row didn't mention," which is useful for spotting novel confabulation classes and reviewing 8.8.6 step 1+ candidate fixes — but the list is too noisy to drive a confabulation rate threshold by itself.

For each turn:

1. Capture the `evidence_set` = union of all content tokens from every row the formatter received on that turn. Evidence dict shape **must** match `tier2_db_query._provider_dict` / `_program_dict` / `_event_dict` exactly — do not inflate the dicts with ORM fields the formatter never saw (notably do not add `featured_description` or `website` to provider evidence unless the underlying `_provider_dict` already includes them). The evidence set must reflect what the model actually had, not what was theoretically available.

   Token extraction: union of content tokens from each dict's keys named `name`, `description`, `category` / `activity_category`, `address`, `phone`, `hours`, `website` (if present in the dict), `schedule`, `cost`. Tokens normalized: lowercased, lemmatized, stripped of punctuation. Phone-number-shaped tokens (regex per implementation) stripped before POS tagging on both sides — Layer 3 handles phone-number invention via `ph:` prefix tokens.

2. Tokenize the response. Filter to content words via a stoplist + POS tag (NOUN / ADJ / VERB excluding generic verbs). Numbers handled by Layer 3.

3. Subtract: `response_content_tokens − evidence_set_tokens − safe_framing_vocabulary`.

4. Any remainder is a **candidate token**. Each emitted as a Layer 1 entry with token, sentence-of-occurrence in the response, and row IDs in scope. Reported in `runs.jsonl` and surfaced in `summary.md` under a separate "Layer 1 candidate tokens (advisory)" section.

`safe_framing_vocabulary` is a curated list of generic concierge-voice tokens that appear in responses but aren't confabulation: concierge framing verbs, evaluative tone words, place / venue generics, hedges, regional aliases. v1 is unigrams only — multi-word handling deferred to v2. Function words are excluded by the POS filter, not by safe_framing. Owner-reviewed at HALT 1, with HALT 2 dry-run iterations adding scaffolding terms surfaced by real outputs.

##### 3.5.1a Evidence-set capture mechanism

Evidence-set capture is implemented as a **harness-only monkeypatch** on `app.chat.tier2_formatter.format`. Mechanics:

- `app/eval/confabulation_evidence.py` defines a module-level `contextvars.ContextVar` named `tier2_evidence` plus a module-local `_last_captured` buffer.
- `app/eval/confabulation_invoker.py`, before calling `unified.route(...)`, calls `install()` which replaces `tier2_formatter.format` with a wrapper that:
  1. sets the ContextVar to `(query, [dict(r) for r in rows])` (defensive copy);
  2. **also writes the same payload to `_last_captured`** (because the ContextVar is reset in step 4 before the invoker has a chance to read it);
  3. calls the original `format(query, rows)`;
  4. resets the ContextVar in `finally` regardless of return value or exception;
  5. **returns the original function's return value unchanged.**
- After the route call returns, the invoker reads `_last_captured` (not the ContextVar — that's already been reset) via `consume_last_evidence()` which reads-and-clears the buffer. The invoker uses the result to construct the evidence_set, then calls `restore()` which puts the original `format` back.
- The buffer is cleared in three places to prevent cross-invocation leakage: at `install()` start, at `consume_last_evidence()` read, and at `restore()`.

**Wrapper signature requirement:** `tier2_formatter.format` has the signature `(query: str, rows: list[dict]) -> tuple[Optional[str], int | None, int | None]`. The 3-tuple is `(text, input_tokens, output_tokens)`. The wrapper must preserve this signature exactly — same call shape, same return shape. The wrapper does not interpret or modify the return value; it forwards whatever `format` returns.

Constraints baked into this mechanism (cross-reference §8 #9):

- **No production code touched.** All hook code lives in `app/eval/`. The do-not-modify list in §4.2 is fully respected.
- **No signature change** to `tier2_formatter.format`.
- **No `ChatResponse` change.** Evidence is harness-side only.
- **Zero production overhead** when harness is not running. The patch is not installed unless `app/eval/confabulation_invoker.py` calls `install()`.
- **`try`/`finally`** ensures evidence does not stick to a later request, even if `format` raises.
- **ContextVar + buffer** combination is the right choice for today's synchronous call stack. If `tier2_handler` is ever moved to a thread pool or async scheduler, the wrapper must be revisited — documented as a known assumption in the runbook, not a TODO.

The architecture finding that drove this design: `unified_router.py` is *not* the formatter call site. The actual call site is `app/chat/tier2_handler.py`, which calls `tier2_db_query.query()` then `tier2_formatter.format(query, rows)`. The router only sees the string output and token tallies. By the time control returns to the router, rows are gone (they were locals in `tier2_handler`). HALT 1 surfaced this; the resolution is the harness-only monkeypatch above. See §10 amendment changelog and §8 #9 for the resolved approach.

#### 3.5.2 Layer 2 — Curated extrapolation wordlist (GATING)

Layer 2 is a primary signal contributing to the confabulation rate. It catches today's known confabulation vocabulary deterministically.

A literal wordlist of known confabulation vocabulary, scoped to category-extrapolation patterns:

- Facility / amenity invention: `heated, indoor, outdoor, private, air-conditioned, climate-controlled, shaded, covered`
- Audience-fit invention: `family-friendly, kid-friendly, kid-appropriate, romantic, upscale, casual, cozy, intimate, quiet, lively`
- Procedural invention: `book directly, reservation required, walk-ins welcome, no reservations, enrollment, RSVP`

For each hit, we flag any wordlist member appearing in the response but not in the evidence set. Owner-reviewed and locked at HALT 1; allowed to grow during operation as new patterns surface, similar to the implementation-lexicon governance from 8.8.5 §3.1.3.

**HTTP mode caveat:** Layer 2 in HTTP mode runs without an evidence set (the monkeypatch isn't available across process boundaries). It can still flag wordlist-member appearances in responses, but it cannot tell whether the row actually contained the word. Words like `pool, deck, patio, studio` are legitimate row content for some providers; in HTTP mode Layer 2 will flag them unconditionally, producing high false-positive rates. HTTP mode hits are a degraded signal, not a comparable one. Document in the runbook.

#### 3.5.3 Layer 3 — Number / quantity invention (GATING)

Layer 3 is a primary signal contributing to the confabulation rate. It catches invented numerical content (prices, hours, durations, capacities, phone numbers).

For each turn:

1. Extract digit sequences and quantity nouns (`several, multiple, dozen, dozens, handful, few, many, most, a couple, couple, numerous, various, some, couple of, a few, majority, minority`) from both the response and the evidence set. (`bunch, tons, loads` deferred to v1.1 unless pilot shows they're needed.)

2. **Normalize before diff.** Both sides are passed through a canonicalizer. Required rules:

   - **Currency:** strip currency symbols. Map `free`, `no charge`, `no cost`, `$0`, `$0.00` all to canonical `price:0` (or implementation-equivalent free-cost token). Use the prefixed form (not bare `0`) to avoid collision with non-price `0` tokens elsewhere. Apply to both sides. **Decimal handling:** `$5`, `$5.00` both → `usd:5` (zero cents collapse to integer dollars). `$5.50` → `usd:5.50` (nonzero cents preserved). Canonical form symmetric on both sides.

   - **Time:** normalize 24h forms and AM/PM-disambiguated 12h forms to canonical `HH:MM`. **For ambiguous 12h-without-AM/PM, do NOT guess** — keep as a tagged unresolved token and exclude from Layer 3 diff. False negatives strongly preferred to false positives here.

   - **Duration:** canonical scale is **minutes**. `1 hr` / `1 hour` → `60min`. `90-minute`, `90 min`, `90 minutes` → `90min`. Apply consistently.

   - **Day of week:** v1 keeps `weekday` and `weekend` as separate tokens, no mapping to specific days. Days themselves normalized: `mon|monday|m` → `monday`, etc. Revisit weekday/weekend mapping in v1.1 if pilot shows false diffs.

   - **Price ranges:** strip `$`, `ea`, `each`, `approx`, `~`, `about` before extraction. `$10-15`, `$10–15`, `$10 to $15`, `10 to 15 dollars` all → `10-15`. `under $20` → `<=20`. Note: v1 diff structure does not fully handle inequality semantics — if evidence says `<=20` and response says `$15`, they won't match (a technical false positive). Accept as v1 limitation; revisit if it bites in practice. Price-range matches require a `$` symbol in the matched span to avoid misclassifying phone-number-shaped strings as dollar ranges.

   - **Phone numbers:** NANP-shaped tokens (e.g., `(602) 555-1212`, `602-555-1212`) extracted with a `ph:` prefix on canonical digits. The pre-tokenization phone-strip in §3.5.1 ensures Layer 1 doesn't double-flag these; Layer 3's `ph:` tokens catch invented phone numbers symmetrically.

3. Diff response canonical-numbers against evidence-set canonical-numbers. Any remainder is a candidate hit and contributes to the confabulation rate.

The normalization step is required, not optional. Without it, the layer produces high false-positive rates on every catalog row that lists hours, prices, or schedule durations in formats the response then re-renders. Canonicalizer rules are owner-reviewed at HALT 1 alongside the lexicons.

Catches invented hours, capacities, prices, phone numbers, recurrence counts. Cheap; high precision once normalized; covers a failure class wordlists miss.

#### 3.5.4 Out of v1 — documented as v2 extensions

- **Layer 4 — entity invention.** Flag mentions of provider / place / program names not in the evidence set or the catalog. Catches London Bridge Beach class of failure.
- **Layer 5 — LLM judge.** A separate Haiku call: *"Given these rows and this response, list any factual claims in the response that are not supported by the rows."* Useful for catching what cheap detectors miss — including the Layer 1 advisory-class confabulations that v1 surfaces but doesn't gate on. Expensive enough to be opt-in. Layer 5 is the most likely v2 path to converting Layer 1's advisory output into a gating signal.

### 3.6 Reporting

Each run emits three artifacts under `scripts/confabulation_eval_results/<utc-timestamp>/`:

1. **`runs.jsonl`** — one record per (query, flag_state, run_index): query text, query template, row IDs probed, flag state, run index, response text, evidence set, detector hits per layer (split into `layer_2_hits`, `layer_3_hits`, `layer_1_advisory_tokens`), response latency, tier classification of the response, `excluded_from_summary` flag with `excluded_reason` for Tier 1 / Tier 3 rows.

2. **`summary.md`** — human-readable summary with these sections in order:
   - **Inclusion policy.** Total runs, included in rate (Tier 2 only), excluded from rate (Tier 1, Tier 3 separately). v1 measures Tier 2 only.
   - **Per-flag confabulation rate.** Computed from Layer 2 + Layer 3 hits only (Layer 1 advisory tokens do not contribute). One row per flag state.
   - **Top offending rows.** Rows with highest Layer 2 + Layer 3 hit rates. Sample response excerpts.
   - **Top confabulated tokens (Layer 2 + Layer 3).** Frequency-ranked. Real confabulation vocabulary and invented numerical content.
   - **Layer 1 candidate tokens (advisory).** Frequency-ranked separately. Marked clearly as not contributing to the rate. For human review during 8.8.6 step 1+ — these are tokens the response used that the row didn't, which may include real novel confabulation classes alongside conversational scaffolding.
   - **Tier breakdown.** Tier 1 / Tier 2 / Tier 3 invocation counts.
   - **Regression-anchor sanity check.** Aqua Beginnings and Grace Arts Live hit rates on Layer 2 + Layer 3 (which is what the rate is computed from).

3. **`per_row.csv`** — row × confabulation-token matrix for spreadsheet review on mobile. Columns: row_id, row_name, total_runs, included_runs (Tier 2 only), gating_runs_with_hit (Layer 2 + Layer 3), advisory_token_count (Layer 1), top_3_gating_tokens.

A baseline result directory will be committed (one per quarter or per significant phase) so progress is comparable across runs. Day-to-day result directories are gitignored.

### 3.7 HALT checkpoints

Three HALTs. None should bend on second testing.

- **HALT 1 — pre-implementation lexicon, template, and hook review.** Status: **closed 2026-04-25.** Owner reviewed and approved: (a) per-row probe template list (§3.2), (b) safe_framing_vocabulary stoplist scope (§3.5.1, with v1-unigrams-only constraint), (c) Layer 2 wordlist (§3.5.2), (d) Layer 3 quantity-noun list and canonicalizer rules (§3.5.3). Lexicon governance follows 8.8.5 §3.1.3 model: conceptual classes locked, literal lists implementation-owned and may evolve post-deploy with owner review. **HALT 1 also surfaced the formatter call-site location finding that drove this spec's first amendment** — `unified_router.py` does not see rows; the actual call site is `tier2_handler.py`. The resolved approach is a harness-only monkeypatch in `app/eval/`, not any production touch. See §3.5.1a, §8 #9, and §10. Final lexicons land in a `relay/halt1-closure-final-lexicons.md` artifact for implementation reference, not as a doc commit.

- **HALT 2 — dry-run on 5-provider subset.** Status: **closed 2026-04-25** after iterative G, G1, G2 calibration rounds. Run the harness against a hand-picked 5-provider subset (Aqua Beginnings, Grace Arts Live, Lake Havasu City Aquatic Center, Flips for Fun Gymnastics, Open Jump – 90 Minutes) including both regression anchors and rich/sparse/program coverage. Owner reviewed report shape and detector calibration across three iterations. **HALT 2's findings drove three spec amendments:** the format() signature correction (HALT 2-A), the confirmation that Layer 1's per-row scoped diff cannot serve as a primary v1 metric (HALT 2 dry-run G2-C), and a series of detector defect fixes (Tier 3 exclusion, phone POS-asymmetry, currency canonicalization, em-dash tokenization, contraction handling, lemmatizer normalization, dash-normalization in CLI filters). Final v3 dry-run produced clean signal differentiation when the rate is computed from Layer 2 + Layer 3 only.

- **HALT 3 — first full-sweep report.** Owner reviews the full-catalog baseline before harness is declared 8.8.6-ready. Confirms the Layer 2 + Layer 3 signal is signal, not noise, and reviews the Layer 1 advisory output as input to 8.8.6 step 1+ planning. May trigger lexicon adjustments under HALT 1's governance rule.

---

## 4) Implementation file list

### 4.1 Files to create

1. `scripts/confabulation_eval.py` — CLI runner. Flags: `--mode={inprocess,http}`, `--runs N`, `--flags={off,on,both}`, `--rows={providers,programs,both}`, `--output-dir`, `--limit` (for HALT 2 subset), `--include` / `--exclude` (row filters with dash normalization). Excludes Tier 1 and Tier 3 from rate calculation via `excluded_from_summary`.
2. `app/eval/__init__.py`
3. `app/eval/confabulation_query_gen.py` — `generate_probes(session) -> list[Probe]`. Returns one Probe per (row, template). `normalize_row_name_for_include()` helper that maps en-dash and em-dash to ASCII hyphen plus lowercases, used for include/exclude filter comparison.
4. `app/eval/confabulation_evidence.py` — `tier2_evidence` ContextVar plus `_last_captured` buffer; `install()`, `restore()`, `consume_last_evidence()` helpers. Wrapper preserves the actual `format` signature `(query: str, rows: list[dict]) -> tuple[Optional[str], int | None, int | None]` per §3.5.1a. Buffer cleared in three places to prevent leakage.
5. `app/eval/confabulation_invoker.py` — `invoke(probe, flag_state) -> InvocationResult`. Two implementations behind a strategy interface: `InProcessInvoker` (calls `install()` before `unified.route`, reads `_last_captured` after, calls `restore()`) and `HttpInvoker` (no monkeypatch; degraded detection). Returns `InvocationResult(response_text, evidence_set, tier_used, latency_ms, raw_log)`.
6. `app/eval/confabulation_detector.py` — `detect(invocation_result) -> list[DetectorHit]`. Hits carry layer (`"1"`, `"2"`, `"3"` or `"1_advisory"` for Layer 1), token, sentence_index, row_ids_in_scope. Layer 1 hits emitted as advisory only. Includes the Layer 3 canonicalizer per §3.5.3, the phone-number stripping logic per §3.5.1, and the safe_framing list expanded across HALT 1 closure + HALT 2 dry-run iterations.
7. `app/eval/confabulation_report.py` — `write_jsonl`, `write_summary_md`, `write_per_row_csv`. Summary computes rate from Layer 2 + Layer 3 only; reports Layer 1 candidate tokens in a separate advisory section.
8. `tests/test_confabulation_query_gen.py` — includes `normalize_row_name_for_include` equivalence test with non-ASCII dash.
9. `tests/test_confabulation_detector.py` — fixture cases for §1.1 anchors plus negative fixtures (clean responses) plus Layer 3 normalization fixtures (currency decimal, time, duration, phone) plus Layer 1 advisory-vs-gating split assertion.
10. `tests/test_confabulation_invoker.py` — in-process invoker integration test against a 1-provider stub catalog plus the no-stale-evidence-between-calls test.
11. `tests/test_confabulation_evidence.py` — install/restore correctness, ContextVar reset on exception, no leakage between requests, return-passthrough verifying the 3-tuple.
12. `tests/test_confabulation_report.py` — Tier 1 + Tier 3 excluded from rate; Layer 1 reported separately from Layer 2 + Layer 3.
13. `tests/test_confabulation_eval_script.py` — script-level test for `--include` / `--exclude` with non-ASCII dash row names.
14. `docs/confabulation-eval-runbook.md` — operator guide. Covers: how to invoke, how to read each artifact (including the gating-vs-advisory split), how to interpret hits, how to expand lexicons under HALT 1 governance, the threading/async caveat from §3.5.1a, the HTTP-mode degraded-Layer-2 caveat from §3.5.2, the v1 inequality-semantics limitation from §3.5.3, the Tier 1 + Tier 3 exclusion policy, the dash-normalization behavior, and an explicit note that Layer 1 advisory output is candidate-token surface for human review during 8.8.6 step 1+, not a rate metric.

### 4.2 Files explicitly NOT to modify

- `app/chat/llm_router.py`
- `app/chat/unified_router.py`
- `app/chat/tier2_handler.py` ← **load-bearing** for §8 #9 — this is the actual formatter call site, intentionally left untouched in favor of the harness-only monkeypatch in `app/eval/`
- `app/chat/tier2_db_query.py`
- `app/chat/tier2_formatter.py` ← runtime-patched by `app/eval/confabulation_evidence.install()` during in-process eval runs only; the on-disk file is not modified
- `app/chat/tier3_handler.py`
- `app/chat/tier2_schema.py`
- `prompts/*.txt`
- `app/db/models.py`
- `app/main.py`

The harness is read-only against the on-disk system. Runtime monkeypatching of `tier2_formatter.format` in-process during eval runs is in scope per §3.5.1a; permanent edits to any file above are not.

### 4.3 `.gitignore` additions

```
scripts/confabulation_eval_results/*
!scripts/confabulation_eval_results/baselines/
```

### 4.4 `requirements.txt` addition

```
# Eval harness only (app/eval/) — used for confabulation detection lemmatization.
# Not used by any production code path. See docs/phase-8-8-6-step-0-eval-harness-spec.md.
nltk==3.9.2
```

NLTK requires WordNet and tagger corpora downloaded on first run — handled by the detector module's lazy auto-download path.

---

## 5) Test plan

### 5.1 Unit tests

1. `test_confabulation_query_gen`: given a stub catalog of 2 providers + 1 program, generate_probes returns 9 probes with expected templates and row references.
2. `test_confabulation_query_gen_normalize_row_name`: en-dash and em-dash row names match ASCII-hyphen include strings after normalization.
3. `test_confabulation_detector_layer1_advisory`: Layer 1 hits are marked as advisory in the output structure; do not contribute to the rate calculation when consumed by report.
4. `test_confabulation_detector_layer2_anchors`: against the Aqua Beginnings fixture, Layer 2 flags `heated`, `outdoor`, `private`. Against Grace Arts Live, Layer 2 flags `air-conditioned`, `family-friendly`. (These are the regression anchors; Layer 2 is the gating signal that catches them in v1.)
5. `test_confabulation_detector_layer2_evidence_scoping`: wordlist members in a response without row support are flagged; same words present in row description are NOT flagged.
6. `test_confabulation_detector_layer3_invented`: invented hours / prices / capacities / phone numbers flagged; row-supported numbers not flagged.
7. `test_confabulation_detector_layer3_currency_decimal`: `$5` and `$5.00` canonicalize to the same token; `$5.99` flagged when row says `$5`.
8. `test_confabulation_detector_layer3_phone_symmetry`: phone numbers in row content do not produce Layer 3 hits when echoed in response; invented phone numbers do.
9. `test_confabulation_detector_em_dash_split`: em-dash and en-dash split tokens correctly; `small—max` does not become a single token.
10. `test_confabulation_detector_contraction_filter`: `'re`, `n't`, etc. do not appear as content tokens.
11. `test_confabulation_detector_outdoor_normalization`: `outdoor` and `outdoors` collapse to a common form.
12. `test_confabulation_evidence_install_restore`: `install()` replaces `tier2_formatter.format`; `restore()` puts it back; idempotent.
13. `test_confabulation_evidence_exception_safety`: when wrapped `format` raises, ContextVar and buffer reset; subsequent requests don't see leaked evidence.
14. `test_confabulation_evidence_no_install_no_overhead`: when `install()` has not been called, `tier2_formatter.format` is the original — assert by identity.
15. `test_confabulation_evidence_return_passthrough`: wrapper returns the original 3-tuple unchanged for success and failure paths.
16. `test_confabulation_invoker_no_stale_evidence_between_calls`: Tier 2 invocation followed by Tier 1/3 invocation doesn't carry stale evidence.
17. `test_confabulation_report_excludes_tier1_and_tier3`: Tier 1 and Tier 3 runs included in jsonl with `excluded_from_summary: true`; not counted in summary rate.
18. `test_confabulation_report_layer1_advisory_split`: Layer 1 hits reported in advisory section; Layer 2 + Layer 3 in gating section; rate computed from gating only.

### 5.2 Integration tests

1. `test_inprocess_invoker_smoke`: against a 1-provider stub catalog, in-process invoker returns a populated `InvocationResult` with non-empty evidence_set. Verifies the full install → route → read → restore cycle.

### 5.3 Validation gate (for the harness itself)

The harness ships when:

1. Full unit + integration suite passes.
2. HALT 2 dry-run on the 5-provider subset produces a clean report. (Closed 2026-04-25 after G, G1, G2 iterations.)
3. HALT 3 full-sweep report flags both §1.1 regression anchors at >0 Layer 2 + Layer 3 hit rate per (query, flag-state).
4. Full-sweep report produces meaningful signal differentiation: rich-and-well-described rows show substantially lower Layer 2 + Layer 3 rates than confabulation-prone rows. "Meaningful" is owner-judged at HALT 3.
5. Layer 1 advisory output is reported but does not influence the rate-based pass/fail decision. The advisory output is reviewed during 8.8.6 step 1+ planning.

### 5.4 Not a gate this phase

This phase does NOT define a confabulation-rate threshold for shipping a formatter change. That threshold belongs in 8.8.6 step 1+ once we have a measured baseline. The harness produces numbers; 8.8.6 step 1+ decides what "good enough" means.

The threshold will be set against the Layer 2 + Layer 3 rate, not against Layer 1 advisory. Layer 1 advisory output may inform 8.8.6 step 1+ design (e.g., identifying novel confabulation classes that need new Layer 2 wordlist entries) but does not contribute to the threshold.

---

## 6) Risk and rollback

### 6.1 Risks

1. **Layer 1 advisory false-negative class.** Real confabulations that aren't in the Layer 2 wordlist and don't involve numbers won't show up in the rate. Layer 1 advisory captures them in the report but doesn't gate. Mitigation: HALT 1 lexicon governance allows expanding Layer 2 wordlist when Layer 1 advisory surfaces novel confabulation patterns. v2 Layer 5 (LLM judge) is the long-term path to converting Layer 1 advisory output into gating signal.

2. **Detector noise on Layer 1 advisory.** Layer 1's scoped diff produces a long-tail of conversational-scaffolding tokens. This is acknowledged and accepted in v1 — Layer 1 is advisory specifically because the noise is structural, not a calibration gap that can be closed by safe_framing expansion alone. Mitigation: clearly label Layer 1 output as advisory in `summary.md`. Reviewers know to skim the advisory tokens for novel confabulation patterns rather than treating each as an issue.

3. **Detector entrenches today's failure modes.** Layer 2's wordlist captures known patterns. Mitigation: HALT 1 governance allows wordlist growth as Layer 1 advisory surfaces new patterns.

4. **In-process mode masks HTTP-layer behavior.** Mitigated by HTTP mode being available for staging validation. Layer 1 advisory and Layer 2 evidence-scoping are degraded in HTTP mode (§3.5.2 caveat). Document in runbook.

5. **Tier 3 stochasticity makes per-run findings unstable.** Mitigated by N-runs aggregation. Per-(query, flag-state) rate is the unit of analysis, not per-run pass/fail. Tier 3 invocations are excluded from rate calculation in v1 because they have no evidence_set.

6. **Cost creep at bulk-import scale.** Curated catalog is ~24 providers + ~28 programs. v1 sweep is roughly (24+28) × 3 templates × 3 runs × 2 flag states = 936 invocations. Mostly Tier 1/Tier 2 (free) for direct lookups. Estimated <$5 in API cost worst case. Bulk-catalog scale (~4,574 providers post-8.11) requires sampling strategy — out of v1 scope, documented for v2.

7. **Evidence-set capture via monkeypatch.** Resolved at HALT 1 via the harness-only patch in §3.5.1a / §8 #9, with the wrapper signature corrected at HALT 2 to `tuple[Optional[str], int | None, int | None]` and the ContextVar + `_last_captured` buffer combination clarified. The patch:
   - replaces `tier2_formatter.format` only when `install()` is called from `app/eval/confabulation_invoker.py`;
   - uses a `ContextVar` set inside a `try`/`finally` wrapper plus a module-local buffer to bridge the `finally`-reset-vs-invoker-read sequencing;
   - returns the original function's return value unchanged (3-tuple, signature-faithful);
   - has zero overhead when not installed (production paths unaffected);
   - assumes today's synchronous call stack.

8. **Layered detector adds maintenance burden.** Three layers, three lexicons (Layer 2 wordlist, Layer 3 quantity nouns + canonicalizer, Layer 1 safe_framing). Layer 1 advisory designation reduces the maintenance pressure on safe_framing — false positives on Layer 1 are tolerable because they're advisory, not gating. Mitigated by clear lexicon governance (HALT 1) and by Layer 2 + Layer 3 carrying the gating load.

9. **Layer 3 normalization rules mis-canonicalize an edge case.** Required mitigation: §5.1 tests cover the canonical pairs. Owner reviewed canonicalizer rules at HALT 1 and HALT 2 G2; specific decisions captured in §3.5.3 (no guessing on ambiguous 12h, `usd:N` form for currency, minutes as canonical duration scale, `ph:` prefix for phone numbers, etc.).

10. **Evidence dict shape drift.** If `_provider_dict` / `_program_dict` / `_event_dict` change in production over time, the harness's evidence-set construction must follow. Mitigation: evidence extraction reads from the dicts the patched `format` actually receives, not from a separate schema definition. Drift is automatic. Tests assert against current dict shape and will fail if it drifts.

11. **`format` signature drift.** If `tier2_formatter.format` gains new parameters or changes its return shape in production over time, the wrapper signature in §3.5.1a is no longer faithful. Mitigation: §5.1 test 15 asserts the wrapper preserves the current 3-tuple return shape; signature drift will cause that test to fail.

### 6.2 Mitigations summary

- Layered detection with explicit role split (Layer 1 advisory, Layer 2 + Layer 3 gating).
- Layer 3 canonicalization required, not optional, with owner-reviewed rules.
- HALT 1 owner-reviewed lexicons, templates, canonicalizer rules, and resolved hook approach.
- HALT 2 iterative dry-run calibration with G, G1, G2 rounds; final close on Layer 2 + Layer 3 signal differentiation.
- HALT 3 full-sweep review before declaring harness ready for 8.8.6 step 1+.
- N-runs default 3.
- In-process default for full detector fidelity; HTTP opt-in for staging.
- Evidence capture via harness-only monkeypatch in `app/eval/` — zero production touch.

### 6.3 Rollback

- Pure tooling. No production code changed on disk. No prompts, no schema, no router.
- Rollback = revert harness commits + delete result artifacts + drop `.gitignore` and `requirements.txt` entries.
- No dependency on harness from any production code path. Trivial removal if the approach turns out to be wrong.
- The runtime monkeypatch is process-local and self-restoring via `restore()` plus `install()`/`restore()` discipline in the invoker. If the harness process exits unexpectedly without calling `restore()`, the process dies anyway — production processes are unaffected.

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
- `docs/known-issues.md` — note that "Tier 2 formatter rich-row confabulation" is now measured by the harness via Layer 2 + Layer 3 with Layer 1 advisory support, baseline rate captured at HALT 3.
- `docs/pre-launch-checklist.md` — add harness as a pre-launch tool.

Known-issues entries this phase touches (listed for context, not all closed by it):

1. Tier 2 formatter rich-row confabulation — measurement instrument exists post-this-phase; fix lands in 8.8.6 step 1+.
2. Tier 2 formatter sparse-row confabulation — 8.8.5's sparse rule worked in validation; the harness will detect any regression when 8.8.6 step 1+ ports the rule forward.
3. Tier 3 confabulation observations from 8.8.4 validation — Tier 3 excluded from v1 rate; v2 Layer 5 LLM-judge is the path forward.
4. London Bridge Beach class of entity-invention — flagged for v2 detector layer.
5. Aquatic Center selection misses for "kids on a hot day" — separate retrieval concern; harness does not measure retrieval correctness.
6. Catalog data quality: descriptive prose in address fields — surfaced by HALT 2 dry-run on Aqua Beginnings; address says `"Private heated outdoor pool (address at booking)"` which the model faithfully echoes. Input to 8.8.6 step 1+: formatter should not treat address-field prose as facility description.

---

## 8) Resolved decisions (owner-approved at HALT 0, with HALT 1, HALT 2, and HALT 2 dry-run corrections)

All nine open decisions resolved 2026-04-25. Item #2 refined by HALT 2 dry-run finding (Layer 1 advisory). Item #9 corrected by HALT 1 finding; wrapper signature in §3.5.1a corrected by HALT 2-A finding; Layer 1 role corrected by HALT 2 dry-run G2-C finding. See §10.

1. **Phase number:** 8.8.6 step 0. Eval harness is foundation, fix is step 1+.
2. **v1 detector layer set (refined at HALT 2 G2-C):** Layer 1 (per-row scoped extrapolation diff, **advisory**) + Layer 2 (wordlist, **gating**) + Layer 3 (number/quantity invention with canonicalization, **gating**). Layer 4 (entity invention) and Layer 5 (LLM judge) deferred to v2. The advisory/gating split was added after HALT 2 dry-run iterations demonstrated Layer 1's structural noise floor; rate is computed from Layer 2 + Layer 3 only.
3. **v1 catalog scope:** curated Provider + Program rows (current live catalog ≈ 24 providers + 28 programs). Bulk-catalog sweep (Phase 8.11 scale) deferred. Sampling strategy is a separate v2 phase once bulk ingest is closer.
4. **Run mode default:** in-process (required for evidence-set introspection). HTTP opt-in for staging validation.
5. **N runs default:** N=3. Configurable via `--runs`.
6. **Pass/fail gate placement:** NOT in this phase. Threshold defined in 8.8.6 step 1+ informed by the baseline this phase produces. Gate placement is the most disciplined decision in §8 — defining a threshold before measuring would repeat the 8.8.5 mistake. Threshold will be set against Layer 2 + Layer 3 rate; Layer 1 advisory does not gate.
7. **Disposition of `docs/phase-8-8-5-halt5-followup-baseline-verification-and-staging.md`:** kept and committed with a status-update header noting the 8.8.5 rollback. Methodology in §1 of that doc is reusable for any future baseline-verification work.
8. **Probe template lock:** templates in §3.2 confirmed as-is at HALT 1. All six approved without change.
9. **Evidence-set capture (corrected at HALT 1, signature corrected at HALT 2-A, buffer mechanism documented at HALT 2 dry-run):** implemented as a **harness-only monkeypatch** on `app.chat.tier2_formatter.format`, lived entirely in `app/eval/confabulation_evidence.py` and `app/eval/confabulation_invoker.py`. **No production code is modified on disk.** The original spec text named `unified_router.py` as a candidate hook site; HALT 1 found that the router never receives rows — the actual call site is `app/chat/tier2_handler.py`, which is on §4.2's do-not-modify list. The monkeypatch approach satisfies §8 #9's original constraints (logged side-effect only, no signature change, no behavior change, no-op when harness isn't running) more cleanly than any production hook would, and is the resolved approach. **Wrapper signature corrected at HALT 2-A:** `format` returns `tuple[Optional[str], int | None, int | None]`. **Buffer mechanism clarified:** ContextVar plus `_last_captured` module-local buffer; the buffer bridges the `finally`-reset-vs-invoker-read sequencing. Mechanics in §3.5.1a; risk in §6.1.7; tests in §5.1.12–16.

---

## 9) Code-reading references

Authoritative context for HALT 1 / HALT 2 implementation reading. Order reflects priority for the harness-only monkeypatch approach.

- `app/chat/tier2_handler.py` — **the actual formatter call site.** Contains `try_tier2_with_usage` and `try_tier2_with_filters_with_usage`, both of which call `tier2_db_query.query()` then `tier2_formatter.format(query, rows)`. This is where the monkeypatch in §3.5.1a takes effect.
- `app/chat/tier2_formatter.py` — `format(query, rows) -> tuple[Optional[str], int | None, int | None]` signature. The function the harness wraps. **Signature must be preserved by the wrapper exactly** — same call shape, same 3-tuple return shape, return value forwarded unchanged.
- `app/chat/tier2_db_query.py` — `_provider_dict`, `_program_dict`, `_event_dict`, query/merge flow. **Source of evidence dict shape** — harness evidence extraction must follow these dicts exactly per §3.5.1.
- `app/chat/unified_router.py` — entry point for in-process invoker (`unified.route(...)`). Does NOT see rows — the invoker calls `route` after installing the monkeypatch and reads the `_last_captured` buffer populated by the wrapper. Includes `ChatResponse` shape; harness must record `tier_used` for reporting.
- `app/chat/tier3_handler.py` — Tier 3 path; harness must record tier classification (via `ChatResponse.tier_used`, not by reading this module directly). Tier 3 invocations are excluded from confabulation rate calculation in v1.
- `app/db/models.py` — `Provider`, `Program`, `Event` ORM shape. Informational only — evidence extraction reads from `_*_dict` outputs, not from ORM directly.
- `app/api/routes/chat.py` — `/api/chat` endpoint contract for HTTP mode. Implements `POST /api/chat` (not `app/main.py`, which only mounts the router).
- `prompts/tier2_formatter.txt` — current formatter prompt (informational; harness does not change it).
- `docs/phase-8-8-5-formatter-grounding-spec-v2.md` — the spec that failed; lineage and rationale.
- `docs/phase-8-8-5-halt5-followup-baseline-verification-and-staging.md` — baseline-verification methodology, reusable for any future phase that needs to confirm a test failure is pre-existing.
- `docs/persona-brief.md` §6.7 — voice spec the harness measures against (factually-descriptive at per-provider level for bulk; firsthand at landscape level).

---

## 10) Amendment changelog

### 2026-04-25 — HALT 2 dry-run amendment (Layer 1 redefined as advisory)

**What HALT 2 dry-run iterations found:** Across three calibration rounds (G, G1, G2), Layer 1's per-row scoped diff produced a long-tail of conversational-scaffolding false positives. Each round's safe_framing expansion silenced the top 10 offenders only to surface the next 10. Top tokens after the v3 final rerun included `cost, enrollment, row, dodgeball, daily, facility, theater, day, small-group, heated, 90-minute, week, search, handle, program, outdoor, session, catalog, lesson, track` — a mix of regression-anchor confabulation (`heated, outdoor, enrollment`) and conversational scaffolding the safe_framing list could not absorb without bleeding into real confabulation territory.

**Why this is a structural finding, not a calibration gap:** The model's vocabulary for constructing sentences is much larger than any safe_framing list can be without absorbing real confabulation territory. The pattern of "fix the top 10, see the next 10 emerge" is structural — Layer 1's premise (response tokens minus evidence tokens = candidate confabulation) is correct, but the floor of conversational scaffolding tokens is high enough that Layer 1 cannot serve as a primary metric. Layer 2 (wordlist) and Layer 3 (canonicalized numbers) produce clean signal and capture the regression anchors.

**What's now resolved:** Layer 1 is redefined as **advisory** in v1. It runs and is reported, but does not contribute to the headline confabulation rate. The rate is computed from Layer 2 + Layer 3 hits only. Layer 1's output is reported in `summary.md` under a separate "Layer 1 candidate tokens (advisory)" section and serves as a candidate-token surface for human review during 8.8.6 step 1+. Real value preserved (the regression-anchor `private heated outdoor` still appears in Layer 1 advisory alongside being flagged by Layer 2); structural noise no longer gates the confabulation rate.

**Sections updated by this amendment:**
- Status header — third amendment date noted.
- §2.1 goal 1 + 6 — rate metric clarified as Layer 2 + Layer 3; regression-anchor detection requires "at least one of Layer 2, Layer 3, or Layer 1 advisory."
- §2.2 — non-goal added: Layer 1 not a gating signal in v1.
- §3.3 — Layer 1 advisory unavailable in HTTP mode noted.
- §3.5 — opening paragraph rewritten to introduce the gating-vs-advisory split with rationale lineage.
- §3.5.1 — Layer 1 marked ADVISORY; description of role; phone-number-stripping mention added (defense for §3.5.1's response/evidence symmetry).
- §3.5.2 — Layer 2 marked GATING; `enrollment, RSVP` added to procedural wordlist.
- §3.5.3 — Layer 3 marked GATING; phone-number `ph:` rule added to canonicalizer; price-range $-required guard added; currency decimal handling clarified.
- §3.5.4 — note added that Layer 5 (LLM judge) is the most likely v2 path to gating Layer 1's advisory output.
- §3.6 — reporting changed: `runs.jsonl` splits hits into `layer_2_hits`, `layer_3_hits`, `layer_1_advisory_tokens`. `summary.md` adds explicit Layer 1 advisory section clearly labeled. `per_row.csv` columns updated to reflect gating vs advisory split.
- §3.7 HALT 2 — marked closed; iterations G, G1, G2 documented; amendments lineage noted.
- §4.1 file 6 description — Layer 1 hits emitted as advisory only.
- §4.1 file 7 description — summary computes rate from gating hits only.
- §4.1 file 14 (runbook) — explicit note about Layer 1 advisory designation.
- §5.1 — tests reorganized: test 3 now `test_confabulation_detector_layer1_advisory` asserting Layer 1 is advisory; test 4 covers Layer 2 anchors (the gating workhorse); tests 7-11 expanded for HALT 2 detector defect fixes.
- §5.3 validation gate — gate criteria 3 and 4 reference Layer 2 + Layer 3 specifically; gate criterion 5 added for Layer 1 advisory reporting.
- §5.4 — clarified that the 8.8.6 step 1+ threshold will be set against Layer 2 + Layer 3, not Layer 1 advisory.
- §6.1 — risk 1 rewritten: Layer 1 advisory false-negative class. Risk 2 updated: Layer 1 advisory noise is acknowledged structural floor. Risk 8 updated: maintenance burden lower because Layer 1 is advisory.
- §6.2 — mitigations summary updated to mention the gating-vs-advisory role split.
- §7 — known-issues entry 6 added: catalog data quality (Aqua Beginnings address-field prose surfaced by HALT 2 dry-run).
- §8 #2 — refined to reflect the advisory/gating split.
- §8 #9 — buffer mechanism mention clarified.

**HALT 2 was the right phase to catch this.** A 5-row dry-run with three iterative calibration rounds surfaced the structural noise floor before HALT 3 full-sweep poisoned a 156-invocation baseline with Layer 1 noise. Catching it at HALT 2 cost a spec amendment plus iterative detector fixes. Catching it at HALT 3 would have meant rebuilding the baseline.

### 2026-04-25 — HALT 2 amendment (§3.5.1a wrapper signature correction)

**What was wrong:** §3.5.1a's wrapper-signature description said `tier2_formatter.format` has the signature `(query, rows) -> str | None`. This was wrong.

**What HALT 2 found:** Cursor's pre-implementation read pass of `app/chat/tier2_formatter.py` showed the actual signature is `def format(query: str, rows: List[Dict[str, Any]]) -> tuple[Optional[str], int | None, int | None]`. The 3-tuple is `(text, input_tokens, output_tokens)`.

**What's now resolved:** §3.5.1a wrapper-signature description corrected to the actual 3-tuple. The wrapper's contract is now: preserve the call shape `(query, rows)` exactly; preserve the return shape `tuple[Optional[str], int | None, int | None]` exactly; return the original function's value unchanged. New test `test_confabulation_evidence_return_passthrough` added to assert the wrapper's return-value forwarding contract.

### 2026-04-25 — HALT 1 amendment (§8 #9 formatter call-site correction)

**What was wrong:** The original §8 #9 named `app/chat/unified_router.py` as the candidate hook site. This was based on a wrong assumption about where the formatter call site lives.

**What HALT 1 found:** Cursor's read pass of `unified_router.py` showed that the router never receives rows from Tier 2. The router calls into `tier2_handler.py`, which calls `tier2_db_query.query()` to get rows, then calls `tier2_formatter.format(query, rows)`. By the time control returns to the router, rows are gone (locals in `tier2_handler`).

**What's now resolved:** Evidence-set capture is implemented as a **harness-only monkeypatch** on `app.chat.tier2_formatter.format`. All hook code lives in `app/eval/confabulation_evidence.py` and `app/eval/confabulation_invoker.py`. No production code is modified on disk.

---

## End of spec
