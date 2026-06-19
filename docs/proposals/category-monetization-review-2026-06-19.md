# Ask Hava — Category review for ad/listing monetization

**Date:** 2026-06-19 · **Lens:** maximize sellable listing inventory in the
verticals Lake Havasu businesses actually buy ads in.

## How monetization maps to categories (why this matters)

Every leaf category page is a sellable surface. Per `app/monetization/serving.py`
each leaf/category page can carry:

- **up to 5 `category_rank` tier slots** (tier 1 locked to position 1; tiers 2–5
  float within their band), and
- **1 `page_ad`** unit near the top, plus participation in the **homepage
  rotating** pool.

So a new leaf = up to **6 new paid spots**. But a leaf only renders (and is
therefore sellable, sitemap-eligible, and chat-routable) once it clears the
live render gate, `LEAF_PAGE_MIN_PROVIDERS`, which is **1** active primary-linked
provider (verified 2026-06-19 in `app/categories/leaf_pages.py`). Below that it
404s by design (anti-thin-content). The seed's `gate_ok` flag uses a stricter
editorial threshold (≥3) and the curated *trade* pages use `TRADE_PAGE_MIN_PROVIDERS = 3`,
but a generalized leaf page goes live at the first listing. **Adding the category
is step one; backfilling at least one (ideally several) providers onto it is what
turns on the revenue.**

## What we already have

15 departments / 126 leaves in `docs/proposals/taxonomy-seed.json`. The
recreation/home/auto core Casey called out is largely covered:

| Casey's ask | Existing coverage |
|---|---|
| Boats | `boat-and-watercraft-rentals`, `boat-tours-and-charters`, `boat-sales`, `boat-repair-and-service`, `auto-marine-detailing`, `boat-and-rv-storage-service`, `jet-ski-and-watersports` |
| Pools | `pools-and-spas` (single combined leaf) |
| Golf | `golf-courses`, `disc-golf` |
| Mechanics | `auto-repair` |
| Off-road | `off-road-and-ohv` (trails), `powersports-and-atv` (vehicle sales/rentals) |
| HVAC | `hvac` |

The chat router (`app/categories/leaf_query.py`) already had synonyms staged for
many high-value trades, parked in `PENDING_LEAF_SLUGS` as deliberate no-ops
until the taxonomy seeded them.

## Gaps found and filled (13 new leaves)

These are the highest ad-revenue, demonstrably-supplied Havasu verticals that
had no dedicated leaf. All seeded into `taxonomy-seed.json` (gate-closed until
backfill) and wired into chat routing.

**Auto, RV & Marine**
- **Golf Carts** (`golf-carts`) — 8+ local dealers/repair shops; recurring
  service + sales advertisers.
- **Off-Road Shops & Accessories** (`off-road-shops-and-accessories`) — *new*
  leaf for Casey's "off road stores and sales" (parts, lift kits, UTV/SxS
  upfitters) — distinct from trail recreation and from powersports sales.
- **Window Tint & Wraps** (`window-tint-and-wraps`) — heavy local + franchise
  ad spend.
- **Auto Glass** (`auto-glass`) — windshield repair/replacement; aggressive
  advertisers.
- **Trailer Sales & Repair** (`trailer-sales-and-repair`) — boat/utility
  trailers in a tow-everything town.

**On the Water**
- **Marine Supply** (`marine-supply`) — *new* leaf for boat parts/supplies
  retail (also flagged in the v2 build spec as a cross-surface to On the Water).

**Home & Property Services**
- **Garage Doors** (`garage-doors`) — *new* leaf; high-ticket, recurring repair.
- **Painters** (`painters`) — *new* leaf; common high-ad-spend trade.
- **Pressure Washing & Exterior Cleaning** (`pressure-washing-and-exterior-cleaning`).
- **Junk Removal & Hauling** (`junk-removal-and-hauling`).
- **Shade Screens & Patio Covers** (`shade-screens-and-patio-covers`) — desert
  signature (sun screens, patio/awning).

**Professional & Money**
- **Property Management** (`property-management`) — strong in a vacation-rental
  market.

**Health & Medical**
- **Hearing & Audiology** (`hearing-and-audiology`) — retiree/snowbird town;
  high LTV advertisers.

## Code changes made (additive, low-risk)

