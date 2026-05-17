# Phase 5.10 -- Lodging & Vacation Rentals -- 2 audit (combined pre+post)

> **What this is:** the combined 1 post-load + 2 ambiguous-queue audit
> for Phase 5.10 (`lodging-vacation-rentals`, cat-10). Mirrors
> `outputs/phase5_9_classes_audit.md` structure with 5.10-specific
> axes (cat-3 on-the-water primary / cat-1 eat-drink secondary / cat-2
> events tertiary).
>
> **Source data:**
> - `outputs/phase5_10_ambig_audit_data.json` (37 records from 1 load)
> - `outputs/phase5_10_ambig_audit_stdout.txt` (dump stdout, aggregates +
>   3 special-audit sections + edge-case rubric for 67 cat-10 entries +
>   DB-verify carry candidates)
> - `outputs/phase5_10_dupe_check_stdout.txt` (DB-verify for 5 Slice E
>   hotel candidates + HEAT Bar + Slice D waterfront candidates + 7
>   lodging-primary vacation rentals + full 37-record ambig
>   enumeration split by discovery_domain)
> - `outputs/phase5_10_db_spot_check.py` (pre-1 DB state) +
>   `outputs/phase5_10_post_load_check.py` (post-1.6+1.7c DB state)
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.10 session 1
> (2026-05-17) post-1-load, pre-2-apply. Per the 5.8 + 5.9 close-out
> lesson, every cross-cat move premise was DB-verified via the dupe-
> check before slice assignment.
>
> **Pre-1 cat-10 count: 31 entities** (per 0 spot-check Block D; the
> pre-Phase-5 `rv_park` direct mapping caught 14 RV parks; the pre-
> Phase-5 `lodging` direct mapping caught 7 lodging-primary vacation
> rentals; the secondary-types[] first-match behavior on `lodging`
> caught 6 campgrounds + 2 mobile_home_park + 1 camping_cabin + 1
> service).
>
> **Pre-2 cat-10 count: 67 entities** (post-1.6 load 31 + 35 inserts
> with EntityCategory; post-1.7c Vanderpump villa flipped from
> NULL->cat-10 +1).
>
> **Post-2 cat-10 count projection: 73 entities** (67 + 6 NEW Slice E
> creates).

---

## 1 Layer 1 load summary

```
1.6 ORIGINAL LOAD (pre-1.7 sustainability commit bf24e16):
[load] enriched rows: 2645
[load] after --category lodging-vacation-rentals filter: 365 rows
[load] after ZIP filter: 297 kept, 68 dropped (mostly Parker / Bullhead /
                                                Mohave Valley / out-of-state)
[load] input rows:         297
[load] skipped (no name):  0
[load] inserted (new):     36
[load] updated (existing): 224
[load] reconcile skipped (ambiguous): 37
[load] reconcile merged (geo):        0
[load] category_id resolved (Tier 1): 295  <- 99.3% resolution rate
[load] category_id unmapped (operator queue): 2  <- Vanderpump villa + JR RV Rentals
[load] EntityCategory rows inserted:  35  <- 36 inserts - 1 NULL-cat (Vanderpump)

1.7c RE-RUN POST-bf24e16 SUSTAINABILITY COMMIT:
[load] input rows:         297
[load] inserted (new):     0    <- everything in DB from 1.6
[load] updated (existing): 260  <- 224 original + 36 new this re-run
[load] reconcile skipped (ambiguous): 37  <- stable across re-runs
[load] reconcile merged (geo):        0
[load] category_id resolved (Tier 1): 297  <- 100%; +2 from 1.6
[load] category_id unmapped (operator queue): 0  <- down from 2; sustainability VALIDATED
[load] EntityCategory rows inserted:  1  <- Vanderpump villa cat-10 link added
```

**Sustainability validation:** 0 unmapped of 297 post-1.7c. The 5 new
direct `_PRIMARY_TYPE_MAP` entries (hotel/motel/resort_hotel/extended_
stay_hotel/bed_and_breakfast) + new `(None, "lodging")` catch-all +
existing pre-Phase-5 `lodging`/`rv_park` direct mappings + secondary-
types[] first-match behavior + 5.2 `(None, "lake_recreation") ->
"on-the-water"` catch-all together covered every primary_type Google
emitted. The 1.7 sustainability commit shipped at `bf24e16` (Phase
5.10 sustainability layer).

