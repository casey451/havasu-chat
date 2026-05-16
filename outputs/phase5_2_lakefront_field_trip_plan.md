# Phase 5.2 — Lakefront Field-Trip Plan (Layer 5 + boat_access completion)

> **What this is:** the operator-facing planning artifact for the
> highest-value Layer 5 sweep called out in
> `docs/maintainability/manual_recovery_checklist.md` §2 + §7 + §3.
> Two trips, ~half-day each, that close the remaining survey work
> after Phase 5.2's data plane shipped 2026-05-15 at `81cd70c`+.
>
> **What it covers:**
> 1. Backfill the 3 `{}` placeholder marinas + verify the 2
>    evidence-populated ones (closes a known soft-edge of gate item 2)
> 2. Surface Layer 5 entities Google + OSM missed (BLM primitive
>    ramps, informal beach access, fishing pull-offs, scenic overlooks)
>
> **Authored by:** Cowork primary, Phase 5 lane, end of Phase 5.2
> session (2026-05-15).

---

## §1 The two trips

Per the checklist §2 boat-ramps note: "Plan a single Saturday morning
sweep covering the southern lake (Cattail Cove + Site Six) and a second
weekday morning covering the channel (English Village + Lake Havasu
State Park)."

### Trip A — Saturday morning, southern lake (~4-5h)

Goal: backfill `Havasu Cove` marina + sweep Cattail Cove, Site Six,
Castle Rock beaches, Pittsburgh Point. Saturday morning is intentional
— peak boater activity, so ramp wait times and parking saturation are
visible.

Route (south-to-north loop, ~30 mi):

| Stop | Time | Targets | Capture |
|---|---|---|---|
| 1. Cattail Cove State Park | 8-9am | Ramp + beaches + camping | boat_access marina shape; photo of ramp lanes |
| 2. Pittsburgh Point bluffs | 9-9:30am | Scenic overlooks + viewpoint pull-offs | overlook entries; photos |
| 3. Castle Rock beaches | 9:30-10am | Informal beach access points | beach shape; photo per access point |
| 4. Site Six public ramp | 10-11am | Multi-lane public ramp + adjacent fishing pier | public_ramp shape; trailer parking count; weekend wait estimate |
| 5. Havasu Cove area | 11-12pm | OSM way 622179700 entity (`5a25ca41`) | marina shape; verify whether private/public; slip count if any |

### Trip B — Weekday morning, channel + north (~3-4h)

Goal: backfill `Lake Havasu Yacht Club` + verify `Lake Havasu Marina`
+ `Havasu Riviera Marina` + `Riverside Boat Dock Sales`. Weekday
morning avoids weekend rush; gatehouse staff is more available for
questions about transient_dock policy + slip rental terms.

Route (channel north, ~10 mi):

| Stop | Time | Targets | Capture |
|---|---|---|---|
| 1. Lake Havasu Marina (`8ce77957`) | 8-9am | Verify `ramps=6`, `fuel=true`; backfill `slips`, `haul_out`, `pump_out`, `transient_dock` | Update boat_access; ask gatehouse for transient policy |
| 2. English Village dock | 9-9:30am | Channel-side venues + Shugrue's Cornerside Bakery water_adjacent decision (carry-forward from 5.1) | Note any new Layer 5 dock/access entities |
| 3. Lake Havasu State Park marina | 9:30-10:30am | Multi-ramp state park (illustrative entry in rubric §3.1) | If not in DB: new entry with marina shape |
| 4. Lake Havasu Yacht Club (`4b5b7c2a`) | 10:30-11am | Full survey — private vs members-only; slip count; transient policy | Update boat_access (or set to NULL if private-only) |
| 5. Riverside Boat Dock Sales (`7265d2ca`) | 11-11:30am | Verify: marina vs shoreline_commercial (boat dealer with dock?) | Confirm shape; if dealer-only, may need re-route to auto-rv-fuel + NULL boat_access |
| 6. Havasu Riviera Marina (`a63febcb`) | 11:30am-12pm | Verify `ramps=6`, `fuel=true`; backfill `slips`, `haul_out`, `pump_out`, `transient_dock` | Update boat_access |

---

## §2 The 5 marinas — boat_access status post-`apply_on_the_water_boat_access_marinas.py`

| entity_id | Marina | Current state | Trip B target |
|---|---|---|---|
| `8ce77957` | Lake Havasu Marina | `{type, ramps:6, fuel:true, fee_required:true, fee_notes}` | Backfill `slips`, `haul_out`, `pump_out`, `transient_dock` |
| `a63febcb` | Havasu Riviera Marina | `{type, ramps:6, fuel:true, fee_required:true, fee_notes}` | Backfill `slips`, `haul_out`, `pump_out`, `transient_dock` |
| `4b5b7c2a` | Lake Havasu Yacht Club | `{}` placeholder | Full survey (or NULL if private-only) |
| `7265d2ca` | Riverside Boat Dock Sales | `{}` placeholder | Confirm marina vs shoreline_commercial; re-shape or re-route |
| `5a25ca41` | Havasu Cove (OSM) | `{}` placeholder | Full survey — confirm public vs private |

