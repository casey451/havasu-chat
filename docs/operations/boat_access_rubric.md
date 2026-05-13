# Boat Access JSON Rubric — Phase 5 Operator-Curated Entry

> **Purpose:** Lock the per-venue-type JSON shape for `entities.boat_access` (Phase 3.1 column) so the Phase 6 boat-mode toggle, profile-page boat-access region, and search-result boat-attribute filtering all consume consistent keys. Without this rubric, the operator types varying JSON shapes per entity during Phase 5 field entry and Phase 6 rendering becomes a per-row reverse-engineer.
>
> **Status:** authored 2026-05-13 at session-23-extension-3 alongside Phase 5 lead-up. Lives at `docs/operations/boat_access_rubric.md` per Phase 5 prereq checklist §3.3.i.
>
> **Schema:** `entities.boat_access` is a `JSON` column (Phase 3.1 migration `d0e1f2a3b4c5`). Nullable. NULL means "not applicable to this venue" (e.g., an inland restaurant with no water proximity). An empty object `{}` means "applicable but unknown — operator should follow up." A populated object follows one of the four shapes below depending on venue type.
>
> **Phase 6 consumer:** the boat-mode toggle in the header (per master plan §4 Phase 6) reads `boat_access` to filter entities + populate the profile-page top-of-fold region. Phase 8 alerts may read certain keys (`fuel`, `pump_out`) for boater-targeted advisories. Consistent keys here directly map to consistent UI surfaces there.

---

## §1 Shape per venue type

Four canonical shapes, indexed by venue type. Operator picks the shape matching the entity's primary nature; secondary shapes can be omitted entirely rather than partially populated.

### §1.1 Marinas + full-service docks

For entities where boating is the **primary** activity. Includes private marinas, public marinas, full-service docks with fuel.

```json
{
  "type": "marina",
  "ramps": 3,
  "slips": 240,
  "fuel": true,
  "haul_out": true,
  "pump_out": true,
  "transient_dock": true,
  "fee_required": true,
  "fee_notes": "$15 day-use launch; slip rentals separate"
}
```

| Key | Type | Meaning |
|---|---|---|
| `type` | `"marina"` (literal) | Locks the shape for the renderer + filter |
| `ramps` | int | Number of trailerable boat ramps on-site (count multiple lanes as 1 if they share an approach) |
| `slips` | int | Number of permanent or transient slips; round to nearest 10 for >100; explicit count for ≤100 |
| `fuel` | bool | Marine fuel sold on-site (gas, diesel, or both) |
| `haul_out` | bool | Travel-lift or sling available for haul-out |
| `pump_out` | bool | Waste pump-out station available |
| `transient_dock` | bool | Short-term tie-up for visitors (overnight or day-rate, not seasonal slip) |
| `fee_required` | bool | TRUE if any non-zero fee applies for the primary boater interaction (launch, slip, fuel surcharge); FALSE if free public access |
| `fee_notes` | string | Short operator note on fee structure; omit if `fee_required=false` |

### §1.2 Public ramps + access points

For entities where boat-launching is the **only** boating interaction. Includes city-maintained public ramps, BLM-land ramps, state-park boat launches.

```json
{
  "type": "public_ramp",
  "trailer_ramp": true,
  "kayak_launch": false,
  "dock_walk_m": 12,
  "parking_spaces": 24,
  "trailer_parking_spaces": 18,
  "fee_required": false,
  "restroom": true,
  "lighted": true
}
```

| Key | Type | Meaning |
|---|---|---|
| `type` | `"public_ramp"` (literal) | Locks the shape |
| `trailer_ramp` | bool | Suitable for trailered boats (motorboats, ski boats, fishing rigs) |
| `kayak_launch` | bool | Easy hand-carry / dolly launch for kayaks, SUPs, canoes |
| `dock_walk_m` | int \| null | Approximate walking distance in meters from parking to dock; `null` if no fixed dock |
| `parking_spaces` | int | Total parking spaces (passenger + trailer combined if striped together) |
| `trailer_parking_spaces` | int | Parking spaces specifically sized/striped for trailer rigs |
| `fee_required` | bool | TRUE if any per-launch or daily fee; FALSE for free public access |
| `restroom` | bool | On-site restroom (vault toilet, flush, or porta-john) |
| `lighted` | bool | After-dark lighting at ramp + parking |

### §1.3 Beaches + shoreline access

For entities where the **shoreline itself** is the primary feature. Includes public beaches, designated swim areas, shoreline parks with water access.