**Cost actuals:** 10 discovery requests + 1 new enrichment (85 of 86
cache-hit). ~$0.32 total -- under the kickoff 1 forecast $0.30-0.60
(post-revision; original was $0.50-1.20).

---

## 2 Discovery scope vs load scope (key insight)

| Stage | Filter | Output |
|---|---|---|
| Discovery (Narrow scope wrapper at `outputs/phase5_10_narrow_label_filter.py`) | 5 in-scope lodging-domain labels only | 86 unique places |
| Enrichment | All 86 (cache-aware) | 86 / 1 new / 85 cache-hit |
| **Load** (`--category lodging-vacation-rentals`) | Filters cache by `_first_seen_domain in {"lodging", "lake_recreation"}` | **365 -> 297 (ZIP) -- INCLUDES all lake_recreation-cached entries from prior phases (5.2 absorption + cache-only)** |

**Implication:** the 224 1.6 updates (= 260 1.7c updates - 36 newly
inserted from 1.6) are mostly **5.2-absorbed lake_recreation entities**
(marinas/boat rentals/boat repair/boat dealers/etc.) being re-touched.
They KEEP cat-3 via the preserve-operator-choice rule
(`places_load.py:537-538`). The 37 ambig include both fresh 5.10
discoveries (5 lodging labels) AND 5.2-cached lake_recreation entries
that the reconciler caught on geo+name. **Most of the 37 ambig are
deferred-to-current-cat candidates** (lake_recreation-domain noise);
only **6 are real cat-10 NEW creates** worth applying via Slice E.

---

## 3 Ambig aggregate

```
=== aggregates: 37 ambig-skipped breakdown ===
  total ambig hits:        37
  no match (orphan ambig): 2   (Hooks Boat Rentals, Dek X USA LLC)
  same-category match:     0   (matched entity already in lodging-vacation-rentals)
  cross-category match:    35  (matched entity in a different Tier-1 slug)
  cross-cat slug breakdown:
    eat-drink                            25   <- McCulloch Blvd N
                                                strip-mall false-ambig pattern
    health-wellness-care                 3
    shopping-essentials                  2
    home-property-services               2
    on-the-water                         1
    auto-rv-fuel                         1
    events                               1
```

**Eat-drink dominance (25)** mirrors the 5.6 strip-mall false-ambig
pattern -- 5.10 candidates clustered along McCulloch Blvd N (LHC's
main commercial corridor) routinely match nearby restaurants within
50m. Benign geo-proximity; not real misroutes.

**Domain split of the 37 ambig records** (per dupe-check [5]):
- **Lodging-domain candidates: 8** (Slice E NEW-create surface; 6
  strong + 2 uncertain)
- **Lake_recreation-domain candidates: 29** (Slice F KEEP-ambig;
  geo-noise -- the bundle's broader load scope pulled cached
  5.2-absorbed boat/marina entities through the ambig filter)

---

## 4 Slice decisions (this is what the apply-script implements)

### Slice A -- KEEPs (no apply needed)

**67 cat-10 entries (post-1.6+1.7c)** all stay in cat-10:
- 14 `rv_park` -- pre-Phase-5 direct mapping
- 13 `hotel` (new from 1) -- 5.10 1.7 direct mapping
- 7 `lodging` (vacation rental properties; pre-existing or new) --
  pre-Phase-5 direct mapping
- 6 `campground` -- secondary-types[] match on `lodging` direct map
- 15 `cottage` (vacation rentals; new from 1) -- secondary-types[]
  match on `lodging` direct map
- 4 `motel` (new from 1) -- 5.10 1.7 direct mapping
- 2 `resort_hotel` (new from 1) -- 5.10 1.7 direct mapping
- 2 `mobile_home_park` -- secondary-types[] match on `lodging`
- 1 `camping_cabin` -- secondary-types[] match on `lodging`
- 1 `guest_house` (new from 1) -- secondary-types[] match on `lodging`
- 2 `service` (JR RV Rentals + Vanderpump Rules villa) -- caught via
  the NEW `(None, "lodging")` catch-all shipped at `bf24e16`

