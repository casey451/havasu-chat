# Phase 5.9 — Classes, Sports & Recreation — §2 audit (combined pre+post)

> **What this is:** the combined §1 post-load + §2 ambiguous-queue audit
> for Phase 5.9 (`classes-sports-recreation`, cat-12). Mirrors
> `outputs/phase5_8_events_audit.md` structure with 5.9-specific axes
> (cat-5 HWC primary / cat-7 outdoors secondary / cat-13 cross-list).
>
> **Source data:**
> - `outputs/phase5_9_ambig_audit_data.json` (30 records — 23 in-scope
>   from §1 load + 7 cross-cache from prior phases)
> - `outputs/phase5_9_ambig_audit_stdout.txt` (dump stdout, full
>   aggregates + 3 special-audit sections + edge-case rubric)
> - `outputs/phase5_9_dupe_check.py` output (DB-verify for New Day
>   School / Psalms+Ark / Hilltop / Knights of Columbus / Our Lady of
>   the Lake / Stormy Wade + Sand Volleyball / Aquatic+Nomadic+Lions
>   Dog+Main Street Commons V1.5 carry candidates)
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.9 session 1
> (2026-05-17) post-§1-load, pre-§2-apply. Per the 5.8 close-out §4
> lesson, every cross-cat move premise was DB-verified via the dupe-
> check before slice assignment.
>
> **Pre-§2 cat-12 count: 27 entities** (per §1 load summary: 27 inserts
> + 32 updates (preserved in original cats; mostly cat-5 HWC) + 23
> ambig-skipped). The 32 updates kept cat-5 routing per the
> `places_load.py` "preserve operator's choice" rule (line 537-538).
>
> **Post-§2 cat-12 count projection: 29 entities** (27 + 3 NEW creates
> + 1 FLIP-in − 2 FLIPs-out).

---

## §1 Layer 1 load summary

```
[load] enriched rows: 2644
[load] after --category classes-sports-recreation filter: 85 rows
[load] after ZIP filter: 82 kept, 3 dropped (2x non-LHC 92363 Parker,
                                             1x non-LHC 86440 Mohave Valley)
[load] inserted (new):     27
[load] updated (existing): 32
[load] reconcile skipped (ambiguous): 23
[load] reconcile merged (geo):        0
[load] category_id resolved (Tier 1): 82  ← sustainability layer 100%
[load] category_id unmapped (operator queue): 0
[load] EntityCategory rows inserted:  27  ← matches insert count
```

**Sustainability validation:** 0 unmapped of 82. The 9 direct
`_PRIMARY_TYPE_MAP` entries + new `(None, "childcare_education")`
catch-all + the existing 5.4 `(None, "fitness_sports") → HWC`
catch-all (for the 32 deferred-label updates) covered every primary
type Google emitted.

**Cost actuals:** 11 discovery requests + 0 enrichment new (all 71
cache-hit). ~$0.55 total — under the kickoff §1 forecast $0.50-1.20.

---

## §2 Discovery scope vs load scope (key insight)

| Stage | Filter | Output |
|---|---|---|
| Discovery (Narrow scope wrapper) | 9 in-scope labels only | 71 unique places |
| Enrichment | All 71 (cache-aware) | 71 / 0 new / 71 cache-hit |
| **Load** (`--category classes-sports-recreation`) | Filters cache by `_first_seen_category in <16 labels of cat-12 bundle>` | **85 → 82 (ZIP) — INCLUDES 5.4 HWC cached entries under the 7 deferred fitness_sports labels** |

**Implication:** the 32 §1-updates are mostly 5.4 HWC entities (gyms /
yoga / pilates / dance / martial arts / sports_schools) being
re-touched. They KEEP cat-5 via the preserve-operator-choice rule.
The 23 ambig include both fresh 5.9 discoveries (9 in-scope labels)
AND 5.4-cached entries (7 deferred labels) that the reconciler caught
on geo+name. **Most of the 23 ambig are deferred-V1.5 candidates**
(low signal or HWC-bound); only **2-3 are cat-12 NEW-creates worth
applying**.

