# confabulation_report

`app/eval/confabulation_report.py` (~175 lines)

## Purpose

Serializes confabulation harness outputs into durable artifacts:

- raw run records as JSONL
- per-row aggregate CSV
- human-readable markdown summary with inclusion policy, rates, offenders, token breakdowns, and anchor checks

This module is output-focused and intentionally separate from invocation/detection logic.

## Public surface

**`write_jsonl(path, runs) -> None`** — Writes one JSON object per line (UTF-8, `\n` line endings).

**`write_per_row_csv(path, runs) -> None`** — Writes grouped per-row stats:
- total/included runs
- gating-hit runs
- advisory hit counts
- top-3 gating tokens

**`write_summary_md(path, runs) -> None`** — Writes markdown summary sections including:
- inclusion policy details
- per-flag gating rates
- top offender rows
- top gating/advisory tokens
- tier breakdown
- regression-anchor sanity checks

## Inputs and outputs

**Input shape.** `runs: list[dict[str, Any]]` with keys consumed opportunistically, including:
- `row_id`, `row_name`, `tier_used`, `flag_state`
- `excluded_from_summary`
- gating counts/tokens (`gating_hit_count` or fallback `hit_count`, `gating_tokens` or fallback `hit_tokens`)
- advisory counts/tokens (`advisory_hit_count`, `layer_1_advisory_tokens`)
- layer-2 presence (`layer_2_hits`)

**Outputs.**
- file writes to provided paths
- parent directories auto-created

## Internal structure

### Shared helpers

- `_ensure_parent(path)` creates parent dirs.
- `_gating_tokens(x)` and `_advisory_tokens(x)` normalize token-list fallbacks.

### JSONL writer

- writes each run via `json.dumps(..., ensure_ascii=False)` with newline per record.

### Per-row CSV writer

1. Group runs by `(row_id, row_name)`.
2. Compute total vs included counts.
3. Count included runs with `gating_hit_count > 0`.
4. Sum advisory hit counts.
5. Aggregate top 3 gating tokens.
6. Emit sorted rows by `row_name` lowercased.

### Summary markdown writer

1. Compute tier distribution across all runs.
2. Split included/excluded by `excluded_from_summary`.
3. Calculate exclusion subsets (Tier 1, Tier 3-no-L2) and included Tier 3-with-L2 counts.
4. Emit per-flag gating rates for `off`, `on`, `both`, `unknown` (when data exists).
5. Rank top offender rows by included gating-hit runs.
6. Emit top gating tokens and top Layer-1 advisory tokens.
7. Emit tier breakdown and fixed anchor checks (`Aqua Beginnings`, `Grace Arts Live`).

## Conventions

**Best-effort key fallbacks.** Reader tolerates historical key variants (`hit_count` vs `gating_hit_count`, etc.).

**Inclusion-aware headline math.** Summary rates use included subset only; exclusion rationale is documented inline.

**Deterministic ordering where practical.** Per-row CSV sorted by row name; summary token sections sorted by frequency.

**UTF-8 text outputs.** JSONL/MD use explicit UTF-8 encoding.

## Configuration

No environment configuration. Behavior is data-shape driven plus hardcoded section conventions (including anchor names and summary labels).

## Known limitations and design notes

**Schema is duck-typed.** Missing keys silently default/fallback; malformed run payloads can skew stats without hard failure.

**Markdown summary is opinionated.** Section set and wording are fixed in code; not templated.

**Anchor checks are static strings.** If anchor row names change, sanity section drifts until code update.

**No write-atomic temp swap.** Writers write directly to target paths.

## Related

**Direct callers:**
- `scripts/confabulation_eval.py` after run collection.
- `tests/test_confabulation_report.py`.

**Direct dependencies:**
- Python stdlib: `csv`, `json`, `pathlib`, `collections`

**Cross-references:**
- `app/eval/confabulation_detector.py`
- `app/eval/confabulation_invoker.py`
- `app/eval/confabulation_query_gen.py`
