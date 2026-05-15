# Phase 5.2 — On the Water — Data-quality audit

> Mirrors `outputs/phase5_1_eat_drink_data_quality_audit.md` shape.
> Audits the 73 entities at `/category/on-the-water` post-Layer-1+Layer-2
> for non-water leak, plus the `auto-rv-fuel` (41) + `shopping-essentials`
> (35) rows from this load for the boat-dealer-as-car_dealer follow-on
> open since `8800761`.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.2 session
> (2026-05-15) post-`87d0703`.

---

## §1 Summary

Inventory dump:
`outputs/phase5_2_audit_inventory.txt` (raw output of the diagnostic).

| Slice | Rows examined | KEEP | RE-ROUTE-OUT | DEACTIVATE | REVIEW |
|---|---|---|---|---|---|
| A — at `/category/on-the-water` | 73 | 67 | 2 | 0 | 4 |
| B — `auto-rv-fuel` (this load) | 41 | 39 | 2 | 0 | 0 |
| C — `shopping-essentials` (this load) | 35 | 6 | 27 | 0 | 2 |
| **Net effect on on-the-water** | | | **+27 in, −2 out = +25** | | |

Projected: `/category/on-the-water` 73 → **~98** entities post-cleanup.

---

## §2 Slice A — entities currently at `/category/on-the-water`

### 2.1 RE-ROUTE-OUT (2)

| entity_id | name | primary_type | Decision |
|---|---|---|---|
| `76280ea0` | 3-T's RV Products, Inc | `point_of_interest` | → `auto-rv-fuel` (RV products, not boat) |
| `6f453929` | JR RV Rentals | `service` | → `lodging-vacation-rentals` (RV-only rental) |

### 2.2 REVIEW (4)

Discovery domain was `lake_recreation` so they surfaced from a boat-related
query, but the names suggest auto. Operator can confirm via Google search
+ flip to DEACTIVATE or RE-ROUTE-OUT-TO-AUTO-RV-FUEL if needed; the
apply-script defaults to KEEP for these.

| entity_id | name | primary_type | Why review |
|---|---|---|---|
| `77692a10` | Chong Servicenter | `service` | Generic auto repair? |
| `35d59b7a` | HBC MOTORS | `service` | Auto/motorcycle? |
| `b9efdb34` | West Coast Drives | `service` | Driveline? |
| `538b607f` | GO FAST US / T1R.COM LLC | `service` | Performance — could be boat or auto |

### 2.3 KEEP (67)

The 4 `marina` rows + `ferry_service` + `fishing_pier` + 4 `tour_agency`
boat-tour rows + 1 `tourist_attraction` (London Bridge Beach boat rental)
+ 1 `tourist_information_center` (Go Lake Havasu) + Havasu Cove (OSM) +
the 11 mobile-detailing shops (came from "boat detailing" discovery —
operator can deactivate any obvious car-only ones via a follow-on if
needed) + the 44 service rows that are clearly boat rentals / charters /
marine services / yacht clubs.

---

## §3 Slice B — `auto-rv-fuel` (this load)

### 3.1 RE-ROUTE → on-the-water (2)

Pure boat businesses Google tagged with vehicle types:

| entity_id | name | primary_type | Why |
|---|---|---|---|
| `e15c7638` | Marine One Motorsports | `service` | "Marine" + boat-only |
| `aa47b572` | Connolly Marine Performance | `store` | Marine performance shop |

### 3.2 KEEP in auto-rv-fuel (39)

The 9 RV dealers (`car_dealer`), 18 RV-and-vehicle repairs (`car_repair`),
5 detailing shops (`car_wash`), 5 sales/service hybrids that mention BOTH
RV/auto AND marine. Those last 5 are arguably dual-category (auto-rv-fuel
+ on-the-water) — but V1 schema is single-primary EntityCategory so we
keep them in auto-rv-fuel. Phase 6 can add secondary EntityCategory rows
if dual-category surfacing matters; deferred.

---

## §4 Slice C — `shopping-essentials` (this load)

### 4.1 RE-ROUTE → on-the-water (27)

This is the bulk of the cleanup. Google tagged Havasu boat manufacturers
+ marine retailers as `store`/`supplier`/`sporting_goods_store`, so they
landed in shopping-essentials. They belong on-the-water.

**Boat manufacturers / dealers (10):**

| entity_id | name |
|---|---|
| `ca6b3ea1` | Cheetah Power Boats |
| `5cc611eb` | Advantage Boats |
| `e7f95f35` | Domn8er Power Boats |
| `8af3d328` | Hallett Boats |
| `351532b5` | HTM Performance Boats |
| `cd69eba9` | Interceptor Boats Lake Havasu |
| `daf7b64e` | Nordic Boats |
| `e132f4fc` | Maxed Out Marine |
| `34f69bdc` | R & D Marine |
| `516d455c` | IMAGE MARINE |

**Marine retail / parts (6):**

