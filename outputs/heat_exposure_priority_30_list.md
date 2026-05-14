# Heat Exposure Priority List — Phase 5 Lead-Up (RECONCILED + DECIDED)

> **Purpose:** Lock the entities that get explicit `heat_exposure` tagging during Phase 5 field entry. Per §3.3.g lock (sealed in `acf5e2b` 2026-05-13), everything not on this list defaults to `indoor` at field-entry time; this list captures the priority outdoor / shaded / water_adjacent venues where the tag actually changes Phase 8 alert behavior.
>
> **Phase 8 consumer:** the heat-warning alert surface (master plan §4 Phase 8) reads `entities.heat_exposure` to decide which venues surface in "be careful out there today" advisories. A `restaurant` tagged `outdoor` shows up in the patio-dining advisory at 110°F; the same restaurant defaulted to `indoor` is invisible to that alert. Tagging accuracy on this list = alert accuracy in Phase 8.
>
> **Status — DECIDED (2026-05-14):** scaffolded post-`acf5e2b`; Cowork web-research first pass post-`5d429aa`; reconciled against the ChatGPT deep-research pass (`outputs/deep-research-report-b947a1f2.md`); then the operator delegated the open judgment calls to Cowork ("do what you think is best"). §9 records every decision + its rationale + how to override it. **Rows marked ✅ LOCKED are settled. The 2 rows marked PROVISIONAL get a 30-second operator confirm during the §3.1 Eat & Drink scrape — they do not block the lock.** This file is **commit-ready**; committing it closes Phase 5.0 item B2-c.
>
> **Rubric (carry-forward from prereq §3.3.g + Phase 3.1 schema):** `heat_exposure` is an enum of `indoor` / `shaded` / `outdoor` / `water_adjacent`. Semantic locks:
>
> - `outdoor` — venue's primary use is outdoors, no significant shade, full sun exposure. Parks, sports fields, dog parks, open-air markets, courts.
> - `shaded` — venue's primary use is outdoors but with persistent shade (ramadas, mature trees, covered patios that are usable in mid-day heat). The "outdoor-but-bearable-in-summer" tier.
> - `water_adjacent` — venue is on/at the water; heat is moderated by water proximity + breezes + swimming access. Marinas, beaches, lakeside restaurants, public ramps.
> - `indoor` — the default; not on this list.

---

## §1 Outdoor (full-sun exposure — Phase 8 patio/field advisories)

These venues hit hardest in summer. Phase 8 surfaces them in the "avoid mid-day outdoor activity" advisory.