---

## §3 Ambig aggregate

```
=== aggregates: 30 ambig-skipped breakdown ===
  total ambig hits:        30  (23 actual §1 + 7 cross-cache leak)
  no match (orphan ambig): 1   (The Study Yoga Studio)
  same-category match:     0
  cross-category match:    29
  cross-cat slug breakdown:
    eat-drink                            14   ← McCulloch / Lake Havasu Ave
                                                strip-mall false-ambig pattern
    health-wellness-care                 5
    home-property-services               3
    auto-rv-fuel                         3
    public-civic-resources               1   ← Aquatic Center near Parks & Rec
    events                               1
    shopping-essentials                  1
    on-the-water                         1
```

**Eat-drink dominance (14)** mirrors the 5.6 strip-mall false-ambig
pattern — cat-12 candidates clustered along McCulloch Blvd N (LHC's
main commercial corridor) routinely match nearby restaurants within
50m. Benign geo-proximity; not real misroutes.

---

## §4 Slice decisions (this is what the apply-script implements)

### Slice A — KEEPs (no apply needed)

**27 §1-inserts in cat-12** ✓ — Already linked via the Phase 1D
dual-write hook. Includes:
- 3 `child_care_agency` (Family Tree Daycare / Little People's Day Care / Nelly's Nursery)
- 6 `preschool` (Guiding Light Christian / Head Start-WACOG / Little Knights / **3 distinct New Day School campuses** — Sotol Ln, Oro Grande Blvd, Havasupai Blvd — verified non-dupe via `phase5_9_dupe_check.py`)
- 7 `primary_school` (elementary schools — routed via new `(None, childcare_education)` catch-all)
- 2 `educational_institution` (Grace Learning Center + 1 New Day School campus)
- 4 `school` (Calvary Christian Academy / Grand Piano Studio / RockerBens Music Lessons / Swivel & Sway Ballroom Dance) — via pre-Phase-5 direct mapping
- 3 `(None)` primary_type (Hava Math Tutor / Hilltop Learning Center / Telesis Preparatory Academy) — routed via new catch-all
- 1 `association_or_organization` (Lake Havasu Tennis Association — legit cat-12) — routed via new catch-all
- 1 `church` (Our Lady of the Lake Catholic School — Slice D will ADD cat-13 dual-cat)

**26 §1-updates kept in cat-5 HWC** ✓ — Default V1 policy per kickoff
§2. The load preserved existing cat-5 routing on `place_id` match
(line 537-538). Includes Sand Volleyball at Rotary Park
(primary=`athletic_field`; per the current sustainability layer
without `athletic_field` direct mapping, it correctly routes to
cat-5; **V1.5 may add `athletic_field` to direct mappings**, but for
V1 KEEP). All gyms / yoga / pilates / dance / martial arts entries
from 5.4 absorption stay. V1.5 may selectively dual-cat.

### Slice B — FLIP cat-5 → cat-12 (1 entry)

| Entity | place_id | Reason |
|---|---|---|
| **Stormy Wade Courts** (`c514b766-1a9d-4718-a459-26092373f7cc`) | `ChIJr6o5LG3y0YAREZD34mh9U4c` | primary=`tennis_court` — direct map per 5.9 sustainability. The 5.4 HWC absorption caught it via the `(tennis_court, fitness_sports) → HWC` fallback. New direct mapping `("tennis_court", ("classes-sports-recreation", "place"))` beats the catch-all per resolver order — for fresh loads. The existing entry needs an explicit FLIP. |

Address: 2675 Palo Verde Blvd S (same address as Little Knights
Preschool — note potential dual-cat opportunity in V1.5).

### Slice C — FLIP cat-12 → cat-13 (2 entries)

