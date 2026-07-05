# Session 6a — Browse-orphans cleanup (GATED, two-phase: enumerate+review → apply)
**Date:** 2026-07-05 · First slice of the big directory/category audit (plan §6 Session 6+).
**Status:** PLAN ONLY — no prod writes. Read-only code investigation.

> A **browse-orphan** = an ACTIVE entity that renders on **zero shipping leaf** (invisible to browse/leaf-search) because of bad categorization. Fixing it is **entirely a gated prod data op — no serving-code change** (the leaf gate auto-includes a listing the moment its primary link points at a gate-clearing leaf). Assigning the *right* leaf is a judgment call, so this runs in two phases with your review in the middle.

## Don't trust "131"
That figure is from the 2026-07-01 crawl. Since then Session 5 deactivated 50 vacation-rentals (they leave the active population entirely) and 5.1 repointed HEAT Bar / (optionally) reactivated PM firms. **Recompute live** — the real first step is a fresh enumeration, not reusing 131.

## Enumeration — 4 causes (the current check only catches one)
The nightly `scripts/integrity_report.py` "check A" (lines 95–109) flags only entities with **no `entity_categories` row at all** — it counts *any* link as "on a leaf," so it misses the other three causes. The upgraded recompute (using the leaf-page contract in `app/categories/leaf_pages.py::_leaf_provider_query` + `_gate_counts`, `LEAF_PAGE_MIN_PROVIDERS=1`) must bucket by cause:

- **(a) No primary link** — active entity with no `EntityCategory.is_primary=True` row.
- **(b) Primary points at a department (level 0) or a dangling/retired category** — `is_primary=True` but the joined `Category.level != 1` (or the FK is dangling). A leaf must be `level==1` with a `level==0` parent, so a department-pointed primary never renders. (This is the "breadcrumb ends at 'Home & Property Services ›'" symptom.)
- **(c) Primary points at a leaf that is itself below the publish gate** — `level==1` but that leaf's renderable count `< 1`, so the whole leaf 404s and its members vanish.
- **(d) Provider masking** — a valid primary leaf, but `Provider.is_local=False` or `Provider.draft=True` hides it (NULL `is_local` is kept, not a cause).

## Three buckets → fix (from the master audit)
| Bucket | ~stale size | Fix | Review needed? |
|---|---|---|---|
| **A. Stranded in-city businesses** | ~40 | assign a correct **primary leaf** (repoint `EntityCategory`) | **Yes — review CSV** (leaf choice is judgment) |
| **B. Out-of-area** | ~25 | `Entity.is_active=False` + cascade providers (Session-5 pattern) | Semi-auto (clear OOA signal), still dry-run+approve |
| **C. Orphaned dedup twins (page still live)** | ~35 | collapse — deactivate the retired twin (3D/Op1 pattern) | **Yes — confirm which twin is canonical** |

**Exclude:** legitimate place-type entities (Site Six, parks, London Bridge / lighthouse trail) render as place-cards *intentionally* — never deactivate/repoint those.

## Leaf proposal (for bucket A's review CSV)
No fully-trustworthy auto-classifier exists — propose, don't auto-apply. In decreasing reliability:
1. `app/contrib/leaf_type_mapping.py::map_google_types_to_leaf_slug()` — **primary** Google type only (secondary types misfile). Best proposer.
2. `app/contrib/name_leaf_rules.py::leaf_for_name()` + the single-hit `match_new_leaf()` in `scripts/backfill_new_monetization_leaves_2026_06.py` — for kinds Google can't type; returns `None` on ambiguous.
3. `app/categories/subcategories.py::derive_primary_category()` (legacy `Provider.subcategory`) — coarse dept-level hint only, fallback.
Emit a **review CSV**: `entity_id, provider_name, google_primary_category, current_leaf_slug, proposed_leaf, proposer, bucket`. Blank `proposed_leaf` where no confident proposal → you fill it.

## Two-phase gate
**Phase 1 (read-only — safe, no writes):** build/upgrade the enumerator to recompute orphans per-cause, bucket A/B/C, attach a proposed leaf, and write the review CSV + per-bucket counts. Run it, report counts, hand you the CSV. Nothing is written.
**Phase 2 (gated apply — after your CSV review):** one script mirroring `recategorize_lodging_misfiles_2026_07_05.py` (repoint: swap `is_primary` onto an existing target link else rewrite the primary row's `category_id`) + `apply_bogus_deactivation.py` (deactivate + **skip verified/claimed/sponsored/already-done** + undo-CSV + `--reactivate-from`). Dry-run → counts → your approval → apply. Reversible.

## Code vs data op
- Buckets A/B/C = **prod data op** (gated). No deploy needed — takes effect on next render.
- **Optional follow-up PR (not required):** upgrade `integrity_report.py` check A to catch causes (b)/(c)/(d), so the nightly guard stops under-counting orphans. Its own small PR.

## Decisions for you
1. Confirm the **review-CSV workflow** for bucket A (you eyeball proposed leaves before apply) — vs auto-applying only the high-confidence Google-primary-type proposals and CSV-ing the rest.
2. **Bucket B (OOA):** OK to treat `is_local=False`/Parker-Kingman-Needles-Topock as the removal signal (same as Session 5), pending dry-run counts?
3. Want the **integrity_report.py upgrade** bundled as a follow-up PR so this can't silently re-accumulate?