**HEAT Bar (cat-1 eat-drink) stays put** -- per dupe-check [2], HEAT
Bar is in DB with primary='hotel' but cat-1 (loaded in prior phase).
The entity is named "HEAT Bar" -- its identity is a bar, not the
hotel. The primary='hotel' tag is a Google Maps data quirk for the
bar amenity at Heat Hotel. The new Heat Hotel scrape (separate
place_id) becomes Slice E #1 cat-10 NEW-create. Both entities
co-exist at the same physical address (8.6m apart per ambig dump);
this is the **5.7/5.8 dual-place_id pattern** documented in 9 V1.5
carry.

### Slice B -- FLIP cat-X -> cat-10: 0 entries

(HEAT Bar considered but is named "HEAT Bar" -- its identity is a
bar, not the hotel. KEEP cat-1.)

### Slice C -- FLIP cat-10 -> cat-X: 0 entries

(No cat-10 entries belong elsewhere.)

### Slice D -- DUAL ADD cat-3 to cat-10: 0 entries

Kickoff 2 forecast 2-5 waterfront-resort DUAL adds. Dupe-check [3]
empirically refuted: all candidates are INLAND coordinates:
- **Lakeside Inn - Lake Havasu City** (motel, cat-10): coords
  `(34.47522, -114.35110)`, address "111 London Bridge Rd" -- 600-800m
  inland from Lake Havasu's western shoreline (~lng -114.36). "Lakeside"
  in name is marketing; property is in town.
- **Havasu Dunes Resort + GetAways at Havasu Dunes Resort**
  (resort_hotel, cat-10, 2 distinct place_ids same coords): coords
  `(34.45721, -114.32852)`, address "620 Lake Havasu Ave" -- southern
  LHC, well inland (lake is west). Also a **dual-place_id pattern**
  (V1.5 carry).
- **7 cat-10 lodging-primary vacation rentals** (Lake-Area Retreat,
  Sunchief Lake Havasu, Luxury Retreat /pool spa near marina, Lake
  Havasu Luxury Oasis, Havasu Hacienda, Downtown LUX Retreat, 9 Hole
  Mini-golf) -- per dupe-check [4], all 7 are inland residential LHC
  neighborhoods. Names use "Lake" / "Havasu" as marketing references,
  not literal location.

The waterfront-DUAL axis simply doesn't materialize for V1; no
candidates have the lake-PRIMARY identity that would justify dual-cat.

### Slice E -- NEW creates in cat-10 (6 entries via `create_provider_and_entity` dual-write)

| Candidate | place_id (from enrichment) | primary_type | reviews | Why NEW-create |
|---|---|---|---|---|
| **Heat Hotel** | (in enrichment cache) | `hotel` | 406 | Lodging-domain discovery via `hotels` label. Ambig-matched against HEAT Bar (cat-1 eat-drink, 8.6m). HEAT Bar is the hotel's bar amenity (separate Google listing); Heat Hotel is the hotel proper. Per 5.7/5.8 dual-place_id pattern, both entities co-exist. Dupe-check [1] confirmed 0 entities in DB by name. **NEW-create**; route to cat-10 via 5.10 1.7 `hotel` direct mapping. |
| **Travelodge by Wyndham Lake Havasu** | (in enrichment cache) | `hotel` | 901 | Lodging-domain discovery via `hotels` label. Ambig-matched against Angelina's Italian Kitchen (cat-1, 49.6m) -- adjacent unrelated restaurant; geo-noise. Highest review count of the 6 NEW candidates. Chain hotel. **NEW-create**. |
| **Knights Inn Lake Havasu City** | (in enrichment cache) | `hotel` | 266 | Lodging-domain discovery via `hotels` label. Ambig-matched against New West Dental Lab (cat-5 HWC, 41.8m) -- unrelated medical neighbor. **NEW-create**. |
| **LAKE PLACE INN** | (in enrichment cache) | `motel` | 64 | Lodging-domain discovery via `hotels` label. Ambig-matched against New West Dental Lab (cat-5 HWC, 41.7m) -- co-located strip with Knights Inn; unrelated. **NEW-create**. |
| **Holiday Inn Express & Suites Lake Havasu - London Bridge by IHG** | (in enrichment cache) | `hotel` | 619 | Lodging-domain discovery via `hotels` label. Ambig-matched against The Local Craving (cat-1, dessert_shop, 49.0m) -- adjacent unrelated dessert shop; geo-noise. Chain hotel. **NEW-create**. |
| **Queens Bay Resort Condominiums** | (in enrichment cache) | `lodging` | 69 | Lodging-domain discovery via `hotels` label. Primary='lodging' directly maps to cat-10 (pre-Phase-5 direct mapping). Ambig-matched against Havasu Handyman Services (cat-4 home-property-services, 11.0m) -- unrelated handyman. Name has "Bay" -- possible future waterfront-DUAL review (V1.5 carry; coordinates not yet verified). **NEW-create**. |

