# Phase 8.8.6 step 0 — Confabulation Eval Harness Spec

Status: HALT 0 closed (2026-04-25). HALT 1 amendment applied (2026-04-25) — see §10.
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

Templates locked at HALT 1. `<n>` substitution uses the row's display name verbatim. No fuzzing in v1.

### 3.3 Run mode

**Default: in-process.** The runner imports the unified router and calls it directly with each probe. It captures both the assistant response *and* the full set of rows the formatter received for that turn (`evidence_set`) via a harness-only monkeypatch on `app.chat.tier2_formatter.format` (see §3.5.1a and §8 #9). In-process is the default because (a) row-level introspection is required for the primary detection layer (§3.5.1), and (b) it removes network and deploy latency from the loop.

**Opt-in: HTTP mode** (`--mode=http --base-url=<url>`). For staging validation. The monkeypatch is not installed in HTTP mode (it's a different process). HTTP mode therefore skips evidence-set introspection and falls back to wordlist + number-invention layers only (degraded detection — see §3.5.2 caveat). Documented; not the default path.

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

1. Capture the `evidence_set` = union of all content tokens from every row the formatter received on that turn. Evidence dict shape **must** match `tier2_db_query._provider_dict` / `_program_dict` / `_event_dict` exactly — do not inflate the dicts with ORM fields the formatter never saw (notably do not add `featured_description` or `website` to provider evidence unless the underlying `_provider_dict` already includes them). The evidence set must reflect what the model actually had, not what was theoretically available.

   Token extraction: union of content tokens from each dict's keys named `name`, `description`, `category` / `activity_category`, `address`, `phone`, `hours`, `website` (if present in the dict), `schedule`, `cost`. Tokens normalized: lowercased, lemmatized, stripped of punctuation.

2. Tokenize the response. Filter to content words via a stoplist + POS tag (NOUN / ADJ / VERB excluding generic verbs). Numbers handled by Layer 3.

3. Subtract: `response_content_tokens − evidence_set_tokens − safe_framing_vocabulary`.

4. Any remainder is a candidate hit. Each hit records the token, its sentence-of-occurrence in the response, and the row IDs in scope.

`safe_framing_vocabulary` is a curated list of generic concierge-voice tokens that appear in responses but aren't confabulation: concierge framing verbs, evaluative tone words, place / venue generics, hedges, regional aliases. v1 is unigrams only — multi-word handling deferred to v2. Function words are excluded by the POS filter, not by safe_framing. Owner-reviewed at HALT 1.

This layer is the workhorse. It catches `private`, `heated`, `outdoor`, `air-conditioned`, `family-friendly` against Aqua Beginnings / Grace Arts Live evidence sets — and equally catches future confabulation in vocabulary we haven't yet seen.

##### 3.5.1a Evidence-set capture mechanism

Evidence-set capture is implemented as a **harness-only monkeypatch** on `app.chat.tier2_formatter.format`. Mechanics:

- `app/eval/confabulation_evidence.py` defines a module-level `contextvars.ContextVar` named `tier2_evidence`.
- `app/eval/confabulation_invoker.py`, before calling `unified.route(...)`, calls `install()` which replaces `tier2_formatter.format` with a wrapper that:
  1. sets the ContextVar to `(query, [dict(r) for r in rows])` (defensive copy);
  2. calls the original `format(query, rows)`;
  3. resets the ContextVar in `finally` regardless of return value or exception.
- After the route call returns, the invoker reads the ContextVar to construct the evidence_set, then calls `restore()` which puts the original `format` back.

Constraints baked into this mechanism (cross-reference §8 #9):

- **No production code touched.** All hook code lives in `app/eval/`. The do-not-modify list in §4.2 is fully respected.
- **No signature change** to `tier2_formatter.format`. The wrapper has the same `(query, rows) -> str | None` shape.
- **No `ChatResponse` change.** Evidence is harness-side only.
- **Zero production overhead** when harness is not running. The patch is not installed unless `app/eval/confabulation_invoker.py` calls `install()`.
- **`try`/`finally`** ensures evidence does not stick to a later request, even if `format` raises.
- **ContextVar** is the right choice for today's synchronous call stack. If `tier2_handler` is ever moved to a thread pool or async scheduler, the wrapper must be revisited — documented as a known assumption in the runbook, not a TODO.

The architecture finding that drove this decision: `unified_router.py` is *not* the formatter call site. The actual call site is `app/chat/tier2_handler.py`, which calls `tier2_db_query.query()` then `tier2_formatter.format(query, rows)`. The router only sees the string output and token tallies. By the time control returns to the router, rows are gone (they were locals in `tier2_handler`). HALT 1 surfaced this; the resolution is the harness-only monkeypatch above. See §10 amendment changelog and §8 #9 for the resolved approach.

#### 3.5.2 Layer 2 — Curated extrapolation wordlist (SECONDARY)

Cheap regression check. A literal wordlist of known confabulation vocabulary, scoped to category-extrapolation patterns:

- Facility / amenity invention: `heated, indoor, outdoor, private, air-conditioned, climate-controlled, shaded, covered`
- Audience-fit invention: `family-friendly, kid-friendly, kid-appropriate, romantic, upscale, casual, cozy, intimate, quiet, lively`
- Procedural invention: `book directly, reservation required, walk-ins welcome, no reservations`

For each hit, we flag any wordlist member appearing in the response but not in the evidence set. Owner-reviewed and locked at HALT 1; allowed to grow during operation as new patterns surface, similar to the implementation-lexicon governance from 8.8.5 §3.1.3.

This layer is partially redundant with Layer 1 by design — it gives us a clean per-pattern frequency report (which extrapolation words confabulate most often) that Layer 1's diff doesn't produce as cleanly.

**HTTP mode caveat:** Layer 2 in HTTP mode runs without an evidence set (the monkeypatch isn't available across process boundaries). It can still flag wordlist-member appearances in responses, but it cannot tell whether the row actually contained the word. Words like `pool, deck, patio, studio` are legitimate row content for some providers; in HTTP mode Layer 2 will flag them unconditionally, producing high false-positive rates. HTTP mode hits are a degraded signal, not a comparable one. Document in the runbook.

#### 3.5.3 Layer 3 — Number / quantity invention (SECONDARY)

For each turn:

1. Extract digit sequences and quantity nouns (`several, multiple, dozen, dozens, handful, few, many, most, a couple, couple, numerous, various, some, couple of, a few, majority, minority`) from both the response and the evidence set. (`bunch, tons, loads` deferred to v1.1 unless pilot shows they're needed.)

2. **Normalize before diff.** Both sides are passed through a canonicalizer. Required rules:

   - **Currency:** strip currency symbols. Map `free`, `no charge`, `no cost`, `$0`, `$0.00` all to canonical `price:0`. Use the prefixed `price:0` form (not bare `0`) to avoid collision with non-price `0` tokens elsewhere. Apply to both sides.

   - **Time:** normalize 24h forms and AM/PM-disambiguated 12h forms to canonical `HH:MM`. **For ambiguous 12h-without-AM/PM, do NOT guess** — keep as a tagged unresolved token and exclude from Layer 3 diff. Layer 1's content-word diff catches actually-invented time strings indirectly via context. False negatives strongly preferred to false positives here.

   - **Duration:** canonical scale is **minutes**. `1 hr` / `1 hour` → `60min`. `90-minute`, `90 min`, `90 minutes` → `90min`. Apply consistently.

   - **Day of week:** v1 keeps `weekday` and `weekend` as separate tokens, no mapping to specific days. Days themselves normalized: `mon|monday|m` → `monday`, etc. Revisit weekday/weekend mapping in v1.1 if pilot shows false diffs.

   - **Price ranges:** strip `$`, `ea`, `each`, `approx`, `~`, `about` before extraction. `$10-15`, `$10–15`, `$10 to $15`, `10 to 15 dollars` all → `10-15`. `under $20` → `<=20`. Note: v1 diff structure does not fully handle inequality semantics — if evidence says `<=20` and response says `$15`, they won't match (a technical false positive). Accept as v1 limitation; revisit if it bites in practice.

3. Diff response canonical-numbers against evidence-set canonical-numbers. Any remainder is a candidate hit.

The normalization step is required, not optional. Without it, the layer produces high false-positive rates on every catalog row that lists hours, prices, or schedule durations in formats the response then re-renders. Canonicalizer rules are owner-reviewed at HALT 1 alongside the lexicons.

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

- **HALT 1 — pre-implementation lexicon, template, and hook review.** Status: **closed 2026-04-25.** Owner reviewed and approved: (a) per-row probe template list (§3.2), (b) safe_framing_vocabulary stoplist scope (§3.5.1, with v1-unigrams-only constraint), (c) Layer 2 wordlist (§3.5.2), (d) Layer 3 quantity-noun list and canonicalizer rules (§3.5.3). Lexicon governance follows 8.8.5 §3.1.3 model: conceptual classes locked, literal lists implementation-owned and may evolve post-deploy with owner review. **HALT 1 also surfaced the formatter call-site location finding that drove this spec's amendment** — `unified_router.py` does not see rows; the actual call site is `tier2_handler.py`. The resolved approach is a harness-only monkeypatch in `app/eval/`, not any production touch. See §3.5.1a, §8 #9, and §10. Final lexicons land in a `relay/halt1-closure-final-lexicons.md` artifact for implementation reference, not as a doc commit.

- **HALT 2 — dry-run on 5-provider subset.** Before full-catalog sweep, run the harness against a hand-picked 5-provider subset that includes both regression anchors (Aqua Beginnings, Grace Arts Live) and at least three rows that should produce zero hits (a rich, well-described provider; a sparse provider that gets handled correctly today). Owner reviews report shape and detector calibration.

- **HALT 3 — first full-sweep report.** Owner reviews the full-catalog baseline before harness is declared 8.8.6-ready. Confirms the detector signal is signal, not noise. May trigger lexicon adjustments under HALT 1's governance rule.

---

## 4) Implementation file list

### 4.1 Files to create

1. `scripts/confabulation_eval.py` — CLI runner. Flags: `--mode={inprocess,http}`, `--runs N`, `--flags={off,on,both}`, `--rows={providers,programs,both}`, `--output-dir`, `--limit` (for HALT 2 subset), `--include` / `--exclude` (row filters).
2. `app/eval/__init__.py`
3. `app/eval/confabulation_query_gen.py` — `generate_probes(session) -> list[Probe]`. Returns one Probe per (row, template). Probe carries query text, row reference, template id.
4. `app/eval/confabulation_evidence.py` — `tier2_evidence` ContextVar; `install()` and `restore()` helpers for the monkeypatch on `tier2_formatter.format`.
5. `app/eval/confabulation_invoker.py` — `invoke(probe, flag_state) -> InvocationResult`. Two implementations behind a strategy interface: `InProcessInvoker` (calls `install()` before `unified.route`, reads ContextVar after, calls `restore()`) and `HttpInvoker` (no monkeypatch; degraded detection). Returns `InvocationResult(response_text, evidence_set, tier_used, latency_ms, raw_log)`.
6. `app/eval/confabulation_detector.py` — `detect(invocation_result) -> list[DetectorHit]`. Hits carry layer, token, sentence_index, row_ids_in_scope. Includes the Layer 3 canonicalizer per §3.5.3.
7. `app/eval/confabulation_report.py` — `write_jsonl`, `write_summary_md`, `write_per_row_csv`.
8. `tests/test_confabulation_query_gen.py`
9. `tests/test_confabulation_detector.py` — fixture cases for §1.1 anchors plus negative fixtures (clean responses) plus Layer 3 normalization fixtures.
10. `tests/test_confabulation_invoker.py` — in-process invoker integration test against a 1-provider stub catalog.
11. `tests/test_confabulation_evidence.py` — verify install/restore correctness, ContextVar reset on exception, no leakage between requests.
12. `docs/confabulation-eval-runbook.md` — operator guide. Covers: how to invoke, how to read each artifact, how to interpret hits, how to expand lexicons under HALT 1 governance, the threading/async caveat from §3.5.1a, the HTTP-mode degraded-Layer-2 caveat from §3.5.2, the v1 inequality-semantics limitation from §3.5.3.

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

---

## 5) Test plan

### 5.1 Unit tests

1. `test_confabulation_query_gen`: given a stub catalog of 2 providers + 1 program, generate_probes returns 9 probes with expected templates and row references.
2. `test_confabulation_detector_layer1`: against the Aqua Beginnings fixture (row + confabulated response), Layer 1 flags `private`, `heated`, `outdoor`. Against a clean Aqua Beginnings response that stays within the row, Layer 1 flags nothing.
3. `test_confabulation_detector_layer2`: wordlist members in a response without row support are flagged; same words present in row description are NOT flagged.
4. `test_confabulation_detector_layer3_invented`: invented hours / prices / capacities flagged; row-supported numbers not flagged.
5. `test_confabulation_detector_layer3_normalization`: `"$19"` in response matches `"19"` in row (no hit); `"8am"` matches `"8:00 AM"` (no hit, when AM/PM is unambiguous on both sides); `"90-minute"` matches `"90 min"` (no hit); `"Mon"` matches `"Monday"` (no hit); `"free"` matches `"$0"` (no hit, both → `price:0`). Negative side: `"$25"` in response when row says `"$19"` IS flagged. Ambiguous 12h side: `"8"` in response with no AM/PM context produces a tagged unresolved token, not a Layer 3 hit.
6. `test_confabulation_detector_safe_framing`: tokens in the safe_framing_vocabulary stoplist do not produce Layer 1 hits even when not in the evidence set.
7. `test_confabulation_detector_grace_arts_live`: the multi-row evidence-set scoping works — `youth theatre` is NOT flagged when an associated Event row in the evidence set contains it; `air-conditioned` IS flagged.
8. `test_confabulation_evidence_install_restore`: `install()` replaces `tier2_formatter.format`; `restore()` puts it back; double-install or double-restore are safe (idempotent or clearly errored, document chosen behavior).
9. `test_confabulation_evidence_exception_safety`: when the wrapped `format` raises, the ContextVar is reset and subsequent requests do not see leaked evidence.
10. `test_confabulation_evidence_no_install_no_overhead`: when `install()` has not been called, `tier2_formatter.format` is the original function — assert by identity.
11. `test_confabulation_report`: JSONL / MD / CSV emission produces parseable artifacts.

### 5.2 Integration tests

1. `test_inprocess_invoker_smoke`: against a 1-provider stub catalog, in-process invoker returns a populated `InvocationResult` with non-empty evidence_set. Verifies the full install → route → read → restore cycle.

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

3. **In-process mode masks HTTP-layer behavior.** Mitigated by HTTP mode being available for staging validation. Does not affect detector correctness, but Layer 2 is degraded in HTTP mode (§3.5.2 caveat). Document in runbook.

4. **Tier 3 stochasticity makes per-run findings unstable.** Mitigated by N-runs aggregation. Per-(query, flag-state) rate is the unit of analysis, not per-run pass/fail.

5. **Cost creep at bulk-import scale.** Curated catalog is ~24 providers + ~28 programs. v1 sweep is (24+28) × 3 templates × 3 runs × 2 flag states = 936 invocations. Mostly Tier 1/Tier 2 (free) for direct lookups. Estimated <$5 in API cost worst case. Bulk-catalog scale (~4,574 providers post-8.11) requires sampling strategy — out of v1 scope, documented for v2.

6. **Evidence-set capture via monkeypatch.** Resolved at HALT 1 via the harness-only patch in §3.5.1a / §8 #9. The patch:
   - replaces `tier2_formatter.format` only when `install()` is called from `app/eval/confabulation_invoker.py`;
   - uses a `ContextVar` set inside a `try`/`finally` wrapper so evidence does not leak across requests if `format` raises;
   - has zero overhead when not installed (production paths unaffected);
   - assumes today's synchronous call stack — if Tier 2 is ever moved to a thread pool or async scheduler, the wrapper must be revisited (documented in runbook, not a TODO).

7. **Layered detector adds maintenance burden.** Three layers, three lexicons, three sets of edge cases, plus the Layer 3 canonicalizer rules. Mitigated by clear lexicon governance (HALT 1) and by Layer 1 carrying most of the load.

8. **Layer 3 normalization rules mis-canonicalize an edge case.** Required mitigation: §5.1 test 5 covers the canonical pairs. Owner reviewed canonicalizer rules at HALT 1; specific decisions captured in §3.5.3 (no guessing on ambiguous 12h, `price:0` prefix, minutes as canonical duration scale, etc.).

9. **Evidence dict shape drift.** If `_provider_dict` / `_program_dict` / `_event_dict` change in production over time, the harness's evidence-set construction must follow. Mitigation: evidence extraction reads from the dicts the patched `format` actually receives, not from a separate schema definition. Drift is automatic. Tests assert against current dict shape and will fail if it drifts.

### 6.2 Mitigations summary

- Layered detection (Layer 1 primary, generalizes; Layers 2/3 secondary, regression coverage).
- Layer 3 canonicalization required, not optional, with owner-reviewed rules.
- HALT 1 owner-reviewed lexicons, templates, canonicalizer rules, and resolved hook approach (§8 #9).
- HALT 2 dry-run sanity check.
- HALT 3 full-sweep review before declaring harness ready for 8.8.6 step 1+.
- N-runs default 3.
- In-process default for full detector fidelity; HTTP opt-in for staging.
- Evidence capture via harness-only monkeypatch in `app/eval/` — zero production touch.

### 6.3 Rollback

- Pure tooling. No production code changed on disk. No prompts, no schema, no router.
- Rollback = revert harness commits + delete result artifacts + drop `.gitignore` entries.
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
- `docs/known-issues.md` — note that "Tier 2 formatter rich-row confabulation" is now measured by the harness, with a baseline rate captured at HALT 3.
- `docs/pre-launch-checklist.md` — add harness as a pre-launch tool.

Known-issues entries this phase touches (listed for context, not all closed by it):

1. Tier 2 formatter rich-row confabulation — measurement instrument exists post-this-phase; fix lands in 8.8.6 step 1+.
2. Tier 2 formatter sparse-row confabulation — 8.8.5's sparse rule worked in validation; the harness will detect any regression when 8.8.6 step 1+ ports the rule forward.
3. Tier 3 confabulation observations from 8.8.4 validation — harness measures these too; remediation deferred per prior decision.
4. London Bridge Beach class of entity-invention — flagged for v2 detector layer.
5. Aquatic Center selection misses for "kids on a hot day" — separate retrieval concern; harness does not measure retrieval correctness.

---

## 8) Resolved decisions (owner-approved at HALT 0, with HALT 1 corrections)

All nine open decisions resolved 2026-04-25. Item #9 corrected by HALT 1 finding (see §10).

1. **Phase number:** 8.8.6 step 0. Eval harness is foundation, fix is step 1+.
2. **v1 detector layer set:** Layer 1 (per-row scoped extrapolation diff, primary) + Layer 2 (wordlist, secondary) + Layer 3 (number/quantity invention with canonicalization, secondary). Layer 4 (entity invention) and Layer 5 (LLM judge) deferred to v2.
3. **v1 catalog scope:** curated Provider + Program rows (current live catalog ≈ 24 providers + 28 programs). Bulk-catalog sweep (Phase 8.11 scale) deferred. Sampling strategy is a separate v2 phase once bulk ingest is closer.
4. **Run mode default:** in-process (required for evidence-set introspection). HTTP opt-in for staging validation.
5. **N runs default:** N=3. Configurable via `--runs`.
6. **Pass/fail gate placement:** NOT in this phase. Threshold defined in 8.8.6 step 1+ informed by the baseline this phase produces. Gate placement is the most disciplined decision in §8 — defining a threshold before measuring would repeat the 8.8.5 mistake.
7. **Disposition of `docs/phase-8-8-5-halt5-followup-baseline-verification-and-staging.md`:** kept and committed with a status-update header noting the 8.8.5 rollback. Methodology in §1 of that doc is reusable for any future baseline-verification work.
8. **Probe template lock:** templates in §3.2 confirmed as-is at HALT 1. All six approved without change.
9. **Evidence-set capture (corrected at HALT 1):** implemented as a **harness-only monkeypatch** on `app.chat.tier2_formatter.format`, lived entirely in `app/eval/confabulation_evidence.py` and `app/eval/confabulation_invoker.py`. **No production code is modified on disk.** The original spec text named `unified_router.py` as a candidate hook site; HALT 1 found that the router never receives rows — the actual call site is `app/chat/tier2_handler.py`, which is on §4.2's do-not-modify list. The monkeypatch approach satisfies §8 #9's original constraints (logged side-effect only, no signature change, no behavior change, no-op when harness isn't running) more cleanly than any production hook would, and is the resolved approach. Mechanics are in §3.5.1a; risk in §6.1.6; tests in §5.1.8–10.

---

## 9) Code-reading references

Authoritative context for HALT 1 implementation reading. Order reflects priority for the harness-only monkeypatch approach.

- `app/chat/tier2_handler.py` — **the actual formatter call site.** Contains `try_tier2_with_usage` and `try_tier2_with_filters_with_usage`, both of which call `tier2_db_query.query()` then `tier2_formatter.format(query, rows)`. This is where the monkeypatch in §3.5.1a takes effect.
- `app/chat/tier2_formatter.py` — `format(query, rows)` signature. The function the harness wraps. Signature must be preserved by the wrapper.
- `app/chat/tier2_db_query.py` — `_provider_dict`, `_program_dict`, `_event_dict`, query/merge flow. **Source of evidence dict shape** — harness evidence extraction must follow these dicts exactly per §3.5.1.
- `app/chat/unified_router.py` — entry point for in-process invoker (`unified.route(...)`). Does NOT see rows — the invoker calls `route` after installing the monkeypatch and reads the ContextVar populated by the wrapper. Includes `ChatResponse` shape; harness must record `tier_used` for reporting.
- `app/chat/tier3_handler.py` — Tier 3 path; harness must record tier classification (via `ChatResponse.tier_used`, not by reading this module directly).
- `app/db/models.py` — `Provider`, `Program`, `Event` ORM shape. Informational only — evidence extraction reads from `_*_dict` outputs, not from ORM directly.
- `app/api/routes/chat.py` — `/api/chat` endpoint contract for HTTP mode. Implements `POST /api/chat` (not `app/main.py`, which only mounts the router).
- `prompts/tier2_formatter.txt` — current formatter prompt (informational; harness does not change it).
- `docs/phase-8-8-5-formatter-grounding-spec-v2.md` — the spec that failed; lineage and rationale.
- `docs/phase-8-8-5-halt5-followup-baseline-verification-and-staging.md` — baseline-verification methodology, reusable for any future phase that needs to confirm a test failure is pre-existing.
- `docs/persona-brief.md` §6.7 — voice spec the harness measures against (factually-descriptive at per-provider level for bulk; firsthand at landscape level).

---

## 10) Amendment changelog

### 2026-04-25 — HALT 1 amendment (§8 #9 formatter call-site correction)

**What was wrong:** The original §8 #9 (resolved at HALT 0) named `app/chat/unified_router.py` as the candidate hook site if evidence-set introspection required a production touch. This was based on a wrong assumption about where the formatter call site lives.

**What HALT 1 found:** Cursor's read pass of `unified_router.py` showed that the router never receives rows from Tier 2. The router calls into `tier2_handler.py`, which calls `tier2_db_query.query()` to get rows, then calls `tier2_formatter.format(query, rows)`. By the time control returns to the router, rows are gone (locals in `tier2_handler`). `unified_router.py` therefore cannot be a hook site without re-querying the DB (which would diverge from what the formatter actually saw) or threading new parameters through the call stack (which the §4.2 do-not-modify constraint forbids).

**What's now resolved:** Evidence-set capture is implemented as a **harness-only monkeypatch** on `app.chat.tier2_formatter.format`. All hook code lives in `app/eval/confabulation_evidence.py` and `app/eval/confabulation_invoker.py`. No production code is modified on disk. The patch is installed before each in-process eval invocation and restored after, with a `ContextVar` populated inside a `try`/`finally` wrapper to ensure clean state across requests and across exceptions.

**Sections updated by this amendment:**
- §3.1 — added `app/eval/confabulation_evidence.py` to the architecture file list.
- §3.3 — clarified that in-process mode installs the monkeypatch; HTTP mode does not (different process).
- §3.5.1 — evidence dict shape rule: must match `_provider_dict` / `_program_dict` / `_event_dict` exactly, no ORM inflation. Token extraction key list explicit.
- §3.5.1a — new subsection: full mechanics of the harness-only monkeypatch (install/restore, ContextVar, try/finally, constraints satisfied).
- §3.5.2 — HTTP mode degraded-Layer-2 caveat documented.
- §3.5.3 — canonicalizer rules tightened with HALT 1 specifics: `price:0` prefix, no guessing on ambiguous 12h, minutes as canonical duration scale, weekday/weekend kept separate in v1, inequality semantics flagged as v1 limitation.
- §3.7 HALT 1 — marked closed; note that final lexicons land in `relay/halt1-closure-final-lexicons.md` (not a doc commit).
- §4.1 — added `app/eval/confabulation_evidence.py` and `tests/test_confabulation_evidence.py`. Updated invoker description to reference install/restore cycle.
- §4.2 — `tier2_handler.py` highlighted as load-bearing for §8 #9 (intentionally do-not-modify in favor of the monkeypatch). `tier2_formatter.py` clarified as runtime-patched, not on-disk modified.
- §5.1 — added tests 8/9/10 for install/restore correctness, exception safety, and no-install-no-overhead.
- §6.1.6 — risk text rewritten to describe the monkeypatch mechanics, not a production hook.
- §6.1.9 — new risk: evidence dict shape drift; auto-mitigated by extraction following the patched function's actual inputs.
- §6.3 — rollback updated: process-local monkeypatch is self-restoring; production processes unaffected even if harness crashes.
- §8 #9 — full rewrite to reflect the resolved approach with HALT 1 lineage.
- §9 — code-reading references re-prioritized: `tier2_handler.py` is now first, with explicit note that it's the actual call site. `unified_router.py` retained but with note that it does not see rows.

**No content was removed** beyond the wrong-target hook references in the original §8 #9 and the cross-references that named `unified_router.py` as the candidate hook site. The revised text replaces those references in place.

**HALT 1 was the right phase to catch this.** Pre-implementation read passes are exactly the kind of HALT designed to surface "the spec is built on a wrong assumption about the code." Catching it at HALT 1 cost a small spec amendment. Catching it during implementation would have cost wasted work on an unworkable hook.

---

## End of spec
