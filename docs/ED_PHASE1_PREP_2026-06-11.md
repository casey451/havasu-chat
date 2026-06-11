# B3 Phase 1 (Eat & Drink) — prep + dry-run package (2026-06-11)

Cowork prep from the 2026-06-10 prod export. Everything below is staged; the
apply is Casey-gated per CLAUDE.md and spec §7.

## The finding that reshapes the phase

**The A-migration CSV's E&D proposals are identical to current prod state**
(274 rows, 0 would-move) — current state *came from* that CSV, so the QSR
reclassification §3.3 describes was never encoded anywhere. The phase needs
its own remap CSV; it now exists:

**`docs/proposals/ed_phase1_qsr_remap.csv` — 12 rows**, chain QSRs misfiled
under Restaurants, all → Quick Bites & Takeout: McDonald's · 3× "Subway at …"
(CVB-named rows) · Dairy Queen · Domino's Pizza · Little Caesars · Panda
Express · Chipotle · Culver's · 2× Filiberto's. Detection: chain-name match
among E&D Restaurants primaries (Google types were no help — prod has ZERO
`fast_food_restaurant` types under Restaurants; the 18 correctly-filed QSRs
in Quick Bites carry them, the misfiled ones are untyped or generic).

Judgment calls baked in (veto any row by deleting it from the CSV):
Chipotle / Panda Express / Culver's are fast-casual counter service →
Quick Bites; Filiberto's (2 rows) is a regional chain drive-thru → Quick
Bites.

## Post-move counts vs spec §4

| Leaf | Now | After moves | Spec range | Status |
|---|---|---|---|---|
| Restaurants | 160 | 148 | 110–145 | ~3 ABOVE — residual is real sit-downs; suggest accepting or range → 110–150 |
| Quick Bites & Takeout | 29 | 41 | 45–70 | still BELOW — see contradiction below |
| Bars & Breweries | 30 | 30 | 25–35 | in range |
| Cafés & Coffee | 21 | 21 | 15–25 | in range |
| Bakeries & Desserts | 29 | 29 | 15–25 | ABOVE — Casey's open range call (widen to 15–30 or move dessert shops) |
| Food Trucks & Catering | 5 | 5 | 10–25 | BELOW — discovery gap |

**Spec contradiction to resolve at the gate:** §4.1 says "Eat & Drink needs
none" (no discovery queries), but §4's own table flags Food Trucks as a
"Known discovery gap" and Quick Bites lands below range even after every
identifiable QSR moves. Either E&D gets a small query pass (food trucks +
local quick-serve) or the QB/Food-Truck ranges drop. Phase can close either
way — the §7 gate just needs the decision recorded.

## Dedupe coupling (note, not blocker)

Same-name pairs across the two leaves (Domino's, Dairy Queen, McDonald's,
Subway×) suggest cross-source duplicates — the CVB-named "Subway at …" rows
vs Google rows. Moving both members to Quick Bites is harmless; the pairs
will surface in the B1 phone-match queue regardless. No ordering constraint.

## Runbook (Casey, after the prep PR merges)

```powershell
# 1. Dry-run, phase-scoped (prints assign/unchanged counts, writes nothing)
python scripts/apply_taxonomy_remap.py --csv docs/proposals/ed_phase1_qsr_remap.csv --department "Eat & Drink"

# 2. Anchors green before and after (case 3 anchor lives in E&D)
python scripts/check_taxonomy_anchors.py --department "Eat & Drink"

# 3. After reviewing the dry-run plan:
python scripts/apply_taxonomy_remap.py --csv docs/proposals/ed_phase1_qsr_remap.csv --department "Eat & Drink" --apply --confirm

# 4. Post-apply verification
python scripts/check_taxonomy_anchors.py
#    + spot-check /categories/eat-and-drink/{restaurants,quick-bites-and-takeout}
#    render counts (gate: no leaf below LEAF_PAGE_MIN_PROVIDERS that cleared it before)
```

§7 step 6 (close): the E&D review queue is trivially empty (no §5 classifier
changes ride this phase — that machinery lands with H&M, where the catch-all
redistribution actually needs it).

## Anchors reconciled (done, in this change set)

All 10 regression anchors now name real prod rows
(`scripts/eval_anchors/taxonomy_regression_10.{txt,csv}`): the three
placeholders became **Havasu Barber Shop**, **Stubbys Red Wagon BBQ**, and
**SARA Park Disc Golf Course**. Pending only the WS-3 paste diff, which may
swap anchor *choices* — the names are real either way.
