# V1.5 Carry Inventory Triage — Phase 5.0–5.11 consolidated

> **What this is:** the single triage doc for ~50 V1.5 carries that accumulated across the Phase 5.0–5.11 close-outs. Closes the observability gap flagged in `outputs/session_close_out_2026_05_19.md` §3 Lane F (the V1.5 picture was scattered across 11 close-outs; no consolidated view existed).
>
> **Authored by:** Cowork primary, 2026-05-20, against origin/main tip `23b3a70`.
>
> **Source docs synthesized:**
> - `outputs/phase5_5_session_closeout.md` through `outputs/phase5_11_session_closeout.md` (7 close-outs with explicit V1.5 labels; ~123 V1.5 mentions total)
> - `outputs/phase5_2_session_closeout.md` + `phase5_3_session_closeout.md` + `phase5_4_session_closeout.md` (carry-over / deferred items; no explicit V1.5 labels but operationally adjacent)
> - `outputs/phase5_0_close_out.md` (1 V1.5 mention — off-island heat list)
> - `outputs/phase5_1_field_entry_close_out.md` (field-entry close-out — no V1.5 carries)
> - `outputs/phase5_11_session_closeout.md` §6 "V1.5 carry inventory (full 5.0–5.11 consolidation)" (most authoritative pre-existing seed)
> - `outputs/session_close_out_2026_05_19.md` §4 "Open carries" (partial 5.7–5.11 echo)
> - `docs/maintainability/master_build_plan.md` §4 Phase 13 (canonical V1.5 features list)
>
> **Total carries inventoried:** 52 line items across 8 categories.

---

## §1 Disposition legend

| Disposition | Meaning |
|---|---|
| **V1.5 — defer** | Genuine V1.5 product/data work. Build post-launch as time + revenue allow. Belongs in the canonical Phase 13 backlog. |
| **V1 — small dev** | Small dev task (~1–2 lines, ≤1h) that should be folded into V1 before launch — too cheap to defer. Typically sustainability-layer mapping widenings. |
| **V1 — operator action** | No code; operator handles directly during the V1 window. Audit reviews, DRAFT decisions, file pruning. |
| **Drop / closed** | No longer applicable. Either resolved mid-Phase-5, superseded, or determined to be a non-issue. |
| **Operator-decide** | Needs operator decision before disposition can be locked. Surfaced in §6 below. |

The canonical Phase 13 V1.5 features list (per master plan §4 Phase 13) — peer recommendations, UGC "describe this district", SMS alerts via Twilio, accessibility profile data collection, `Provider.category → category_id` backfill, owner-uploaded video, bookings/reservations, itinerary builder, real-time fuel prices / room availability / launch conditions, white-label, native review system — is **out of triage scope** here. None of the Phase 5.x carries below overlap with that list; they all add to it or are independent operational items.

---

## §2 Layer-4 verifier surfaces (operator picked "Option C — defer to V1.5" at every Phase 5.x kickoff)

Every Phase 5.5–5.11 sub-phase documented one or more Layer-4 verifier paths (regulator scrapes / state-board APIs / tourism-board directories) and deferred via Option C. These are the largest V1.5 lift category by hours and the lowest-risk to keep deferred (V1 ships fine without them; they upgrade `Provider.verified` coverage post-launch).