### Slice F -- KEEP ambig (no apply needed) -- 31 entries

**29 lake_recreation-domain candidates** discovered via boat/marina/RV
labels. The bundle's broader load scope pulled these through the
ambig filter but they belong in their current cats (cat-3
on-the-water for marina/boat shape; cat-9 auto-rv-fuel for RV
shape; etc.). Per kickoff 1 Narrow scope decision, the 24
lake_recreation labels are deferred to V1.5 -- don't NEW-create
them in 5.10. Notable Slice F entries (all KEEP-ambig; no apply):

| Candidate | primary | reviews | discovery label | Notes |
|---|---|---|---|---|
| Stonebridge Pier | marina | 3 | marinas | Low signal; 6.8m from Hav A Craving (eat-drink) |
| Sunset Charter & Tour Co. | tour_agency | 338 | pontoon rentals | High signal; 42.7m from Burgers by the Bridge (eat-drink); V1.5 cat-3 NEW-create candidate |
| Dixie Belle | tour_agency | 112 | boat rentals | 20.6m from Papa Leone's (eat-drink); V1.5 cat-3 |
| At The Bridge Rentals | service | 284 | boat rentals | High signal; 0.0m from Ru Art Gallery (cat-2 events) |
| HAVASU RENTALS | service | 217 | boat rentals | V1.5 cat-3 candidate |
| Camp Kayak Pack | sporting_goods_store | 2 | paddleboard rentals | Low signal |
| Lake Havasu VIP Storage | storage | 28 | boat storage | Low signal; commercial storage |
| Rubba Duck Safari Tour | tour_agency | 38 | boat tours | V1.5 cat-3 candidate |
| River Sports Boat Rentals | service | 40 | boat rentals | V1.5 cat-3 candidate |
| ...(plus 20 more in the 29) | | | | |

**2 uncertain lodging-domain candidates:**

| Candidate | primary | reviews | Notes |
|---|---|---|---|
| **Havasu Suites** | `travel_agency` | 6 | primary is travel_agency (booking agency), not a Google lodging primary_type. 6 reviews = low signal. 6.6m from Forget Me Nots Gift Shop. Likely a booking/management entity, not a hotel itself. **V1.5 carry** for re-evaluation. |
| **Xanadu** | `point_of_interest` | 0 (None) | primary=point_of_interest is generic Google catch-all. 0 reviews. Discovered under `hotels` label but no signal of being a hotel. May be a private residence or defunct business. **V1.5 carry** for identity verification. |

**Rationale:** kickoff 1 explicitly deferred all lake_recreation labels
(24 in total) to V1.5; NEW-creating boat/marina entities in 5.10 would
expand cat-3 / cat-9 scope beyond what 5.2 / 5.5 chose to absorb. The
2 uncertain lodging candidates have insufficient signal to justify
NEW-create as cat-10 entries; defer to V1.5 for per-row review.

### Slice G -- DRAFT / DELETE: 0 entries

No candidates flagged for draft-create or delete.

### Cross-cache informational: 0 entries

