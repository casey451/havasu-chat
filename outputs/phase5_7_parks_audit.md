# Phase 5.7 — Outdoors, Parks & Trails — Post-load audit

> Mirrors `outputs/phase5_6_shopping_essentials_audit.md` shape with
> three 5.7-specific overrides:
>
> 1. **Narrow-scope input set.** Phase 5.7 §1 dispatched only 3 of the
>    10 entertainment_attractions labels (parks, golf courses, mini
>    golf) per kickoff §1 — fitness_sports collisions with HWC and
>    indoor entertainment labels (movie theaters, bowling, museums,
>    art galleries, live music, event venues) were deferred. The
>    audit dump's `is_entertainment(row)` filter pulls the broader
>    114-row entertainment_attractions+ZIP-filtered pool (the cache
>    accumulated rows from non-narrow labels in prior phases); the
>    ambig set of 32 is a subset of that pool.
> 2. **Three special-audit axes** (vs 5.6's single gas-station axis):
>    (a) cat-6 on-the-water cross-list (3 ambig hits, all stay-in-cat-6
>    per V1 policy);
>    (b) cat-12 classes-sports-recreation cross-list (0 ambig hits,
>    but 6 §1-inserted entries surface cat-12-suggestive primary_types
>    — decisions per §6);
>    (c) SARA Park same-cat de-dup (6 §1-surfaced SARA-named entries,
>    KEEP all 6 per V1 with one trail-pair flagged as a V1.5
>    navigation-alias soft-edge).
> 3. **Tighter ambig pool** — 32 ambig-skipped rows (vs 5.6's 177).
>    Narrow scope dropped 7 of 10 labels, so the input pool is
>    significantly smaller than the full retail domain produced in 5.6.
>
> **TL;DR:** No misroutes among the 32 ambig-skipped rows (28 cross-cat
> benign geo-adjacency matches against eat-drink ×17 / HWC ×4 /
> on-the-water ×3 / HPS ×2 / shopping-essentials ×2; 1 same-cat ambig
> on an existing outdoors-parks-trails entry; 3 orphan ambigs with no
> close match). The 13-row edge-case catch-all routing review surfaces
> **3 FLIPs** (Buses By The Bridge + Desert Storm HQ to cat-2 events,
> Parks & Recreation Department to cat-13 public-civic-resources) and
> **1 DRAFT** (Altitude Trampoline Park — indoor entertainment per
> kickoff §1 defer). Other 26 entries KEEP-in-cat-7. **Gate-2 met by
> review.**
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.7 session 2
> (2026-05-17) pre-`apply_phase5_7_parks_audit.py` dispatch. Final
> post-apply numbers in §8 surface after the apply-script runs.

---

## §1 Summary

Phase 5.7 §1 Layer 1 (Narrow scope: 3 labels — parks, golf courses,
mini golf) produced **114 entertainment_attractions+ZIP-filtered
candidates** through the reconciler across two loads (cache-reload +
fresh-sweep, idempotent). Outcomes:

| Reconciler action | Count | Disposition |
|---|---|---|
| `insert` (new entity) | 29 cache-reload + 1 fresh-sweep | outdoors-parks-trails = 30 post-load (6 pre-existing + 24 net new to cat-7 after cross-cat routing) |
| `update` (existing place_id) | 32 cache-reload + 60 fresh-sweep | Idempotent; existing rows refreshed (the dump's 82 "inserted" count includes pre-5.7 rows with `google_place_id` in the entertainment pool) |
| `ambig` (geo+name conflict) | **32** (audit dump's DB-diff method; load log showed 42 at first run before sustainability commit `1dfd28e` patched 11 catch-all routes) | This audit's §2 subject |
| `merge` (geo proximity + name match) | 0 | None qualified |

The 32-vs-42 discrepancy reflects the `1dfd28e` sustainability layer
extending `_DISCOVERY_DOMAIN_FALLBACK` for 5 `entertainment_attractions`
catch-all primary_types — what would have been ambig-skipped pre-fix
became clean inserts post-fix (matching the fresh-sweep's 1-row insert
of Bill Williams River NWR via the new `(None, "entertainment_
attractions")` catch-all). The audit's 32-count is post-sustainability;
that's authoritative.

**Of the 32 ambig hits (audit dump's coverage):**

| Bucket | Count | Match shape | Decision |
|---|---|---|---|
| **A — cross-category** | **28** | Candidate geo-matches an entity in another Tier-1 slug (eat-drink ×17, health-wellness-care ×4, on-the-water ×3, home-property-services ×2, shopping-essentials ×2) | KEEP-SKIP (V1 — see §2) |
| **B — same-category** | 1 | Candidate geo-matches an existing outdoors-parks-trails entity | KEEP-SKIP (V1 — see §3) |
| **C — orphans (no-geo-match)** | 3 | Candidate has no entity within 75m | KEEP-SKIP (V1 — see §3) |
| **Total reviewed** | **32** | | gate-2 §2 cleared by review |

**Plus** the 13-row edge-case catch-all routing review (§4), the 3-hit
on-the-water cross-list (§5), the 6-row cat-12-suggestive §1-inserted
surface (§6), and the 6-entry SARA Park same-cat de-dup (§7).

---

## §2 The Lake-Havasu-strip / event-cluster false-ambig pattern

### Why 28 cross-category hits

The kickoff §2 anticipated 20-60 ambig hits and flagged that 5.7's
Narrow scope would minimize spillover relative to 5.6's full-retail
domain. The actual 28 cross-cat count lands mid-range and is
**categorically the same pattern** as 5.4 medical-plaza / 5.5
auto-industrial-blvd / 5.6 strip-mall — entertainment-discovered
candidates geo-colliding (within 50m) with existing restaurants,
clinics, contractors, retail, and marine businesses in adjacent
suites or waterfront cluster spots.

Cross-cat slug breakdown (28 records with cross-cat match):

| Existing entity's slug | Count |
|---|---|
| eat-drink | 17 |
| health-wellness-care | 4 |
| on-the-water | 3 |
| home-property-services | 2 |
| shopping-essentials | 2 |

The eat-drink dominance (17 / 28 = 61%) reflects entertainment
candidates' tendency to cluster near restaurants — event venues,
art galleries, mini golf, and arcades are commonly adjacent to
food-and-drink establishments along McCulloch Blvd and the
waterfront. The 3 on-the-water hits are covered by the §5 special
audit (all stay-in-cat-6).

Discovery-label breakdown of the 28 cross-cat hits (top labels):

| Discovery label | Cross-cat ambig count |
|---|---|
| event venues | 7 |
| art galleries | 6 |
| mini golf | 2 |
| arcades | 2 |
| bookstores | 2 |
| hotels | 2 |
| parks | 2 |
| 8 singleton labels | 7 |

The event-venues and art-galleries labels dominate because they're
NOT in the Narrow scope — their candidates were in the cache from
earlier 5.x sessions' broader-domain scrapes and resurfaced when
the dump's `is_entertainment(row)` filter pulled them. None of these
labels' candidates should route to outdoors-parks-trails under V1
policy regardless; the ambig-skip is correct.

### Verdict

All 28 cross-cat hits are **benign geo-adjacency**. The reconciler's
"ambig" verdict is conservative-correct under V1 policy: the candidate
is a different business from the matched existing entity, just located
within 50m. No misroutes, no apply-script flips needed for this slice.
**Mirrors the 5.4 / 5.5 / 5.6 outcome exactly.**

---

## §3 Same-category bucket (1 hit) + orphans (3 hits)

### Same-cat (1 hit)

Per kickoff §2 / 5.5+5.6 pattern: same-cat ambig hits are adjacent
entries in the same physical complex. Operator-skip verdict is correct
— the candidate is a distinct surface, not a duplicate.

### Orphans (3 hits)

3 ambig-skipped candidates have no entity within 75m. These are
candidates the reconciler couldn't disambiguate against any existing
DB entity but also couldn't auto-insert. Per V1 policy: leave in the
ambig-skip pool for Layer 5 manual-recovery review later if they
turn out to be net-new park-like surfaces. None of the 3 orphans
have a `parks` / `golf courses` / `mini golf` discovery label (all 3
are non-Narrow-scope labels), so they're outside V1 scope anyway.

---

## §4 Edge-case catch-all routing review — 13 providers, 4 actions

The sustainability fix at commit `1dfd28e` added 5 entries to
`_DISCOVERY_DOMAIN_FALLBACK` keyed on `(*, "entertainment_attractions")`
plus a `_PRIMARY_TYPE_MAP` widening for `golf_course`. The resolver's
second-chance lookup (`places_load.py:368-371`) routed **all** unmapped
entertainment-discovered rows to outdoors-parks-trails — including 13
rows with edge-case primary_types the original surgical-fix plan
intended to leave in the operator queue. The catch-all behavior matches
every prior phase (`(None, "auto")` / `(None, "retail")` / etc.); 5.7's
`entertainment_attractions` domain catches less category-spillover than
5.6's `retail` because Narrow scope drops most labels.

The 13 edge-case rows surfaced by the dump's `edge_types` filter
(`event_venue`, `amusement_park`, `garden`, `sports_complex`,
`race_course`, `sports_activity_location`, `wildlife_refuge`,
`hiking_area`, `athletic_field`, `tourist_attraction`,
`point_of_interest`, `establishment`):

### Slice A — 3 FLIPs (re-routed to other Tier-1 slugs)

Apply-script: `outputs/apply_phase5_7_parks_audit.py`.

| Entity (8-char id) | Provider | google_primary | Flipped to | Rationale |
|---|---|---|---|---|
| `[id-1]` | **Buses By The Bridge** | event_venue | events (cat-2) | Annual bus-and-cars festival; event_venue with seasonal activation, not a place-based park surface. |
| `[id-2]` | **Desert Storm Headquarters** | event_venue | events (cat-2) | Annual boat poker run venue; event_venue with seasonal activation, same shape as Buses By The Bridge. |
| `[id-3]` | **Parks & Recreation Department** | sports_activity_location | public-civic-resources (cat-13) | Municipal department, not a place-based recreation surface. Consumer discovery utility lives in cat-13 (civic resources / "how do I rent a pavilion"), not cat-7 ("where do I go play"). |

### Slice B — 1 DRAFT (Provider.draft=True; EntityCategory preserved)

Indoor entertainment that's outside V1 outdoors-parks-trails scope but
lacks a more appropriate Tier-1 home in the V1 taxonomy. Per kickoff §1
indoor-entertainment-defer policy.

| Entity (8-char id) | Provider | google_primary | Rationale |
|---|---|---|---|
| `[id-4]` | **Altitude Trampoline Park** | amusement_park | Indoor trampoline facility; kickoff §1 explicitly deferred indoor entertainment to a future "indoor entertainment" or "classes-sports-recreation" phase. Draft preserves the cat-7 EntityCategory link for V1.5 re-evaluation; `draft=True` hides from default `/category/outdoors-parks-trails` listing. |

### Slice C — 9 KEEPs (no script action)

Edge-case primary_types that legitimately belong in outdoors-parks-trails.

| Provider | google_primary | Rationale |
|---|---|---|
| **Bill Williams River National Wildlife Refuge** | wildlife_refuge | Federal land; valid outdoors-parks-trails entry. Catch-all via new `(None, "entertainment_attractions")` route — see V1.5 carry-over for direct `_PRIMARY_TYPE_MAP` widening. |
| **Sara Mountain Park Loop Trail** | hiking_area | Valid trails entry; SARA Park sub-feature (see §7 de-dup). |
| **Sara Park Trail Head** | hiking_area | Valid trails entry; SARA Park sub-feature (see §7 de-dup). |
| **SARA Park Disc Golf Course** | athletic_field | Recreational disc golf; SARA Park sub-feature. Soft-edge: V1.5 dual-cat with cat-12 (see §6). |
| **Lake Havasu Motocross Park** | race_course | Outdoor recreational track; valid V1 parks-and-trails surface. Soft-edge: V1.5 dual-cat with cat-12. |
| **Ofd Racing** | race_course | Outdoor recreational track (unclear sub-shape — operator may want to investigate the actual venue). Default KEEP per "recreational track as park amenity" rubric; flag as V1.5 investigation. |
| **Thompson Bay Beach** | sports_activity_location | Lake-shore beach surface; valid parks/beaches entry. Soft-edge: V1.5 dual-cat with cat-6 on-the-water (the §5 special audit shows 0 current dual-tags). |
| **Lake Havasu City Sportsman's Club** | sports_complex | Outdoor shooting / sportsman facility; recreational use suggests cat-7. Soft-edge: V1.5 dual-cat with cat-12 if scheduled-club-use shape applies. |
| **Butterfly Garden** | garden | Treat as KEEP pending investigation — operator may flip to DRAFT if it's a community garden (B2C-discovery utility low) rather than a public garden surface. Default KEEP for V1; flag as V1.5 investigation. |

---

## §5 Special audit (a) — on-the-water (cat-6) cross-list (3 hits)

Per kickoff §2 special surface. 3 ambig candidates geo-match existing
on-the-water entities:

| Candidate | Matched cat-6 entity | Distance | V1 policy verdict |
|---|---|---|---|
| AZ Party Express (event venues) | Saleen Fiberglass Restoration (service) | 21.9m | Stay in cat-6 — marine-primary existing entity, candidate is an event-rental business |
| Four Quarters Amusements (arcades) | HTM Performance Boats (supplier) | 20.9m | Stay in cat-6 — marine-primary existing entity, candidate is indoor arcade |
| Lake Havasu Museum of History & Havasu Rocks (museums) | Go Lake Havasu (tourist_information_center) | 17.5m | Stay in cat-6 — visitor-center matched entity, candidate is a museum (defer to indoor-entertainment future phase) |

**0 flips needed.** V1 policy (per kickoff §2): cat-6/cat-7 boundary
honors the matched entity's primary domain unless the candidate is
clearly the primary draw. None of the 3 candidates are park surfaces.

**§1-inserted outdoors-parks-trails entries with cat-6 overlap:** **0**.
None of the 30 cat-7 entries are currently dual-tagged with on-the-water,
even Thompson Bay Beach (lake-shore beach surface). The
Thompson-Bay-Beach-to-cat-6 dual-cat is documented as a V1.5 soft-edge
in §4 Slice C above and §9 below.

---

## §6 Special audit (b) — classes-sports-recreation (cat-12) cross-list

Per kickoff §2 special surface.

### Ambig hits (0)

**0 ambig candidates** geo-match existing classes-sports-recreation
entities. Either cat-12 is sparse enough that no candidate's 50m
neighborhood includes an existing cat-12 entity, or 5.7's Narrow scope
candidates don't physically cluster near cat-12 venues. **0 flips
needed for this slice.**

### §1-inserted entries with cat-12-suggestive primary_types (6)

These are the 6 §1-inserted entries whose `google_primary_category`
suggests they could legitimately route to cat-12 (sports_complex /
race_course / athletic_field / sports_activity_location). Per the §4
edge-case rubric output:

| Entity | google_primary | V1 decision | V1.5 soft-edge |
|---|---|---|---|
| SARA Park Disc Golf Course | athletic_field | KEEP cat-7 | Dual-cat with cat-12 |
| Lake Havasu Motocross Park | race_course | KEEP cat-7 | Dual-cat with cat-12 |
| Ofd Racing | race_course | KEEP cat-7 (default) | Investigate venue shape; dual-cat with cat-12 if scheduled-use |
| **Parks & Recreation Department** | sports_activity_location | **FLIP to cat-13** | n/a (civic, not recreational) |
| Thompson Bay Beach | sports_activity_location | KEEP cat-7 | Dual-cat with cat-6 |
| Lake Havasu City Sportsman's Club | sports_complex | KEEP cat-7 (default) | Dual-cat with cat-12 if club-scheduled-use shape |

**1 FLIP needed (Parks & Rec Dept → cat-13).** The 5 KEEPs surface
V1.5 dual-cat soft-edges; not gate-blocking.

---

## §7 Special audit (c) — SARA Park same-cat de-dup (6 entries)

Per kickoff §2 + midpoint §4 V1 recommendation: KEEP all 6 SARA-named
entries if each is a distinct physical surface; compress only if any
pair is a clear navigation alias for the same physical surface.

| Entity (8-char id) | Provider | google_primary | Lat / Lng | V1 decision |
|---|---|---|---|---|
| `f881f795` | SARA Park | park | 34.44700 / -114.24632 | KEEP — parent park |
| `d17ff063` | SARA Park Disc Golf Course | athletic_field | 34.44873 / -114.26777 | KEEP — sub-feature, recreational (see §6) |
| `7e07db65` | SARA Park Dog Park | dog_park | 34.45025 / -114.26747 | KEEP — sub-feature |
| `38c83c28` | Sara Mountain Park Loop Trail | hiking_area | 34.44291 / -114.25171 | KEEP — sub-feature, ~1.5km east of disc-golf cluster |
| `87797565` | Sara Park Hiking Trail | park | 34.44383 / -114.26479 | KEEP — sub-feature; **possible navigation alias for `ce68ae90` below — V1.5 soft-edge** |
| `ce68ae90` | Sara Park Trail Head | hiking_area | 34.44369 / -114.26486 | KEEP — sub-feature; **possible navigation alias for `87797565` above — V1.5 soft-edge** |

**Spatial check:** `87797565` (Sara Park Hiking Trail) and `ce68ae90`
(Sara Park Trail Head) sit at coordinates that are **~16m apart**
(latitude delta 0.00014 = ~15.5m; longitude delta 0.00007 = ~6.5m).
This is well below the reconciler's 50m proximity threshold. Either:
(a) one is the trailhead entrance and the other is the trail itself
(legitimately distinct surfaces — KEEP both); or (b) Google indexed
the same physical surface under two slightly different names and the
reconciler missed the dedup because the names diverge enough (Jaccard
similarity is low between "Hiking Trail" and "Trail Head"). The 5
SARA primary_type distribution argues for (a) — `park` vs
`hiking_area` are distinct shapes — but the coordinates are tight
enough to flag as a V1.5 review item.

**V1 decision: KEEP all 6.** V1.5 soft-edge: review whether
`87797565` ↔ `ce68ae90` should be merged after operator-side surface
inspection (consumer-app or LHC Parks & Rec municipal page check).

---

## §8 Net effect on Phase 5.7 gate-1 (post-apply actuals)

| Category | Pre-apply | Post-apply (actual) |
|---|---|---|
| `/category/outdoors-parks-trails` | 30 entries (0 draft) | **27 entries / 26 render (1 draft)** ✓ |
| `/category/events` | 0 | **2 / 2** (Buses By The Bridge, Desert Storm HQ) ✓ |
| `/category/public-civic-resources` | 0 | **1 / 1** (Parks & Recreation Department) ✓ |

**Gate-1 cleared:** 27 entries / 26 render — clears ≥20 threshold
**1.35× (entries) / 1.30× (render)** (vs 5.6's 1.90× and 5.5's
1.55× — tighter but still cleanly clear). Apply-script ran live at
2026-05-17 post-`5f8fe08`; self-verify confirmed in the live-run output.

**Gate-6 cleared:** 26 render — clears ≥15 threshold **1.73×**.

**Note on events / public-civic-resources baselines:** Both target
slugs had **0 entries** pre-apply — Phase 5.7 is the first lane to
land entries in either, via the §2 audit FLIPs. Future Tier-1 phases
working `events` (cat-2) and `public-civic-resources` (cat-13) will
build on this baseline. (Mirrors 5.4 → 5.5 / 5.6 → 5.7 progression of
backfilling under-populated cats as later lanes surface relevant
entries via audit-driven FLIPs.)

**§4 outcomes (gate items 4 + 5, both CLEARED):**
- **heat_exposure:** `outputs/apply_phase5_7_parks_heat_exposure.py`
  ran live post-§2-apply. Self-verify: **26 outdoor + 1 indoor**
  (Altitude Trampoline Park, drafted in §2 but still gets
  heat_exposure per gate-5 "on every entry" precedent). 0 NULL across
  27. **Gate-5 CLEARED.**
- **crowd_notes top-10:** `outputs/apply_phase5_7_parks_crowd_notes.py`
  ran live post-heat_exposure. Top-10 surfaced via
  `outputs/phase5_7_top10_discovery.py` against
  `Provider.google_review_count` desc (post-§2-flip set, so the 3
  FLIPped entries are excluded). **100% snippet coverage** (5
  snippets each — higher than the kickoff §4 forecast of 70-85%
  because parks have abundant reviews + the top-10 includes 2 state
  parks + the federal wildlife refuge + LHC's biggest community park).
  Hand-curated short+long notes; long-form ranges 708-909 chars
  (well above the 200-char gate-4 threshold). Self-verify: 10
  entities with long-form crowd_notes. **Gate-4 CLEARED.**

| # | Entity | reviews | rating | primary | short / long chars |
|---|---|---|---|---|---|
| 1 | Lake Havasu State Park | 5046 | 4.7★ | state_park | 256 / 759 |
| 2 | Rotary Community Park & Playgrounds | 2564 | 4.7★ | park | 280 / 748 |
| 3 | Cattail Cove State Park | 1121 | 4.7★ | state_park | 261 / 719 |
| 4 | Bill Williams River NWR | 567 | 4.7★ | wildlife_refuge | 262 / 804 |
| 5 | SARA Park | 469 | 4.7★ | park | 300 / 909 |
| 6 | SARA Park Dog Park | 334 | 4.6★ | dog_park | 279 / 770 |
| 7 | Avalon Park | 320 | 4.4★ | park | 270 / 826 |
| 8 | Jack Hardie Park | 271 | 4.5★ | park | 244 / 708 |
| 9 | Bridgewater Links Golf Course | 245 | 4.4★ | golf_course | 282 / 775 |
| 10 | Sara Park Trail Head | 225 | 4.8★ | hiking_area | 268 / 898 |

---

## §9 Carry-forwards

- **`Provider.draft=True` for 1 provider** (Altitude Trampoline Park)
  in outdoors-parks-trails. Doesn't render at
  `/category/outdoors-parks-trails` but preserves EntityCategory link
  for V1.5 re-evaluation if/when an indoor-entertainment phase opens.
- **No Layer-4 verifier surface built** — operator picked Option C
  (defer to V1.5) per kickoff §3. AZ State Parks + NPS + LHC Parks
  & Rec paths documented in the kickoff §3 for V1.5 pickup.
- **V1.5 soft-edges from §6 + §7:**
  - 5 entries flagged for V1.5 dual-cat consideration: SARA Park Disc
    Golf Course (cat-12), Lake Havasu Motocross Park (cat-12), Ofd
    Racing (cat-12 + venue-shape investigation), Thompson Bay Beach
    (cat-6), Lake Havasu City Sportsman's Club (cat-12).
  - Sara Park Hiking Trail ↔ Sara Park Trail Head ~16m-apart pair —
    candidate for V1.5 merge or KEEP-both confirmation.
  - Butterfly Garden — investigate community-vs-public-garden shape.
  - ASU SWANSON FIELDS uppercase name — investigate source and decide
    whether to normalize (cosmetic; not gate-blocking).
- **V1.5: `wildlife_refuge` direct mapping in `google_types_mapping.py`**
  — soft-edge surfaced by Bill Williams River NWR (`wildlife_refuge`
  isn't in `_PRIMARY_TYPE_MAP` directly; caught by `(None,
  "entertainment_attractions")` catch-all from `1dfd28e`). 1-line
  addition `"wildlife_refuge": ("outdoors-parks-trails", "place")`
  would catch federal-land entries regardless of discovery domain.
  Same shape as the 5.7 §1 `medical_clinic` / `golf_course` widenings.
- **`scripts/places_categories.json` corruption** — the fifth
  recurrence forecast did NOT materialize this session (four-file
  shape check at §0 returned empty). Pattern still worth watching for
  in 5.8+.
- **`parks-rec-scrapes` CI sidebar (Decision 3, §4.5) — investigated
  + root cause identified + handed off:** Both kickoff §4.5
  hypotheses **rejected**. (a) Workflow does NOT reference the
  pre-Phase-3.2 `outdoors-and-parks` slug — slug-rename PR is not
  the fix. (b) The `1dfd28e` sustainability fix does NOT retroactively
  fix the cron — totally different code path. **Actual root cause:**
  `scripts/parks_rec_prune.py` hits a Postgres FK constraint violation
  trying to DELETE stale events (`open-swim-schedule` past
  2026-05-10) that are still referenced by rows in
  `contributions.created_event_id`. Error: `psycopg2.errors.ForeignKey
  Violation: update or delete on table "events" violates foreign key
  constraint "contributions_created_event_id_fkey" on table
  "contributions". DETAIL: Key (id)=(195fb13e-0b09-4cec-b7e7-
  8be69ffc5ed7) is still referenced from table "contributions".`
  Pre-existing since 5.3+ (per carry-over notes). The Phase 5.7 §1
  data plane (`places_load.py` resolver + `_DISCOVERY_DOMAIN_FALLBACK`)
  is unrelated. Fix options for V1.5 / Phase 6 sidecar (defer):
  (i) Alembic migration adding `ON DELETE SET NULL` on
  `contributions.created_event_id` FK — preserves contribution row,
  severs link to deleted event (recommended; least destructive).
  (ii) `parks_rec_prune.py` adds `WHERE NOT EXISTS (SELECT 1 FROM
  contributions ...)` clause — preserves both rows; events stay
  forever if cited by a contribution.
  (iii) `ON DELETE CASCADE` — destructive; deletes contributions when
  referenced event is pruned. Probably wrong UX, listed for
  completeness.
  **Phase 6 lane dispatch suggested.** Not gate-blocking for 5.7 ship.
- **PowerShell `\"` escape footgun (NEW)** — surfaced this session.
  `\"` inside a PowerShell `"..."` string is NOT an escape sequence;
  embedding `\"\"\"` in a `git commit -m "..."` body causes git to
  parse subsequent tokens as pathspecs (we hit `fatal: /: '/' is
  outside repository`). Use single-quoted `-m '...'` flags for git
  commit messages when the body contains `"` or `/` characters; PS
  single quotes are literal (no interpolation, no escaping).
  Sibling to the existing empty-`-m""`-pathspec footgun.
- **Sandbox bash mount staleness** continued to affect 5.7 §0
  (sandbox-side `data/events.db` mtime showed May 8; sqlite3 read
  failed with "readonly database" recovery attempt). Read tool +
  Windows-side `python` execution remain authoritative; sandbox bash
  is unreliable for SQLite DB inspection.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.7 session 2
(2026-05-17) pre-`apply_phase5_7_parks_audit.py` dispatch. Final
post-apply numbers in §8 surface after the apply-script runs.*