| # | Source | Carry | Effort | Disposition | Why |
|---|---|---|---|---|---|
| 1 | 5.5 | AZ MVD Dealer Locator (Playwright; cat-9 dealers) | ~2–4h | **V1.5 — defer** | Mirror of 5.3 AZ ROC build pattern (`scripts/az_roc_verify.py` @ `420f893`). Coverage benefit is post-launch trust upgrade for car dealers; no V1 gate depends on it. |
| 2 | 5.5 | AZCC towing carrier (REST; cat-9 towing) | ~1–2h | **V1.5 — defer** | Lighter than MVD. Same rationale. |
| 3 | 5.6 | AZ TPT Playwright (cat-8 retail) | ~3–5h | **V1.5 — defer** | TPT registration is the trust signal for retail; not blocking V1 ship. |
| 4 | 5.6 | BBB cross-reference (cat-8 retail) | ~2–3h | **V1.5 — defer** | Lower-priority trust overlay. |
| 5 | 5.7 | AZ State Parks Playwright (cat-7 parks) | ~2–3h | **V1.5 — defer** | Operator-driven follow-up; default `outdoor` heat_exposure already lands correctly without verifier. |
| 6 | 5.7 | NPS REST API (cat-7 federal lands) | ~1–2h | **V1.5 — defer** | Easiest verifier build of the bunch (REST); also lowest yield (very few NPS-tagged entries in cat-7). |
| 7 | 5.7 + 5.9 | LHC Parks & Rec municipal scrape (cat-7 + cat-12) | ~3–4h | **V1.5 — defer** | Shared surface between 5.7 (parks) + 5.9 (pool / tennis / pickleball schedules). Phase 9 (Events) may absorb this if the schedule infrastructure lands earlier. |
| 8 | 5.8 | visitarizona.com + golakehavasu.com event aggregators (cat-2) | ~2–4h | **V1.5 — defer** | Phase 9 (Events) absorbs this naturally — RRULE-based event scraper subsystem is the right home, not a V1.5 retrofit. **Recommend: re-tag as Phase 9, not V1.5.** |
| 9 | 5.9 | AZDHS childcare-license registry (cat-12) | ~4–6h | **V1.5 — defer** | Covers ~70–90% of cat-12 childcare candidates. Trust signal for daycare/preschool; high parent-anxiety category, so worth shipping early in V1.5. |
| 10 | 5.9 | Franchise gym chain APIs (Anytime / Snap / Orange Theory / CycleBar) | ~6–8h | **V1.5 — defer** | Narrow coverage (~10–20% of cat-12 fitness). Lower priority than AZDHS childcare. |
| 11 | 5.10 | AZDOR transient-lodging tax registry (cat-10) | ~4–6h | **V1.5 — defer** | Covers ~70–90% of hotels/motels/B&Bs. Strong trust signal. |
| 12 | 5.10 | AZRE vacation-rental license registry (cat-10) | ~3–5h | **V1.5 — defer** | Narrower coverage (managed properties only). Pair with AZDOR for combined cat-10 verifier story. |
| 13 | 5.10 | LHC Tourism Board lodging directory (cat-10) | ~2–3h | **V1.5 — defer** | Smaller surface. Pair with #11 + #12. |
| 14 | 5.11 | AZ State Veterinary Medical Examining Board (vets) | ~2–3h | **Drop / closed** | Out of scope per 5.11 design — vets land in cat-5 HWC via `medical_clinic` primary, not cat-11 pets. No V1.5 work needed here unless cat-5 verifier surface gets re-opened. |
| 15 | 5.11 | National pet franchise locators (PetSmart / Petco / Banfield) | ~3–5h | **V1.5 — defer** | Low coverage (~5–10% of cat-11). Lowest priority of the franchise-locator carries. |