After Trip B, write the backfill apply-script at
`outputs/apply_on_the_water_boat_access_marinas_backfill.py` (same
pattern; populates the verified fields per the rubric).

---

## §3 Layer 5 prompts — what to look for that Google/OSM missed

Per the checklist §2:

### Public ramps + access points
- BLM-land primitive launches not on Google or OSM (often unsigned pull-offs)
- Cattail Cove ramp (may be in DB; verify)
- Lake Havasu State Park ramps (multiple — check if all entered)
- Fishing-only access points (bank fishing pull-offs along Hwy 95)

### Public beaches
- All of Lake Havasu State Park's individual beach segments (Windsor, Crazy Horse, etc.)
- Castle Rock area beaches (multiple informal pull-offs)
- Mesquite Bay south beaches
- Rotary Park beach (cross-check; should be in `outdoors-parks-trails`)
- London Bridge Beach (cross-check; verify in DB)

### Fishing access points
- AZ Game & Fish fishing access map (`https://www.azgfd.com`)
- Bank-fishing pull-offs along Hwy 95

### Scenic overlooks (less time-sensitive)
- Pittsburgh Point bluffs
- SARA Park trail viewpoints
- Crystal Beach overlook
- Pull-offs along Hwy 95 with lake panorama

---

## §4 Capture / entry workflow

For each new Layer 5 entity:

1. **Drop a pin** in Google Maps or note GPS coords (BLM/primitive
   ramps often have no street address).
2. **Photograph** — at least one wide shot + one ramp-lane / dock /
   beach close-up. Phase 6 hero images depend on operator photos.
3. **Note in field notebook** (or voice memo):
   - Name (official or locals')
   - Type (State Park / city / BLM / private)
   - Boat-access details per the rubric shape
   - Notes (fee, parking count, restroom, peak-hour observation)
4. **Back at desk**, write `outputs/phase5_2_layer5_entries.md`
   with each entry. For each, queue an INSERT via
   `apply_phase5_2_layer5_inserts.py` (new apply-script in the 5.1/5.2
   pattern) — sets `source='operator'`, `entity_type='place'`,
   `category_id=on-the-water`, `boat_access` per shape, plus a
   `EntityCategory(is_primary=True)` row.

The reconciler will catch geo collisions with the 100 existing
on-the-water entities (ambiguous → operator review), so duplicates
won't sneak in.

---

## §5 Post-trip apply-script template

The shape for the backfill apply-script Trip B will produce. Operator
fills in cells from field notes:

```python
BOAT_ACCESS_BACKFILL: dict[str, dict[str, Any]] = {
    # Lake Havasu Marina — backfill verified fields onto existing payload
    "8ce77957": {
        "type": "marina",
        "ramps": 6,
        "slips": ___,          # backfill from field notes
        "fuel": True,
        "haul_out": ___,       # bool, field-verified
        "pump_out": ___,       # bool, field-verified
        "transient_dock": ___, # bool, field-verified
        "fee_required": True,
        "fee_notes": "Day-use $21 at the gatehouse; slip rentals separate",
    },
    # Havasu Riviera Marina — same pattern
    "a63febcb": { ... },
    # Lake Havasu Yacht Club — full populate or set NULL if private-only
    "4b5b7c2a": { ... },
    # Riverside Boat Dock Sales — confirm shape; either marina or shoreline_commercial
    "7265d2ca": { ... },
    # Havasu Cove — full populate
    "5a25ca41": { ... },
}
```

---

## §6 Coordination with the gate

Phase 5.2 acceptance gate item 2 ("Every marina has boat_access JSON
populated") is already CLEARED at `81cd70c`+ — `{}` placeholders count
as populated per the rubric §2 lock. Trip B upgrades them to fully
populated, which strengthens Phase 6.4 boat-mode UI rendering but
isn't gate-blocking.

Trip A's Layer 5 inserts ADD entities to /category/on-the-water (no
removal). Re-running the gate verification post-trips will show
higher counts but still all 6 items PASS.

---

## §7 Reference

- `docs/operations/boat_access_rubric.md` — the 4 canonical shapes +
  NULL-vs-`{}`-vs-populated semantic lock
- `docs/maintainability/manual_recovery_checklist.md` §2 + §7 — the
  source checklist this plan derives from
- `outputs/phase5_1_boat_access_candidates.md` — the 5.1 worksheet
  covering 12 shoreline eat-drink venues (cross-list overlap with Trip B
  for English Village waterfront, London Bridge Resort, The Nautical)
- `outputs/apply_on_the_water_boat_access_marinas.py` — the current
  state of the 5-marina boat_access apply
- `outputs/phase5_2_gate_verification.py` — re-run after trips to
  confirm gate items still all pass

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.2 close-out
(2026-05-15) post-`81cd70c`. Trip execution is operator-led; Cowork
companion writes the backfill apply-script + Layer 5 inserts artifact
when operator returns with field notes.*
