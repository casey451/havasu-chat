# Phase 5.11 Kickoff -- Pets (`pets`)

> **What this is:** a single paste-and-go operator runbook for Phase 5.11,
> the eleventh Tier 1 category and the **LAST remaining 5.x sub-phase**.
> Mirrors `outputs/phase5_10_lodging_vacation_rentals_kickoff.md` shape
> with 5.11-specific overrides. **Single-layer scrape** (Google only --
> OSM scope is locked to on-the-water per brief 3.2.e) over a clean
> **single-domain** label set (no bundle / Narrow scope complexity).
>
> **GATE 1 -- Phase 5.10 SHIPPED** at `592ee74` (2026-05-17) with all 6
> gate items cleared, plus SHA-cleanup at `accc06d`. Met.
>
> **GATE 2 -- no pre-built verifier surface for 5.11.** There is no
> consolidated public registry for pet groomers / dog boarders / dog
> trainers in Arizona. The Arizona State Veterinary Medical Examining
> Board (azvetboard.gov) licenses VETERINARIANS but the 5.11 scope
> excludes vet clinics by label (the 4 in-scope labels are pet stores
> / dog groomers / dog boarding / dog trainers; vets are absorbed by
> 5.4 HWC via the `medical_clinic` direct mapping). National
> franchise locators (PetSmart, Petco) cover retail-chain pet stores
> but not the full LHC pet-service surface. **This kickoff resolves
> 3 as Option C** (defer Layer-4 verifier surface to V1.5; document
> the narrow paths). Mirrors 5.5 + 5.6 + 5.7 + 5.8 + 5.9 + 5.10
> outcome.
>
> **GATE 3 -- pre-flight integrity gotcha (now EIGHTH+ recurrence
> watch):** `scripts/places_categories.json` has drifted locally on
> sessions 5.5 / 5.6 / 5.7-boot / 5.7-session-2-pre-flight. The
> 5.7 / 5.8 / 5.9 / 5.10 sessions found the four-file shape check
> (places_categories.json + places_load.py + models.py +
> google_types_mapping.py) clean at 0. The 5th + 6th + 7th + 8th
> recurrence forecasts did NOT materialize but the pattern remains
> watch-worthy. Pre-flight item #6 below is the same four-file check.
>
> **5.11 IS THE LAST 5.x SUB-PHASE.** After 5.11 ships, all 13 Tier-1
> categories are populated and V1 acceptance gate (Phase 6) becomes
> the next major milestone. The 5.11 SHIP commit close-out should
> reference V1 readiness in its hand-off section (no Phase 5.12
> follows; instead the next session picks up V1 cross-category review
> or Phase 6 V1 gate work).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.10 session 1
> (2026-05-17) post-`592ee74` SHIP + `accc06d` SHA-cleanup, pre-0
> hand-off artifact. Commit inline before 0 pre-flight dispatches
> per the established cadence.

---

## 0 Pre-flight (do once, at Phase 5.11 dispatch)

1. **`git log --oneline -15`** -- origin should top at `<this commit>`
   (Phase 5.11 kickoff doc pre-stage) over `accc06d` (5.10 SHA-cleanup)
   over `592ee74` (5.10 SHIP) over `bf24e16` (5.10 sustainability) or
   later if Phase 6 lane has shipped the consolidated amend5-X dispatch
   between sessions. The 5.10 lane chain since 5.9's `bc08bf6`
   SHA-cleanup: `ef8325d -> d597ef9 -> bf24e16 -> 592ee74 -> accc06d`.
2. **`git status`** -- clean. **Sandbox bash note:** `git status` hits
   the index-format gotcha (`fatal: unknown index entry format
   0xffff0000`); run Windows-side via PowerShell. Carry-over untracked
   from 5.10: `hava_api_catalog.docx` + `~$va_api_catalog.docx` Word
   lock + 2 historical `outputs/ci_*_log_failed.txt` files +
   `outputs/_deltest` -- all unrelated to lane; operator prunes when
   comfortable.
3. **`python -m alembic current`** -- confirm local `data/events.db` at
   `0a1b2c3d4e5f`. If behind, `python -m alembic upgrade head`. (No
   migrations expected on the 5.11 lane unless the parks-rec-scrapes
   prune-fix sidecar lands -- that would add an `ON DELETE SET NULL`
   migration on `contributions.created_event_id`.)
4. **`python -m pytest -q --collect-only 2>&1 | Select-Object -Last 3`**
   -- record baseline. Phase 5.10 closed at **2002 collected** (5.9
   baseline 1985 + 17 in-lane regression guards for the `bf24e16`
   `_PRIMARY_TYPE_MAP` extension for the 5 cat-10 primary types +
   1 new `(None, "lodging")` catch-all). Verify no drift.
5. **`python outputs/diagnose_category_id_gap.py`** -- confirm Phases
   5.1-5.10 categorization is intact and the `pets` slug exists in the
   `categories` table (id=11 per the diagnose script output).