**Subtotal:** 15 carries; 14 V1.5 — defer (including #8 with a re-tag-to-Phase-9 recommendation per §8 #2); 1 Drop/closed (#14). Total V1.5 effort ~35–60h.

---

## §3 Sustainability layer extensions (small dev — fold into V1)

The `google_types_mapping.py` direct-map table has progressively grown across Phase 5 as each sub-phase surfaced a Google `primary_type` that landed via catch-all instead of a direct map. These are all 1-line additions in the same shape as the 5.7 `golf_course` / `medical_clinic` widenings — too cheap to defer.

| # | Source | Direct mapping to add | Disposition | Why |
|---|---|---|---|---|
| 16 | 5.6 | `medical_clinic` → cat-5 HWC (was catch-all via health_medical) | **Drop / closed** | Already landed in 5.7 §1 closure of the 5.4 + 5.6 carry. |
| 17 | 5.7 | `wildlife_refuge` → cat-7 outdoors | **V1 — small dev** | 1-line addition. Caught by Bill Williams River NWR via `(None, "entertainment_attractions")` catch-all. 5.8 carries it forward, still un-shipped. **Recommend: include in next data-quality commit pass.** |
| 18 | 5.9 | `athletic_field` / `educational_institution` / `primary_school` / `church` / `sports_complex` / `sports_club` / `country_club` | **V1 — small dev** | 7-line addition. Each ~1 line; total 10–15 min. Pair with #17. |
| 19 | 5.10 | `camping_cabin` / `cottage` / `mobile_home_park` / `guest_house` → cat-10 lodging | **V1 — small dev** | 4-line addition. Currently caught via secondary-types[] match — works but direct mapping is more deterministic. |
| 20 | 5.11 | `pet_supply_store` / `animal_shelter` / `aquarium_store` → cat-11 pets | **V1 — small dev** | 3-line addition. Same pattern. |

**Subtotal:** 5 carries; 4 small-dev fold-ins (~20–30 min total); 1 already closed. **Recommend: bundle #17 + #18 + #19 + #20 into a single Phase 6.x or pre-Phase-7 commit `chore(data): sustainability layer extensions (5.7+5.9+5.10+5.11 V1.5 carries)`.**

---

## §4 Dual-place_id / dual-category consolidations (operator-decide per entity)

Same physical entity surfacing under multiple Google `place_id` values, OR a single entity that arguably belongs in two categories. V1 default is KEEP-as-separate or KEEP-single-cat; V1.5 candidate for consolidation/DUAL ADD per entity.

| # | Source | Pair / entity | Disposition | Why |
|---|---|---|---|---|
| 21 | 5.10 | HEAT Bar ↔ Heat Hotel (same building, 8.6m apart; HEAT Bar in cat-1, Heat Hotel in cat-10) | **V1.5 — defer** | Three options: (a) cross-link via DUAL ADD, (b) consolidate as same entity, (c) keep distinct per primary identity (V1 default). Operator picks per-entity. |
| 22 | 5.10 | Havasu Dunes Resort ↔ GetAways at Havasu Dunes Resort (same address + coords, 2 place_ids, both cat-10) | **V1.5 — defer** | Likely "GetAways" is the booking entity, "Havasu Dunes Resort" is the property. Per-entity consolidation review. |
| 23 | 5.11 | 3 Beautiful Beards franchise locations | **V1.5 — defer** | Multi-place_id consolidation; operator decides if franchise locations stay distinct or consolidate. |
| 24 | 5.11 | 3 PetSmart franchise locations (existing cat-8 + new cat-11 sub-services) | **V1.5 — defer** | Distinct sub-services (PetSmart Grooming, PetSmart Dog Training) — V1.5 may merge or keep granular. |
| 25 | 5.11 | 3 cat-8 pet-retail DUAL candidates (PetSmart / Doggie Shades / Rok Dog Leashes for cat-8 + cat-11 DUAL ADD) | **V1.5 — defer** | DUAL ADD candidates; V1 default = KEEP cat-8 single. |
| 26 | 5.9 | 26 cat-5 HWC §1-updates (gyms/yoga/pilates/dance/martial arts) — dual-cat with cat-12 review | **V1.5 — defer** | Per-entry V1.5 review. Per kickoff §2 V1 policy = KEEP cat-5; no V1 lift. |
| 27 | 5.9 | Universal Sonics Gymnastics + Shah Racquetball Club — NEW-create in cat-12 with primary_type override | **V1.5 — defer** | Both primary=`gym` but actual sport is cat-12. KEEP-ambig in V1. |
| 28 | 5.9 | Sand Volleyball at Rotary Park — FLIP cat-5 → cat-12 OR dual-cat with cat-7 | **V1.5 — defer** | Currently cat-5 athletic_field primary. Depends on #18 (`athletic_field` direct mapping). |
| 29 | 5.9 | The Ark Center recategorization (currently cat-5; building also houses cat-12 Psalms Learning Center) | **V1.5 — defer** | Re-cat to cat-13 religious / nonprofit AND/OR dual-cat with cat-12. |
| 30 | 5.9 | Lake Havasu City Aquatic Center primary identity (currently cat-12 swimming_pool primary; civic facility) | **V1.5 — defer** | Could dual-cat with cat-13 (Parks & Rec municipal facility). |
| 31 | 5.7 | 5 dual-cat soft-edges: SARA Disc Golf / Motocross Park / Ofd Racing / Thompson Bay Beach / Sportsman's Club | **V1.5 — defer** | All KEEP in cat-7 per V1; V1.5 considers dual-cat with cat-12 (recreational/sport). |

**Subtotal:** 11 carries; all V1.5 — defer (per-entity operator decisions).

---

## §5 Specific-entity reviews (operator action OR V1.5)

Individual entities flagged for identity / DRAFT / waterfront / re-cat review. Some are operator-side V1 actions (DRAFT reviews can be done in the V1 window); some genuinely need V1.5 attention.

| # | Source | Entity | Disposition | Why |
|---|---|---|---|---|
| 32 | 5.6 | Anderson AZ West — un-DRAFT decision (B2B wholesale by default; may be consumer-retail) | **V1 — operator action** | One-row review; operator un-drafts or keeps. ~5 min. |
| 33 | 5.7 | Sara Park Hiking Trail ↔ Sara Park Trail Head — navigation-alias merge (16m apart) | **V1.5 — defer** | Either V1.5 merge or KEEP-both confirmation. V1 KEEP-both is safe. |
| 34 | 5.7 | Butterfly Garden — community-vs-public-garden shape investigation | **V1 — operator action** | One-row research; operator decides cat-7 fit. |
| 35 | 5.7 | ASU SWANSON FIELDS — uppercase-name normalization + source investigation | **V1 — operator action** | Casing fix + cat decision. ~10 min. |
| 36 | 5.8 | Lake Havasu Museum of History — place_id unification (5.7-ambig + 5.8 candidate, same business) | **V1.5 — defer** | Operator picks primary place_id, archives the other. |
| 37 | 5.8 | Simply Savage Designs — DRAFT review (art_gallery primary, name suggests design shop) | **V1 — operator action** | One-row un-DRAFT or DELETE. |
| 38 | 5.8 | art_gallery / museum entity_type review — `place` vs `commercial` (most LHC museums + many galleries charge admission) | **V1.5 — defer** | Per-entry V1.5 decision; current `place` works for V1. |
| 39 | 5.9 | 5.8 §9 carry candidates revisit: Nomadic coworking / Lions Dog Park / Main Street Commons (all confirmed 0 in DB) | **V1.5 — defer** | Single-entity Layer 5 manual recovery candidates; each ~10–15 min field entry. |
| 40 | 5.9 | Bridge Body Fitness (94r) + Feelin' Good Fitness (110r) — high-signal gyms in §1 ambig pool | **V1.5 — defer** | NEW-create in cat-5 HWC if 5.4 lane re-opened. |
| 41 | 5.9 | River City Music — cross-cat consideration if it offers music lessons in addition to retail | **V1.5 — defer** | Per-entity review. |
| 42 | 5.10 | Havasu Suites — identity re-evaluation (primary=`travel_agency`, 6 reviews) | **V1.5 — defer** | Booking agency vs. hotel? Per-row review. |
| 43 | 5.10 | Xanadu — identity verification (primary=`point_of_interest`, 0 reviews) | **V1.5 — defer** | Private residence / defunct / non-lodging? |
| 44 | 5.10 | Queens Bay Resort Condominiums — waterfront-DUAL review (name has "Bay") | **V1.5 — defer** | May qualify for cat-3 DUAL ADD. |
| 45 | 5.10 | 5 waterfront-suggestive RV park / campground candidates (Sam's Beachcomber / Anchor Lake House / Campbell Cove / Islander / Havasu Falls) | **V1.5 — defer** | water_adjacent override review per entity. |
| 46 | 5.10 | 29 lake_recreation-domain ambig records (boat/marina/RV adjacent to McCulloch Blvd) | **V1.5 — defer** | cat-3 NEW creates IF the 5.2 lane is re-opened. Large V1.5 lift (~3–4h). |
| 47 | 5.11 | 5 zero-review Slice E entries (Obedience Please / PetSmart Grooming / PetSmart Dog Training / Penney's Pampered Pawz / TagWorks) | **V1 — operator action** | DRAFT review post-SHIP at operator discretion. May be defunct or placeholder. ~15 min total. |
| 48 | 5.11 | Manual recovery surface — mobile groomers, independent dog walkers, cat boarding, pet sitting (Care.com / Rover not Google-indexed) | **V1.5 — defer** | Layer 5 manual recovery; not Google-indexed. Genuinely V1.5 — requires human-curated additions. |
| 49 | 5.0 | heat list — deferred off-island venues (Cattail Cove, Take-Off Point) | **V1.5 — defer** | Off-island sweep per `manual_recovery_checklist.md` §7. |

**Subtotal:** 18 carries; 5 V1 — operator action (~45–60 min total); 13 V1.5 — defer.

---

## §6 Cross-phase carries (operator-side, repeats across multiple close-outs)

| # | Source | Carry | Disposition | Why |
|---|---|---|---|---|
| 50 | 5.4 → 5.5 → 5.6 → 5.7 → 5.8 → 5.9 → 5.10 → 5.11 (~7 carries) | 86 of 265 HWC providers remain `verified=False` — operator-driven DBA→NPI follow-up | **V1.5 — defer** | Layer 5 manual recovery. Low priority for V1; the verified=False rows still render with the freshness band signaling. |
| 51 | 5.2 → onward | Google Places API key rotation (deferred per operator: "all keys will be changed at the conclusion of this project") | **V1 — operator action** | Operator-locked timing. Pre-launch hygiene. |
| 52 | 5.3 → onward | `data/events.db.bak-*` files accumulating | **V1 — operator action** | Operator prunes when comfortable. No code work. |

**Subtotal:** 3 cross-phase carries; 1 V1.5 — defer; 2 V1 — operator action.

---

## §7 Disposition summary

| Disposition | Count | Effort estimate |
|---|---|---|
| **V1.5 — defer** | 39 | ~50–80h total V1.5 work (verifier surfaces dominate at ~35–60h; per-entity reviews are operator hours, not eng) |
| **V1 — small dev** | 4 | ~20–30 min total (sustainability layer single bundled commit) |
| **V1 — operator action** | 7 | ~2h total operator time |
| **Drop / closed** | 2 | n/a (already resolved or out of scope) |
| **Total inventoried** | 52 | |

**Re-tag recommendation:** #8 (5.8 visitarizona.com + golakehavasu.com event aggregators) is currently labeled V1.5 — defer in §2 but §8 #2 recommends re-tagging to Phase 9 (event scraper subsystem absorbs it naturally). Pending operator decision.

---

## §8 Recommendations to lock with operator

1. **Bundle the 4 sustainability-layer extensions (#17 + #18 + #19 + #20) into a single pre-Phase-7 chore commit.** Total ~20–30 min eng work. Closes a recurring carry that appeared in 5.7, 5.9, 5.10, 5.11 close-outs without ever landing. Recommended commit subject: `chore(data): sustainability layer direct mappings (5.7+5.9+5.10+5.11 V1.5 carries)`. Touches `app/providers/google_types_mapping.py` only (or whichever module owns the direct-map table).

2. **Re-tag carry #8 (5.8 event aggregators) from V1.5 to Phase 9.** Phase 9's RRULE-based event scraper subsystem is the right home for visitarizona.com + golakehavasu.com scrapes, not a V1.5 retrofit. Update `outputs/phase5_8_session_closeout.md` §6 to reflect this if the operator agrees. **Operator-decide.**

3. **Close out the 7 V1 — operator action items in a single ~2h operator session.** Specifically: API key rotation (or defer per existing operator lock), `.bak` file prune, Anderson AZ West un-DRAFT, Butterfly Garden cat-7 fit, ASU SWANSON casing, Simply Savage Designs DRAFT, 5 zero-review Slice E DRAFT reviews. None blocks V1 ship but they tidy the data plane.

4. **Confirm the canonical V1.5 backlog (master plan §4 Phase 13) is the authoritative home for the 39 V1.5 — defer items above.** If yes, recommend a follow-up commit appending a "Phase 5 carry-forward" sub-section to master plan §4 Phase 13 that cross-references this triage doc. If no, propose a separate `docs/maintainability/v1_5_backlog.md` as the inventory home. **Operator-decide.**

5. **The Layer-4 verifier surfaces (#1–#13, #15) are the single largest V1.5 lift category (~35–60h eng).** Operator may want to prioritize within that bundle ahead of V1.5 dispatch. Recommended priority order: (a) AZDHS childcare (#9 — high parent-anxiety category), (b) AZDOR + AZRE lodging (#11 + #12 — combined cat-10 trust story), (c) AZ MVD + AZCC (#1 + #2 — cat-9 dealers/towing), (d) AZ TPT + BBB (#3 + #4 — cat-8 retail), (e) AZ State Parks + NPS + LHC Parks & Rec (#5 + #6 + #7 — cat-7 + cat-12 shared surface), (f) franchise gym chains (#10 — narrow coverage), (g) national pet franchise locators (#15 — lowest yield).

---

## §9 What's NOT in this triage

- **Canonical Phase 13 V1.5 features** (peer recommendations, UGC district layer, SMS alerts, accessibility profiles, `Provider.category → category_id` backfill, owner video, bookings, itinerary builder, real-time prices, white-label, native reviews) — already documented in master plan §4 Phase 13; out of scope here.
- **Phase 6.4 deliverables** (map view, boat-mode toggle, themed group landing pages, search bar) — these are V1 work, not V1.5 carries. Tracked in `outputs/session_close_out_2026_05_19.md` §3 Lane D.
- **Phase 7 deliverables** (chat ENTITY wiring, HALT 3 close-out, cross-entity queries, snowbird-return view) — V1 work, tracked in `outputs/phase7_handoff_note.md` + master plan §4 Phase 7.
- **Apply-script in-session reporting bug** (5.9 carry) — FIXED in 5.10 (via `select(func.count())` + `session.flush()`), validated again in 5.11. Closed; not a V1.5 item.
- **`parks-rec-scrapes` cron unblock** (5.7–5.10 carry) — RESOLVED 2026-05-19 via Claude Code sidecar at `532d48b` + `ba0befb`. Closed; not a V1.5 item.
- **Pytest count drift 2018↔2016** (session close-out §4 carry) — diagnostic curiosity; not a V1.5 item. Forensic answer in `git log --oneline -10 -- tests/` between `54f17e6` and `ba0befb` per the session close-out.

---

*Authored by Cowork primary, 2026-05-20, against origin/main tip `23b3a70`. Lives at `outputs/v1_5_carry_inventory_triage.md`. Closes the observability gap flagged in `outputs/session_close_out_2026_05_19.md` §3 Lane F. Awaits operator dispositions per §8.*
