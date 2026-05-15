# Phase 5.1 Field Entry — `boat_access` Candidate List (Shoreline Eat & Drink)

> **What this is:** a **survey worksheet**, not a runnable artifact. Cowork
> identified the 12 shoreline / dock-and-dine eat-drink entities in the loaded DB,
> grouped them by waterfront cluster, and pre-filled what web research solidly
> supports. The remaining fields (`guest_dock_slips`, `ramp_walkable_m`, etc.) are
> genuine boat-survey measurements — per `boat_access_rubric.md` §4 ("Booleans
> should be definitive. If unsure, leave the entity at `{}`. Don't guess"), Cowork
> does **not** fill those. This doc turns the operator's survey from "which
> restaurants do I even check?" into "here's the list, here's what's pre-confirmed,
> here's what to measure."
>
> **Best paired with** the runbook §3 "English Village + Channel sweep" field trip
> — `manual_recovery_checklist.md` §7 already ranks that sweep highest-value, and
> it physically covers most of this list.
>
> **DB read method:** `/tmp` copy (the mount can't open `events.db` directly —
> gotcha #4/#15). All 12 entity_ids + 4 category-artifact ids verified against the
> live DB on 2026-05-15.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat
> (post-`d34d4c3`, 2026-05-15). Brand-new `outputs/` file — safe under the
> parallel-chat scope lock.

---

## §1 The shape (from `boat_access_rubric.md` §1.4)

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

`dockable` = a boat can approach the shoreline + tie up, even informally.
`guest_dock` = a *dedicated* guest tie-up. `ramp_walkable_m` = meters from the
nearest public ramp to the front door (`null` if no nearby ramp).
`guest_dock_time_limit_min` = posted limit (`null` if unlimited/unposted).
Per rubric §2: shoreline-accessible eat-drink entities the operator **knows** are
accessible MUST be populated with this shape; unsure → leave at `{}`; not
shoreline → leave `NULL`.

## §2 The 12 shoreline eat-drink candidates

**Updated 2026-05-15** with a deeper web-research pass (Cowork sub-agent). The
`dockable` and `guest_dock` booleans below are now web-confirmed where evidence
exists; `unknown` means no evidence was found — the operator confirms those
on-site. The numeric fields (`guest_dock_slips`, `guest_dock_time_limit_min`,
`ramp_walkable_m`, `fuel`) always need the field survey — that's the "still to
survey" column.

### Cluster A — English Village (Bridgewater Channel, 1420/1425 McCulloch Blvd N)

Shugrue's, Barley Brothers, and Javelina Cantina are a restaurant group of
"dock-and-dine destinations" on the channel; the others share the English Village
channel frontage. HEAT Bar's own site has a "Dock Your Boat" page (onsite docks +
slip rental).

| Entity | entity_id | `dockable` | `guest_dock` | Still to survey |
|---|---|---|---|---|
| Shugrue's Restaurant and Brewery Group | `c1c8829c-b200-49ac-8cab-f69bf7ff23bd` | **yes** (golakehavasu) | **yes** (golakehavasu — dock for boat-in dining) | slips, time limit, `ramp_walkable_m`, `fuel` |
| HEAT Bar | `f491e591-256f-4dc7-8280-42ea83d584f8` | **yes** (heathotel.com) | **yes** (heathotel.com "Dock Your Boat" + slip rental) | slips, time limit, `ramp_walkable_m`, `fuel` |
| Barley Brothers Brewery | `400e7926-68cf-4eb8-a94e-639b02e4c817` | **yes** (Shugrue's group, channelside) | unknown — shares group/channel frontage, no separate dock named | guest_dock, slips, time limit, `ramp_walkable_m`, `fuel` |
| Javelina Cantina | `ba787210-66ac-45f2-b7eb-54b3a8cbff1f` | **yes** (Shugrue's group, channelside) | unknown — same caveat | guest_dock, slips, time limit, `ramp_walkable_m`, `fuel` |
| Makai Cafe | `d7e8fb73-9c1f-4491-9881-821026e16220` | **yes** (own site — "closest to the London Bridge dock") | unknown — uses the shared/public bridge dock | guest_dock, slips, time limit, `ramp_walkable_m`, `fuel` |
| Island Mall & Brewery | `16faff70-41cd-4f67-9dc4-67e1a641ed24` | **yes** (the channelfront building itself) | unknown | guest_dock + confirm it's a distinct operating venue (only 9 reviews) |
| Shugrue's Cornerside Bakery | `3723c4ba-3115-401b-a31c-78c7724d5c27` | unknown — no water-access evidence found | unknown | everything — and decide if it's a distinct dock-relevant venue (also open in the heat_exposure staging) |

### Cluster B — London Bridge Resort (Queens Bay, 1477 Queens Bay)

Both are on the London Bridge Resort property on the Bridgewater Channel; the
resort offers courtesy boat docking 6am–6pm + complimentary guest slips.

| Entity | entity_id | `dockable` | `guest_dock` | Still to survey |
|---|---|---|---|---|
| Martini Bay | `e50c0500-24eb-4a29-b2f9-4a590a92d604` | **yes** (resort marina, channel-side) | **yes** (courtesy docking 6am–6pm) | slips, time limit, `ramp_walkable_m`, `fuel` |
| Kokomo Beach Club | `c5b4c1cc-8ebe-41a9-87f9-19977e98eba6` | **yes** (same resort property) | **yes** (complimentary slips + courtesy docking) | slips, time limit, `ramp_walkable_m`, `fuel` |

### Cluster C — The Nautical Beachfront Resort (1000 McCulloch Blvd, lakefront)

The Nautical has courtesy docks "outside the Turtle Grille for guests of the
resort and others in the community." Turtle Beach Bar is the lakeside sand-beach
bar on the same property.

| Entity | entity_id | `dockable` | `guest_dock` | Still to survey |
|---|---|---|---|---|
| Turtle Grille | `458ad457-37ca-4495-b3dc-62dcbc9834b2` | **yes** (boat-up access advertised) | **yes** (courtesy docks outside the Grille) | slips, time limit, `ramp_walkable_m`, `fuel` |
| Turtle Beach Bar | `9e3dedfc-aaa0-4744-9b25-b2796faf8cb1` | **yes** (boat-up beaching + shared courtesy docks) | **yes** (shared resort courtesy docks) | slips, time limit, `ramp_walkable_m`, `fuel` |

### Cluster D — Beachcomber Blvd

| Entity | entity_id | `dockable` | `guest_dock` | Still to survey |
|---|---|---|---|---|
| Boat House Grill | `4b157e3c-87bc-4c93-a551-0ceb1fbb60b0` | unknown — "just off the lake" / on the island, but no dock or tie-up confirmed | unknown | everything — on-site survey needed |

**Survey priorities after the web pass:** the two `unknown` venues — Shugrue's
Cornerside Bakery and Boat House Grill — need the most attention (no evidence
either way). For the English Village `dockable: yes / guest_dock: unknown` venues
(Barley Brothers, Javelina, Makai, Island Mall), the open question is whether each
has its own dedicated dock or shares one group/public channel dock.

## §3 Category artifacts found — 4 non-eateries in `food_drink` (finding, not a task)

While building this list, the DB query surfaced **4 non-eatery entities loaded
into `category=food_drink`** — the discovery sweep's food labels caught some
on-the-water / lodging entities. Flagging because the Phase 5.1 acceptance gate
includes "Phase 6 `/category/eat-drink` renders 15+ per default filter" — these
would render in the eat-drink category page as-is:

| Entity | entity_id | `google_primary_category` | Really a… |
|---|---|---|---|
| London Bridge Beach | `f0497e6e-d433-4df9-9a0f-278dd1fe0f1d` | `park` | parks / on-the-water (heat list §3 #18) |
| Site Six Launch Ramp | `1b58b28e-7ea8-4d09-8c3b-a409c77d7a7c` | `None` | on-the-water boat ramp (heat list §3 #19) |
| The Nautical Beachfront Resort | `2b38d5af-5bce-46aa-bd4a-2bc12574e334` | `resort_hotel` | lodging |
| London Bridge Resort | `240c4f19-23c6-4f19-b8e4-5be5b8eaf7b5` | `hotel` | lodging |

Not a blocker and not in this chat's lane to fix unilaterally — but worth a
decision before Phase 6 renders the eat-drink page. The two resorts have their
actual eateries already loaded as separate entities (Martini Bay, Kokomo, Turtle
Grille, Turtle Beach Bar — all in §2). Recommend recategorizing or deactivating
these 4 in `food_drink`; coordinate since recategorization touches shared scope.

## §4 How to use this

1. Take this list on the **English Village + Channel sweep** (runbook §3). Clusters
   A and B are walkable from the London Bridge; Cluster C (The Nautical) and D
   (Boat House Grill) are short hops.
2. For each venue, confirm `dockable`, then measure/observe the survey fields and
   assemble the `shoreline_commercial` JSON.
3. Enter via direct DB SQL (runbook §4) — `UPDATE entities SET boat_access = ?,
   updated_at = ? WHERE id = ?` with the JSON string. (crowd_notes apply pattern
   in `apply_crowd_notes_top17.py` is a usable template if you'd rather script it.)
4. Per rubric §2: any venue you can't confirm on the sweep → set `boat_access = {}`
   (not NULL) so Phase 6 shows it as "boat info coming soon" rather than hiding it.
5. Three of these (Shugrue's, Javelina, HEAT Bar) are also on the `heat_exposure`
   priority list — `heat_exposure` and `boat_access` are independent columns; set
   both.

## §5 References

- `docs/operations/boat_access_rubric.md` §1.4 (shoreline_commercial shape) + §2 (NULL vs `{}` vs populated) + §4 (entry tips, "don't guess")
- `outputs/phase5_1_eat_drink_kickoff.md` §3 (Layer-5 manual recovery, English Village sweep) + §4 (boat_access entry)
- `docs/maintainability/manual_recovery_checklist.md` §7 (field-trip planner — English Village + Channel sweep)
- `outputs/phase5_1_heat_exposure_field_entry_staged.md` (the 3 overlapping water_adjacent venues)

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat (post-`d34d4c3`,
2026-05-15). Lives at `outputs/phase5_1_boat_access_candidates.md` — brand-new
`outputs/` file, safe under the parallel-chat scope lock. Candidate ids verified
against a `/tmp` copy of the live `data/events.db`; `dockable` proposals are
web-research-based and need on-sweep confirmation per `boat_access_rubric.md` §4.*
