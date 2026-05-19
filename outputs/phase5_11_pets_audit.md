# Phase 5.11 Pets -- Combined post-load audit (2026-05-17)

> **What this is:** Phase 5.11 §2 audit doc, mirrors `outputs/phase5_10_lodging_audit.md` shape with 5.11-specific findings. Captures the §1 load summary, ambig-pool §2 breakdown, special-audit axis verifications (cat-5 / cat-7 / cat-8 / cat-1), Slice plan, gate-1 projection, and V1.5 carries.
>
> **Sources:** `outputs/phase5_11_db_spot_check.py` (Block A-J), `outputs/phase5_11_ambig_audit_dump.py` (25-record dump + 4 special-audit axes), `outputs/phase5_11_dupe_check.py` (DB-verify cross-cat axes + full ambig enumeration). Authored by Cowork primary, Phase 5 lane, Phase 5.11 session 1 (2026-05-17) post-`1dd443a` SHIP-prep.

---

## §1 Layer 1 load summary

**Discovery (§1.1 dry-run + §1.2 LIVE):**
- 4 in-scope labels (pet stores / dog groomers / dog boarding / dog trainers); clean single-domain `pets`; no Narrow scope wrapper needed.
- §1.1 dry-run (2 of 4 labels): 41 unique places, 4 API requests.
- §1.2 LIVE (all 4 labels): 51 unique places, 6 API requests, ~$0.06 spend.
- §1.2b enrichment: 51/51 cache hits (100% — all pets-domain candidates surfaced as cross-references in prior phases' enrichment sweeps), 0 new API calls.

**Load (§1.3 dry-run + §1.4 LIVE + §1.4b sustainability re-run):**
- 2,647 enriched rows in cumulative cache after §1.2b.
- After `--category pets` filter: 43 rows.
- After ZIP filter: **37 in-LHC rows kept**, 6 dropped (non-LHC ZIPs 73069 / 93446 / 86409 / 86334 / 86429 / 85383).

**§1.4 first-run resolver outcome (pre-sustainability):**

| Counter | Value |
|---|---|
| input rows | 37 |
| inserted (new) | 12 |
| updated (existing) | 0 |
| reconcile skipped (ambig, geo within 50m + name differs) | 25 |
| reconcile merged (geo) | 0 |
| `category_id` resolved (Tier 1) | 9 |
| `category_id` unmapped (operator queue) | **28** |
| EntityCategory rows inserted | 5 |

Of the 12 inserts: 5 mapped immediately (primary types `pet_store` or `veterinary_care` already in `_PRIMARY_TYPE_MAP`), 7 at `category_id=NULL`. Pre-sustainability NULL-primary distribution: 4× `pet_care` + 3× `service`.

**Sustainability commit `1dd443a`** (Phase 5.11 §1 Option A pattern; mirrors 5.10 `bf24e16`):
- Added 4 direct `_PRIMARY_TYPE_MAP` entries: `pet_care` (live; 4 entities), `dog_groomer` + `pet_boarding` + `dog_trainer` (defensive — Google emitted consolidated `pet_care` instead of the kickoff-forecast label-specific types).
- Added 1 new `_DISCOVERY_DOMAIN_FALLBACK` catch-all: `(None, "pets") → "pets"` (handles the 3 `service`-primary entities; same shape as 5.10 Vanderpump fix).
- 4 + 1 + 11 = 16 regression tests in `tests/test_phase5_11_places_load_resolver.py` (parametrized cat-11 + catch-all + preservation guards for 5.10 cat-10 + 5.10 lodging catch-all + 5.9 cat-12 + 5.9 childcare catch-all + 5.4 medical_clinic + 5.2-5.6 domain catch-alls + pre-Phase-5 park/dog_park/veterinary_care/pet_store).

**§1.4b sustainability re-run (post-`1dd443a`):**

| Counter | Value | Delta |
|---|---|---|
| input rows | 37 | (same) |
| inserted (new) | 0 | (entities already exist) |
| updated (existing) | 12 | +12 |
| reconcile skipped | 25 | (same) |
| `category_id` resolved (Tier 1) | **37** | +28 |
| `category_id` unmapped | **0** | -28 |
| EntityCategory rows inserted | 7 | (the 7 previously-NULL inserts now linked to cat-11) |

Sustainability **fully effective**. All 37 in-LHC rows mapped; the 25 ambig-skipped resolve at category-level (resolver returns cat-11) but stay ambig-skipped at entity-level (deferred to §2 audit).

**§1.4 cumulative outcome:**
- 12 new entities in DB
- 8 of 12 in cat-11 (5 from §1.4 first run + 3 from sustainability re-run... wait, 7 sustainability ECs total)

Spot-check shows **13 cat-11 entries** (5 baseline + 8 new). Reconciliation: 12 new entities created total; 8 went to cat-11; the other 4 went to **cat-8 shopping-essentials** via `store` primary type (pre-Phase-5 direct mapping). This matches the kickoff §2 tertiary axis prediction: "Mixed retail venues have `store` or `supermarket` primary -- cat-8 -- so they stay correctly categorized."

The 4 cat-8-routed entries are confirmed via `phase5_11_dupe_check.py` Block 4 as: PetSmart (the existing 5.6-era entry; primary=`store`), Doggie Shades (`store`), Rok Dog Leashes (`store`), plus possibly Tile & Carpets Unlimited (`building_materials_store`) — but the last is a noise match (Tile & Carpets isn't pet-related). So 3 genuine pet-retail cat-8 entries.

---

## §2 Ambig audit -- 25 records (post-§1.4 + sustainability re-run)

`outputs/phase5_11_ambig_audit_data.json` enumerates 25 reconciler-skipped records. All 25 are real LHC pet businesses; the reconcile-50m geo-noise pattern flagged them because they happen to share strip-mall buildings with non-pet entities.

### 2.1 Aggregates

| Metric | Count |
|---|---|
| Total ambig records | **25** |
| No match (orphan, no geo-near entity) | 0 |
| Same-category match (matched entity already in `pets`) | **0** |
| Cross-category match (matched entity in different Tier 1 slug) | 25 |

**Cross-cat slug distribution** (all benign geo-proximity):

| Slug | Count |
|---|---|
| eat-drink | 8 |
| on-the-water | 4 |
| health-wellness-care | 4 |
| home-property-services | 3 |
| events | 2 |
| shopping-essentials | 2 |
| auto-rv-fuel | 1 |
| outdoors-parks-trails | 1 |
| **Total** | **25** |

### 2.2 Special audit (a) -- cat-5 HWC vet-overlap PRIMARY axis: **VACANT**

Kickoff §2 framed cat-5 HWC vet-overlap as the **primary** axis. Forecast: vets in cat-5 from 5.4 absorption via `medical_clinic` direct mapping.

Empirical findings (Block F + dupe-check Block 2):
- 0 entities with primary_type=`medical_clinic` are vets (verified across 52 cat-5 `medical_clinic`-primary entries; all are human medical providers — Family Practice, Pediatrics, Cancer Care, etc.).
- Name keyword sweep: "Veterinary" 0 hits, "Animal Hospital" → 1 cat-11 hit (Animal Hospital of Havasu), "Animal Clinic" 0, "Pet Hospital" 0, "Vet Clinic" 0, "Vet Hospital" 0, "Animal Medical" 0, "DVM" → 1 cat-11 hit (Buckman Cary DVM), "Pet Medical" 0, "Animal Care" → 1 cat-11 hit (Paws and Claws Animal Care).
- All 5 LHC vets are in cat-11 via `veterinary_care` direct mapping (none in cat-5 via `medical_clinic`).

5 ambig-pool candidates matched cat-5 entities, but ALL are strip-mall geo-noise:
- Beautiful Beards Pet Spaw → Fiore's Endorphin Factory (fitness_center, 21.0m) -- pet groomer next to gym
- XO Pet Grooming and Academy → Fiore's Endorphin Factory (fitness_center, 0.3m) -- same strip mall
- Dorita's Place → Stanton Patricia L (doctor, 38.8m) -- pet store near doctor's office
- TagWorks → Milemarkers-Lake Havasu City (medical_clinic, 71.6m) -- pet shop near medical clinic, > 50m so reconcile skipped
- Beautiful Beards Boutique → Fiore's Endorphin Factory (fitness_center, 26.7m) -- same Beautiful Beards franchise location

**V1 policy: KEEP all 5 ambig candidates as Slice E NEW creates in cat-11** (they're pet-primary; the cat-5 match is geometric noise). cat-5 vet axis confirmed VACANT.

### 2.3 Special audit (b) -- cat-7 outdoors-parks-trails dog-park SECONDARY axis: 1 geo-noise hit

Kickoff §2 framed cat-7 dog-park overlap as the secondary axis. Forecast: 1 entity in cat-7 from pre-Phase-5 `dog_park` direct mapping (SARA Park Dog Park).

Empirical findings:
- 1 cat-7 entity matched: SARA Park Dog Park (cat-7, primary=`dog_park`).
- 1 ambig candidate near a cat-7 entity:
  - Picky Mickie's Overnight Pet Sitting → Realtor Park (cat-7, primary=`park`, 42.9m)

This is geo-noise (a pet sitter near a generic city park, not actually a dog park). **V1 policy: KEEP Picky Mickie's as Slice E NEW create in cat-11**; Realtor Park stays cat-7.

### 2.4 Special audit (c) -- cat-8 shopping-essentials retail-overlap TERTIARY axis: 2 PetSmart sub-services

Kickoff §2 framed cat-8 retail-overlap as the tertiary axis. Forecast: mixed-retail venues (Walmart, Albertsons) stay cat-8 via `store`/`supermarket` primary; standalone pet stores route cat-11 via `pet_store` primary.

Empirical findings:
- 1 PetSmart entry in cat-8 (existing, primary=`store`).
- 2 PetSmart sub-services in the §1 ambig pool, both ~65m from Famous Footwear (which is also in the PetSmart shopping plaza):
  - PetSmart Grooming (primary=`pet_care`, 0r)
  - PetSmart Dog Training (primary=`service`, 0r)

This mirrors the **5.10 Heat Hotel ↔ HEAT Bar dual-place_id pattern** (separate Google place_ids for sub-services of a single parent business).

**V1 policy:**
- Existing PetSmart in cat-8: KEEP cat-8 (mixed-retail per kickoff guidance; primary=`store`).
- PetSmart Grooming + PetSmart Dog Training: **Slice E NEW creates in cat-11** as distinct entities. Mirrors 5.10 V1 default (separate entities for distinct place_ids).
- V1.5 carry: PetSmart cat-8 ↔ cat-11 DUAL ADD consideration + franchise consolidation review (link the 3 PetSmart place_ids to a single consolidated entity).

### 2.5 Special audit (d) -- cat-1 eat-drink decorative axis: 9 strip-mall geo-noise hits

Kickoff §2 dropped cat-1 eat-drink as decorative (not gate-relevant). The audit dump surfaces 9 candidates matched against cat-1 entities (the bulk of the cross-cat distribution):

| Candidate | Matched cat-1 entity | Distance |
|---|---|---|
| ManyPets Services | Linda's Italian Foods (grocery_store) | 5.4m |
| Bow Wow's Pet Clips | Booby Falls Restaurant & Rodeo (american_restaurant) | 43.5m |
| De-Tails Mobile Pet Grooming | Chipotle Mexican Grill (mexican_restaurant) | 25.2m |
| Beautiful Beards Pet Spaw | Subway (sandwich_shop) | 11.9m |
| Pooch Paradise, LLC | El Mariachi Mexican Restaurant (mexican_restaurant) | 31.1m |
| Vicki's Grooming | Loaded Gun Coffee (food_store) | 10.4m |
| Penney's Pampered Pawz | Batter Up Bakery (bakery) | 0.0m |
| A Cut Above Grooming | Golf N' Brews (bar) | 5.8m |
| Grooming By Jodi | R.O. Bar (bar) | 32.0m |

All 9 are strip-mall geo-noise (the McCulloch Blvd N pattern shared with 5.6 retail / 5.10 lodging audits). **V1 policy: KEEP all 9 as Slice E NEW creates in cat-11**; cat-1 entries stay cat-1.

### 2.6 Same-business multi-place_id observations (V1.5 carry)

**Beautiful Beards franchise (3 listings):**
- Beautiful Beards Pet Spaw (pet stores label, 54r, primary=`pet_care`)
- Beautiful Beards Pet Spaw (dog groomers label, 5r, primary=`pet_care`) -- distinct place_id, same name
- Beautiful Beards Boutique (pet stores label, 8r, primary=`store`)

V1: 3 separate Slice E NEW creates. V1.5: consolidation review (same franchise, possibly same physical location with multiple Google profiles).

**PetSmart franchise (3 listings, 1 existing + 2 new):**
- PetSmart (existing cat-8, primary=`store`)
- PetSmart Grooming (new, primary=`pet_care`)
- PetSmart Dog Training (new, primary=`service`)

V1: existing stays cat-8; 2 new sub-services Slice E NEW creates in cat-11. V1.5: consolidate to single PetSmart entity with DUAL cat-8 + cat-11.

---

## §3 Layer-4 verifier surface -- Option C deferred (per kickoff §3)

Kickoff §3 resolved as **Option C** (defer Layer-4 verifier to V1.5). No verifier built for 5.11.

V1.5 paths documented in kickoff §3:
- AZ State Veterinary Medical Examining Board (`azvetboard.gov`) -- licenses VETERINARIANS only; out of 5.11 scope by design (vets absorbed by cat-5 HWC for `medical_clinic` primary OR cat-11 for `veterinary_care` primary). Not applicable to 5.11's 4 in-scope labels.
- National pet franchise locators (PetSmart, Petco, Banfield) -- ~5-10% coverage of cat-11 candidates; cost-of-build ~3-5h; not worth V1 build.

**5.11 ships without a Layer-4 verifier surface.** Gate item 3 satisfied via Option C deferral.

---

## §4 Slice plan

| Slice | Action | Count | Notes |
|---|---|---|---|
| A | KEEP (no apply) | 13 + 3 | 13 cat-11 entries already in DB (5 baseline + 8 §1 new) + 3 cat-8 pet-retail (PetSmart, Doggie Shades, Rok Dog Leashes -- V1.5 DUAL carry) |
| B | FLIP cat-X → cat-11 | **0** | No real cross-cat overlap; all 25 ambig matches are geo-noise |
| C | FLIP cat-11 → cat-X | **0** | No cat-11 entries need to leave |
| D | DUAL ADD | **0** for V1 | V1.5 carries: 3 cat-8 pet-retail DUAL + 3 Beautiful Beards consolidation + 3 PetSmart consolidation |
| **E** | **NEW creates cat-11** | **25** | All 25 ambig records, all `commercial` + `draft=0` |
| F | KEEP-ambig (no apply) | **0** | All 25 ambig records are real pet businesses; none are true geo-dupes |
| G | DRAFT / DELETE | **0** | 5 candidates have 0 reviews (Obedience Please, PetSmart Grooming, PetSmart Dog Training, Penney's Pampered Pawz, TagWorks) -- defaulting to draft=0 per 5.10 cadence; operator can DRAFT post-apply if needed |

### Slice E enumeration (25 NEW creates, sorted by place_id per ambig dump)

| # | Name | Primary | Reviews | Discovery label |
|---|---|---|---|---|
| 1 | ManyPets Services | pet_care | 2 | pet stores |
| 2 | Debonair Dogs | pet_care | 31 | pet stores |
| 3 | PetSmart Grooming | pet_care | 0 | pet stores |
| 4 | Suds in the tub dog grooming | pet_care | 5 | pet stores |
| 5 | Bow Wow's Pet Clips | pet_care | 107 | pet stores |
| 6 | Wizard of Pawz | pet_care | 73 | dog groomers |
| 7 | Beautiful Beards Pet Spaw | pet_care | 54 | pet stores |
| 8 | Royal Furs & Tails Spaw LLC | pet_care | 3 | pet stores |
| 9 | De-Tails Mobile Pet Grooming | pet_care | 33 | pet stores |
| 10 | XO Pet Grooming and Academy | pet_care | 7 | dog groomers |
| 11 | Gentle Touch Pet Grooming | pet_care | 27 | dog groomers |
| 12 | Beautiful Beards Pet Spaw (2nd) | pet_care | 5 | dog groomers |
| 13 | Pooch Paradise, LLC | pet_care | 11 | pet stores |
| 14 | Vicki's Grooming | pet_care | 37 | dog groomers |
| 15 | Obedience Please | service | 0 | dog trainers |
| 16 | Picky Mickie's Overnight Pet Sitting | pet_care | 9 | dog boarding |
| 17 | Dorita's Place | pet_store | 347 | pet stores |
| 18 | Michelle's Bark In Style Grooming Salon | pet_care | 28 | pet stores |
| 19 | Paws Dog Grooming | pet_care | 41 | pet stores |
| 20 | Penney's Pampered Pawz | pet_care | 0 | dog groomers |
| 21 | A Cut Above Grooming | pet_care | 93 | pet stores |
| 22 | PetSmart Dog Training | service | 0 | dog trainers |
| 23 | TagWorks | store | 0 | pet stores |
| 24 | Grooming By Jodi | pet_care | 96 | dog groomers |
| 25 | Beautiful Beards Boutique | store | 8 | pet stores |

All 25 created via `outputs/apply_phase5_11_pets_audit.py` (mirror of `outputs/apply_phase5_10_lodging_audit.py`; reads place_ids from `outputs/phase5_11_ambig_audit_data.json` at runtime; idempotent; dry-run flag).

---

## §5 Top-10 by review count -- crowd_notes targets

| Rank | Name | Reviews | Primary | Status |
|---|---|---|---|---|
| 1 | Dorita's Place | 347 | pet_store | Slice E NEW |
| 2 | Bow Wow's Pet Clips | 107 | pet_care | Slice E NEW |
| 3 | Grooming By Jodi | 96 | pet_care | Slice E NEW |
| 4 | A Cut Above Grooming | 93 | pet_care | Slice E NEW |
| 5 | Wizard of Pawz | 73 | pet_care | Slice E NEW |
| 6 | Beautiful Beards Pet Spaw (54r) | 54 | pet_care | Slice E NEW |
| 7 | Paws Dog Grooming | 41 | pet_care | Slice E NEW |
| 8 | Vicki's Grooming | 37 | pet_care | Slice E NEW |
| 9 | De-Tails Mobile Pet Grooming | 33 | pet_care | Slice E NEW |
| 10 | Debonair Dogs | 31 | pet_care | Slice E NEW |

Plus the 5 baseline cat-11 entries (review counts unknown post-spot-check; verify via §4 top-10 discovery script). The top-10 will be drawn from the combined cat-11 set post-§4 apply, ordered by review count.

Pet-service reviewer signals per kickoff §4: staff care for animals, cleanliness of facility, pricing transparency, scheduling availability, named staff callouts (groomers often have repeat-client relationships), kid- and family-friendliness, training methodology, facility size/layout, safety supervision ratios.

Source: `Provider.google_review_snippets` (own column, NOT inside `attributes` JSON, per the 5.4 close-out source-path correction). Forecast snippet coverage: ~70-90% for pet services (chains abundant, independents lower).

---

## §6 heat_exposure -- indoor default + 2-5 outdoor overrides

Kickoff §4: "**`indoor` for most 5.11 entries** (pet stores, dog groomers, dog trainers in studios, vet clinics are all indoor-by-definition). **`outdoor` overrides** expected for: pet boarding facilities with outdoor runs / dog daycare with outdoor yards (most LHC pet boarding venues have outdoor exercise areas). Expected override count: 2-5."

**Outdoor override candidates (forecast based on names + primary types):**
- The Dog House Doggy Day Care (post-§1 cat-11, primary=`pet_care`) -- daycare typically has outdoor yards
- Pet Oasis Doggy Daycare and Spa (post-§1 cat-11, primary=`pet_care`) -- daycare typically has outdoor yards
- Picky Mickie's Overnight Pet Sitting (Slice E NEW, primary=`pet_care`) -- overnight boarding may have outdoor runs
- Royal Furs & Tails Spaw LLC (Slice E NEW, primary=`pet_care`) -- "Spaw" suggests grooming spa, likely indoor
- Pooch Paradise, LLC (Slice E NEW, primary=`pet_care`) -- name suggests boarding/daycare with outdoor

3-5 outdoor overrides expected, in line with kickoff forecast. Apply via `outputs/apply_phase5_11_pets_heat_exposure.py` (mirrors `apply_phase5_10_lodging_heat_exposure.py` shape with cat-11 swaps).

**No `water_adjacent` overrides expected** for cat-11 (pet services aren't lake-adjacent by definition).

---

## §7 V1.5 carries

- **Beautiful Beards franchise consolidation** (3 place_ids -- Pet Spaw 54r + Pet Spaw 5r + Boutique 8r). Same physical location with multiple Google profiles? Or distinct sub-businesses?
- **PetSmart franchise consolidation** (3 place_ids -- PetSmart in cat-8 + PetSmart Grooming in cat-11 + PetSmart Dog Training in cat-11). Mirrors 5.10 Heat Hotel pattern.
- **3 cat-8 pet-retail DUAL candidates** (PetSmart, Doggie Shades, Rok Dog Leashes -- all primary=`store`, cat-8). Consider DUAL cat-8 + cat-11 if pet-primary in V1.5 surface.
- **5 zero-review Slice E entries** worth DRAFT-flag review (Obedience Please, PetSmart Grooming, PetSmart Dog Training, Penney's Pampered Pawz, TagWorks) -- may be defunct / placeholder Google listings.
- **TagWorks specifically** -- primary=`store`, name doesn't clearly indicate pet-primary; could be a key/tag cutting shop rather than pet-tag retail. Operator confirms.
- **Beautiful Beards Boutique specifically** -- primary=`store`, could be pet supply boutique or generic boutique. Operator confirms.
- **Cat boarding services** -- per kickoff §1 Layer 5, smaller surface than dog boarding; some may not have Google listings. Manual recovery surface.
- **Mobile groomers** -- 2 in this load (Mandy's Mobile, De-Tails Mobile). More may exist Google-unindexed. Manual recovery surface.
- **Independent dog walkers** -- typically not Google-indexed as venues. Manual recovery surface.
- **Layer-4 verifier surface** -- AZ Vet Board + national chain locators paths documented in §3; deferred to V1.5 per Option C.

---

## §8 Gate-1 projection

| Source | Count |
|---|---|
| Baseline cat-11 entries (pre-§1) | 5 |
| §1.4 first-run inserts → cat-11 (mapped primary) | 5 |
| §1.4 sustainability re-run resolutions → cat-11 (post-`1dd443a`) | 7 |
| §1.4 inserts → cat-8 (primary=`store`, kickoff §2 tertiary axis prediction) | -4 (not in cat-11) |
| §2 Slice E NEW creates → cat-11 (this apply-script) | **+25** |
| **Total cat-11 post-§2** | **38** |

Gate-1 target: **≥20**. Forecast 38 = **1.9× target**. Comfortably clear.

Gate-1 query uses `(e.entity_type != 'commercial' OR provider-visible)` OR-clause shape per kickoff §6 (mirrors 5.2/5.7/5.8/5.9/5.10 gate verifications). For cat-11 all entries are `commercial` so the OR-clause routes via `provider-visible` (provider exists + is_active=1 + draft=0). All 38 forecast entries should render.

---

## §9 Apply-script reference

See `outputs/apply_phase5_11_pets_audit.py` for the executable Slice E apply.

**Pre-flight before apply:**
1. Confirm sustainability commit `1dd443a` is on `origin/main` (verified post-bundle apply).
2. Confirm CI green on `1dd443a` (operator runs `gh run list --workflow CI --branch main --limit 5`).
3. Confirm `outputs/phase5_11_ambig_audit_data.json` exists (re-run `outputs/phase5_11_ambig_audit_dump.py` if missing).
4. Stop the FastAPI dev server if running (events.db lock).

**Apply order:**
1. Dry-run: `python outputs/apply_phase5_11_pets_audit.py --dry-run` -- expect "Slice E NEW creates cat-11: 25 created, 0 skipped, 0 missing"; rolls back.
2. Apply: `python outputs/apply_phase5_11_pets_audit.py` -- 25 NEW creates committed; post-apply count delta +25 (13 → 38).
3. Re-run spot-check: `python outputs/phase5_11_db_spot_check.py` -- verify cat-11 = 38 in Block E (5 baseline + 33 new... wait 13 + 25 = 38, so 38 total).
4. Surface to agent for §4 heat_exposure + crowd_notes work.

---

## §10 Sustainability validation

Sustainability commit `1dd443a` validated empirically by §1.4b re-run:
- `category_id` unmapped: 28 → 0 (sustainability fully effective).
- 7 EntityCategory rows added for the 4 `pet_care` + 3 `service` previously-NULL inserts.
- All 4 new direct `_PRIMARY_TYPE_MAP` mappings (`pet_care` + 3 defensive) + 1 new `(None, "pets")` catch-all functioning as designed.

V1.5 sustainability layer extensions to consider (carry):
- `pet_supply_store` direct mapping (if Google ever emits this primary type — currently absorbed by `pet_store` + `store`).
- `animal_shelter` direct mapping (pre-Phase-5 unmapped; potential cat-11 or cat-13 public-civic depending on operator decision).
- `aquarium_store` direct mapping (specialty retail; pre-Phase-5 unmapped).

---

## §11 Coordination summary

| Lane | Coordination need |
|---|---|
| Phase 6 (parallel agent OR in-line) | Extend `outputs/claude_code_dispatch_phase6_amend5_to_8.md` consolidated dispatch to amend5-11 (covers all 5.5-5.11 SHIPPED ledger lines on master_build_plan.md §4). Coordinate timing with 5.11 SHIP commit. |
| Cursor | No dispatches pending (5.11 produces its own regression tests in-lane: +16 at `1dd443a`). |
| Operator | Audit doc carry-over actions (V1.5 -- §7 list); file-prune list (3 sandbox-leaked probe files + hava_api_catalog.docx + .bak files); API key rotation deferred to project end. |

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.11 session 1 (2026-05-17) post-`1dd443a` SHIP-prep. Phase 5.11 §2 audit complete; Slice E apply-script ready; §4 heat_exposure + crowd_notes next.*
