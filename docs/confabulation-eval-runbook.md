# Confabulation Eval Runbook (v1)

## Purpose

Run the Phase 8.8.6 step 0 harness, inspect confabulation signals, and compare per-row behavior before formatter changes.

## How To Run

### In-process (default, full detector fidelity)

```bash
python scripts/confabulation_eval.py \
  --mode=inprocess \
  --runs=3 \
  --flags=both \
  --rows=both \
  --output-dir=scripts/confabulation_eval_results/<name>
```

### HTTP mode (degraded detector)

```bash
python scripts/confabulation_eval.py \
  --mode=http \
  --base-url=http://127.0.0.1:8000 \
  --runs=3 \
  --flags=both \
  --rows=both
```

### Row filtering

- `--include="Aqua Beginnings,Grace Arts Live"`: only listed names
- `--exclude="..."`: remove listed names
- `--limit=N`: cap probes after filtering

**Display name normalization:** `--include` / `--exclude` matching is case-insensitive and treats **en dash (U+2013)** and **em dash (U+2014)** in catalog titles as **ASCII hyphen** for comparison. You can paste names from the CLI with plain hyphens even when the database uses typographic dashes (for example, `Open Jump - 90 Minutes` matches `Open Jump – 90 Minutes` in the programs table).

### v1 summary inclusion policy (Tier 1 + Tier 3) and gating vs advisory

- **Headline confabulation rate** uses **Layer 2 + Layer 3 (gating)** on Tier 2, and **Layer 2** on Tier 3 when Layer 2 fires (partial inclusion; spec §3.5.2). **`hit_count` / `gating_hit_count`** in `runs.jsonl` count gating hits, not Layer 1.
- **Layer 1** is **advisory** (per-row lemma diff; see spec §3.5.1): it still runs and is reported as **Layer 1 candidate tokens** for human review during 8.8.6 step 1+ planning, but it **does not** contribute to the headline rate, top-gating-token tables, or offender row ranking.
- **`summary.md` gating-rate denominator:** Tier **2** always; Tier **3** only when there is at least one **Layer 2** hit on that run (Layer 3 has no evidence set in v1, so Layer 1 and Layer 3 do not apply the same way as Tier 2).
- **Tier 1** runs stay in `runs.jsonl` but are **excluded** from gating summaries (`excluded_reason`: `tier_1_no_formatter`).
- **Tier 3** runs with **no** Layer 2 hits are **excluded** from the headline (`excluded_reason`: `tier_3_no_layer2_hits`). Tier 3 runs **with** Layer 2 hits are **included** so wordlist confabulation is not dropped from the rate.
- **Future (v2):** Tier 3 confabulation measurement is a candidate for **Layer 5 LLM-judge** (spec §3.5.4).

## Artifacts

Each run writes into an output directory:

- `runs.jsonl`: per run: probe, response, evidence rows, **split hits** (`layer_1_advisory_hits`, `layer_2_hits`, `layer_3_hits`, `layer_1_advisory_tokens`), **`gating_hit_count`**, `advisory_hit_count`, latency, tier, exclusion flags.
- `summary.md`: **gating** rate by flag, top offenders (by gating), **top gating tokens (L2+L3)**, separate **Layer 1 advisory** token section, tier split, regression anchors (gating only).
- `per_row.csv`: `row_id`, `row_name`, `total_runs`, `included_runs`, `gating_runs_with_hit`, `advisory_token_count`, `top_3_gating_tokens`.

## Reading Results

- Start with `summary.md` for overall rates and top rows.
- Use `per_row.csv` to identify rows with repeated hits.
- Use `runs.jsonl` to inspect exact responses/evidence/hits for a flagged row.

## Interpreting Hits

- **Layer 1 (advisory):** candidate tokens (lemmas) in the response not supported by evidence lemmas and not in safe framing—**for review**, not for the headline rate.
- **Layer 2 (gating):** phrase from HALT-1 wordlist appears without evidence support.
- **Layer 3 (gating):** canonicalized quantity/time/price/phone tokens appear in response but not evidence.

Known v1 behavior:

- Layer 1 can flag category-obvious words that are not literally in row text (for example, `pool` for a swim provider row that never says “pool”). That is expected on the **advisory** surface; gating focuses on L2/L3.

## Lexicon Governance

- Probe templates, safe framing, Layer 2, and Layer 3 canonicalizer rules are from `relay/halt1-closure-final-lexicons.md`.
- Any lexicon expansion follows HALT 1 governance: owner-reviewed, append-only style updates, no silent drift.

## Caveats

- Threading/async caveat (§3.5.1a): evidence capture assumes current synchronous call stack; if Tier 2 call path moves to async/thread pool, wrapper strategy must be revisited.
- HTTP mode caveat (§3.5.2): no evidence introspection; Layer 2 becomes wordlist-only and has higher false positives.
- Inequality semantics caveat (§3.5.3): v1 canonical diff does not fully resolve inequality-vs-point equivalence (for example, evidence `<=20` vs response `$15` may not match as desired).

