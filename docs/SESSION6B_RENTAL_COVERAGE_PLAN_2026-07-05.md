# Session 6b — Rental-coverage consolidation (off-road / jet-ski / golf-cart / bike)
**Date:** 2026-07-05 · Category-audit slice (plan §6 / competitive coverage §11).
**Status:** PLAN ONLY — no prod writes, no code changes. Read-only investigation.

> **Goal:** make off-road/UTV, jet-ski/watersports, golf-cart, and bike/e-bike **rentals** as well-organized and complete as Go Lake Havasu. Two parts: **(A) recat** operators we have but misfiled (gated data op) + **(B) coverage-fill** operators we're missing (research+insert), plus **(C) a small classifier PR** so the misfile can't recur on the next scrape.

## Root cause (the off-road analog of the charter bug)
The water side was already fixed: `app/categories/water_misfiled_rules.py:65-67` lifts charter/tour/fishing names out of the generic boat-rentals leaf. **Off-road has no equivalent.** The CVB crosswalk `app/contrib/source_category_map.py:75-77` maps `ohv`/`off road`/`offroad` → `off-road-and-ohv` (the **trails** leaf), and the name-lift at `:174-185` only fires for water leaves — so a real UTV **rental** operator tagged "off road" lands on trails, or (via Google type `motorcycle_dealer`, `leaf_type_mapping.py:147`) in `powersports-and-atv` (the **dealer** leaf). Golf-cart and bike rentals have no name-signal path at all.

## Leaf map (rental vs shop/dealer/trails)
| Leaf | Dept | Kind | ~count |
|---|---|---|---|
| `utv-and-offroad-rentals` | Things to Do | **RENTAL** (target) | 3 |
| `off-road-and-ohv` | Outdoors & Rec | trails (NOT rental) | 6 |
| `powersports-and-atv` | Auto/RV/Marine | dealer (NOT rental) | 9 |
| `jet-ski-and-watersports` | On the Water | **RENTAL** | 3 |
| `kayak-and-paddle` | On the Water | **RENTAL** | 3 |
| `boat-and-watercraft-rentals` | On the Water | **RENTAL** | 114 |
| `bikes-and-e-bikes` | Things to Do | **RENTAL + shop** | 3 |
| `golf-carts` | Auto/RV/Marine | sales/service/rental hub | 0 (doesn't ship yet) |
| `off-road-shops-and-accessories` | Auto/RV/Marine | shop | 0 |

Gate = `LEAF_PAGE_MIN_PROVIDERS=1` — `golf-carts` and `off-road-shops` are empty and 404 until they get ≥1 member. Query-side routing is **already wired** (`leaf_query.py`: `atv/utv rentals`→utv-and-offroad-rentals `:373-374`, `golf cart rental`→golf-carts `:935`, `bike/e-bike rental`→bikes-and-e-bikes `:936-940`, `waverunner/sea-doo rental`→jet-ski-and-watersports `:912-913`) — those routes self-activate the moment each leaf clears the gate.

## Existing tooling — most of the op already exists
`scripts/backfill_rentals_2026_07_01.py` already bundles A + B + dedup + publish, dry-run default, `--apply --confirm` gated, JSON snapshot for reversal. `_REHOME` (`:81-86`) = the A list; `_INSERTS` (`:95-111`) = the B list. **It's dated 2026-07-01 and may be partially stale** (e.g. Wake Surf was reinstated same-day) — so it must be re-run **idempotently** (skip rows already correct) and its live dry-run reviewed, not assumed. CC can run it directly, or split A (pure repoints, mirror `recategorize_lodging_misfiles` / `apply_browse_orphans`) from B (inserts).

### (A) Recat — have-but-misfiled (repoint primary EntityCategory)
- Desert Experience UTV Offroad Rentals: `powersports-and-atv` → `utv-and-offroad-rentals`
- Wet Monkey Powersport Rentals: `powersports-and-atv` → `utv-and-offroad-rentals`
- Bee's Rentals → `utv-and-offroad-rentals`
- Cycle Therapy: `sporting-goods` → `bikes-and-e-bikes`
- Lake Havasu Bike & Fitness: admin DRAFT → publish + `bikes-and-e-bikes`
- Wake Surf Adventures: reactivate + secondary `boat-tours-and-charters`
- Premier Golf Cars: description note (resort-guest-only rentals) — makes `golf-carts` ship
- Desert Experience Offroad Rentals (orphan twin `fd8bb3cc`): dedup-deactivate

### (B) Coverage-fill — missing (research + insert new listings)
- Havasu E-Bikes → `bikes-and-e-bikes`
- Lake Havasu Houseboats, Lake Havasu Party Boat, VIP Cabana Boats → `boat-and-watercraft-rentals`
- Lake Havasu RV & Boat Rentals → `rv-sales-and-service`

### HELD — do NOT auto-insert (need your confirmation)
- **Adrenaline RZR** — its phone matches "Adrenaline Trailers" already in catalog; confirm it's a distinct operator.
- **Sunn Slide Beach Rentals** — no verified contact.
- **Southwest Outfitters** — rental claim unconfirmed (keep `sporting-goods` primary).

## (C) Classifier fix — separate small CODE PR (stops recurrence)
The data op only fixes today's rows; the next daily scrape re-misfiles unless the classifier learns off-road/golf-cart/bike rentals:
1. `app/contrib/name_leaf_signals.py::leaf_from_name` — add conservative rental regexes → `utv-and-offroad-rentals` / `golf-carts` / `bikes-and-e-bikes` (anchor on "rental/rentals/rzr/side by side/e-bike/golf cart" so no false positives; mirror the water rules).
2. `app/contrib/source_category_map.py:174-185` — widen the name-lift beyond `_WATER_LEAVES` so a CVB `off road`/`water sports` tag on a *rental*-named operator lifts to the rentals leaf, not trails/dealer.
Add unit tests (mirror the water name-signal tests). **Do NOT** strip charter/tour/guide from `water_misfiled_rules` — that was the already-fixed charter case.

## Code vs data op
- **(A) recat + (B) inserts = gated PROD data op** (dry-run → counts → your approval → apply). No serving-code change — the leaf gate + wired routing auto-include repointed members.
- **(C) classifier = a normal code PR** (test + PR + merge). Do it so the next scrape doesn't undo the recat.

## Decisions for you
1. Confirm the **3 HELD** operators (Adrenaline RZR / Sunn Slide / Southwest Outfitters).
2. Run the existing `backfill_rentals` op (idempotent re-run) vs a fresh scoped `recategorize_*` for A + separate inserts for B — I'd re-run the existing one after a fresh dry-run review.
3. OK to ship the classifier PR (C) alongside, so the fix sticks?
