# Heat Exposure Priority-30 List — Phase 5 Lead-Up Scaffold

> **Purpose:** Lock the ~30 entities that get explicit `heat_exposure` tagging during Phase 5 field entry. Per §3.3.g lock (sealed in `acf5e2b` 2026-05-13), everything not on this list defaults to `indoor` at field-entry time; this list captures the priority outdoor / shaded / water_adjacent venues where the tag actually changes Phase 8 alert behavior.
>
> **Phase 8 consumer:** the heat-warning alert surface (master plan §4 Phase 8) reads `entities.heat_exposure` to decide which venues surface in "be careful out there today" advisories. A `restaurant` tagged `outdoor` shows up in the patio-dining advisory at 110°F; the same restaurant defaulted to `indoor` is invisible to that alert. Tagging accuracy on this list = alert accuracy in Phase 8.
>
> **Status:** authored as a scaffold by Cowork primary (post-`acf5e2b`, 2026-05-13). **The list below is partially seeded with named LHC venues drawn from existing project docs (`docs/operations/boat_access_rubric.md` examples + brief / strategy / prereq references); operator should review, validate, swap in correct names, fill placeholders, and remove rows that don't fit. Target final count: 30 entities total across the four heat_exposure values.**
>
> **Rubric (carry-forward from prereq §3.3.g + Phase 3.1 schema):** `heat_exposure` is an enum of `indoor` / `shaded` / `outdoor` / `water_adjacent`. Semantic locks:
>
> - `outdoor` — venue's primary use is outdoors, no significant shade, full sun exposure. Parks, sports fields, dog parks, open-air markets.
> - `shaded` — venue's primary use is outdoors but with persistent shade (ramadas, mature trees, covered patios that are usable in mid-day heat). The "outdoor-but-bearable-in-summer" tier.
> - `water_adjacent` — venue is on/at the water; heat is moderated by water proximity + breezes + swimming access. Marinas, beaches, lakeside restaurants, public ramps.
> - `indoor` — the default; not on this list.

---

## §1 Outdoor (~12 entries — full-sun exposure, Phase 8 patio/field advisories)

These venues hit hardest in summer. Phase 8 surfaces them in the "avoid mid-day outdoor activity" advisory.

| # | Entity name | Tier 1 category | Rationale | Confidence |
|---|---|---|---|---|
| 1 | SARA Park | `outdoors-parks-trails` | Multi-use park with disc golf + open sports fields; minimal shade outside the ramada area. Anchor outdoor venue for the south side of town. | medium — referenced in project context, operator should confirm extent |
| 2 | Rotary Park | `outdoors-parks-trails` | Community park; mix of shaded + open areas; operator decides whether overall tag is `outdoor` or `shaded` based on dominant usage pattern. | medium |
| 3 | *Operator names: primary disc golf course* | `classes-sports-recreation` | Disc golf is full-sun + no shade between holes; tag the course entity `outdoor`. Per prereq §4.7 PDGA verification. | placeholder — operator fills LHC course name |
| 4 | *Operator names: largest dog park (off-leash)* | `outdoors-parks-trails` | Dog parks are full-sun; owners + dogs both at risk in summer. Tag the primary LHC off-leash facility. | placeholder |
| 5 | *Operator names: secondary dog park if separate* | `outdoors-parks-trails` | Same rationale; if LHC has a second dog park, include it. Omit row if not applicable. | placeholder |
| 6 | *Operator names: primary skate park* | `classes-sports-recreation` | Skate parks are concrete + full-sun; dangerous summer surface temperatures. | placeholder |
| 7 | *Operator names: BMX / pump track if present* | `classes-sports-recreation` | Same as skate park rationale. Omit if not applicable. | placeholder |
| 8 | *Operator names: primary outdoor tennis complex* | `classes-sports-recreation` | Hard-court tennis in full sun; surface temperatures hit 140°F+ in summer. | placeholder |
| 9 | *Operator names: primary outdoor pickleball complex* | `classes-sports-recreation` | Per prereq §4.6 USAPickleball verification — LHC pickleball courts; same rationale as tennis. | placeholder |
| 10 | *Operator names: city softball / baseball fields* | `classes-sports-recreation` | League fields; afternoon games dangerous in summer. Single entity row for the complex; tag `outdoor`. | placeholder |
| 11 | *Operator names: farmers market venue (when seasonal)* | `eat-drink` or `shopping-essentials` | Open-air market; tag the market entity `outdoor` if it has its own row. Phase 5 §3.4.j manual recovery may surface this. | placeholder — depends on market having its own entity |
| 12 | *Operator names: outdoor concert / amphitheater venue* | `classes-sports-recreation` | Open-air event venue; tag `outdoor` even though events are usually evening. | placeholder — omit row if LHC has no dedicated outdoor venue |

