# provider_name

`app/core/provider_name.py` (~49 lines)

## Purpose

Single helper **`_norm_provider_name`** normalizes **provider display names** for **stable comparison keys** (dedupe alignment and program-import backfill) without treating typography variants as distinct entities.

## Public surface

**`_norm_provider_name(name: str) -> str`** — Leading underscore signals “internal,” but the function is the module’s only API and is safe to import where normalization is needed.

### Layer 1 — portable Unicode folding

- **`unicodedata.normalize("NFKC", ...)`** + lowercase + whitespace collapse.
- Maps en/em dash and minus variants to ASCII **`-`**.
- Maps curly quotes/apostrophes/primes to straight **`'` / `"`**.
- Replaces NBSP with space; strips soft hyphen (**`\u00ad`**).

### Layer 2 — Lake Havasu legacy suffix folds

End-anchored **`re.sub`** removals (case-insensitive):

- Optional **`(ACPA)`** suffix.
- Trailing **` - Sonics`**.
- Trailing **` - Lake Havasu City`**.

Docstring states these exist because some legacy program-import rows used shorter **`provider_name`** strings than canonical Section 9 headers — **remove once seed naming is canonicalized** during Phase 8 verification.

## Inputs and outputs

Input may be **`None`-ish via `(name or "")`** — always returns a trimmed normalized string (possibly empty).

## Internal structure

Sequential Unicode normalization → punctuation folding → lowercase token squash → three suffix regex passes → final whitespace squeeze.

## Conventions

**Phase 1.3 / 1.4 commentary in docstring** ties this key to Provider upsert and backfill imports — **exact-match keys must agree with seed-derived normalization**.

## Known limitations and design notes

**No Python importers at Slice 67a repo-wide grep** — module may be staged for upcoming lane work or temporarily disconnected after refactors; **`docs/maintainability/non_river_scene_cleanup.md`** records a historical move of **`_norm_provider_name`** into **`app/core/provider_name.py`**. Treat behavior as **speculative-until-wired**: normalization rules remain the contract.

## Configuration

None.

## Related

**Cross-references:**

- **`docs/maintainability/non_river_scene_cleanup.md`** — refactor note for this helper’s relocation.
