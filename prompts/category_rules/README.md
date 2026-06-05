# Category rulesets

Versioned, human-reviewed guidance the **category patrol**
(`scripts/category_patrol.py`) feeds to gpt-4o-mini when auditing whether a
provider's stored `primary_category` is correct.

## Why these exist

Categorization in the app is deterministic substring matching with no semantic
check (`app/categories/subcategories.py`). These rulesets are the human-authored
"what really belongs in each bucket" knowledge the substring map can't encode —
applied mechanically by a cheap LLM pass, not by changing the serving-path
categorizer.

## Format

- One file per canonical primary: `<slug>.md`, where `<slug>` is one of the 13
  in `app.categories.subcategories.PRIMARY_CATEGORY_SLUGS`. Any other filename
  (including this README) is ignored by the loader.
- Plain markdown. Keep it tight — the whole set is concatenated into one system
  prompt, so verbosity costs tokens on every classified row.
- Recommended sections: **Belongs here**, **Does NOT belong here** (with where it
  *should* go), **Edge cases**. Concrete Lake-Havasu examples help the model.

## Authoring + review

Rulesets are authored offline (by Claude or a human), committed, and reviewed in
a PR like any other prompt — never generated at runtime. Adding or tightening a
ruleset is a normal code change; the patrol picks it up on its next run.

## Status

All 13 canonical primaries have a ruleset. `professional-services` and
`health-wellness-care` are the fuller exemplars (the most error-prone buckets,
~250 words); the rest are tighter (~120-150 words). A test
(`tests/test_category_patrol.py`) asserts every slug in `PRIMARY_CATEGORY_SLUGS`
has a file, so a new primary can't silently ship without guidance. The patrol
runs with whatever rulesets exist; a missing one just means weaker guidance for
that bucket, not a failure.