| Entity | place_id | Reason |
|---|---|---|
| **Knights of Columbus** (`5c431179-b2c5-47f7-a2c9-aed85576849e`) | `ChIJZVbXQJrt0YAR1g-httr7rGU` | primary=`association_or_organization` — Knights of Columbus is a Catholic civic/fraternal organization, not an educational institution. Was caught by the new `(None, "childcare_education")` catch-all but belongs in cat-13 public-civic-resources. |
| **Hilltop Community Church** (`26e794d7-f9a0-41ba-8066-e4679fbadf6c`) | `ChIJV9hpw0_y0YAR_UxJeKygV-A` | primary=`church` — the Church itself is a church (cat-13). The Hilltop Learning Center entity (a separate place_id `ChIJqa5UnPTz0YAR57zjQkHeBZI`, same 3180 McCulloch Blvd N address) IS the educational arm and stays in cat-12. |

### Slice D — DUAL cat-12 + cat-13 (1 entry)

| Entity | place_id | Reason |
|---|---|---|
| **Our Lady of the Lake Catholic School** (`cab0c922-9c2c-4bcc-8ae9-9a9d8ca02964`) | `ChIJc9Q61Yby0YARDqFc-0_Dij8` | primary=`church`, name explicitly contains "Catholic School". IS a school (cat-12, KEEP existing) AND a church (cat-13, ADD). Currently cat-12 only per dupe-check. |

### Slice E — NEW creates in cat-12 (3 entries via `create_provider_and_entity` dual-write)

| Candidate | place_id | primary_type | reviews | Why NEW-create |
|---|---|---|---|---|
| **Lake Havasu City Aquatic Center** | `ChIJN55Jln7t0YAR18RO0S_8qtc` | `swimming_pool` | **595** | The 5.8 §9 V1.5 carry candidate. Dupe-check confirmed 0 entities in DB (kickoff §2 forecast was correct — NOT a FLIP, NEW-create). Currently in enrichment cache via 5.4 `spas` label (discovery_domain=beauty_personal_care). Excluded from §1 load by `--category` filter (correct: beauty_personal_care isn't in cat-12's 2-domain bundle). But the resolver would route it cleanly to cat-12 via the `swimming_pool` direct mapping. The ambig pool shows it matching Parks & Recreation Department at 22m (different place_id — same physical complex, different Google entries). 595 reviews = highest-signal cat-12 candidate. **Explicitly apply-script NEW-create** with cached enrichment data + force cat-12 routing. Mirrors the 5.8 Slice A pattern (16 NEW creates beyond `--category` scope). |
| **Psalms Learning Center** | `ChIJ_bG0seLt0YARY3ZqkgUYCmo` | `school` | 0 | In §1 load ambig pool. Matched against The Ark Center at 3.8m (SAME ADDRESS — 2700 Jamaica Blvd S). Likely a preschool program operated from The Ark Center building (which itself is a weakly-typed cat-5 HWC entity, primary=`point_of_interest`, possibly a religious org based on the name "Ark"). Discovery label was `preschools` (in-scope). `school` primary maps directly to cat-12. **NEW-create**. V1.5 carry: consider Ark Center recategorization to cat-13 + Psalms dual-cat. |
| **Mohave Traffic School** | `ChIJm89F6nzy0YAR7lZNRJSfAHQ` | `educational_institution` | 0 | In §1 load ambig pool. Discovery label was `driving schools` (in-scope). 5 eat-drink ambig matches all benign geo (430 El Camino Way, near a strip with Broken Yolk Cafe etc.). Routes to cat-12 via the new `(None, childcare_education)` catch-all. **NEW-create**. |

### Slice F — KEEP ambig (no apply needed) — 20 entries

Most of the 23 in-scope ambig are gym/yoga/pilates/martial-arts
entries discovered under the 7 HWC-deferred labels (cached from 5.4)
that the reconciler caught on cross-cat geo match. Per kickoff §1
Narrow scope decision, these are deferred to V1.5 (don't NEW-create
them in 5.9; the 5.4 HWC scope decided to skip them too).

Notable Slice F entries (all KEEP-ambig; no apply):