---

## §2 Shaded (~6 entries — outdoor-but-shaded, mid-day-usable)

Outdoor venues with persistent shade where summer mid-day use is still tolerable. Phase 8 surfaces them as "OK outdoor option in the heat" alternatives.

| # | Entity name | Tier 1 category | Rationale | Confidence |
|---|---|---|---|---|
| 13 | *Operator names: largest ramada-rich park* | `outdoors-parks-trails` | A park with 5+ ramadas (e.g., from boat_access rubric §3.3 London Bridge Beach has 6 shade structures — a similar park-only entity). Operator picks the right LHC venue. | placeholder |
| 14 | *Operator names: secondary heavily-shaded community park* | `outdoors-parks-trails` | Per Rotary Park-style mix; if there's a second park dominated by shaded areas, include. | placeholder |
| 15 | *Operator names: notable shaded restaurant patio (1)* | `eat-drink` | A restaurant whose patio has persistent shade (sail shade, mature tree, covered structure). Operator picks 2-3 most well-known. | placeholder |
| 16 | *Operator names: notable shaded restaurant patio (2)* | `eat-drink` | Same. | placeholder |
| 17 | *Operator names: notable shaded restaurant patio (3)* | `eat-drink` | Same. | placeholder |
| 18 | Library exterior / community center patio (if applicable) | `classes-sports-recreation` or civic | Some community-center reading patios are heavily shaded; operator decides whether the venue's primary entity warrants the `shaded` tag. | placeholder — likely omit if entity primary use is indoor |

---

## §3 Water adjacent (~12 entries — on-or-at-water, heat-moderated)

Venues where water proximity meaningfully changes the heat experience. Phase 8 may surface these as preferred "be on the water" destinations during heat advisories.