1. `docs/proposals/taxonomy-seed.json` — 13 leaves added to their departments
   (`count: 0, gate_ok: false, new: true`), structure verified well-formed.
2. `app/categories/leaf_query.py`:
   - Added chat-routing synonyms for the four genuinely-new slugs
     (`marine-supply`, `off-road-shops-and-accessories`, `garage-doors`,
     `painters`).
   - Removed the 9 now-seeded slugs from `PENDING_LEAF_SLUGS` so the sync test
     (`tests/test_leaf_query_additions.py`) stays green; left a comment trail.

The relevant invariants were checked by hand against the freshly written files:
every synonym target is now in the seed or still in `PENDING`, and nothing is in
both. The type-mapping and seed-script tests use synthetic seeds and
one-directional checks, so they're unaffected.

> **Verification gate:** I could not run the full suite from this sandbox (the
> mount view of just-edited files is unreliable — a known issue noted in
> CLAUDE.md). Per repo rules, please run `python -m pytest -q` and `ruff check .`
> locally on a feature branch before committing. The edits are in your working
> tree now; create the branch off `main` and the changes carry over.

## Recommended next steps (not yet implemented)

1. **Backfill providers** onto the new leaves — this is what actually unlocks
   the paid slots (a leaf renders at ≥1 primary-linked provider). Most of these
   businesses already exist in the DB filed under broader leaves (e.g. golf-cart
   dealers under `powersports-and-atv` or `auto-repair`); a primary-link remap is
   the fastest path. `scripts/backfill_new_monetization_leaves_2026_06.py` does
   this (dry-run by default). The 2026-06-19 dry-run against prod staged **19
   moves** (after dropping a secondary-category false positive): property-management
   and hearing-and-audiology at 5 each; off-road-shops-and-accessories at 3;
   auto-glass at 2; golf-carts, trailer-sales-and-repair, garage-doors and
   pressure-washing at 1 — eight leaves that go live immediately. **Applied to
   prod 2026-06-19** (13 leaf rows created, 19 primary moves, one transaction,
   rollback snapshot written). window-tint, marine-supply, junk-removal,
   shade-screens and painters found 0 by name. The script's opt-in `--wide` flag
   fills the first four from secondary Google categories (review the CSV — it is
   noisier); **painters is deliberately excluded from `--wide`** because general
   contractors routinely list "Painter" as a secondary service, so it needs
   pure-painting names or manual tagging. The matcher rules are locked under CI
   by `tests/test_new_monetization_leaves_matcher.py`. **Prod-DB op —
   dry-run → review CSV → approve.**
2. **Split `pools-and-spas`** into **Pool Service & Cleaning** vs **Pool Builders
   & Remodeling**. Different buyers (recurring-revenue cleaners vs high-ticket
   builders) and "pool cleaners" was an explicit ask. Each split leaf only needs
   ≥1 provider to render, so the split is low-risk as long as the current 6
   `pools-and-spas` providers can be sorted into the two buckets.
3. **Wire the `garage-door` curated-trade twin** to the new `garage-doors` leaf
   in `app/categories/trades.py` `LEAF_TWINS` once the leaf clears the gate, so
   the two pages don't compete for the same search term.
4. **Consider seeding** the remaining parked leaves if supply/ad demand warrants:
   `laundry-and-dry-cleaning`, `funeral-cremation-and-cemeteries`,
   `firearms-and-shooting-sports`, `mobile-home-services` (left in `PENDING`).
5. **Per-category price overrides** — the placement price book supports
   per-`category_slug` overrides; the signature high-demand leaves (boat rentals,
   golf carts, HVAC, auto glass) can command premium tier pricing vs the global
   default.

## Sources

- [The Boat Broker — boat & RV dealer, Lake Havasu City](https://www.theboatbroker.com/)
- [JR Motors — RV & Marine dealership, Lake Havasu City](https://www.jrmotorsales.com/)
- [Anderson Powersports (Can-Am/Sea-Doo/UTV), Lake Havasu City](https://www.andersonpowersportshavasu.com/)
- [Golf cart dealers in Lake Havasu City (Yelp)](https://www.yelp.com/search?cflt=golfcartdealers&find_loc=Lake+Havasu+City%2C+AZ)
- [UTV shops in Lake Havasu City (Yelp)](https://www.yelp.com/search?find_desc=Utv+Shops&find_loc=Lake+Havasu+City,+AZ)