| Candidate | primary | reviews | discovery label | Notes |
|---|---|---|---|---|
| Body Shop Fitness | fitness_center | 1 | gyms | Low signal; HWC-bound |
| Trevor the Trainer | health | 0 | personal trainers (IN-SCOPE) | Low signal |
| Titan Gym & Fitness Center | gym | 61 | gyms | HWC-bound per 5.4 catch-all |
| Foot Lite School of Dance | sports_school | 4 | dance studios | HWC-deferred |
| Elite Martial Arts, Inc. | sports_school | 1 | martial arts | HWC-deferred |
| Bridge City Combat | sports_school | 7 | gyms | HWC-deferred |
| Feelin' Good Fitness | fitness_center | 110 | gyms | High signal but HWC-bound; V1.5 |
| The Study Yoga Studio | yoga_studio | 12 | gyms | Orphan (no matched entity); HWC-bound |
| Shah Racquetball Club | gym | null | gyms | Interesting: racquetball = sport (cat-12) but primary=gym; no reviews; defer |
| Havasu Shao-Lin Kempo | sports_school | 25 | martial arts | HWC-deferred |
| Universal Sonics Gymnastics & All Star Cheer | gym | 24 | gyms | Interesting: gymnastics = cat-12 sport but primary=gym; defer |
| THE TAP ROOM JIU JITSU | sports_club | 28 | gyms | HWC-deferred; primary=sports_club not in any direct map |
| Fit Lab 928 | gym | 32 | gyms | HWC-bound |
| Bridge Body Fitness | gym | 94 | gyms | High signal but HWC-bound |
| Crazy Eds Cardio & Pilates | gym | 6 | gyms | HWC-deferred |
| Heartbridge Breathwork | yoga_studio | null | yoga studios | HWC-deferred |
| ...(plus ~4 more in the 23) | | | | |

**Rationale:** kickoff §1 explicitly deferred the 7 HWC-absorbed
fitness_sports labels (gyms, yoga, pilates, crossfit, martial arts,
jiu-jitsu, dance studios) to V1.5. NEW-creating these in cat-5 HWC
in 5.9 would expand HWC scope beyond what 5.4 chose to absorb.
Better to defer the whole HWC re-evaluation to V1.5.

### Cross-cache informational (7 entries — NOT in §1 load; SKIP)

These surfaced in the dump because their `_seen_categories` from prior
phases overlap cat-12 labels, but they were NOT processed by the §1
load (excluded by `--category classes-sports-recreation` filter):

- River City Music (discovery_domain=retail, primary=store, 105
  reviews) — V1.5: cross-cat consideration if River City offers
  music lessons in addition to retail.
- Eight Lotus Wellness and Yoga (discovery_domain=beauty_personal_care)
- PRO Therapy (discovery_domain=health_medical) — already in HWC scope
- Bella Faccia Skincare and Pilates (discovery_domain=beauty_personal_care)
- Ben Hicks Yoga (discovery_domain=beauty_personal_care)
- plus 2 others

---

## §5 Special audit (a) — cat-5 HWC primary axis (THE BIG ONE)

**Ambig pool — cat-5 HWC matches: 7 records** (all geo-noise per
above; all listed in Slice F as KEEP-ambig — distinct businesses to
their geo-neighbors, but per kickoff §1 V1.5 deferral, no NEW-create).

**§1-updated entries currently in cat-5 HWC — 26 (dual-cat
candidates):** see dump stdout. All KEEP cat-5 per V1 policy. V1.5
may dual-cat selectively. Notable individual cases:

| Entity | primary | Notes |
|---|---|---|
| **Sand Volleyball, Rotary Park, Three North Courts** | `athletic_field` | At Rotary Park (cat-7). Athletic_field is a cat-12 amenity by nature but not in 5.9 direct mappings. V1.5 carry: add `athletic_field` to `_PRIMARY_TYPE_MAP` OR dual-cat with cat-7. |
| **Stormy Wade Courts** | `tennis_court` | Slice B FLIP (see above). |
| 23 gyms / yoga / pilates / martial arts / sports_schools / dance / fitness_centers / 1 consultant / 1 point_of_interest (Ark Center) | various | Default KEEP cat-5. V1.5 individual review. |

---

## §6 Special audit (b) — cat-7 outdoors-parks-trails secondary axis

