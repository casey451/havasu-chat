# Phase 5.8 — Events combined pre+post-load audit

> **What this is:** the §2 audit doc for Phase 5.8 (events, cat-2).
> Combines the ambiguous-queue review + cross-cat sweep + special-axis
> findings from `outputs/phase5_8_ambig_audit_dump.py` (run output at
> `outputs/phase5_8_ambig_audit_stdout.txt`, structured records at
> `outputs/phase5_8_ambig_audit_data.json`).
>
> Mirrors `outputs/phase5_7_parks_audit.md` shape with 5.8-specific
> classifications.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.8 session 1
> (2026-05-17) post-§1 load.

---

## §1 Summary (TL;DR)

**§1 Layer 1 outcome** (per `docs/scrape_logs/events_2026-05-17.md`):
- Discovery: 89 unique places across 7 in-scope labels (9 requests).
- Enrichment: 87 cache-hits / 2 new (97.8% cache reuse).
- Load: 52 in-LHC rows → 1 insert + 29 updates + 22 ambig + 0 unmapped.
- Sustainability commit `0b426e1` validated: 0 unmapped of 52 ✅.

**§2 audit outcome (this doc; final post-apply):**
- 33 ambig records dumped (22 from 5.8's actual ambig pool + 11 ambient
  cross-phase noise from the dump's wider entertainment-label filter).
- **17 FLIPs to cat-2** = **16 NEW entity creates** (Slice A) + **1
  cross-cat move + un-DRAFT** (Slice B-2: Altitude Trampoline).
  Slice B-1 (Lake Havasu Museum of History cat-6 → cat-2) was
  reclassified mid-apply: DB query confirmed no pre-existing museum
  entity existed in cat-6 — the 5.7 §1 ambig pool included a museum
  candidate but it was KEPT-ambig per 5.7 close-out §4 (no DB row). The
  5.8 candidate "Lake Havasu Museum of History & Havasu Rocks" was
  added to Slice A as the 16th NEW create.
- **1 DRAFT to cat-2** (Simply Savage Designs — art_gallery → place →
  renders even drafted)
- **15 KEEPs as ambig** (4 5.8-relevant low-signal candidates + 11
  cross-phase noise)

**Actual post-apply gate-1 state:**
- 2 pre-existing cat-2 entries (Buses By The Bridge, Desert Storm HQ)
- 0 §1 net inserts in cat-2 (the 1 §1 insert routed to cat-7 via the
  5.7 catch-all — its primary_type was not one of the 7 directly-mapped
  events types, so it landed in cat-7 outdoors-parks-trails instead)
- 16 §2 Slice A NEW creates (all visible: 6 place-typed +
  10 commercial)
- 1 §2 Slice B-2 cross-cat move + un-DRAFT (Altitude Trampoline)
- 1 §2 Slice C DRAFT (Simply Savage Designs, art_gallery → place,
  renders even drafted)
- **= 20 entities in cat-2, 20 rendering** — clears gate-1 (≥20) ✅
  (zero margin; the 16th Slice A entry — the museum — is load-bearing
  for the gate)

**No real misroutes detected.** The cross-cat overlap (30 cross-cat
matches in the ambig pool, dominated by 17 eat-drink hits) is all
benign geo-proximity false positives — the matched eat-drink /
HWC / HPS / on-the-water entities all stay in their current cats; the
candidates are NEW businesses (event venues, art galleries, etc.)
that happen to be geo-adjacent.

---

## §2 §1 inserts + updates (post-load DB state)

`outputs/phase5_8_ambig_audit_dump.py` reports 83 Providers in DB whose
place_ids match this 5.8 scrape (1 fresh insert + 29 §1 updates + 53
ambient cache hits from earlier phases). Special audit (a) shows the
28 §1-updated entries currently in cat-7 — all parks/golf/state-park/
trail entities from 5.7's load.

**No FLIP candidates from the 28 cat-7 entries except Altitude
Trampoline Park** (already DRAFTed in cat-7 per 5.7 §2; per kickoff §1
deferred indoor-entertainment-now-properly-cat-2 narrative, FLIP to
cat-2 + un-DRAFT). See §4 Slice B-2.

The other 27 cat-7 entries are correctly placed (state parks,
playgrounds, golf course, racing/sports parks, gardens, hiking trails)
and stay in cat-7 per V1 policy.

---

## §3 §1 ambig pool cross-cat aggregate

| Matched-entity slug | Count |
|---|---|
| eat-drink | 17 |
| health-wellness-care | 4 |
| home-property-services | 3 |
| on-the-water | 3 |
| shopping-essentials | 2 |
| public-civic-resources | 1 |
| (no match in 75m) | 3 |
| **Total** | **33** |

All 30 cross-cat hits are benign geo-proximity false positives — the
matched entities stay in their original cats; the candidates that
deserve cat-2 placement get FLIP/DRAFT decisions in §4 below.

---

## §4 Slice A — 16 NEW entity creates in cat-2 (15 high-confidence + 1 reclassified-from-Slice-B-1)

Each row is a candidate from the §1 ambig pool that the reconciler
ambig-skipped (geo within 50m of an existing entity but name differs).
Operator-curated decision: CREATE new cat-2 entity (not the same
business as the matched entity; the reconciler was correct to flag
ambig and we override by creating a distinct entity).

| # | Candidate | Primary | Reviews | Discovery label | Matched (existing) | Decision rationale |
|---|---|---|---|---|---|---|
| 1 | Star Cinemas | `movie_theater` | 814 | movie theaters | Buffalo Wild Wings @ 0.1m (cat-1) | LHC's main movie theater; 814 reviews; matched entity is co-located restaurant — distinct businesses |
| 2 | Havasu Art Center | `art_gallery` | 8 | art galleries | The Pour House @ 33.2m (cat-1) | Real art center; distinct from matched eat-drink entity |
| 3 | The Q Art Gallery | `art_gallery` | 9 | art galleries | Booby Falls Restaurant @ 19.6m (cat-1) | Real gallery; name explicit; distinct from matched |
| 4 | Christine's Fine Art LLC | `art_gallery` | 4 | art galleries | Prielipp Construction @ 36.3m (cat-4) | Real LLC art gallery; distinct from matched HPS |
| 5 | Jaque Meng | `art_gallery` | None | art galleries | Booby Falls Restaurant @ 19.6m (cat-1) | Artist studio / small gallery; art_gallery primary; new entity |
| 6 | Tyanna Renee Gallery | `art_gallery` | None | art galleries | Hypnotherapist On Line @ 21.9m (cat-5) | Real gallery (name says Gallery); art_gallery primary |
| 7 | American Legion | `association_or_organization` | 140 | event venues | Piccadilly's @ 41.5m (cat-1) | Real veterans org with 140 reviews; community event venue role |
| 8 | Realtor Convention Center | `real_estate_agency` | 4 | event venues | Crystal Eppling Eye Doctor @ 37.2m (cat-5) | Name explicitly says Convention Center; primary_type is misleading |
| 9 | AZ Party Express | `service` | 11 | event venues | Saleen Fiberglass Restoration @ 21.9m (cat-6) | Event-rental service; 5.7 §4 KEPT as ambig because no cat-2 home — now there is |
| 10 | Four Quarters Amusements | `manufacturer` | 46 | arcades | HTM Performance Boats @ 20.9m (cat-6) | Arcade business (manufacturer primary is misleading); 5.7 §4 KEPT as ambig |
| 11 | Lake Havasu, AZ Elks Lodge #2399 | `association_or_organization` | 388 | mini golf | Gallagher's Dining & Pub @ 48.2m (cat-1) | Real Elks Lodge with 388 reviews; community event venue; label mismatch (mini golf) is Google noise |
| 12 | Ru Art Gallery and Boutique | `clothing_store` | 18 | clothing stores | Shugrue's Cornerside Bakery @ 0.0m (cat-1) | Name says "Art Gallery and Boutique"; dual-purpose retail+gallery; placing in cat-2 over cat-8 |
| 13 | Quest Realm | `store` | 100 | gift shops | Harmony Health & Wellness Center @ 12.8m (cat-5) | 100 reviews; name "Quest Realm" suggests gaming/escape-room venue; place over store |
| 14 | WORCS Racing | `race_course` | 1 | event venues | SERVPRO @ 36.0m (cat-4) | World Off-Road Championship Series — real motorsport event organizer |
| 15 | High End Productions LLC | None | 2 | event venues | S-2 Contractors @ 12.9m (cat-4) | Event production company; primary=None + 2 reviews so low confidence but label is explicit |
| 16 | Lake Havasu Museum of History & Havasu Rocks | `history_museum` | 213 | museums | Go Lake Havasu @ 17.5m (cat-6) | Reclassified from Slice B-1 mid-apply: no pre-existing museum entity in DB (the 5.7 §1 ambig pool surfaced this but never wrote to DB). NEW create per the actual scrape; `history_museum` → place per the 5.8 sustainability commit |

**entity_type assignment per FLIP:**

- art_gallery / history_museum primary → `place` (per 5.8 sustainability `0b426e1`)
- movie_theater / association_or_organization / association / amusement_arcade / clothing_store / store / race_course → `commercial`
- Realtor Convention Center (real_estate_agency primary, but functions as convention center) → `commercial`
- AZ Party Express (service primary, event-rental) → `commercial`
- High End Productions LLC (None primary) → `commercial` (event-production company)

---

## §4 Slice B-1 — REMOVED (reclassified to Slice A #16)

**Original premise (pre-apply):** Lake Havasu Museum of History was
believed to be an existing cat-6 entity that needed to FLIP to cat-2.

**Actual finding (post-first-apply):** DB query confirmed no entity
with "Museum" in its name exists in the DB. The 5.7 §1 ambig pool
included a museum candidate that 5.7 close-out §4 KEPT as ambig ("0
flips needed") — meaning no DB row was created. The kickoff §2
framing "currently in on-the-water from 5.2" was a misreading.

**Resolution:** the 5.8 candidate "Lake Havasu Museum of History &
Havasu Rocks" (history_museum primary, 213 reviews) was added to
Slice A as the 16th NEW create. The apply-script's
SLICE_B1_CROSS_CAT_MOVE_BY_NAME is now an empty dict (preserved for
documentation; the apply-script still loops it for idempotency).

---

## §4 Slice B-2 — 1 cross-cat MOVE + un-DRAFT (cat-7 → cat-2)

| # | Existing entity | Current state | New state | Rationale |
|---|---|---|---|---|
| 1 | Altitude Trampoline Park | cat-7 DRAFT | cat-2 visible | DRAFTed in cat-7 per 5.7 §2 (indoor-entertainment-defer; "Phase 5.8 lane will properly home it"). Phase 5.8 IS that lane. amusement_park primary → commercial entity_type; un-DRAFT to make visible in cat-2 events. |

---

## §4 Slice C — 1 DRAFT to cat-2 (low-confidence, operator review)

| # | Candidate | Primary | Reviews | Reason DRAFT |
|---|---|---|---|---|
| 1 | Simply Savage Designs | `art_gallery` | 1 | art_gallery primary surfaced but name "Designs" suggests design/print shop rather than gallery. 1 review = low signal. Place-typed (renders even drafted) so operator can review and either un-DRAFT or DELETE. |

---

## §4 Slice D — 15 KEEPs as ambig (no DB action)

### Slice D-1: 5.8-relevant low-signal candidates (4)

| # | Candidate | Primary | Reviews | Discovery label | Reason KEEP-ambig |
|---|---|---|---|---|---|
| 1 | Queens Real Estate By Connie | `real_estate_agency` | 2 | event venues | Clearly a real estate agency, not event venue. Label is Google noise (geo-collision with El Mariachi restaurant). |
| 2 | The Wedding Specialist | `service` | 4 | event venues | 0.0m + name overlap with matched "Tux and Tulips" (florist). Likely same business under different listing (wedding planner / florist combo). Defer to operator. |
| 3 | Nomadic | `coworking_space` | 17 | event venues | Coworking space that hosts events. Closer to cat-12 classes-sports-recreation than cat-2 events; primary identity is workspace, not event venue. Defer. |
| 4 | Main Street Commons | `park` | 110 | parks | Park (cat-7 deferred label per 5.8 Narrow scope; surfaced because dump's `is_entertainment` includes all 10 entertainment_attractions labels). Should route to cat-7 via 5.7 cadence if not already; defer to V1.5 hand-curation. |

### Slice D-2: Cross-phase ambient noise (11)

Discovery labels NOT in 5.8 Narrow scope; surfaced because the dump's
`is_entertainment` filter is wider than the load's `--category events`
filter. All KEEP-ambig (defer):

| # | Candidate | Discovery label | Primary cat lane |
|---|---|---|---|
| 1 | Havasu Dunes Resort | hotels | cat-10 lodging (5.10) |
| 2 | HavaPic | photographers | services |
| 3 | Lake Havasu City Aquatic Center | spas | cat-5 HWC (5.4) |
| 4 | Lions Dog Park | parks | cat-7 (defer; 5.7 may handle in V1.5) |
| 5 | Quest Realm (gift shops label) | gift shops | already FLIPped above per name signal — see Slice A #13 |
| 6 | At The Bridge Rentals | boat rentals | cat-6 (5.2) |
| 7 | The Shops At Lake Havasu | grocery stores | cat-8 shopping-essentials (5.6) |
| 8 | Holiday Inn Express | hotels | cat-10 lodging (5.10) |
| 9 | Golf USA | mini golf | cat-7 deferred / cat-8 retail |
| 10 | Havasu Adult Bookstore | bookstores | cat-8 shopping-essentials (5.6) |
| 11 | The Views at Lake Havasu | senior living | services / V1.5 |
| 12 | Flashback Toys & Collectibles | bookstores | cat-8 shopping-essentials (5.6) |

(13 entries with Quest Realm counted in Slice A — net 11 KEEPs from
cross-phase noise.)

---

## §5 Special audit (a) — cat-7 outdoors-parks-trails cross-list

0 hits in the ambig pool ✅. 28 §1-updated entries currently in cat-7
were enumerated by the dump — all stay in cat-7 except Altitude
Trampoline Park (FLIP to cat-2 per Slice B-2).

The 27 §1-updated entries that STAY in cat-7:
ASU SWANSON FIELDS, Avalon Park, Bill Williams River NWR, Bridgewater
Channel, Bridgewater Links Golf Course, Butterfly Garden, Cattail Cove
State Park, Dick Samp Memorial, Grand Island Park, Jack Hardie Park,
Lake Havasu City Sportsman's Club, Lake Havasu Motocross Park, Lake
Havasu State Park, Mesquite Park, Ofd Racing, Realtor Park, Rotary
Community Park & Playgrounds, SARA Park, SARA Park Disc Golf Course,
SARA Park Dog Park, Sara Mountain Park Loop Trail, Sara Park Hiking
Trail, Sara Park Trail Head, Spezzano Cactus Park, Thompson Bay Beach,
Wheeler Park, Yonder Park.

---

## §6 Special audit (b) — cat-13 public-civic-resources cross-list

1 hit: Lake Havasu City Aquatic Center (label=spas, swimming_pool
primary) matched Parks & Recreation Department @ 22.2m.

**Decision: KEEP-ambig.** The Aquatic Center is a civic facility but
its discovery label was "spas" (a HWC label not in 5.8 scope). The
matched entity (Parks & Rec Dept) is already correctly in cat-13 per
5.7 §2's FLIP. No 5.8 action. The Aquatic Center may be a V1.5 cat-13
or cat-12 candidate.

---

## §7 Special audit (c) — seasonal-activation de-dup

2 pre-existing cat-2 entries:
- Buses By The Bridge (event_venue, 34.47576,-114.35418)
- Desert Storm Headquarters (event_venue, 34.47582,-114.35451)

Coordinates ~30m apart but they're DISTINCT annual events
(bus festival vs boat poker run). No year-suffix duplicates. **0
merges needed.** Same-cat update: refresh address/snippets via the §1
update branch (already happened).

---

## §8 Gate-1 projection

Post-§2 + §4 apply, before §4-rubric (heat_exposure + crowd_notes):

| Category source | Count |
|---|---|
| Pre-load cat-2 (5.7 FLIPs) | 2 |
| §1 net insert | 1 |
| §1 net insert (auto-resolved by load) | 0 (the 1 §1 insert routed to cat-7 via the 5.7 catch-all, not cat-2) |
| §4 Slice A FLIPs (NEW entity creates) | 16 (15 high-confidence + 1 reclassified-from-Slice-B-1) |
| §4 Slice B-1 FLIPs (cat-6 → cat-2) | 0 (REMOVED — reclassified to Slice A) |
| §4 Slice B-2 FLIPs (cat-7 → cat-2 + un-DRAFT) | 1 |
| §4 Slice C DRAFTs (art_gallery → place → renders even drafted) | 1 |
| **Total cat-2 entries post-§2** | **20** |
| **Rendering (gate-1 query)** | **20** (all visible; DRAFT is place-typed so renders) |

**Gate-1 target ≥20 → actual 20 ✅** (0× margin — the 16th Slice A
entry, Lake Havasu Museum of History & Havasu Rocks, is load-bearing)

---

## §9 Carry-forwards

### V1.5 dual-cat soft-edges (5.8 §2 surfaced)

- **Lake Havasu City Aquatic Center** — civic facility with HWC discovery
  label; consider cat-12 (classes-sports-recreation) or cat-13 dual-cat
  in V1.5
- **Nomadic** (coworking space hosting events) — consider cat-12
- **Lake Havasu Museum of History** ↔ "Lake Havasu Museum of History &
  Havasu Rocks" — same business, two Google place_ids. V1.5 unify
  decision (operator chooses primary place_id; archive the other).
- **Lions Dog Park** (cat-7 candidate not yet in DB) — V1.5 hand-curation
  for cat-7
- **Main Street Commons** (park, cat-7 label, 110 reviews) — V1.5 hand-
  curation for cat-7

### V1.5 operator-review for DRAFTs

- **Simply Savage Designs** — art_gallery primary but name suggests
  design/print shop. Operator decides un-DRAFT or DELETE.

### Carry-forward from 5.7 (still open)

- 5 entries flagged for V1.5 dual-cat consideration: SARA Disc Golf,
  Motocross, Ofd Racing, Thompson Bay Beach, Sportsman's Club
- Sara Park Hiking Trail ↔ Sara Park Trail Head ~16m-apart pair
- Butterfly Garden community-vs-public investigation
- ASU SWANSON FIELDS uppercase normalization
- wildlife_refuge widening in `google_types_mapping.py` (5.7 §6 carry)
- Lake Havasu Museum of History cat-6→cat-2 FLIP carry — handled this
  session in Slice B-1
- `parks-rec-scrapes` cron prune-fix sidecar — Phase 6 lane

### Carry-forward from prior phases (still open)

- 86 of 265 HWC providers `verified=False` (5.4 carry)
- `data/events.db.bak-*` files prune (5.3+ carry)
- Google Places API key rotation (deferred per operator)

---

## §10 Apply-script reference

Apply via `outputs/apply_phase5_8_events_audit.py`:

- Reads enrichment data from
  `scripts/output/places_pull/enrichment_enriched.jsonl` to construct
  the 15 NEW entities (Slice A) — name, address, lat/lng, place_id,
  primary_type, snippets, review_count.
- Looks up existing entities by name for the 2 cross-cat moves
  (Slice B) + 1 DRAFT (Slice C).
- Idempotent: re-running on an already-FLIPped entity DELETEs +
  re-INSERTs the same EntityCategory row (net no-op except
  updated_at).

```
python outputs/apply_phase5_8_events_audit.py --dry-run
python outputs/apply_phase5_8_events_audit.py
```

DB-write — stop FastAPI dev server first to avoid events.db lock per
the 5.4/5.5/5.6/5.7 close-out gotcha.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.8 session 1
(2026-05-17) post-§1-load. 17 FLIPs (15 NEW + 2 cross-cat) + 1 DRAFT
+ 15 KEEPs against 33 ambig records; gate-1 projects 21 ≥20.*
