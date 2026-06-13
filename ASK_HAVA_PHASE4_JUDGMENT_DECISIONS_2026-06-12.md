# Ask Hava — Phase 4 judgment-row decisions

**Date:** 2026-06-12 · **Author:** Cowork session · **Status:** ✅ Decisions APPROVED by Casey (2026-06-12) — **NO database writes performed**
**Resolves:** the "15 judgment rows" left open in `ASK_HAVA_PHASE4_RETAG_DRYRUN_2026-06-12.md` (§"What I need from you").

**Approved:** (A) encode the marine sales/repair **rule**; (B) all **3 realty firms → lodging-vacation-rentals**.

These are recommendations, evidence-backed where a judgment call needed real-world
context. Nothing here is applied: the apply is still `dry-run → confirm counts →
**you** run --apply --confirm against prod`, per `CLAUDE.md`.

---

## A — Marine businesses: sales vs repair (the 12 marine judgment rows)

Don't hand-decide these. The split is deterministic from `google_primary_category`,
which is exactly how `recategorize_health_beauty.py` classifies. Encode one rule in
`app/categories/water_misfiled_rules.py`:

| `google_primary_category` contains | → proposed leaf | Rationale |
|---|---|---|
| `supplier`, `store`, or `dealer` | `boat-sales` | These are dealers/retailers (Google's own primary type) |
| `service` (and not supplier/store) | `boat-repair-and-service` | Service-typed marine shops are repair/rigging/custom work |
| neither (blank primary type) | **leave as-is** / hold | Not enough signal to move confidently |

Applying that rule to the audit snapshot (`subcategory_audit_20260611T201931Z.csv`):

**→ `boat-sales`** (primary type supplier/store): Domn8er Power Boats, Sun Country Marine
Group, IMAGE MARINE, R & D Marine, Cheetah Power Boats, Germaine Marine, Maxed Out
Marine, Prestige Marine, Fallon Marine LLC, Xtreme Speed And Marine.

**→ `boat-repair-and-service`** (primary type service): Barrett Custom Marine, JandJ
Performance & Marine Service, Chong Servicenter, Gelcraft Customs, J C Marine,
Absolute Speed & Marine, So Cal Speed & Marine, Pro-Marine, Patriot Marine, Savage
Marine, Unlimited Marine, Kornowskis Kustom Marine, Havasu Marine Specialties,
Lakeland Marine, Saleen Fiberglass Restoration, Boat Body Shop, Caliber 1 Custom
Boats, Max Machine Worx, D1 Performance, Flat Tops Marine & Motorsports.

Note this is broader than the doc's "12" — the dry-run flagged a curated subset, but the
rule generalizes cleanly to every ambiguous marine row, which is the more durable fix.
**Recommendation: encode the rule, dry-run it, and review the full flagged list before apply.**

## B — Realty / property-management → lodging (the 3 realty judgment rows)

All three were stored `professional-services`; the fresh classifier proposed
`lodging-vacation-rentals`. The doc's open question was "brokerage (pro-services) vs
vacation-rental manager (lodging)." Web check on each: **all three actively run
short-term/vacation-rental booking operations**, not brokerage-only. For a "where can I
stay" concierge, lodging is the user-intent-correct tag.

| Firm | Finding | Recommendation |
|---|---|---|
| **Destination Havasu** | Full-service vacation-home/condo rental manager (booklakehavasu.com); est. 2001 | **→ lodging-vacation-rentals** (clear) |
| **First Choice Property of Mohave County** | Runs "Lake Havasu Vacation Rentals" (fcphavasu.com): furnished short-term condos/homes | **→ lodging-vacation-rentals** (clear) |
| **Copper Canyon Realty** | Brokerage **and** long-term + vacation rentals; Yelp lists it as Property Management | **→ lodging-vacation-rentals** (it books stays; defensible) |

If you'd rather keep a pure brokerage out of lodging, Copper Canyon is the only borderline
one — but its site sells vacation-rental stays, so lodging still serves the user better.

## Sources
- [Copper Canyon Realty — Yelp](https://www.yelp.com/biz/copper-canyon-realty-lake-havasu-city) · [vacation rentals page](https://coppercanyonrealty.com/lake-havasu-city-vacation-rentals.html)
- [Destination Havasu — booking site](https://www.booklakehavasu.com/) · [Yelp](https://www.yelp.com/biz/destination-havasu-lake-havasu-city)
- [First Choice Property — fcphavasu.com](https://www.fcphavasu.com/) · [BBB profile](https://www.bbb.org/us/az/lk-havasu-cty/profile/property-management/first-choice-property-of-mohave-county-llc-1126-1000039898)