```json
{
  "type": "beach",
  "trailer_ramp": false,
  "kayak_launch": true,
  "swimming_marked": true,
  "lifeguard": false,
  "shade_structures": 4,
  "parking_spaces": 80,
  "fee_required": true,
  "fee_notes": "State Park day-use $15/vehicle",
  "motorized_boats_ok": false
}
```

| Key | Type | Meaning |
|---|---|---|
| `type` | `"beach"` (literal) | Locks the shape |
| `trailer_ramp` | bool | Adjacent trailer ramp (rare for designated beaches; often FALSE) |
| `kayak_launch` | bool | Sand-or-gravel launch suitable for kayaks/SUPs from the beach |
| `swimming_marked` | bool | Buoy-marked swim area separating swimmers from motorized boats |
| `lifeguard` | bool | Seasonal or permanent lifeguard staffing |
| `shade_structures` | int | Count of ramadas, gazebos, or canopied picnic structures |
| `parking_spaces` | int | Approximate total spaces |
| `fee_required` | bool | TRUE if vehicle / day-use / parking fee; common for State Parks |
| `fee_notes` | string | Short structure note; omit if `fee_required=false` |
| `motorized_boats_ok` | bool | TRUE if motorboats can pull up to the shoreline (some swim-only beaches forbid this) |

### §1.4 Shoreline commercial (dock-and-dine, lakefront retail)

For entities that are **primarily commercial** (restaurant, retail, lodging) but offer boat-accessible secondary interaction. Cross-listed: the entity's primary category is eat-drink / shopping-essentials / lodging-vacation-rentals; `boat_access` adds the water-side detail.

```json
{
  "type": "shoreline_commercial",
  "dockable": true,
  "ramp_walkable_m": 80,
  "guest_dock": true,
  "guest_dock_slips": 4,
  "guest_dock_time_limit_min": 90,
  "fuel": false
}
```

| Key | Type | Meaning |
|---|---|---|
| `type` | `"shoreline_commercial"` (literal) | Locks the shape |
| `dockable` | bool | TRUE if a boat can approach the venue's shoreline + tie up (even informally); FALSE for shoreline venues without dock infrastructure |
| `ramp_walkable_m` | int \| null | Distance in meters from the nearest public ramp to the venue's front door; `null` if no nearby ramp |
| `guest_dock` | bool | Dedicated guest tie-up (dock-and-dine restaurants, lakefront retail with customer mooring) |
| `guest_dock_slips` | int | Count of guest slips when `guest_dock=true` |
| `guest_dock_time_limit_min` | int \| null | Posted time limit in minutes; `null` if unlimited or unposted |
| `fuel` | bool | Marine fuel sold on-site (unusual for shoreline commercial but happens at some marinas with restaurants) |

---

## §2 NULL vs `{}` vs populated — semantic locks

Three states matter for Phase 6 rendering:

| `boat_access` value | Meaning | Phase 6 rendering |
|---|---|---|
| `NULL` (default) | Not applicable to this venue. Used for inland venues with no water proximity. | No boat-mode-related UI; venue invisible to boat-mode filter |
| `{}` (empty object) | Applicable but unknown — operator hasn't reviewed yet | "boat access info coming soon" placeholder; venue visible to boat-mode filter as low-info |
| `{"type": "...", ...}` populated | Reviewed by operator | Full boat-mode UI surfaces; visible to boat-mode filter as primary result |

**Operator rule:** during Phase 5 field entry, every entity in `on-the-water` MUST have `boat_access` populated (not NULL, not `{}`). Entities in `eat-drink` / `shopping-essentials` / `lodging-vacation-rentals` that the operator knows are shoreline-accessible MUST have `boat_access` populated with the `shoreline_commercial` shape. All other entities leave `boat_access = NULL`.

---

## §3 Examples — real Lake Havasu entities

Concrete examples to anchor the shapes. These are illustrative — operator should re-verify counts during field entry.

### §3.1 Lake Havasu State Park marina (illustrative)

```json
{
  "type": "marina",
  "ramps": 4,
  "slips": 0,
  "fuel": false,
  "haul_out": false,
  "pump_out": true,
  "transient_dock": false,
  "fee_required": true,
  "fee_notes": "State Park day-use $15/vehicle; ramp fee included"
}
```

Note: state-park ramp is a `marina` shape (not `public_ramp`) because it has multiple ramps + pump-out + State Park fee structure. The `slips: 0` is intentional — no slip rentals on-site.

### §3.2 Site Six public ramp (illustrative)

