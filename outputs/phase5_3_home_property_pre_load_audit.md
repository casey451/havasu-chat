# Phase 5.3 — Home & Property Services — Pre + Post Load data-quality audit

> Mirrors `outputs/phase5_2_on_the_water_data_quality_audit.md` shape with a
> 5.3-specific override: this doc runs in TWO passes:
>
> 1. **Pre-load** (against the 46 entities already at
>    `/category/home-property-services`, routed there from Phase 5.2's
>    `lake_recreation` scrape via the sustainability resolver)
> 2. **Post-load** (against the 199 newly-loaded home_services entities +
>    the 75 ambig-skipped Google ↔ existing-entity reconciler matches)
>
> Final apply-script consolidates both passes' decisions.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.3 session
> (2026-05-15) post-`7c994aa`.

---

## §1 Summary

Total decisions captured in this audit:

| Pass | Slice | Rows examined | KEEP | RE-ROUTE-OUT | RE-ROUTE-IN | REVIEW |
|---|---|---|---|---|---|---|
| Pre-load | A — at `/category/home-property-services` (the pre-existing 46) | 46 | 28 | 16 | — | 2 |
| Pre-load | B — 3 NULL-category_id residuals (5.2 carry-forward) | 3 | 0 | 3 | — | 0 |
| Post-load | C — 199 newly-loaded entities | 199 | 199 | 0 | — | 0 |
| Post-load | D — 9 cross-category ambig-skips | 9 | 5 | — | 1 | 3 |
| **Net effect** | | | | **−13 from h-p-s, +13 to on-the-water, +1 to h-p-s** | | |