Unlike 5.9 (which had 7 cross-cache informational records from prior
phases' overlap with cat-12 labels), 5.10's two-domain bundle filter
(`_first_seen_domain in {lodging, lake_recreation}`) is the same
filter the load uses, so no cross-cache leak.

---

## 5 Special audit (a) -- cat-3 on-the-water primary axis

```
=== special audit (a): cat-3 on-the-water primary axis ===
  - cand 'Stonebridge Pier'        label='marinas'      -> 'Champion Rentals' @ on-the-water (service, 61.8m)
  - cand 'Louis Performance Engines' label='boat repair'  -> 'Savage Marine' @ on-the-water (service, 20.6m)
  - cand 'HAVASU RENTALS'          label='boat rentals' -> 'London Bridge' @ on-the-water (bridge, 63.3m)
```

**0 lodging-domain hits.** All 3 cat-3 ambig hits are lake_recreation-
domain candidates (boat businesses near marinas). The kickoff 2
forecast waterfront-resort DUAL axis revises to 0 (Slice D = 0)
because:
1. Zero of the named waterfront resorts pre-exist in cat-3 from 5.2
   (per 0 spot-check Block E: London Bridge Resort, Nautical Beachfront,
   Heat Hotel, Havasu Springs, Pirate Cove, Sandpoint, Black Meadow
   all return 0 entities)
2. None of the existing cat-10 entries are waterfront-primary (per
   dupe-check [3]+[4] coordinate verification)
3. The Heat Hotel NEW-create (Slice E #1) is inland (HEAT Bar address:
   "1420 McCulloch Blvd N" -- in town, not at lake)

---

## 6 Special audit (b) -- cat-1 eat-drink secondary axis

**25 ambig hits but only 1 real lodging-domain match.** The 24
geo-noise hits are all lake_recreation-domain candidates (boat
dealers, boat rentals, kayak rentals, RV repair, boat storage,
etc.) near restaurants -- McCulloch Blvd N strip-mall geo-proximity
pattern (5.6 history confirms).

**The 1 real lodging-domain hit:**
- **Heat Hotel** (Slice E #1 candidate, primary=`hotel`, 406 reviews)
  -> **HEAT Bar** (existing cat-1 entity at 1420 McCulloch Blvd N,
  primary=`hotel`, 8.6m) -- per dupe-check [2], HEAT Bar IS the bar
  amenity at the Heat Hotel. Both are real distinct businesses /
  distinct place_ids. Same physical address.

**V1 decision:** KEEP HEAT Bar in cat-1 (named "HEAT Bar" -- identity
is a bar); NEW-create Heat Hotel in cat-10 (Slice E #1). No DUAL
cross-link added in V1; document the same-building observation in
V1.5 carry for potential cross-link consideration.

**Other lodging-domain ambig matches against cat-1 (all geo-noise):**
- Travelodge by Wyndham -> Angelina's Italian Kitchen (49.6m) --
  adjacent unrelated
- Holiday Inn Express by IHG -> The Local Craving (dessert, 49.0m) --
  adjacent unrelated

---

## 7 Special audit (c) -- cat-2 events tertiary axis

```
=== special audit (c): cat-2 events tertiary axis ===
  5 ambig hits, all at adjacency distances (34-73m); 0 real cross-links.
```

**0 real lodging-domain matches.** The 5 hits:
- Southwest Outfitters (kayak rentals) -> American Legion (34.0m) -- lake_recreation
- **Knights Inn Lake Havasu City** (Slice E #3) -> The Q Art Gallery (73.0m) -- adjacent, unrelated
- Camp Kayak Pack (paddleboard rentals) -> American Legion (37.4m) -- lake_recreation
- At The Bridge Rentals (boat rentals) -> Ru Art Gallery and Boutique (0.0m) -- lake_recreation; possibly same-building (V1.5 carry)
- **LAKE PLACE INN** (Slice E #4) -> Jaque Meng (73.0m) -- adjacent, unrelated

The 2 lodging hits (Knights Inn + LAKE PLACE INN) are both at 73m
which is at the `NEAR_GEO_INCLUDE_M` upper threshold -- pure adjacency,
not co-location. The kickoff 2 forecast resort-event-venue DUAL axis
revises to 0 (no resort hosts a 5.10 event venue as a primary
sub-amenity in the ambig pool).

---

## 8 Pre-4 gate-1 projection

| Source | Count |
|---|---|
| 31 pre-1 cat-10 entries (5.2 absorption + pre-Phase-5 direct mappings) | +31 |
| + 35 1.6 inserts that landed in cat-10 (35 of 36; the 36th was Vanderpump as NULL-cat) | +35 |
| + 1 1.7c flip (Vanderpump villa NULL -> cat-10 via new catch-all) | +1 |
| **= 67 entities pre-2 cat-10** | **67** |
| + 6 Slice E NEW creates (Heat Hotel, Travelodge, Knights Inn, LAKE PLACE INN, Holiday Inn Express, Queens Bay Resort) | +6 |
| **Total cat-10 entities post-2** | **73** |

Comfortably >= 20 gate threshold (3.65x target).

**Gate-1 query shape:** must use the `(e.entity_type != 'commercial'
OR provider-visible)` OR-clause shape from
`outputs/phase5_2_gate_verification.py` for parity with prior phase
verifiers -- though for 5.10 all 73 entities are expected
`entity_type='commercial'` (no `place`-typed entries; no
swimming_pool / tennis_court-style public amenities in lodging
scope). The OR-clause is still required for route-render match.

---

## 9 Carry-forwards to V1.5 + Phase 5.11

### Slice carry -- V1.5 reconsideration

- **HEAT Bar <-> Heat Hotel dual-place_id observation** -- same
  physical building (8.6m apart in 5.10 1 ambig dump). HEAT Bar is in
  cat-1 eat-drink with primary='hotel' (Google data quirk); Heat
  Hotel is the new cat-10 entry. V1.5: consider (a) cross-link via
  DUAL ADD cat-10 to HEAT Bar (it's the hotel amenity); (b) DUAL ADD
  cat-1 to Heat Hotel (the hotel's bar IS its restaurant draw); or
  (c) consolidate as same entity. V1 keeps them distinct.
- **Havasu Dunes Resort <-> GetAways at Havasu Dunes Resort dual-
  place_id observation** -- same address (620 Lake Havasu Ave),
  same coords (34.45721, -114.32852), 2 distinct Google place_ids,
  both in cat-10 as resort_hotel. Likely "GetAways" is the booking
  entity; "Havasu Dunes Resort" is the property itself. V1.5: consider
  consolidation or distinguishing the relationship in a `parent_entity_id`
  attribute.
- **Lake Havasu Aquatic Center analog** -- 5.10 didn't surface a
  cross-cat civic facility like 5.9's Aquatic Center; no equivalent
  for 5.10.
- **Havasu Suites (travel_agency primary, 6 reviews)** -- 5.10 1
  ambig pool. Identity uncertain (booking agency vs hotel). V1.5
  carry for per-row identity verification.
- **Xanadu (point_of_interest primary, 0 reviews)** -- 5.10 1 ambig
  pool. Identity uncertain (private home / defunct / non-lodging).
  V1.5 carry for identity verification.
- **Queens Bay Resort Condominiums** -- name has "Bay"; coordinates
  not yet checked for waterfront-DUAL. V1.5 review.
- **5.10 1 ambig lake_recreation surface** -- 29 boat/marina/RV
  candidates surfaced under lake_recreation labels (e.g., Sunset
  Charter & Tour Co. at 338 reviews; Dixie Belle at 112 reviews;
  HAVASU RENTALS at 217 reviews) are NEW-create candidates for cat-3
  on-the-water if the 5.2 lane is re-opened in V1.5.
- **Stonebridge Pier** (marina primary, 3 reviews, lake_recreation):
  6.8m from Hav A Craving (cat-1). Low signal; V1.5 evaluate as
  potential cat-3 marina entry.

### Sustainability layer V1.5 extensions

- Consider `camping_cabin` direct mapping -> cat-10 (catches the 1
  camping_cabin entry today via secondary-types[] match on `lodging`;
  direct entry would be more explicit)
- Consider `cottage` direct mapping -> cat-10 (catches the 15 cottage
  entries today via secondary-types[] match; direct entry would route
  vacation rental properties regardless of types[] composition)
- Consider `mobile_home_park` decision -- currently caught in cat-10
  via secondary-types[] match. Some may belong elsewhere (residential
  shape vs lodging shape). V1.5 per-entry review.
- Consider `guest_house` direct mapping -> cat-10

### Phase 5.11 carry -- pets (`pets`, cat-11)

5.11 is the last remaining Tier-1 category. Per kickoff 1 framing
correction in the 5.10 boot prompt, pets IS single-domain (per
`DISCOVERY_CATEGORY_TO_DOMAINS["pets"] = frozenset({"pets"})`) with no
existing pets catch-all -- so the 5.11 sustainability-PIVOT framing
should hold (unlike 5.10 which was a two-domain bundle).

The pre-Phase-5 mappings `veterinary_care` + `pet_store` are already
in `_PRIMARY_TYPE_MAP`. 5.11 may need to add `dog_groomer` /
`pet_boarding` / `dog_trainer` direct mappings if they surface.

### Phase 6 carry -- `parks-rec-scrapes` cron fix

Root cause identified in Phase 5.7 4.5 sidebar; 3 fix options
surfaced. Default deferred-to-sidecar (kickoff 4.5). Not in 5.10 scope.

### Phase 6 carry -- Amendments 5+6+7+8 (and now potentially 9+10)

Consolidated dispatch authored at
`outputs/claude_code_dispatch_phase6_amend5_to_8.md` per Phase 5.9
0 operator decision (defer all 4 to Phase 6 sidecar). Phase 6 lane
or Claude Code parallel agent to land before next 5.x dispatch.
Operator may want to extend to amend5-9 or amend5-10 at SHIP time.

---

## 10 Apply-script reference

`outputs/apply_phase5_10_lodging_audit.py` will implement Slice E
above (Slices A through G except E are no-ops):

- **Slice E NEW create (6 entries):** Heat Hotel + Travelodge by
  Wyndham Lake Havasu + Knights Inn Lake Havasu City + LAKE PLACE
  INN + Holiday Inn Express & Suites Lake Havasu - London Bridge by
  IHG + Queens Bay Resort Condominiums -- call
  `app.db.entity_dual_write.create_provider_and_entity()` with
  payloads constructed from cached enrichment data + force
  `category_id` to cat-10 for all 6. All 6 use default
  `entity_type='commercial'` (per the 5.10 1.7 sustainability
  commit at `bf24e16` -- all 5 lodging primary types are commercial;
  the pre-Phase-5 `lodging` direct mapping is also commercial).

DB-write commit shape mirrors `apply_phase5_9_classes_audit.py`. All
imports at top of file (no inline imports -- I001 footgun from 5.8
4 lesson). Dict-direct to JSON columns (no `json.dumps()` per
5.3 `f35d5e4` gotcha). ASCII-only stdout (5.9 cp1252 lesson). Stop
FastAPI dev server before running (events.db lock).

**5.9 reporting-bug fix applied:** the apply-script uses
`select(func.count())` for the post-apply count instead of `.all()`
length (5.9 2 had the autoflush quirk reporting 27 immediately after
changes when actual DB state was 31). Also includes explicit
`session.flush()` before the COUNT query.

---

## 11 Sustainability validation -- bf24e16 worked as designed

The 5.10 1.7 sustainability commit `bf24e16` (5 `_PRIMARY_TYPE_MAP`
entries + 1 `(None, "lodging")` catch-all in
`_DISCOVERY_DOMAIN_FALLBACK`) achieved its stated goal:

- **Pre-commit (1.6 load):** `category_id_unmapped: 2` -- the
  Vanderpump Rules villa (primary=`service`, _first_seen_domain=
  `lodging`, types[] without `lodging` secondary) escaped both the
  existing `lodging` direct map's secondary-types[] match AND any
  catch-all.
- **Post-commit (1.7c re-run):** `category_id_unmapped: 0`,
  `EntityCategory rows inserted: 1` (Vanderpump villa moved from
  NULL -> cat-10 via the new catch-all).

Plus the 5 direct mappings (hotel/motel/resort_hotel/extended_stay_
hotel/bed_and_breakfast) are documented at the primary level
(beating the catch-all per resolver order Layer 2 > Layer 3) --
defensive vs Google types[] array changes and consistent with
prior-phase sustainability commit shape.

Regression guard at `tests/test_phase5_10_places_load_resolver.py`
(17 tests; bf24e16 +17 to pytest baseline 1985 -> 2002).
