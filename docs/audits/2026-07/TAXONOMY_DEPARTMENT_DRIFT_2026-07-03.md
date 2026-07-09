# Taxonomy department drift — seed vs prod (finding + reconcile plan)

**Date:** 2026-07-03
**Status:** Finding + proposed plan. **No changes made.** Surfaced while staging the
source-parity leaf additions (PR #699); this is a *pre-existing* drift unrelated to
that work.

## The finding

The display taxonomy seed (`docs/proposals/taxonomy-seed.json`) defines **15 clean
departments**. Prod's `categories` table has **32 level-0 rows** — the 15 seed slugs
(minus 2, below) **plus 19 legacy department stubs** — and it is **missing two
departments the seed expects**:

| Seed department | In prod? | Where prod actually keeps those leaves |
|---|---|---|
| `outdoors-and-recreation` | ❌ missing | `hiking-trails`, `parks-and-playgrounds`, `off-road-and-ohv`, … are children of **`things-to-do-and-attractions`** (14 children total) |
| `community-and-civic` | ❌ missing | civic leaves split across legacy depts: `worship-and-nonprofits` (places-of-worship, nonprofits-and-charities), `city-and-government` (government-and-mvd), `public-civic-resources` |

Legacy level-0 stubs still present in prod (kept as 301-redirect targets, never
deleted): `attractions`, `auto-rv-fuel`, `beauty-care`, `city-and-government`,
`classes-sports-recreation`, `eat-drink`, `events`, `health-wellness-care`,
`home-property-services`, `lodging-vacation-rentals`, `outdoors-parks-trails`,
`professional`, `professional-services`, `public-civic-resources`, `services`,
`shopping-essentials`, `tattoo`, `things-to-do`, `worship-and-nonprofits`.

## Root cause

`outdoors-and-recreation` and `community-and-civic` entered the seed in commit
**63776887** ("feat(taxonomy): A.3 apply — parent/level migration + seed + remap").
`scripts/seed_taxonomy.py` is **manual-only** — it is *not* wired into preDeploy /
CI / `nixpacks.toml`. So the A.3 code + migration shipped, but the **seed's new
department structure was never applied to prod** (prod was last seeded from a
pre-A.3 layout for these two areas). Nothing has re-seeded departments since.

## Why this matters (and the trap)

Running `scripts/seed_taxonomy.py --apply --confirm` against prod would NOT just add
leaves — its dry-run shows **2 dept_insert + 2 dept_update + 14 leaf_update**. It
would:

1. create `outdoors-and-recreation` + `community-and-civic` as new departments, and
2. **re-parent ~14 live leaves** off `things-to-do-and-attractions` (and the legacy
   civic depts) into the new departments.

That's a **live navigation restructuring** — every affected leaf's department
breadcrumb, department landing page, and any hardcoded department references change
at once. It must not happen as a side effect of "add two leaves."

## Reconcile options (for a separate, deliberate pass — pick one)

1. **Adopt the seed (split outdoors/civic out).** Run the full seed against prod so
   the department layer matches the 15-dept design. Requires: verifying nav/landing
   code renders the two departments, 301s for every re-parented leaf's old
   department URL, and a full re-crawl of internal links. Highest churn; "correct"
   per the A.3 design.
2. **Adopt prod (fold the seed to match).** Edit `taxonomy-seed.json` to put the
   outdoors leaves back under `things-to-do-and-attractions` and drop
   `outdoors-and-recreation` / `community-and-civic`, so seed==prod and future seed
   runs are safe no-ops. Lowest churn; abandons the A.3 split.
3. **Leave both, document the divergence.** Keep prod as-is and stop treating the
   seed as prod's source of truth for departments; only ever seed *leaves* via a
   targeted script (never the full department pass). Zero churn; permanent drift.

**Recommendation:** Option 2 or 3 short-term (prod is the live truth and Option 1 is
a real nav migration with SEO/redirect work). Revisit Option 1 only if the
outdoors/civic split is a product goal.

## Immediate decision applied (leaves only)

Per Casey (2026-07-03), the two source-parity leaves are inserted **targeted**, under
the department prod actually uses (`things-to-do-and-attractions`), via
`scripts/seed_parity_leaves.py` — **not** the full seed. This adds 2 rows and touches
nothing else, leaving the department drift for the deliberate pass above.