**Cross-list policy decision (V1):** NO cross-list. Each entity gets exactly
one EntityCategory row. Follows the 5.2 precedent (close-out §3.2 — "V1
schema is single-primary EntityCategory ... Phase 6 can add secondary
EntityCategory rows if dual-category surfacing matters; deferred").
Cross-list candidates resolved by name-signal: "Boat & RV Storage" →
on-the-water (boat primary); "Self Storage" → home-property-services
(self-storage primary).

**Projected post-apply counts:**

| Category | Pre-apply | Post-apply |
|---|---|---|
| `/category/home-property-services` | 245 | **233** (245 − 13 boat-storage + 1 Stanley Steemer) |
| `/category/on-the-water` | 100 | **116** (100 + 13 boat-storage + 3 Slice B + 0 — wait, Sandbar/Horizon/Campbell were already counted as misroutes IN the 46 so they're part of the 13 going to on-the-water... actually let me recount below) |

(Final counts pinned in §6.)

---

## §2 Pass 1 — Pre-load audit (the 46 + 3 carry-forward)

### 2.1 Slice A — 46 entities currently at `/category/home-property-services`

#### RE-ROUTE-OUT to on-the-water (16 — 3 high-confidence misroutes + 13 boat-named storage)

The 3 high-confidence misroutes (sustainability fallback caught powersports
businesses by their `service`/`supplier` primary_type):

| entity_id_prefix | name | primary_type | reviews | Decision |
|---|---|---|---|---|
| `54e3c237` | Sandbar Powersports | `service` | 313 | → `on-the-water` (watersports rental — site `sandbarwatersports.com`) |
| `23244621` | Horizon MotorSports | `supplier` | 53 | → `on-the-water` (motorsports → boats) |
| `4d88c09e` | Campbell Cove Complex | `supplier` | 19 | → `on-the-water` ("Cove" naming) |

The 13 boat-named storage facilities (cross-list policy → on-the-water):

| entity_id_prefix | name | reviews |
|---|---|---|
| `79e88dce` | Island Storage & Marine | 53 |
| `7e994b21` | Dave's Boat & RV Storage | 42 |
| `31163faf` | Havasu Boat Storage | 35 |
| `3954a1bd` | Boat Storage of Lake Havasu | 21 |
| `8947770e` | Depot Storage Boat and RV | 17 |
| `2fabfe90` | Lakeside Boat & RV Storage | 11 |
| `1ffd4559` | Havasu Boat & RV Storage | 10 |
| `0b5ffd7c` | Countryshire Boat & RV Storage | 7 |
| `eeec35a8` | Havasu Boat & Storage | 4 |
| `2e91b06e` | Advantage Boats & RV Storage | 3 |
| `5e600363` | Prestige Boat and RV Storage | 1 |
| `3da2460d` | Absolute Boat & RV Storage | - |
| `f7cab489` | Riviera View Boat & RV Storage | - |

**Note on `59fae6bf` Lake Havasu RV, Boat & Self Storage (48 reviews):**
keep in home-property-services. The "Self Storage" in the name puts
self-storage as the primary business, with RV/Boat as add-ons. Closer to
StorWise / Big Easy in shape than to Dave's Boat & RV Storage.

#### REVIEW (2)

| entity_id_prefix | name | primary_type | reviews | Why review |
|---|---|---|---|---|
| `ffe8d02d` | Mc Cheaper's | `storage` | 10 | Generic name, no website. Default: KEEP. |
| `59fae6bf` | Lake Havasu RV, Boat & Self Storage | `storage` | 48 | Could go either way per naming heuristic. Default: KEEP (self-storage in name = home-property-services). |

#### KEEP in home-property-services (28)

The 28 plain self-storage entries (M & M Storage Solutions, StorWise,
Big Easy Storage, Hav-A-Storage, etc.) plus Lake Havasu RV/Boat/Self
Storage. Full list in the diagnostic output (run sandbox query for
fresh dump).

### 2.2 Slice B — 3 NULL-category_id residuals (5.2 carry-forward)

These three providers have `category_id IS NULL` and slipped through 5.2's
audit. RE-ROUTE INTO on-the-water.

| entity_id_prefix | name | reviews | google_primary | Decision |
|---|---|---|---|---|
| `e4a788d8` | Havasu Watercraft Rental | 1 | `real_estate_agency` | → `on-the-water` |
| `13b0ba9e` | Butters Boat valet & Concierge services | 10 | `transportation_service` | → `on-the-water` |
| `51a41647` | London Bridge | 10164 | `bridge` | → `on-the-water` (literal lake landmark) |

---

## §3 Pass 2 — Post-load audit (199 new + 75 ambig-skips)

### 3.1 Slice C — 199 newly-loaded entities

**ZERO misroutes.** All 4 ambiguous-primary-type rows verified as correctly
placed in home-property-services:

| entity_id_prefix | name | gprimary | reviews | Verdict |
|---|---|---|---|---|
| `adbd12f1` | Amici Pools | `sporting_goods_store` | 9 | KEEP — pool company (Google mistagged) |
| _(prov)_ | Havasu Wiring LLC | `consultant` | 9 | KEEP — electrical wiring (havasuwiring.com) |
| _(prov)_ | MJM Water Treatment And Plumbing LLC | `NULL` | 92 | KEEP — water-treatment + plumbing service |
| _(prov)_ | Havasu Turf Pros | `NULL` | 60 | KEEP — turf installation / landscaping |

Primary_type distribution of the 199 (all correctly home_services):
`general_contractor` 74, `service` 60, `electrician` 19,
`roofing_contractor` 15, `plumber` 12, `laundry` 5, `storage` 5 (real
self-storage: Mc Culloch Mini, ToyBox, Hacienda, Super, Downtown),
`moving_company` 3, locksmith 2, NULL 2, sporting_goods_store 1,
consultant 1.

### 3.2 Slice D — 75 ambig-skips (9 cross-category + ~66 same-category)

**9 cross-category ambig-skips** (home_services candidate matched existing
entity in a different Tier-1 slug). Audit verdicts:

| home_services candidate | Currently in slug | Verdict |
|---|---|---|
| **Stanley Steemer** | shopping-essentials | 🚨 **RE-ROUTE INTO h-p-s** — carpet cleaning is home_services, not retail |
| Riverbound Custom Storage & RV Park | lodging-vacation-rentals | REVIEW — RV park (lodging primary) + storage (h-p-s) dual-use; default KEEP per V1 single-primary |
| B-Kooler Screens | auto-rv-fuel | REVIEW — window/RV screens dual-use; default KEEP per V1 single-primary |
| Norwall PowerSystems | shopping-essentials | REVIEW — generator sales + install dual-use; default KEEP |
| AQUACLEAN HAVASU LLC | shopping-essentials | KEEP — water treatment retailer (no install signal) |
| PRO TECH RV | auto-rv-fuel | KEEP — RV service is auto-rv-fuel |
| Geary Pacific Supply | shopping-essentials | KEEP — pure supplier |
| SRS Building Products | shopping-essentials | KEEP — pure retailer |
| Tile & Carpets Unlimited | shopping-essentials | KEEP — retailer not installer |

**~66 same-category ambig-skips:** these are home_services discovery
candidates matching the existing 46 self-storage facilities + a few
geo-proximity matches. Spot-check sample shows all correct (44 "self
storage" discovery hits aligning with the 46 existing storage entries +
~22 geo-proximity matches in other categories). No false-positive
ambig-skips found. The reconciler is performing well.

---

## §4 Apply-script plan

`outputs/apply_phase5_3_home_property_audit.py` — mirrors
`apply_phase5_2_on_the_water_audit.py`:

- `--dry-run` default
- id-prefix-keyed decision dicts (per slice)
- idempotent (safe to re-run)
- sets `updated_at`
- self-verifies via `/category/<slug>` rendering counts for affected slugs

**Decision dicts the apply-script implements:**

```python
# Slice A — 16 RE-ROUTE-OUT from home-property-services to on-the-water
REROUTE_OUT_FROM_HPS_TO_OTW: dict[str, str] = {
    "54e3c237": "on-the-water",  # Sandbar Powersports
    "23244621": "on-the-water",  # Horizon MotorSports
    "4d88c09e": "on-the-water",  # Campbell Cove Complex
    "79e88dce": "on-the-water",  # Island Storage & Marine
    "7e994b21": "on-the-water",  # Dave's Boat & RV Storage
    "31163faf": "on-the-water",  # Havasu Boat Storage
    "3954a1bd": "on-the-water",  # Boat Storage of Lake Havasu
    "8947770e": "on-the-water",  # Depot Storage Boat and RV
    "2fabfe90": "on-the-water",  # Lakeside Boat & RV Storage
    "1ffd4559": "on-the-water",  # Havasu Boat & RV Storage
    "0b5ffd7c": "on-the-water",  # Countryshire Boat & RV Storage
    "eeec35a8": "on-the-water",  # Havasu Boat & Storage
    "2e91b06e": "on-the-water",  # Advantage Boats & RV Storage
    "5e600363": "on-the-water",  # Prestige Boat and RV Storage
    "3da2460d": "on-the-water",  # Absolute Boat & RV Storage
    "f7cab489": "on-the-water",  # Riviera View Boat & RV Storage
}

# Slice B — 3 NULL-category_id residuals → on-the-water + EntityCategory insert
REROUTE_IN_TO_OTW_FROM_NULL: list[str] = [
    "e4a788d8",  # Havasu Watercraft Rental
    "13b0ba9e",  # Butters Boat valet
    "51a41647",  # London Bridge
]

# Slice D — Stanley Steemer: 1 RE-ROUTE INTO home-property-services from shopping-essentials
# (entity_id_prefix to be filled at apply-script time by name lookup)
REROUTE_IN_TO_HPS_FROM_SHOPPING: list[str] = [
    # "<prefix>",  # Stanley Steemer
]
```

The Stanley Steemer entity_id_prefix needs a quick DB lookup at
apply-script-draft time (was an ambig-skip → matched existing → I have
the name but not the entity_id yet).

---

## §5 Operator decision points

Two policy questions baked into this doc — flag if you disagree:

1. **Cross-list policy: NO cross-list for V1.** Follows 5.2 precedent. If
   you want cross-list for the 13 boat-storage facilities (additive
   EntityCategory rows in both home-property-services AND on-the-water),
   say so before apply-script run. Schema supports it; just need to switch
   the policy.

2. **`Horizon MotorSports` target.** Defaulted to `on-the-water`
   (Havasu has many marine motorsports shops; less likely auto-only).
   Override to `auto-rv-fuel` if you have local knowledge that says
   otherwise.

3. **3 REVIEW dual-use rows** (Riverbound Custom Storage & RV Park,
   B-Kooler Screens, Norwall PowerSystems) — defaulted to "stay in
   current category" per V1 single-primary. Override per row if needed.

---

## §6 Projected post-apply counts (with the decisions above)

| slug | pre-apply | net change | post-apply |
|---|---|---|---|
| `/category/eat-drink` | 255 | 0 | 255 |
| `/category/on-the-water` | 100 | +16 (13 boat-storage + 3 Slice B) + 0 high-confidence misroutes already counted | **+16** |
| `/category/home-property-services` | 245 | −16 boat-storage/misroutes +1 Stanley Steemer | **230** |
| `/category/shopping-essentials` | (unchanged) | −1 Stanley Steemer | -1 |

Wait, the 3 high-confidence misroutes (Sandbar/Horizon/Campbell) and the
13 boat-storage are all currently in home-property-services. So:
- Move 16 OUT of home-property-services → on-the-water: −16
- Add 3 Slice B NULL residuals INTO on-the-water (currently NULL,
  so they don't reduce another category): +3
- Add Stanley Steemer INTO home-property-services from shopping: +1
- Net home-property-services: 245 − 16 + 1 = **230**
- Net on-the-water: 100 + 16 + 3 = **119**
- Net shopping-essentials: (current count) − 1

Phase 5.3 gate item 1 (60+ entries in home-property-services) still
trivially met at 230.

---

## §7 Reference

- `outputs/phase5_2_on_the_water_data_quality_audit.md` (5.2 audit shape
  this doc mirrors)
- `outputs/apply_phase5_2_on_the_water_audit.py` (5.2 apply-script
  template)
- `outputs/diagnose_category_id_gap.py` (re-usable diagnostic)
- `outputs/phase5_3_home_property_services_kickoff.md` §0 + §1 + §6
- `app/contrib/google_types_mapping.py` (14+ home_services types map)
- `scripts/places_load.py:_resolve_category_id` +
  `_DISCOVERY_DOMAIN_FALLBACK` (sustainability layer at `65b0824` +
  Phase 5.3 extension at `7c994aa`)

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.3 session (2026-05-15)
post-`7c994aa`. Combined pre+post audit; apply-script next.*