| # | Entity name | Tier 1 category | Rationale | Confidence |
|---|---|---|---|---|
| 19 | Lake Havasu State Park (park + marina) | `on-the-water` + `outdoors-parks-trails` | Anchor lakeside venue; multiple ramps + beach + day-use area. Boat_access rubric §3.1 example anchors the marina entity. | high — named in boat_access_rubric |
| 20 | London Bridge Beach | `on-the-water` | Anchor swim beach; 6 ramadas (shaded but `water_adjacent` is the dominant tag because of swim access). Boat_access rubric §3.3 example. | high — named in boat_access_rubric |
| 21 | Site Six public ramp | `on-the-water` | Anchor public boat ramp; direct water access. Boat_access rubric §3.2 example. | high — named in boat_access_rubric |
| 22 | Pier 19 Bar & Grill | `eat-drink` (cross-listed `on-the-water`) | Anchor dock-and-dine restaurant; lakeside seating + guest dock. Boat_access rubric §3.4 example. | high — named in boat_access_rubric |
| 23 | English Village waterfront restaurant cluster | `eat-drink` | Multiple restaurants face the channel under the London Bridge; tag each individual restaurant entity `water_adjacent`. Operator splits this into N rows once the cluster is enumerated during §3.1 Eat & Drink scrape. | high — referenced in prereq §3.3.h crowd_notes example + master plan |
| 24 | Aquatic Park (if it's a city-pool entity) | `classes-sports-recreation` | Aquatic Park appears in prereq §3.3.h as a crowd_notes long-form target; if the entity exists as a water/pool facility, tag `water_adjacent`. | medium |
| 25 | Cattail Cove State Park | `outdoors-parks-trails` + `on-the-water` | LHC-area state park with shoreline + camping; likely water_adjacent for its primary day-use entity. Operator confirms scope. | medium |
| 26 | *Operator names: primary private marina (1)* | `on-the-water` | LHC has multiple private marinas; tag each `water_adjacent`. Operator splits into N rows during §3.2 On the Water scrape. | placeholder |
| 27 | *Operator names: primary private marina (2)* | `on-the-water` | Same. | placeholder |
| 28 | *Operator names: secondary public ramp* | `on-the-water` | Beyond Site Six, LHC has additional public ramps; operator picks 1-2 highest-traffic. | placeholder |
| 29 | *Operator names: BLM-land beach / informal water access* | `on-the-water` | A Layer-5 manual-recovery candidate per `manual_recovery_checklist.md`; tag if entity exists. | placeholder |
| 30 | *Operator names: secondary lakeside restaurant* | `eat-drink` (cross-listed) | A second dock-and-dine beyond Pier 19; tag `water_adjacent` for the cross-listed entity. | placeholder |

---

## §4 Operator-tag rule (carry-forward from prereq §3.3.g lock)

1. **Default is `indoor`.** Every entity not on this list lands with `heat_exposure = "indoor"` during Phase 5 field entry. Don't second-guess the default — the priority-30 mechanism exists so operator doesn't have to decide per-row across 390-740 entries.

2. **List is amendable during Phase 5.** If a category scrape surfaces a venue that clearly belongs on this list (e.g., §3.1 Eat & Drink reveals a third notable shaded patio that should be priority-tagged), add it to §1/§2/§3 above + tag the entity during that scrape's field entry session. Document the addition with a date so the list grows transparently rather than silently.

3. **Cross-listed entities (Pier 19 in `eat-drink` + `on-the-water`) get tagged once.** The `heat_exposure` column lives on the canonical `entities` row; cross-listing is via `entities.boat_access` (the field that adds the on-the-water-side detail). One entity = one heat_exposure tag.

4. **Re-visit annually.** Like the boat_access rubric, this list should be re-walked once a year to confirm tags still match reality (a restaurant that added a sail-shade canopy might shift from `outdoor` → `shaded`; a park that lost a mature tree might shift the other direction). Phase 8 doesn't auto-detect these changes.

---

## §5 What this list is NOT

1. **Not the canonical Phase 8 alert venue-context map.** Phase 8 will build its own alert-routing config that consumes `heat_exposure` + other signals (capacity, hours, accessibility). This list is the Phase 5 field-entry priority; Phase 8 may surface additional or different venues per alert type.

2. **Not exhaustive of every non-indoor LHC venue.** It's the **priority-30** — the highest-leverage tags. Other outdoor venues lands as `indoor` default during Phase 5 (the conservative-default lock); the operator can amend later if Phase 6 UI surfaces a gap.

3. **Not gated on operator finishing this list before Lane B verifications.** Lane B (§4 external verifications) and Lane D (Railway redeploy) can run in parallel with this list's operator amendment. The list only blocks Lane E (§3.1 Eat & Drink first scrape) since field-entry begins during that lane and the tag-or-default decision tree needs to be locked.

---

## §6 Operator amendment workflow

1. Operator reads §1-§3 above, marks confidence on each placeholder ("yes / no / swap-with-X").
2. Operator fills in LHC-specific names for placeholders, deletes rows that don't fit, adds new rows if the list-of-30 has gaps.
3. Operator commits the amended list with a body like *"docs: operator-name-fill on heat_exposure priority-30 list — N rows confirmed, M rows replaced, K rows added"*.
4. List is locked at that point — Phase 5 field entry uses it as the decision tree for `heat_exposure` tagging.

---

## §7 Reference

- Phase 3.1 migration `d0e1f2a3b4c5_phase3_schema_pass` (`Entity.heat_exposure` enum column: `indoor` / `shaded` / `outdoor` / `water_adjacent`)
- Phase 5 prereq checklist `outputs/phase5_prereq_checklist.md` §3.3.g (lock-the-rubric task) + §3.5 (lock state)
- Phase 5 brief `outputs/cursor_brief_phase_5_tier_1_data.md` §2 row "§3.3.g `heat_exposure` rubric" + per-category rubric in §3.1-§3.6 (each category section references heat_exposure rules)
- Boat access rubric `docs/operations/boat_access_rubric.md` (parallel artifact; the 4 LHC examples in §3 of that doc anchor entries #19-#22 above)
- Phase 8 alerts (master plan §4 Phase 8 — primary downstream consumer)
- Master plan §7 risk row 10 ("Opus hidden dependency: ~30 entities with non-default heat_exposure")

---

*Scaffolded by Cowork primary at the new-chat post-`acf5e2b` session (2026-05-13). Lives at `outputs/heat_exposure_priority_30_list.md`. Operator amends §1-§3 with LHC-specific names + confidence + commits before Phase 5 §3.1 Eat & Drink first scrape begins.*