6. **WIDENED four-file shape check** (carried from 5.7 + 5.8 + 5.9 + 5.10 0):
   ```powershell
   git diff --stat scripts/places_categories.json scripts/places_load.py app/db/models.py app/contrib/google_types_mapping.py
   ```
   MUST be empty Windows-side (sandbox view may lie per the
   recurring mount-staleness pattern). If ANY of the four shows
   deletions in the working tree, restore via `git restore .`
   Windows-side before 1. Expected HEAD line counts post-`accc06d`
   (sanity reference, not validation targets -- content over shape):
   - `scripts/places_categories.json`: 212 lines
   - `scripts/places_load.py`: 700+ lines (carries 5.10 `bf24e16`
     `(None, "lodging")` catch-all)
   - `app/db/models.py`: 1539+ lines
   - `app/contrib/google_types_mapping.py`: 290+ lines (carries 5.10's
     5 cat-10 direct mappings + 5.9's 9 cat-12 direct mappings + 5.8's
     7 events + 5.7's golf_course + medical_clinic widenings)
7. **Google Places key + spend cap** -- operator has deferred rotation
   until project end; still in `.env`, still capped. No mid-session
   rotation needed unless the operator opts in.
8. **CI state** -- check GitHub Actions on the top commit. Should be
   green on `accc06d` (the 5.10 SHA-cleanup commit, docs-only),
   `592ee74` (the 5.10 SHIP commit), and `bf24e16` (the 5.10
   sustainability commit). If red, investigate before starting 5.11.
   The `parks-rec-scrapes` scheduled cron has been failing since 5.3
   -- root cause identified at 5.7 4.5 sidebar; **NOT in 5.11 scope**
   unless operator opts to dispatch the parks-rec-prune sidecar fix
   as part of this lane.
9. **DB state spot-check** -- `lodging-vacation-rentals` should show
   **73 entries / 0 verified / 53 indoor + 19 outdoor + 1 water_adjacent
   / 73 render / 10 long-form crowd_notes** (the 5.10 SHIPPED state).
   `classes-sports-recreation` should still show **31/0/29+2/31/10**
   (5.9 SHIPPED state, unchanged). `events` should still show
   **20/0/17+3/20/10** (5.8 SHIPPED state, unchanged).
   `pets` should show **0-10 entries pre-load** (the cat-11 slug
   exists; pre-Phase-5 `veterinary_care` + `pet_store` direct mappings
   may have absorbed a small number of entities -- operator can verify
   via `python outputs/phase5_11_db_spot_check.py` once authored).

---

## 1 The scrape sequence -- Google only, single-domain CLEAN

Phase 5.11 is **single-layer** (no OSM dispatch -- OSM scope is locked
to on-the-water per brief 3.2.e). **Scope is clean -- no Narrow
scope decision needed** because `pets` is a single-domain mapping with
no bundle collision:

Per `app/contrib/google_places_scraper.py:88`:
```python
"pets": frozenset({"pets"}),
```

The `pets` domain has **4 labels** in `scripts/places_categories.json`
(lines 195-198):

| # | Label | Domain | Expected Google primary_types |
|---|---|---|---|
| 1 | pet stores | pets | `pet_store` (mapped) |
| 2 | dog groomers | pets | `dog_groomer` / `pet_groomer` (NOT mapped) |
| 3 | dog boarding | pets | `pet_boarding` (NOT mapped) |
| 4 | dog trainers | pets | `dog_trainer` (NOT mapped) |

**NOTE -- vet clinics are NOT in 5.11 scope.** The `pets` domain
intentionally excludes veterinary clinics because:
- The 5.4 HWC absorption already caught vet clinics with primary=
  `medical_clinic` (a HWC-mapped primary type via the 5.7 widening at
  `1dfd28e`)
- The `pet stores` label search returns retail pet supply shops, not
  vet clinics
- LHC vet clinics likely have `veterinary_care` primary -- mapped to
  cat-11 pre-Phase-5 -- so any vet that gets discovered via cache
  cross-reference (e.g., a vet store under a pet stores label search)
  will route to cat-11 correctly

### Layer 1 -- Google Places

```
python -m scripts.places_discovery --category pets --dry-run
python -m scripts.places_discovery --category pets
python -m scripts.places_enrichment --limit 200
python -m scripts.places_load --category pets --dry-run
python -m scripts.places_load --category pets
```

**No Narrow scope wrapper needed** -- the 4 pets labels are all in-
scope; no deferred labels. Operator may STILL author a wrapper if a
specific label proves noisy in dry-run (Path A.2 pattern available),
but the default expectation is to use `places_discovery --category
pets` directly.

**Why `--limit 200` on enrichment?** 4 labels x ~10-15 per label = 40-60
raw hits; the cumulative enrichment cache (5.0/5.1/5.2/5.3/5.4/5.5/5.6/
5.7/5.8/5.9/5.10) is ~2,645+ records. Pet stores + vet clinics likely
overlap with 5.4 HWC cache absorption; dog groomers + dog boarding +
dog trainers are mostly NEW discoveries. Expected new enrichments:
~10-30.

### Sustainability layer -- TBD per 1 dispatch findings (CONDITIONAL)

**Pre-existing direct `_PRIMARY_TYPE_MAP` entries for cat-11:**
- `"veterinary_care": ("pets", "commercial")` (pre-Phase-5)
- `"pet_store": ("pets", "commercial")` (pre-Phase-5)

**Google's actual primary_types for pets:** `pet_store`,
`veterinary_care`, `dog_groomer` (or `pet_groomer`), `pet_boarding`,
`dog_trainer`. Only the first two are mapped today.

**Forecast:** dog_groomer + pet_boarding + dog_trainer entries
discovered via their respective labels will likely land at
`category_id=NULL` (operator queue) -- there's no `(None, "pets")`
catch-all today AND no direct mapping for these 3 primary types.
Decision deferred to 1 load output:
- If `category_id unmapped (operator queue) == 0` -- sustainability
  commit not needed (unlikely, but possible if Google emits `pet_store`
  as a secondary type for the unmapped primaries the way `lodging`
  caught most cat-10 entries).
- If `category_id unmapped (operator queue) > 0` -- author
  sustainability commit per Option A pattern below.

**Three options if sustainability IS needed** (operator picks at 1
dispatch time; recommended default is **Option A**):

**(A -- recommended) Add direct `_PRIMARY_TYPE_MAP` entries** for the
3 expected pet-service primary_types. Example shape (`app/contrib/
google_types_mapping.py` `_PRIMARY_TYPE_MAP`):

```python
# pets (cat-11) primary types -- 5.11 1 sustainability extension
"dog_groomer": ("pets", "commercial"),
"pet_boarding": ("pets", "commercial"),
"dog_trainer": ("pets", "commercial"),
```

Plus a safety-net catch-all:
```python
# scripts/places_load._DISCOVERY_DOMAIN_FALLBACK
(None, "pets"): "pets",
```

The new `(None, "pets")` catch-all is NEW (no prior phase populated
this domain). It covers any unmapped pets primary_types Google emits.

**(B) Catch-all only** -- just add the `(None, "pets") -> "pets"`
fallback. Simpler but loses the commercial-vs-place distinction.

**(C -- hybrid)** -- both A + B. Most explicit + future-proof.

**Recommended: Option A.** Mirror the 5.9 `0af5f73` + 5.10 `bf24e16`
shape: single focused `fix(scripts)` commit that adds 3
`_PRIMARY_TYPE_MAP` entries + 1 catch-all + regression tests in
`tests/test_phase5_11_places_load_resolver.py` (~8-10 parametrized
asserts: 3 for the new primary types + 1 catch-all + 4-6 defensive
preservation of prior phases' fallbacks). Land BEFORE the 1 Layer 1
dispatch OR conditionally after (5.10 pattern). **Skip entirely if 1
load shows 0 unmapped.**

### Layer 5 -- Manual recovery (deferred to operator)

Per `docs/maintainability/manual_recovery_checklist.md`. Surface for
5.11:

- Mobile dog groomers (home-service businesses; may have no fixed
  Google Place)
- Independent dog walkers (typically NOT Google-indexed as venues)
- Cat boarding services (smaller surface than dog boarding; some may
  not have separate Google listings)
- Pet sitting services (often listed on Care.com / Rover, not Google
  Places)

Not gate-blocking for V1 ship.

---

## 2 Ambiguous-queue review -- minimal cross-category overlap expected

Pets is the **eleventh non-empty-DB load** (after 5.1-5.10). Reconciler
will match against **~1,308+ existing entities** (post-5.10: 287
eat-drink + 119 on-the-water + 230 HPS + 265 HWC + 140 auto-rv-fuel +
76 shopping-essentials + 27 outdoors-parks-trails + 20 events + 1
public-civic-resources + 31 classes-sports-recreation + 73
lodging-vacation-rentals + 0-10 pre-existing pets + 86 unverified HWC
carry). Expected ambiguous hits: **5-20 per run** (minimal because
pet-service venues cluster less than the eat-drink / HWC density that
drove 5.6-5.10 ambig counts).

**Special audit categories expected for 5.11:**

| Existing entity | 5.11 candidate it'll likely match | V1 policy |
|---|---|---|
| Vet clinics in cat-5 HWC (from 5.4 via `medical_clinic`) | (no 5.11 label maps directly -- pets has no vet label) | KEEP cat-5 if `medical_clinic` primary; potential V1.5 dual-cat with cat-11 if vet also offers grooming/boarding |
| Pet stores already in cat-11 via pre-Phase-5 `pet_store` direct map | pet stores (cat-11) | KEEP cat-11 (already correctly placed) |
| Retail co-located with grocery (cat-8 shopping-essentials) | dog groomers/pet stores (cat-11) | review -- typically pet supply aisles inside grocers stay cat-8; standalone pet stores go cat-11 |
| Dog parks already in cat-7 outdoors-parks-trails (from 5.7 via pre-Phase-5 `dog_park`) | (no 5.11 label maps directly) | KEEP cat-7 |
| Mobile groomers / home-based services | dog groomers (cat-11) -- if Google-indexed as venues | NEW-create in cat-11 if discoverable |

**Primary axis: cat-5 HWC cross-list (vet clinic overlap).** Most LHC
vet clinics are likely in HWC from 5.4 via `medical_clinic` primary.
The 5.11 scrape may rediscover them under pet stores label searches
(unlikely but possible). V1 policy per kickoff: **KEEP cat-5** for
vet-primary identity; V1.5 may dual-cat selectively.

**Secondary axis: cat-7 outdoors-parks-trails (dog park overlap).**
The pre-Phase-5 `dog_park` direct mapping routes dog parks to cat-7.
5.11's `dog boarding` / `dog trainers` labels won't directly match
dog parks (different primary types), so 0 cross-cat hits expected.

**Tertiary axis: cat-8 shopping-essentials (pet retail overlap).** Pet
supply stores tagged as `pet_store` route to cat-11 via the existing
direct mapping. Mixed retail venues (e.g., a Walmart with a pet aisle)
have `store` or `supermarket` primary -- cat-8 -- so they stay
correctly categorized. No cross-cat audit expected.

Mirror the 5.10 audit pattern: post-load audit pulls cross-category +
same-category; an apply-script batches the misroute decisions if any.
**Expected outcome based on 5.4-5.10 history: 0 real misroutes** in
the cross-cat ambig pool (benign geo-proximity false positives), plus
~3-8 NEW creates for pet-service venues not yet in DB.

If a single load produces **>20** ambiguous hits, consider tuning
`GEO_PROXIMITY_THRESHOLD_M` (currently `50.0`) per brief 4.g -- but
prior phases have all stayed under the tune threshold.

### Cross-category sweep -- `_DISCOVERY_DOMAIN_FALLBACK` catch-all behavior

Per 5.6 + 5.7 + 5.8 + 5.9 + 5.10 close-outs: the `(None, "<domain>")`
catch-all routes ALL unmapped primary_types under that domain. The
`pets` domain has NO existing catch-all (no prior phase populated it).
5.11 1 Option A direct mappings + new `(None, "pets")` catch-all (if
shipped) cover the surface.

Apply-script `outputs/apply_phase5_11_pets_audit.py` if any NEW creates
or FLIPs needed. Expected size: ~5-10 rows reviewed, likely 3-8 NEW
creates (mirroring 5.10 Slice E pattern).

### DB-VERIFY discipline (5.8 + 5.9 + 5.10 lesson)

Author `outputs/phase5_11_dupe_check.py` EARLY in 2 audit (before
finalizing the audit doc) to verify all cross-cat move premises:
- Which vet clinics ARE in cat-5 HWC currently? (informs potential
  dual-cat candidate list)
- Which 5.11 candidates have geo-co-located cat-1 / cat-8 / cat-5
  entries? (informs cross-link decisions)
- Are there pet stores already in cat-11 from pre-Phase-5? (informs
  gate-1 baseline)
- Mobile groomers / home-based services -- are any Google-indexed
  as fixed venues?

The 5.8 Slice B-1 lesson + 5.9 Aquatic Center reframe + 5.10
waterfront-resort reframe all underscore: assume nothing about
existing DB state until verified.

---

## 3 Layer-4 verifier surface -- Option C resolved (deferred to V1.5)

**5.11 has no pre-built verifier** (unlike 5.3's `az_roc_verify` and
5.4's `npi_verify`). Three narrow paths exist; this kickoff resolves
3 as **Option C** per the structural reasoning in the header. The
other two paths are documented here for V1.5 pickup.

### Option A -- AZ State Veterinary Medical Examining Board registry (DEFERRED to V1.5, NOT applicable to 5.11 scope)

URL: `https://azvetboard.gov` -- licenses VETERINARIANS only. The 5.11
scope explicitly excludes vet clinics (5.4 HWC absorbed them via
`medical_clinic` primary). This verifier would be useful for a vet-
specific re-scrape or a HWC cross-cat dual-cat sweep, NOT for 5.11's
4 in-scope labels. **Not in 5.11 lane.**

### Option B -- National pet franchise locators (DEFERRED to V1.5)

URLs: PetSmart store locator (petsmart.com), Petco store locator
(petco.com), Banfield Pet Hospital locator (banfield.com -- vet,
out of 5.11 scope). Covers retail-chain pet stores; misses
independent pet stores + all pet-service businesses (groomers,
boarders, trainers).

Coverage: ~5-10% of cat-11 candidates (very narrow). Cost-of-build:
~3-5 hours. **Not worth V1 build.**

### Option C -- Defer verifier surface to V1.5 SELECTED

Gate item 3 rephrased to **"Layer-4 verifier surface scoped -- built
or explicitly deferred to V1.5"**. Document AZ Vet Board + national
chain locator paths in this kickoff and ship 5.11 without verifier
surface. Lowest-friction shape; mirrors 5.5 + 5.6 + 5.7 + 5.8 + 5.9
+ 5.10 outcome.

**Rationale:** pet-service verification has very low V1 utility
(consumer discovery doesn't need a "verified by AZ Vet Board" badge
on a dog groomer); the AZ Vet Board only covers vets (out of 5.11
scope by design); national chain locators cover too narrow a slice.
Better to defer the whole verifier surface to V1.5 when the right
shape can be designed against fuller scope.

---

## 4 Operator-curated field entry -- Pets rubric

Lighter operator surface than 5.4 (no NPI verification) + 5.6 (no
brand-name normalization); on par with 5.7/5.8/5.9/5.10 shape:

- **`heat_exposure`** -- **`indoor` for most 5.11 entries** (pet
  stores, dog groomers, dog trainers in studios, vet clinics are all
  indoor-by-definition). **`outdoor` overrides** expected for: pet
  boarding facilities with outdoor runs / dog daycare with outdoor
  yards (most LHC pet boarding venues have outdoor exercise areas).
  Expected override count: **2-5** (lower than 5.10's 19+1 since pets
  is a smaller surface). Mirror 5.10's apply-script shape: default
  `indoor` + populate `OUTDOOR_OVERRIDES` list.
- **`crowd_notes`** -- short-form for typical entries; long-form for
  the top-10 by review count. Pet-service reviewer signals tend to
  be: staff care for animals, cleanliness of facility, pricing
  transparency, scheduling availability, named staff callouts
  (groomers often have repeat-client relationships), kid- and
  family-friendliness of pet store interactions, training methodology
  (positive reinforcement vs traditional), facility size and layout
  (boarding kennel vs day care vs overnight), safety supervision
  ratios.

Drafts source: **`Provider.google_review_snippets` (own column, not
`attributes`)** -- per the 5.4 close-out 4 source-path correction.
Expected snippet coverage: **~70-90%** (pet stores have moderate
review density; dog groomers / trainers vary -- chain franchises
abundant, independents lower).

**`is_mobile_service`** is NOT a gate item for 5.11 by default --
cat-11 is mostly venue-based (pet stores, kennels, training studios).
Mobile groomers exist but are rare in LHC's Google Places surface.
Skip the `is_mobile_service` apply-script for 5.11.

**`attributes`** JSON -- can be extended with cat-11-specific keys:
`accepts_cats` (bool), `accepts_exotic_pets` (bool), `outdoor_runs`
(bool), `overnight_boarding` (bool), `grooming_service` (bool),
`training_service` (bool), `delivery_service` (bool for pet stores).
Brief 3.4 has the suggestion shape.

### 4.5 sidebar -- `parks-rec-scrapes` prune-fix dispatch (optional)

The scheduled `parks-rec-scrapes` GitHub Actions workflow has been
failing on cron triggers since at least Phase 5.3. Root cause
identified in Phase 5.7 4.5 sidebar: Postgres FK constraint violation
in `scripts/parks_rec_prune.py`. **3 fix options** surfaced in
`outputs/phase5_7_session_closeout.md` 3 -- alembic migration adding
`ON DELETE SET NULL` (recommended), prune-script `WHERE NOT EXISTS`
clause, or ON DELETE CASCADE.

**Operator decision at 5.11 0 dispatch time:** include the prune-fix
in 5.11 scope (sidebar lane), OR keep deferred to Phase 6 / separate
sidecar. **Default recommendation: defer to a separate sidecar
dispatch** unless operator wants to cover it opportunistically. This
is the LAST 5.x lane; if the parks-rec fix is going to land before
Phase 6 V1 acceptance, 5.11 may be the cleanest place.

---

## 5 Daily / weekly rhythm (brief 5)

Similar cadence to 5.5/5.6/5.7/5.8/5.9/5.10 but smaller scope:

| Day | Work |
|---|---|
| 1 | (Conditional) Sustainability-layer commit (Option A -- 3 `_PRIMARY_TYPE_MAP` entries + 1 `(None, "pets") -> "pets"` fallback) BEFORE Layer 1 -- only if 1 dry-run reveals unmapped rows are imminent OR if 1 actual load surfaces them; then Google scrape run + scrape log (`docs/scrape_logs/pets_<YYYY-MM-DD>.md`) -- no Narrow-scope wrapper needed |
| 2 | Ambiguous-queue triage + data-quality audit (cross-category review per 2; minimal cross-cat overlap expected -- primary cat-5 HWC vet axis) |
| 3 | Verifier surface -- Option C deferral confirmed in 3; document V1.5 paths |
| 3-4 | `crowd_notes` for top-10 + `heat_exposure` sweep (indoor default + OUTDOOR_OVERRIDES for pet boarding outdoor runs) |
| 4 | Optional: `parks-rec-scrapes` prune-fix sidebar (4.5) if Decision 4 included in 5.11 scope |
| 5 | Optional Layer 5 manual recovery (mobile groomers, independent dog walkers) |
| 6 | QA spot-check -- 10 random entries vs. the 4 rubric |

**Expected Phase 5.11 total: 3-6 hours over 1 week.** Lighter than
5.10's 5-9h because (a) smaller scope (4 labels vs 5), (b)
single-domain (no bundle complexity), (c) fewer cross-cat axes
(mainly cat-5 HWC for vet overlap), (d) lower review density (pet
services are a smaller market than lodging in LHC).

---

## 6 Acceptance gate -- Phase 5.11 closes when ALL of:

- [ ] **20+ entries** in `pets` post-load
      (modest target -- LHC pet-service density is moderate-low;
      realistic 15-30 net-new from Layer 1 + 0-10 pre-existing). Gate-1
      query MUST use the `(e.entity_type != 'commercial' OR
      provider-visible)` shape from
      `outputs/phase5_2_gate_verification.py` /
      `outputs/phase5_7_gate_verification.py` /
      `outputs/phase5_8_gate_verification.py` /
      `outputs/phase5_9_gate_verification.py` /
      `outputs/phase5_10_gate_verification.py` to correctly count
      `place`-typed entries (though for cat-11 all entries are
      expected to be `commercial`).
- [ ] All Google <-> existing-entity ambiguous reconciler hits
      reviewed (with cross-category review per 2 -- especially the
      cat-5 HWC primary axis for vet overlap).
- [ ] **Layer-4 verifier surface scoped -- Option C explicitly
      deferred to V1.5** (per 3). AZ State Vet Board + national
      pet-franchise locator paths documented in this kickoff 3 for
      V1.5 pickup.
- [ ] Top-10 by review count have long-form `crowd_notes`.
- [ ] `heat_exposure` set on every entry (`indoor` for most;
      `outdoor` overrides expected 2-5 for pet boarding with
      outdoor runs).
- [ ] Phase 6 `/category/pets` renders **>=15** per default filter.

**Note: 6 gate items (not 7).** `is_mobile_service` is dropped by
default (venue-based scope). Operator may opt to re-add as a 7th
gate item if many mobile-service entries surface (mirror 5.5 HPS
pattern -- unlikely for 5.11).

When the gate is met: commit the scrape log, Phase 5.11 gets its
SHIPPED ledger line on `master_build_plan.md` 4 (coordinate with
Phase 6 lane via the now-6-deep amend backlog at
`outputs/claude_code_dispatch_phase6_amend5_to_8.md` -- operator may
want to extend this consolidated dispatch to amend5-11), and **V1
acceptance gate (Phase 6) becomes the next major milestone** -- 5.11
is the LAST 5.x sub-phase. No 5.12 follows.

---

## 7 Reference

- `outputs/phase5_10_session_closeout.md` (the just-shipped 5.10
  state index -- carries the apply-script + audit + sustainability
  layer playbooks 5.11 reuses, especially the 2 in-session COUNT
  bug FIX via `select(func.count())` + `session.flush()`)
- `outputs/phase5_10_lodging_vacation_rentals_kickoff.md` (the 5.10
  runbook this document mirrors)
- `outputs/phase5_2_gate_verification.py` (gate template for
  `entity_type='place'` query shape -- though for 5.11 all entries
  are expected commercial, the OR-clause shape is still required for
  the route-render match)
- `outputs/phase5_10_gate_verification.py` (template for the
  equivalent 5.11 gate-verification script -- note: 6 items not 7;
  no `is_mobile_service` check; threshold >=20)
- `outputs/phase5_10_lodging_audit.md` (combined pre+post audit
  template for the equivalent 5.11 audit doc)
- `docs/scrape_logs/lodging-vacation-rentals_2026-05-17.md` (template
  for the equivalent 5.11 scrape log -- author by hand at session
  start if absent)
- `app/contrib/google_types_mapping.py` (pets types -- already has
  `veterinary_care` + `pet_store` direct mappings; extend per 1
  Option A if needed; current state carries 5.10's 5 cat-10 direct
  mappings + 5.9's 9 cat-12 direct mappings + 5.8's 7 events + 5.7's
  golf_course + medical_clinic widenings)
- `app/contrib/google_places_scraper.py:88`
  (`DISCOVERY_CATEGORY_TO_DOMAINS["pets"]` -- the source of the
  single-domain `pets` mapping; clean and simple)
- `scripts/places_load.py` (`_resolve_category_id` sustainability
  layer; 5.11 Option A may add direct `_PRIMARY_TYPE_MAP` entries +
  new `(None, "pets")` catch-all -- same shape as `bf24e16` did for
  5.10 lodging)
- `outputs/diagnose_category_id_gap.py` (re-usable diagnostic)
- `outputs/apply_phase5_10_lodging_audit.py` (5.10 audit apply
  template -- 5.11's NEW creates surface)
- `outputs/apply_phase5_10_lodging_heat_exposure.py` (5.10 heat sweep
  template -- for 5.11 default stays `indoor`; populate
  `OUTDOOR_OVERRIDES` for the 2-5 expected outdoor pet-boarding
  entries)
- `outputs/apply_phase5_10_lodging_crowd_notes.py` (5.10 crowd_notes
  template -- pass dict directly to JSON column per 5.3 `f35d5e4`
  gotcha; ASCII-only print stdout per 5.9 cp1252-codec lesson)
- `outputs/phase5_10_ambig_audit_dump.py` (5.10 ambig audit dump
  script -- direct copy with paths/slug swap for 5.11;
  single-domain filter for `pets`)
- `outputs/phase5_10_top10_discovery.py` (5.10 top-10 discovery
  helper for crowd_notes drafting -- direct copy with slug swap)
- `outputs/phase5_10_dupe_check.py` (5.10 dupe-check template --
  direct copy with name-list swap for 5.11's vet-overlap +
  pet-store baseline DB-verify pattern)

---

## 8 Hand-off context from the Phase 5.10 session

**Important context that's NOT in this kickoff but the new agent
should read in the 5.10 close-out:**

- 3-commit Phase 5.10 lane chain `d597ef9 -> 592ee74` (`bf24e16`
  sustainability + `592ee74` SHIP), plus `accc06d` SHA-cleanup.
  Plus 4 DB-only writes (1 load + 1 1.7c re-run + 1 audit apply + 1
  heat + 1 crowd_notes).
- **5.10 0 4-file shape check** -- `places_categories.json` +
  `places_load.py` + `models.py` + `google_types_mapping.py` was
  empty Windows-side at 0; 7th-recurrence forecast did NOT
  materialize. Continue the 4-file check in 5.11 0.
- **5.3 `f35d5e4` JSON-column gotcha was avoided in 5.4-5.10** by
  passing dict directly to `Entity.crowd_notes` -- no
  `json.dumps()`. Internalize.
- **5.3 `bff4a79` F401 + 5.7 `5f8fe08` F541 + 5.8 inline-import I001
  + 5.9 cp1252-codec footguns:** `# noqa: E402` silences E402 only.
  F401 (unused imports), F541 (`f"..."` with no placeholders), I001
  (un-sorted imports, including inline `from x import y` blocks
  inside functions), AND PowerShell cp1252 encoding all still
  fail / cause issues. 5.10 stayed clean throughout
  (all ~10 new script artifacts pure-ASCII via the cp1252
  discipline). Continue ASCII-only stdout in 5.11.
- **Sandbox bash git-index gotchas** -- use `git rev-parse` / `git
  show HEAD:` for index-free reads. Operator runs index-dependent
  ops (incl. `git restore`) Windows-side via PowerShell.
- **Sandbox bash MOUNT-STALENESS gotcha** (recurring since 5.5; 5.6
  hit it twice; 5.7 hit it three times; 5.8 hit it twice; 5.9 hit
  it at 0 first git diff; **5.10 hit it once at post-sustainability-
  edit compile-check**). The Read tool is authoritative; sandbox
  bash file-shape queries + `git diff` are unreliable for any
  working-tree state query. Use Windows-side `python` + `git status`
  / `git diff` for all such queries.
- **PowerShell `\"` escape footgun (5.7-discovered, 5.8/5.9/5.10-avoided):**
  Use single-quoted `-m '...'` flags for git commit messages when
  the body contains `"` or `/` characters; PS single quotes are
  literal (no interpolation, no escaping). 5.10 used this discipline
  throughout.
- **5.9 + 5.10 lesson -- DB-verify the "existing entity in cat-X"
  premise BEFORE finalizing audit doc.** 5.10 2 caught it
  prospectively via `outputs/phase5_10_dupe_check.py` -- 3 forecast
  Slice D waterfront-resort DUAL candidates (Lakeside Inn + 2 Havasu
  Dunes Resort entries) all confirmed inland coordinates; revised
  Slice D from 2-5 forecast to 0. **For 5.11:** author
  `outputs/phase5_11_dupe_check.py` EARLY in 2 audit, before
  finalizing the audit doc. Verify vet clinic cat-5 placements + any
  pre-existing cat-11 pet store baseline.
- **5.10 dual-place_id observations** (HEAT Bar <-> Heat Hotel +
  Havasu Dunes Resort <-> GetAways at Havasu Dunes Resort) -- watch
  for similar Google Places dual-listings in 5.11 (e.g., a vet
  clinic with a separate place_id for its grooming arm).
- **DB-write apply-scripts:** stop the FastAPI dev server if running
  (events.db lock).
- **`Provider.google_review_snippets` is its OWN COLUMN** -- not
  inside `attributes` JSON. Drafts for top-10 long-form `crowd_notes`
  source from this column. 5.10's top-10 had 100% snippet coverage
  (5 snippets each); 5.11 forecast 70-90% (pet-service review density
  is moderate -- chains abundant, independents lower).
- **CI can be flaky on intermediate commits** -- 5.5 / 5.7-session-1
  / 5.8 all saw the same pattern (one green + one X on the same
  commit ID, short elapsed time = runner-orchestration flake not
  code). 5.9 + 5.10 didn't hit it. Try `gh run rerun <ID>` before
  shipping a fix commit. Final tree-state CI green is the
  ship-readiness signal.
- **`_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a domain-wide
  catch-all** at `places_load.py:368-371`. 5.10 added
  `(None, "lodging") -> "lodging-vacation-rentals"` as NEW at
  `bf24e16`. 5.11 1 Option A may add `(None, "pets") -> "pets"` as
  NEW if 1 load surfaces unmapped pets primary_types.
- **5.10 2 Slice plan was 6 NEW creates + 31 KEEP-ambig + 0 FLIP/DUAL**
  (no waterfront-resort DUAL materialized; HEAT Bar kept in cat-1).
  5.11 forecast: 3-8 NEW creates + small KEEP-ambig pool + 0 FLIP/DUAL
  unless a vet-clinic-with-grooming case emerges.
- **5.10 in-session reporting bug FIX (carried from 5.9):** apply-
  script uses `select(func.count())` + `session.flush()` before COUNT
  -- accurate post-apply count reported. Mirror in 5.11 apply-script.

**Carry-forwards from the 5.10 session** the new agent should action:

- **Phase 6 lane -- consolidated amend5-X dispatch** --
  `outputs/claude_code_dispatch_phase6_amend5_to_8.md` ready for
  Claude Code parallel agent. Lands Phase 5.5/5.6/5.7/5.8 SHIPPED
  ledger lines. **Operator may want to extend to amend5-10 (adding
  5.9 + 5.10 SHIPPED) OR amend5-11 (adding all three)** before
  dispatching. **5.11 SHIP is the cleanest cut-off** since it's the
  last 5.x lane.
- **`parks-rec-scrapes` prune-fix sidecar** -- root cause + 3 fix
  options in 5.7 close-out 3. Optional inclusion at 4.5; default
  defer to separate sidecar dispatch. **5.11 may be the cleanest
  lane to land this** since it's the last 5.x.
- **V1.5 Layer-4 verifier surface for 5.10** -- AZDOR transient-
  lodging tax + AZRE vacation-rental license + LHC Tourism Board
  paths documented in `phase5_10_lodging_audit.md` 9 + kickoff 3.
- **V1.5 HEAT Bar / Heat Hotel + Havasu Dunes / GetAways dual-
  place_id consolidations** -- same-building Google dual-listings
  documented in 5.10 audit 9.
- **V1.5 Havasu Suites / Xanadu identity verification** -- 5.10 2
  ambig pool entries uncertain (travel_agency primary + point_of_
  interest primary respectively); deferred.
- **V1.5 5 waterfront-suggestive RV/campground name candidates** for
  water_adjacent override review (Sam's Beachcomber RV Resort,
  Anchor Lake House, Campbell Cove RV Resort, Islander Resort,
  Havasu Falls RV Resort).
- **V1.5 sustainability layer extensions** -- consider `camping_cabin`
  / `cottage` / `mobile_home_park` / `guest_house` direct mappings
  per 5.10 audit 9.
- **86 of 265 HWC providers remain `verified=False`** -- carry-over
  from 5.4. Operator-driven DBA->NPI follow-up surface (optional
  V1.5).
- **Operator: prune `data/events.db.bak-*` files** when comfortable
  -- carry-over from 5.3 + 5.4 + 5.5 + 5.6 + 5.7 + 5.8 + 5.9 + 5.10.
- **Google Places API key rotation** -- deferred per operator ("all
  keys will be changed at conclusion of this project").

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.10 session 1
(2026-05-17) post-`592ee74` SHIP + `accc06d` SHA-cleanup, pre-0
hand-off artifact. Commit inline before 0 pre-flight dispatches.
Cowork primary picks up at 0 pre-flight after reading
`outputs/phase5_10_session_closeout.md` first and
`outputs/phase5_11_next_agent_boot_prompt.md` second.*