```json
{
  "type": "public_ramp",
  "trailer_ramp": true,
  "kayak_launch": true,
  "dock_walk_m": null,
  "parking_spaces": 40,
  "trailer_parking_spaces": 30,
  "fee_required": false,
  "restroom": true,
  "lighted": true
}
```

Note: `dock_walk_m: null` because the ramp is direct-into-water with no fixed dock walk required. `lighted: true` because the city installed LED fixtures at the parking + ramp approach.

### §3.3 London Bridge Beach (illustrative)

```json
{
  "type": "beach",
  "trailer_ramp": false,
  "kayak_launch": true,
  "swimming_marked": true,
  "lifeguard": false,
  "shade_structures": 6,
  "parking_spaces": 120,
  "fee_required": false,
  "motorized_boats_ok": false
}
```

Note: `motorized_boats_ok: false` because of the swim-area buoy line + adjacent channel traffic. `shade_structures: 6` is the ramada count at last operator walk.

### §3.4 Pier 19 Bar & Grill (illustrative shoreline_commercial)

```json
{
  "type": "shoreline_commercial",
  "dockable": true,
  "ramp_walkable_m": 200,
  "guest_dock": true,
  "guest_dock_slips": 8,
  "guest_dock_time_limit_min": 120,
  "fuel": false
}
```

Note: Pier 19's primary category is `eat-drink`; the `boat_access` field adds the shoreline-commercial detail. Phase 6 boat-mode filter surfaces this venue alongside on-the-water entities; boat-mode-off mode treats it as a regular restaurant.

---

## §4 Operator entry tips

- **One shape per entity.** Don't mix keys across shapes. If the venue feels like both a marina and shoreline_commercial (e.g., a marina with a restaurant), pick the primary nature for the entity's category + populate `boat_access` with the matching shape. The restaurant gets its own entity row with `shoreline_commercial` shape.
- **Counts: estimate when needed.** `parking_spaces` doesn't need to be exact — round to the nearest 10 for venues over 100 spaces. `slips` count similarly. The data is for "boater plans their day" UX, not for facility planning.
- **`null` vs `0` matters for ints.** `dock_walk_m: null` means "no fixed dock," not "the dock is right at the parking." Use `0` only when there's truly a zero-meter walk. Phase 6 renders `null` differently from `0` ("direct water access" vs "0m walk to dock").
- **Booleans should be definitive.** If unsure, leave the entity at `{}` until the field-trip pass confirms. Don't guess.
- **`fee_notes` is operator-readable, not user-readable directly.** Phase 6 may render the note verbatim OR may use it as the basis for a "fees apply" pill — the renderer can decide. Keep it short (under 80 chars) and factual.
- **Re-visit annually.** Marina slip counts, ramp fees, lifeguard schedules change. Once a year, operator walks the on-the-water entities and updates the JSON. Phase 8 doesn't auto-detect these changes.

---

## §5 Validator (deferred)

Phase 6 may ship a Pydantic schema validator at `app/schemas/boat_access.py` that enforces the four shapes at admin-form-submit time. For Phase 5 (operator-driven direct DB SQL), no validator runs — the operator is responsible for shape consistency. The rubric in this doc is the contract.

If during Phase 5 the operator surfaces a shape that doesn't fit any of the four canonical types (e.g., a kayak-only rental venue that's neither commercial nor a public ramp), document it in §6 below and let Cowork primary triage whether to add a fifth shape OR fit the venue into one of the existing four with notes.

---

## §6 Phase 5 surface gaps (operator-amended as Phase 5 runs)

Empty at authoring. Operator adds entries here when Phase 5 field entry surfaces a venue that doesn't fit cleanly:

- *(no entries yet — Phase 5 field entry will populate)*

---

## §7 Reference

- Phase 3.1 migration `d0e1f2a3b4c5_phase3_schema_pass` (Entity.boat_access JSON column)
- Phase 5 prereq checklist `outputs/phase5_prereq_checklist.md` §3.3.i (lock-the-rubric task)
- Phase 5 brief `outputs/cursor_brief_phase_5_tier_1_data.md` §3.2 (on-the-water playbook)
- Phase 6 boat-mode toggle (master plan §4 Phase 6 — UI consumer)
- Phase 8 alerts (master plan §4 Phase 8 — fuel + pump_out keys may surface in boater advisories)

---

*Authored at session-23-extension-3 (2026-05-13) alongside Phase 5 lead-up artifacts. Lives at `docs/operations/boat_access_rubric.md`. Cowork primary or operator amends §6 as Phase 5 surfaces real shape gaps.*
