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

`dockable` values below marked **(web-confirmed)** are well-sourced; **(cluster
inference)** means the venue shares a waterfront frontage with a web-confirmed
neighbor but wasn't individually confirmed — verify on the sweep. Everything else
is a field measurement — left blank deliberately.

### Cluster A — English Village (Bridgewater Channel, 1420/1425 McCulloch Blvd N)

Web research confirms Shugrue's, Barley Brothers, and Javelina Cantina are a
restaurant group and "popular dock-and-dine destinations" on the channel. The
other three share the same English Village channel frontage.

| Entity | entity_id | `dockable` proposal | Confirm on survey |
|---|---|---|---|
| Shugrue's Restaurant and Brewery Group | `c1c8829c-b200-49ac-8cab-f69bf7ff23bd` | `true` (web-confirmed) | `guest_dock` + slips, time limit, `ramp_walkable_m`, `fuel` |
| Barley Brothers Brewery | `400e7926-68cf-4eb8-a94e-639b02e4c817` | `true` (web-confirmed) | same |
| Javelina Cantina | `ba787210-66ac-45f2-b7eb-54b3a8cbff1f` | `true` (web-confirmed) | same |
| Makai Cafe | `d7e8fb73-9c1f-4491-9881-821026e16220` | `true` (cluster inference) | all fields |
| HEAT Bar | `f491e591-256f-4dc7-8280-42ea83d584f8` | `true` (cluster inference) | all fields |
| Island Mall & Brewery | `16faff70-41cd-4f67-9dc4-67e1a641ed24` | confirm — only 9 reviews, may be a minor/overlapping entity | check it's a distinct operating venue first |
| Shugrue's Cornerside Bakery | `3723c4ba-3115-401b-a31c-78c7724d5c27` | confirm — bakery, 1 review; this is the same judgment-call entity flagged in the heat_exposure staging | decide if it's a distinct dock-relevant venue |

### Cluster B — London Bridge Resort (Queens Bay, 1477 Queens Bay)

Martini Bay is the resort's on-site restaurant with channel-side seating; the
resort has a marina. Kokomo Beach Club is also on the property.

| Entity | entity_id | `dockable` proposal | Confirm on survey |
|---|---|---|---|
| Martini Bay | `e50c0500-24eb-4a29-b2f9-4a590a92d604` | `true` (web-confirmed channel-side) | `guest_dock` + slips, time limit, `ramp_walkable_m`, `fuel` |
| Kokomo Beach Club | `c5b4c1cc-8ebe-41a9-87f9-19977e98eba6` | `true` (cluster inference) | all fields |

### Cluster C — The Nautical Beachfront Resort (1000 McCulloch Blvd, lakefront)

Turtle Grille explicitly advertises boat-up access ("jump off your boat, walk up").
Turtle Beach Bar is on the same lakefront property.

| Entity | entity_id | `dockable` proposal | Confirm on survey |
|---|---|---|---|
| Turtle Grille | `458ad457-37ca-4495-b3dc-62dcbc9834b2` | `true` (web-confirmed boat-up) | `guest_dock` + slips, time limit, `ramp_walkable_m`, `fuel` |
| Turtle Beach Bar | `9e3dedfc-aaa0-4744-9b25-b2796faf8cb1` | `true` (cluster inference) | all fields |

### Cluster D — Beachcomber Blvd

| Entity | entity_id | `dockable` proposal | Confirm on survey |
|---|---|---|---|
| Boat House Grill | `4b157e3c-87bc-4c93-a551-0ceb1fbb60b0` | `true` (listed among "restaurants on the water") | all fields |

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