```
=== special audit (b): cat-7 outdoors-parks-trails secondary axis ===
  (no cat-7 outdoors-parks-trails cross-list hits in ambig pool)
```

**No cross-list overlap in ambig.** The reconciler did not find any
ambig matches between 5.9 candidates and cat-7 parks. Sand Volleyball
at Rotary Park is the closest case but it's in the §1-updates pool
(not ambig) and was already in cat-5 from 5.4.

V1.5 consideration: dual-cat the Sand Volleyball entity with cat-7
(its parent park is in cat-7) OR move it to cat-12 with `athletic_field`
direct mapping. Not gate-blocking; defer.

---

## §7 Special audit (c) — cat-13 public-civic-resources cross-list

```
=== special audit (c): cat-13 public-civic-resources cross-list ===
  - cand 'Lake Havasu City Aquatic Center' label='spas' -> existing
    'Parks & Recreation Department' @ public-civic-resources
    (sports_activity_location, 22.2m)
```

**1 ambig hit, addressed by Slice E:** Lake Havasu City Aquatic
Center matched Parks & Recreation Department at 22m. Different
place_ids; physically same civic complex but distinct businesses
(the Aquatic Center is the actual swimming facility; Parks & Rec
Dept is the administrative office). Slice E NEW-creates Aquatic
Center as cat-12 (`swimming_pool` primary, clear identity); Parks &
Rec Dept stays in cat-13.

**Plus Slice C/D church-related cross-cat decisions:**
- Knights of Columbus → cat-13 (FLIP from cat-12)
- Hilltop Community Church → cat-13 (FLIP from cat-12)
- Our Lady of the Lake Catholic School → cat-12 + cat-13 (DUAL)
- Hilltop Learning Center → KEEP cat-12 (educational arm of Hilltop
  Community Church, separate place_id; should stay cat-12)

---

## §8 Pre-§4 gate-1 projection

| Source | Count |
|---|---|
| 27 §1-inserts (already in cat-12) | +27 |
| + 3 Slice E NEW creates (Aquatic Center, Psalms, Mohave Traffic) | +3 |
| + 1 Slice B FLIP-in (Stormy Wade Courts cat-5 → cat-12) | +1 |
| − 2 Slice C FLIPs-out (Knights of Columbus + Hilltop Community Church → cat-13) | −2 |
| + 0 Slice D (Our Lady gets ADDed cat-13; cat-12 unchanged) | 0 |
| **Total cat-12 entities post-§2** | **29** |

Comfortably ≥20 gate threshold (1.45× target).

**Gate-1 query shape:** must use the
`(e.entity_type != 'commercial' OR provider-visible)` OR-clause shape
from `outputs/phase5_8_gate_verification.py` since 1 of the 29 (the
Aquatic Center) is `entity_type='place'` (swimming_pool maps to
`place` per the 5.9 sustainability commit).

---

## §9 Carry-forwards to V1.5 + Phase 5.10

### Slice carry — V1.5 reconsideration

- **HWC dual-cat** — the 26 §1-updates in cat-5 HWC (gyms/yoga/pilates/
  etc.) may want selective dual-cat with cat-12 for entities offering
  distinct cat-12 services (e.g. a gym whose personal trainers
  deserve a separate cat-12 listing).
- **Sand Volleyball at Rotary Park** — currently cat-5; should either
  FLIP to cat-12 (after `athletic_field` direct mapping V1.5 ext) OR
  dual-cat with cat-7 (its parent park is in cat-7).
- **The Ark Center** — currently cat-5 HWC, weak primary=
  `point_of_interest`. Building also houses Psalms Learning Center
  (the new Slice E cat-12 entity). V1.5: consider recategorizing
  Ark Center to cat-13 (religious org) AND/OR dual-cat with cat-12
  if it operates as a learning center umbrella.
- **Hilltop Community Church + Hilltop Learning Center** — same
  campus, different place_ids. Slice C FLIPs the Church to cat-13;
  V1.5 may want to consolidate / cross-link.