| entity_id | name |
|---|---|
| `1fdedd6d` | West Marine |
| `4abf5327` | Marina Store |
| `e34bd1a2` | Total Marine Pros and Powersports |
| `537f371d` | Alco Marine Sales & Services |
| `ea22e86f` | Germaine Marine |
| `eff14e6f` | Shimmer Boat Service |

**Watersports rentals / services (5):**

| entity_id | name |
|---|---|
| `f68da5e2` | All Seasons Water Sports |
| `99028be4` | Nautical Watersports |
| `cce85063` | Pro Watercraft |
| `9118ee9d` | Wet Monkey Powersport Rentals |
| `ef949e05` | Wolf Watersports |

**Fishing (4):**

| entity_id | name |
|---|---|
| `8fb10bfa` | Bass Tackle Master |
| `ca465d30` | Mc Coy Fishing Line Inc |
| `c13c022f` | Project 72 Custom Baits |

**Marine services (2):**

| entity_id | name |
|---|---|
| `ad258025` | Fallon Marine LLC |
| `2d7ab66d` | Prestige Marine |
| `9ae51449` | Xtreme Speed And Marine |

(27 total above; the Bass Tackle/Mc Coy/Project 72 group has 3 rows so the
fishing subtotal is 3 not 4 — listing exact 27 in the apply-script's dict.)

### 4.2 KEEP in shopping-essentials (6)

| entity_id | name | Why |
|---|---|---|
| `33b4d5a3` | Big 5 Sporting Goods | Generic sporting goods chain — not boat-only |
| `da327e86` | Anderson PowerSports | Generic powersports (ATVs, jet skis, motorcycles) |
| `64b1eb3d` | Anderson Powersports Lake Havasu | Same |
| `c5a5868b` | Anderson AZ West | Same |
| `c3958b0f` | Just 4 Fun Powersports | Same |
| `e55e7833` | Haulinit.com LLC | Trailer hauling — vehicle-related |
| `066a6576` | Epic_lifestyles | Generic — REVIEW; defaulting to KEEP |
| `f227c238` | Lead Dog Motorsports | Generic powersports |

(Operator can flip any of these to RE-ROUTE in the apply-script if they
confirm boat-only on Google.)

### 4.3 REVIEW (2)

| entity_id | name | Why |
|---|---|---|
| (deferred) | (any operator wants to second-guess from §4.2 list) | |

---

## §5 Apply script

`outputs/apply_phase5_2_on_the_water_audit.py` — id-keyed dict in the
5.1 pattern. `--dry-run` first, idempotent, sets `updated_at`,
self-verifies via `/category/<slug>` rendering count for both
on-the-water and the slugs we're re-routing out of.

Per-action behavior:
- **`reroute_to_on_the_water`** — sets `Provider.category_id = on-the-water id`,
  removes existing EntityCategory rows for the entity, inserts a new
  EntityCategory(on-the-water, is_primary=True). Stamps `updated_at`.
- **`reroute_to_auto_rv_fuel`** — same mechanism, target = `auto-rv-fuel`.
- **`reroute_to_lodging`** — same mechanism, target = `lodging-vacation-rentals`.
- **`deactivate`** — sets `Provider.is_active = False` AND
  `Entity.is_active = False`. Removes EntityCategory rows so the entity
  drops off all `/category/<slug>` routes.

---

## §6 Post-apply expected state

| Slug | Pre-audit | Post-audit | Δ |
|---|---|---|---|
| on-the-water | 73 | ~98 | +25 (27 in, 2 out) |
| auto-rv-fuel | 41 | ~40 | −1 (Marine One out, +1 from on-the-water = +1 / out = -1 / net 0... let me recheck — actually +1 from on-the-water "3-T's RV" + 0 since the 2 Marine ones go OUT to on-the-water → net change is -1) |
| shopping-essentials | 35 | 8 | −27 |
| lodging-vacation-rentals | 23 | 24 | +1 (JR RV Rentals in) |

**Phase 5.2 acceptance gate item 1** stays CLEARED with even more headroom
(target was 25+; post-audit ~98).

---

## §7 Open follow-ons (not blocking 5.2 ship)

- Phase 5.3 (Home & Property Services) will hit the same generic-types
  issue with `home_services` discovery domain. The audit-doc + apply-script
  pattern here is the template.
- Dual-category EntityCategory (Phase 6 schema decision) — if surfacing
  hybrid auto/boat businesses (the 5 §3.2 KEEPs that mention both) at
  both `/category/auto-rv-fuel` AND `/category/on-the-water` matters,
  EntityCategory has `is_primary` already so a secondary linkage is just
  inserts. Defer to Phase 6 dispatch.
- The 11 mobile-detailing shops in §2.3 — operator may want to deactivate
  the obvious auto-only ones via a follow-on.
- The 4 §2.2 REVIEW rows — operator confirms via Google + edits the apply
  script.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.2 session
(2026-05-15) post-`87d0703`. Apply script + commit pending operator
review of this doc.*
