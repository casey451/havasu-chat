# confabulation_query_gen

`app/eval/confabulation_query_gen.py` (~105 lines)

## Purpose

Generates deterministic probe queries for the confabulation evaluation harness by enumerating live Provider/Program catalog rows and applying a fixed template set per row type. This module is the harness's "input fabric": every run record downstream (invoker, detector, report) starts from `Probe` objects emitted here.

Template wording and ordering intentionally mirror `relay/halt1-closure-final-lexicons.md` Section 1; `<n>` replacement is literal and single-pass.

## Public surface

**`Probe` (frozen dataclass, slots)** — Canonical per-invocation unit:
- `query_text: str` — final query string with `<n>` substituted.
- `row_id: str` — source catalog row primary key.
- `row_type: Literal["provider", "program"]`.
- `template_id: str` — stable identifier for aggregation/reporting.

**`generate_probes(session: Session) -> list[Probe]`** — Returns all probes for live providers/programs in deterministic order:
- Providers first, ordered by `provider_name` ascending.
- Programs second, ordered by `title` ascending.
- Within each row, templates emitted in fixed tuple order.

**`normalize_row_name_for_include(name: str) -> str`** — Normalizes CLI include/exclude matching keys:
- trims + lowercases
- maps en dash/em dash (`U+2013`/`U+2014`) to ASCII `-`

## Inputs and outputs

**Inputs.**
- SQLAlchemy `Session`.
- `Provider` and `Program` tables.
- Module-constant template tuples:
  - `_PROBES_PROVIDER`
  - `_PROBES_PROGRAM`

**Row filters.**
- Provider: `draft is False` and `is_active is True`
- Program: `draft is False` and `is_active is True`

**Output.**
- Flat list of `Probe` rows (possibly empty if no live providers/programs).

## Internal structure

`generate_probes` runs in two mirrored passes:

1. Query live providers ordered by name.
2. For each provider, expand `_PROBES_PROVIDER` and append `Probe` entries.
3. Query live programs ordered by title.
4. For each program, expand `_PROBES_PROGRAM` and append `Probe` entries.
5. Return combined list.

Template interpolation is delegated to `_apply_template(template, display_name)` (`template.replace("<n>", display_name)`).

## Conventions

**Stable template ids.** `template_id` values are explicit constants (not generated from text) so downstream comparisons and historical regressions survive wording tweaks.

**Deterministic ordering.** SQL `order_by(...)` plus fixed template tuple order yields stable run ordering across invocations.

**Live-row only scope.** The same `draft/is_active` predicates as browse/query paths keep eval probes aligned with user-visible catalog content.

**Name normalization is CLI-focused only.** `normalize_row_name_for_include` is for include/exclude matching; it does not mutate `Probe.query_text`.

## Configuration

No env vars. Behavior is configured by:
- template tuples (`_PROBES_PROVIDER`, `_PROBES_PROGRAM`)
- SQL filters/order clauses in `generate_probes`

## Known limitations and design notes

**Template set is intentionally narrow.** Three templates per row type. Coverage breadth comes from row cardinality, not linguistic variety.

**Single-row lexical substitution.** `<n>` is replaced once with no escaping/sanitization; if names include unusual punctuation, probes preserve it.

**No events in scope.** Module intentionally targets Provider/Program rows only.

**No randomness/shuffling.** Useful for reproducibility, but may under-sample query phrasings that trigger alternate routing behavior.

## Related

**Direct callers:**
- `scripts/confabulation_eval.py` via `generate_probes`.
- `app/eval/confabulation_invoker.py` via `Probe` typing.
- `tests/test_confabulation_query_gen.py`.

**Direct dependencies:**
- `app.db.models.Provider`, `app.db.models.Program`
- SQLAlchemy `select`, `Session`

**Cross-references:**
- `app/eval/confabulation_invoker.py`
- `app/eval/confabulation_detector.py`
- `app/eval/confabulation_report.py`