- **Universal Sonics Gymnastics & All Star Cheer** + **Shah
  Racquetball Club** — both primary=`gym` but the actual sport
  (gymnastics, racquetball) is cat-12 not cat-5. Currently KEEP-ambig
  per Slice F (HWC scope decision). V1.5 may want to NEW-create in
  cat-12 with explicit primary_type override.
- **Bridge Body Fitness** (94 reviews) + **Feelin' Good Fitness** (110
  reviews) — high-signal gyms in the ambig pool. V1.5 may NEW-create
  in cat-5 HWC if 5.4 lane gets re-opened.
- **River City Music** — V1.5 cross-cat consideration if it offers
  music lessons in addition to retail.

### Sustainability layer V1.5 extensions

- Add `athletic_field` direct mapping (mirror tennis_court / swimming_
  pool shape; → cat-12 place)
- Add `educational_institution` direct mapping (currently catches
  cat-12 via new childcare_education catch-all only — direct entry
  would route correctly regardless of discovery_domain)
- Add `primary_school` direct mapping (same as above — `school` is
  already direct mapped; `primary_school` is Google's variant)
- Add `church` direct mapping → cat-13 (cleaner than relying on
  per-row Slice-C-style FLIPs)
- Consider `sports_complex` / `sports_club` / `country_club` /
  `fitness_center` decisions (some are cat-5 HWC, some cat-12; needs
  per-type review)

### Phase 5.10 carry — Nomadic / Lions Dog / Main Street Commons

5.8 §9 V1.5 carry candidates that the dupe-check confirmed are 0 in
DB. None are gate-blocking; each is a single-entity Layer 5 manual
recovery candidate. Note for Phase 5.10 (next Tier-1 category — likely
`lodging-vacation-rentals` or `pets`).

### Phase 6 carry — `parks-rec-scrapes` cron fix

Root cause identified in Phase 5.7 §4.5 sidebar; 3 fix options
surfaced. Default deferred-to-sidecar (kickoff §4.5). Not in 5.9 scope.

### Phase 6 carry — Amendments 5+6+7+8 ledger lines

Consolidated dispatch authored at
`outputs/claude_code_dispatch_phase6_amend5_to_8.md` per Phase 5.9
§0 operator decision (defer all 4 to Phase 6 sidecar). Phase 6 lane
or Claude Code parallel agent to land before next 5.x dispatch.

---

## §10 Apply-script reference

`outputs/apply_phase5_9_classes_audit.py` will implement Slices B + C
+ D + E above (Slices A and F are no-ops):

- **Slice B FLIP cat-5→cat-12 (1 entry):** Stormy Wade Courts —
  replace the cat-5 EntityCategory row with a cat-12 row, preserving
  `is_primary=True`.
- **Slice C FLIP cat-12→cat-13 (2 entries):** Knights of Columbus +
  Hilltop Community Church — replace cat-12 EntityCategory row with
  cat-13 row.
- **Slice D DUAL ADD cat-13 (1 entry):** Our Lady of the Lake
  Catholic School — INSERT cat-13 EntityCategory row (with
  `is_primary=False`), preserving existing cat-12 row as primary.
- **Slice E NEW create (3 entries):** Lake Havasu City Aquatic
  Center + Psalms Learning Center + Mohave Traffic School — call
  `app.db.entity_dual_write.create_provider_and_entity()` with
  payloads constructed from cached enrichment data + force
  `category_id` to cat-12 (Aquatic Center) / cat-12 (Psalms) /
  cat-12 (Mohave Traffic). Aquatic Center entity_type=`place`
  (swimming_pool → place); Psalms entity_type=`commercial` (school →
  commercial); Mohave Traffic entity_type=`commercial`
  (educational_institution → commercial, via catch-all default).

DB-write commit shape mirrors `apply_phase5_8_events_audit.py`. All
imports at top of file (no inline imports — I001 footgun from 5.8
§4 lesson). Dict-direct to JSON columns (no `json.dumps()` per
5.3 `f35d5e4` gotcha). Stop FastAPI dev server before running
(events.db lock).