| # | Entity name | Tier 1 category | Rationale + address | Status |
|---|---|---|---|---|
| 1 | SARA Park | `outdoors-parks-trails` | 7260 S SARA Park Way. ~1,100-acre desert sports park — open fields, trails, motocross/BMX tracks; no significant shade. | ✅ LOCKED — both passes agree |
| 2 | SARA Park Disc Golf Course | `classes-sports-recreation` | At SARA Park (7260 S Sara Pkwy). 18-hole desert course, rugged exposed terrain, minimal tree cover. | ✅ LOCKED — both passes agree |
| 3 | Dylan's Dog Park (at SARA Park) | `outdoors-parks-trails` | ~2-acre fenced off-leash dog park at SARA Park, two sections, mostly open. Both sources agree it's at SARA Park; the exact street address auto-resolves when Google Places scrapes it. (The "is it the largest LHC dog park" question was dropped — it doesn't affect the tag.) | ✅ LOCKED — tag `outdoor`; address resolves at scrape |
| 4 | Avalon Park — dog park | `outdoors-parks-trails` | 1294 Avalon Ave. Fenced dog park; ramadas/trees give *some* shade but not persistent. ChatGPT resolved the tag-check: the dog park itself is `outdoor` (the general park is `shaded` — §2 #12). | ✅ LOCKED — tag-check resolved |
| 5 | Lake Havasu City BMX | `classes-sports-recreation` | 7260 Sara Pkwy (at SARA Park). Standalone USA-BMX-affiliated open-air dirt track, no significant shade. Separate entity from the Tinnell complex; no pump track exists. | ✅ LOCKED — BMX/pump-track question resolved |
| 6 | Lake Havasu High School tennis courts | `classes-sports-recreation` | 2675 S Palo Verde Blvd. 8 hard courts, no roof or cover, fully exposed. | ✅ LOCKED — both passes agree |
| 7 | Mike Delaney Pickleball Complex | `classes-sports-recreation` | Dick Samp Park, 1628 Avalon Ave. 16 outdoor courts, no cover. | ✅ LOCKED — both passes agree |
| 8 | Island Ball Fields | `classes-sports-recreation` | 1150 McCulloch Blvd. The city's primary adult softball complex (ChatGPT resolved this vs. Rotary / Dick Samp). Multi-use, no cover. | ✅ LOCKED — "canonical city fields" resolved |
| 9 | Lake Havasu Farmers Market | `eat-drink` / `shopping-essentials` | 2144 McCulloch Blvd N ("The KAWS" plaza). Open-air, uncovered booths, every Saturday **year-round** (ChatGPT corrected: not seasonal). ⚠️ Operator decides if the market gets its own Provider entity when it surfaces during the §3.1 scrape — if it doesn't, the row simply drops (no harm). | ✅ LOCKED — tag `outdoor`; entity-existence resolves at scrape |
| 10 | Patrick A. Tinnell Memorial Sports Complex (skate/BMX) | `classes-sports-recreation` | 1400 S Smoketree Ave, within Rotary Park on the Thompson Bay shore. ~40,000 sq ft concrete skate/BMX facility. **Cowork decision:** tagged `outdoor`, not `water_adjacent` — a concrete skate surface bakes dangerously regardless of a lakeside breeze, and for Phase 8 *alert behavior* it belongs in the "avoid mid-day outdoor activity" advisory, not the "good water destination" set. Kept as its own entity, separate from Rotary Park (§3 #16) — both are distinct named destinations a directory user searches for separately. | ✅ LOCKED (Cowork call) — operator may override the tag |

---

## §2 Shaded (outdoor-but-shaded, mid-day-usable)

Outdoor venues with persistent shade where summer mid-day use is still tolerable. Phase 8 surfaces them as "OK outdoor option in the heat" alternatives.

| # | Entity name | Tier 1 category | Rationale + address | Status |
|---|---|---|---|---|
| 11 | Jack Hardie Park | `outdoors-parks-trails` | 2470 Baron Drive. 7 large shade ramadas + a covered playground; persistent shade dominates. Not on the water. | ✅ LOCKED — both passes agree |
| 12 | Avalon Park (general park) | `outdoors-parks-trails` | 1294 Avalon Ave. Covered playground + picnic ramadas; significant shade coverage. (The dog park within it is `outdoor` — §1 #4.) | ✅ LOCKED — both passes agree |
| 13 | Locos Bar & Cocina (Northside) | `eat-drink` | 3620 London Bridge Rd. Outdoor patio with palm-shaded seating + string lights, usable mid-day. ChatGPT confidence: high. | ✅ LOCKED — operator spot-confirms at §3.1 scrape |
| 14 | El Paraiso Family Mexican | `eat-drink` | 1530 Palo Verde Blvd S. Large patio (~60 capacity). ChatGPT *inferred* the shade ("likely umbrellas or cover") — not confirmed. **PROVISIONAL:** confirm the patio is genuinely mid-day-shaded when this venue surfaces in the §3.1 Eat & Drink scrape; if not, drop the row (defaults to `indoor`). | PROVISIONAL — confirm at §3.1 scrape |
| 15 | College Street Brewhouse & Pub | `eat-drink` | 1940 College Dr. Outdoor patio dining, lake view. ChatGPT *inferred* shade — not confirmed, and the lake view raises a `shaded`-vs-`water_adjacent` question. **PROVISIONAL:** confirm the tag when this venue surfaces in the §3.1 scrape. | PROVISIONAL — confirm tag at §3.1 scrape |

> **Dropped from §2:** the Lake Havasu City Library outdoor patio (1770 McCulloch Blvd N). ChatGPT found it's a real renovated shaded patio, but **Cowork decision: omit** — a library reading patio is not a venue people decide to visit *based on heat*, so mis-tagging it `indoor` (the default) doesn't degrade any Phase 8 alert. The priority list is kept tight to high-leverage venues. Operator can re-add per §4 rule 2 if they disagree.

---

## §3 Water adjacent (on-or-at-water, heat-moderated)

Venues where water proximity meaningfully changes the heat experience. Phase 8 may surface these as preferred "be on the water" destinations during heat advisories.

| # | Entity name | Tier 1 category | Rationale + address | Status |
|---|---|---|---|---|
| 16 | Rotary Community Park | `outdoors-parks-trails` | 1400 S Smoketree Ave. 40-acre lakeside beach park on Thompson Bay — swim beach + shade ramadas; water proximity dominates. RECLASSIFY resolved → `water_adjacent` (moved here from §1). Kept separate from the Tinnell complex (§1 #10) — distinct named destinations. | ✅ LOCKED — reclassify resolved |
| 17 | Lake Havasu State Park | `on-the-water` + `outdoors-parks-trails` | 699 London Bridge Rd. Sandy beaches, boat ramps, cabins — directly on the lake. | ✅ LOCKED — both passes + boat_access_rubric agree |
| 18 | London Bridge Beach | `on-the-water` | 1340 McCulloch Blvd. Lakeside park on the Bridgewater Channel — swim beach, ramadas. | ✅ LOCKED |
| 19 | Site Six (public boat ramp) | `on-the-water` | 591 Beachcomber Blvd. Free public launch — pier, ramp, beach. | ✅ LOCKED |
| 20 | English Village restaurant cluster | `eat-drink` | Bridgewater Channel by London Bridge. Roster + addresses confirmed: Shugrue's (1425 N McCulloch), Makai Café (1425 N McCulloch), Barley Brothers (1425 N McCulloch), Javelina Cantina (1420 N McCulloch), The Heat Bar (1420 N McCulloch). Operator splits into N rows during the §3.1 Eat & Drink scrape. | ✅ LOCKED — roster confirmed |
| 21 | Lake Havasu Marina | `on-the-water` | 1100 N McCulloch Blvd. Large commercial marina on the Bridgewater Channel — slips + ramps. | ✅ LOCKED |
| 22 | Havasu Riviera Marina | `on-the-water` | 2790 Havasu Riviera Pkwy. Lakeside marina — slips + launch. | ✅ LOCKED |
| 23 | Crazy Horse Campground (19th Hole Bar & Grill) | `on-the-water` (cross-listed `eat-drink`) | 1534 Beachcomber Blvd. Lakefront campground with a fee boat ramp AND a dock-accessible bar/restaurant — ChatGPT used this one venue to fill both first-pass blanks (the "secondary public ramp" and the "secondary dock-and-dine"). Operator confirms it's still operating during the §3.2 On the Water scrape. | ✅ LOCKED — operator confirms operating status at §3.2 |

> **Dropped from §3:** (a) **Pier 19 Bar & Grill** — ChatGPT found it closed / rebranded to "Oasis Eateries" on Swanson Ave. (b) **Lake Havasu City Aquatic Center** — ChatGPT confirmed it's an *indoor* pool → `indoor` is the default → it doesn't belong on a priority list of non-indoor venues. (c) **Cattail Cove State Park** + **Take-Off Point (BLM)** — both real water_adjacent venues but ~15–16 mi *south* of LHC proper; **Cowork decision: defer** per `manual_recovery_checklist.md` §7, which puts off-island venues in a later sweep. Operator can pull them in if they want them in V1.

---

## §4 Operator-tag rule (carry-forward from prereq §3.3.g lock)

1. **Default is `indoor`.** Every entity not on this list lands with `heat_exposure = "indoor"` during Phase 5 field entry. Don't second-guess the default — the priority-list mechanism exists so operator doesn't have to decide per-row across 390-740 entries.

2. **List is amendable during Phase 5.** If a category scrape surfaces a venue that clearly belongs on this list (e.g., §3.1 Eat & Drink reveals a third notable shaded patio that should be priority-tagged), add it to §1/§2/§3 above + tag the entity during that scrape's field entry session. Document the addition with a date so the list grows transparently rather than silently.

3. **Cross-listed entities (e.g. Crazy Horse / 19th Hole in `eat-drink` + `on-the-water`) get tagged once.** The `heat_exposure` column lives on the canonical `entities` row; cross-listing is via `entities.boat_access` (the field that adds the on-the-water-side detail). One entity = one heat_exposure tag.

4. **Re-visit annually.** Like the boat_access rubric, this list should be re-walked once a year to confirm tags still match reality (a restaurant that added a sail-shade canopy might shift from `outdoor` → `shaded`; a park that lost a mature tree might shift the other direction). Phase 8 doesn't auto-detect these changes.

---

## §5 What this list is NOT

1. **Not the canonical Phase 8 alert venue-context map.** Phase 8 will build its own alert-routing config that consumes `heat_exposure` + other signals (capacity, hours, accessibility). This list is the Phase 5 field-entry priority; Phase 8 may surface additional or different venues per alert type.

2. **Not exhaustive of every non-indoor LHC venue.** It's the **priority list** — the highest-leverage tags. The reconciled list is ~23 rows (the English Village cluster expands to ~5 venues, so ~27 venues total); it does not need to hit exactly 30. Other outdoor venues land as `indoor` default during Phase 5 (the conservative-default lock); the operator amends per §4 rule 2 as scrapes surface gaps.

3. **Not gated on operator finishing this list before Lane B verifications.** Lane B and the Railway redeploy run in parallel with this list. The list only blocks Phase 5.1 Eat & Drink first scrape, since field entry begins during that lane and the tag-or-default decision tree needs to be locked.

---

## §6 Operator amendment workflow

1. Operator reviews §1–§3 + the §9 decision log; adjusts any Cowork call they disagree with.
2. Operator commits the list with a body like *"docs: heat_exposure priority list reconciled + locked — Cowork+ChatGPT passes merged, open calls decided"*.
3. List is locked at that point — Phase 5 field entry uses it as the decision tree for `heat_exposure` tagging.
4. The 2 PROVISIONAL rows + the few "confirm at scrape" notes get settled naturally during the §3.1/§3.2 scrapes, amended in place per §4 rule 2.

---

## §7 Reference

- Phase 3.1 migration `d0e1f2a3b4c5_phase3_schema_pass` (`Entity.heat_exposure` enum column: `indoor` / `shaded` / `outdoor` / `water_adjacent`)
- Phase 5 prereq checklist `outputs/phase5_prereq_checklist.md` §3.3.g (lock-the-rubric task) + §3.5 (lock state)
- Phase 5 brief `outputs/cursor_brief_phase_5_tier_1_data.md` §2 row "§3.3.g `heat_exposure` rubric" + per-category rubric in §3.1-§3.6
- Boat access rubric `docs/operations/boat_access_rubric.md` — ⚠️ its §3.4 uses **Pier 19** as a canonical example, and Pier 19 is now defunct (see §9). That doc should be patched; `docs/operations/` is outside this Phase 5 chat's scope — flag for whoever owns it.
- ChatGPT deep-research pass: `outputs/deep-research-report-b947a1f2.md`
- Phase 8 alerts (master plan §4 Phase 8 — primary downstream consumer)
- Master plan §7 risk row 10 ("Opus hidden dependency: ~30 entities with non-default heat_exposure")

---

## §8 Sources

**Cowork first-pass web research** — tourism/city/directory pages: Go Lake Havasu (`golakehavasu.com`), Lake Havasu City P&R (`lhcaz.gov/parks-recreation`), `lakehavasupickleball.com`, `pickleheads.com`, `lakehavasufarmersmarket.com`, `lakehavasumarina.com`, `havasurivieramarina.com`, `azstateparks.com/lake-havasu`, `shugrueslakehavasu.com`, `makaicafe.com`, `bringfido.com`, `lakehavasumagazine.com`, `thelostlongboarder.com`. SARA Park disc golf confirmed via Lane B PDGA verification.

**ChatGPT deep-research pass** — official city parks pages (`lhcaz.gov`), Lake Havasu tourism sites (`golakehavasu.com`), Arizona State Parks, the PDGA course directory, BLM info, the Lake Havasu City Pickleball Association, and local restaurant/marina listings. Full citation markers in `outputs/deep-research-report-b947a1f2.md`.

---

## §9 Decision log (Cowork × ChatGPT reconciliation + delegated calls, 2026-05-14)

Both research passes done and merged. The operator delegated the open judgment calls to Cowork. Every call below is grounded in either rubric-purpose logic or a project-documented default — not local-knowledge guessing. **All are operator-overridable before commit.**

**Resolved by the two passes agreeing or by ChatGPT's findings:**

- All `tag check` flags settled. Avalon: dog park = `outdoor` (§1 #4), general park = `shaded` (§2 #12) — two intentional rows.
- **Aquatic Center dropped** — ChatGPT confirmed it's an *indoor* pool; `indoor` is the default, so it's off a non-indoor priority list.
- **Rotary Community Park** → `water_adjacent`, moved §1 → §3 #16 (ChatGPT confirmed it's a lakeshore beach park).
- **Pier 19 Bar & Grill dropped** — ChatGPT found it closed/rebranded. Side-effect: `boat_access_rubric.md` §3.4 references it as an example and should be patched (flagged in §7).
- **Amphitheater row dropped** — no dedicated outdoor amphitheater exists in LHC.
- Three blank shaded-patio rows + the two blank ramp/restaurant rows filled from ChatGPT findings. Addresses added to every row.

**Cowork calls on the items the operator delegated:**

1. **Tinnell complex tag → `outdoor`** (overriding ChatGPT's `water_adjacent`). Rationale: a concrete skate surface bakes dangerously regardless of a lakeside breeze; for Phase 8 *alert behavior*, it should land in "avoid mid-day outdoor activity," not the "good water destination" set. ChatGPT applied the rubric's letter (near water); Cowork applied its purpose (alert correctness). → §1 #10. **Override:** flip to `water_adjacent`, move to §3, if you disagree.
2. **Tinnell + Rotary → two separate entities.** Both are distinct named destinations a directory user searches for independently. → §1 #10 and §3 #16 stay separate.
3. **Dylan's Dog Park** — the "largest LHC dog park" question was dropped (it doesn't affect the tag); the address conflict resolves automatically when Google Places scrapes the venue. Row is LOCKED on the tag.
4. **El Paraiso + College Street Brewhouse → PROVISIONAL.** ChatGPT only *inferred* their patio shade. They're kept as flagged rows (a useful "look at these two" breadcrumb for the §3.1 scrape) but not locked — the operator confirms or drops them in 30 seconds when they surface during Eat & Drink scraping. They do not block the lock.
5. **Library patio → omitted.** A library reading patio is not a venue people choose based on heat, so an `indoor` default costs no alert accuracy. The list stays tight to high-leverage venues. Operator can re-add per §4 rule 2.
6. **Cattail Cove + Take-Off Point → deferred.** Both ~15–16 mi south of LHC proper; `manual_recovery_checklist.md` §7 already locks off-island venues to a later sweep. Consistent with that default.
7. **Count → accept ~23 rows (~27 venues).** The file is explicitly not meant to be exhaustive (§5) and is amendable during scrapes (§4 rule 2). No filler added to hit exactly 30.

**Net:** the list is **commit-ready**. Review the §9 calls, adjust anything you'd call differently, commit — and Phase 5.0 item B2-c closes, clearing the last gate before Phase 5.1 Eat & Drink dispatches.

---

*Scaffolded by Cowork primary (post-`acf5e2b`, 2026-05-13); web-research first pass (post-`5d429aa`, 2026-05-14); reconciled against ChatGPT deep research + open calls decided on operator delegation (post-`5d429aa`, 2026-05-14 — see §9). Lives at `outputs/heat_exposure_priority_30_list.md`. Commit-ready — committing it closes Phase 5.0 item B2-c.*
