# Phase 5.10 Kickoff — Lodging & Vacation Rentals (`lodging-vacation-rentals`)

> **What this is:** a single paste-and-go operator runbook for Phase 5.10,
> the tenth Tier 1 category. Mirrors
> `outputs/phase5_9_classes_sports_recreation_kickoff.md` shape with
> 5.10-specific overrides. **Single-layer scrape** (Google only — OSM
> scope is locked to on-the-water per brief §3.2.e) over a Narrow-scope
> subset of the combined `lodging` + `lake_recreation` domain bundle (5
> in-scope labels of 16 total; the 11 lake_recreation labels deferred
> to V1.5 because 5.2 absorbed them under on-the-water).
>
> **GATE 1 — Phase 5.9 SHIPPED** at `4527ca1` (2026-05-17) with all 6
> gate items cleared, plus SHA-cleanup at `bc08bf6`. ✅ Met.
>
> **GATE 2 — no pre-built verifier surface for 5.10.** There is no
> consolidated public registry for lodging the way AZ ROC covers
> contractors or NPI covers medical providers. Three narrow paths
> exist (AZ DOR transient-lodging tax registry; AZ Dept of Real Estate
> vacation-rental license registry; LHC Tourism Board lodging
> directory at golakehavasu.com) but none cover the full V1 surface,
> all are scraping-shape not API-shape, and the V1 utility of a
> "verified via AZDOR" badge for a hotel is low. **This kickoff
> resolves §3 as Option C** (defer Layer-4 verifier surface to V1.5;
> document the three paths). Mirrors 5.5 + 5.6 + 5.7 + 5.8 + 5.9
> outcome.
>
> **GATE 3 — pre-flight integrity gotcha (now SEVENTH+ recurrence
> watch):** `scripts/places_categories.json` has drifted locally on
> sessions 5.5 / 5.6 / 5.7-boot / 5.7-session-2-pre-flight. The
> 5.7 / 5.8 / 5.9 sessions found the four-file shape check
> (places_categories.json + places_load.py + models.py +
> google_types_mapping.py) clean at §0. The 5th + 6th + 7th
> recurrence forecasts did NOT materialize but the pattern remains
> watch-worthy. Pre-flight item #6 below is the same four-file check.
>
> **🚨 BOOT-PROMPT FRAMING CORRECTION:** The Phase 5.10 boot prompt
> at `outputs/phase5_10_next_agent_boot_prompt.md` said both
> lodging-vacation-rentals and pets have "single-domain mappings"
> with "no existing catch-alls that would mis-route" — this was
> WRONG for lodging-vacation-rentals. Per
> `app/contrib/google_places_scraper.py:87`,
> `"lodging-vacation-rentals": frozenset({"lodging", "lake_recreation"})`
> is a **two-domain bundle** (same shape as 5.9's
> classes-sports-recreation). The `lake_recreation` domain has the
> 5.2 `(None, "lake_recreation") → "on-the-water"` catch-all already
> in place at `scripts/places_load.py:216`. This kickoff handles the
> bundle via §1 Narrow scope (5 lodging-domain labels only); RV
> parks + campgrounds defer to V1.5.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.9 session 1
> (2026-05-17) post-`4527ca1` SHIP + `bc08bf6` SHA-cleanup, pre-§0
> hand-off artifact. Commit inline before §0 pre-flight dispatches
> per the established cadence.

---

## §0 Pre-flight (do once, at Phase 5.10 dispatch)

1. **`git log --oneline -15`** — origin should top at `<this commit>`
   (Phase 5.10 kickoff doc pre-stage) over `bc08bf6` (5.9 SHA-cleanup)
   over `4527ca1` (5.9 SHIP) over `a99e2c4` (5.9 wrapper-bundle) over
   `0af5f73` (5.9 sustainability) over `4856020` (5.9 kickoff
   pre-stage) or later if Phase 6 lane has shipped the consolidated
   amend5-8 dispatch between sessions. The 5.9 lane chain since
   5.8's `209e99f` SHA-cleanup:
   `4856020 → 0af5f73 → a99e2c4 → 4527ca1 → bc08bf6`.
2. **`git status`** — clean. **Sandbox bash note:** `git status` hits
   the index-format gotcha (`fatal: unknown index entry format
   0xffff0000`); run Windows-side via PowerShell. Carry-over untracked
   from 5.9: `hava_api_catalog.docx` + `~$va_api_catalog.docx` Word
   lock + 2 historical `outputs/ci_*_log_failed.txt` files +
   `outputs/_deltest` — all unrelated to lane; operator prunes when
   comfortable.
3. **`python -m alembic current`** — confirm local `data/events.db` at
   `0a1b2c3d4e5f`. If behind, `python -m alembic upgrade head`. (No
   migrations expected on the 5.10 lane unless the parks-rec-scrapes
   prune-fix sidecar lands — that would add an `ON DELETE SET NULL`
   migration on `contributions.created_event_id`.)
4. **`python -m pytest -q --collect-only 2>&1 | Select-Object -Last 3`**
   — record baseline. Phase 5.9 closed at **1985 collected** (5.8
   baseline 1964 + 21 in-lane regression guards for the `0af5f73`
   `_PRIMARY_TYPE_MAP` extension for the 9 cat-12 primary types).
   Verify no drift.
5. **`python outputs/diagnose_category_id_gap.py`** — confirm Phases
   5.1-5.9 categorization is intact and the `lodging-vacation-rentals`
   slug exists in the `categories` table (id=10 per the diagnose
   script output).
6. **🚨 WIDENED four-file shape check** (carried from 5.7 + 5.8 + 5.9 §0):
   ```powershell
   git diff --stat scripts/places_categories.json scripts/places_load.py app/db/models.py app/contrib/google_types_mapping.py
   ```
   MUST be empty Windows-side (sandbox view may lie per the
   recurring mount-staleness pattern). If ANY of the four shows
   deletions in the working tree, restore via `git restore .`
   Windows-side before §1. The expected HEAD line counts post-`bc08bf6`
   (sanity reference, not validation targets — content over shape):
   - `scripts/places_categories.json`: 212 lines
   - `scripts/places_load.py`: 679+ lines (carries 5.9 `0af5f73`
     childcare_education catch-all)
   - `app/db/models.py`: 1539+ lines
   - `app/contrib/google_types_mapping.py`: 253+ lines (carries 5.9's
     9 cat-12 direct mappings + 5.8's 7 events + 5.7's golf_course +
     medical_clinic widenings)
7. **Google Places key + spend cap** — operator has deferred rotation
   until project end; still in `.env`, still capped. No mid-session
   rotation needed unless the operator opts in.
8. **CI state** — check GitHub Actions on the top commit. Should be
   ✅ green on `bc08bf6` (the 5.9 SHA-cleanup commit, docs-only) and
   `4527ca1` (the 5.9 SHIP commit). If red, investigate before
   starting 5.10. The `parks-rec-scrapes` scheduled cron has been ❌
   since 5.3 — root cause identified at 5.7 §4.5 sidebar; **NOT in
   5.10 scope** unless operator opts to dispatch the parks-rec-prune
   sidecar fix as part of this lane.
9. **DB state spot-check** — `classes-sports-recreation` should show
   **31 entries / 0 verified / 29 indoor + 2 outdoor / 31 render /
   10 long-form crowd_notes** (the 5.9 SHIPPED state). `events`
   should still show **20/0/17+3/20/10** (5.8 SHIPPED state,
   unchanged). `lodging-vacation-rentals` should show **0-5 entries
   pre-load** (the cat-10 slug exists; 5.2-era loads via `rv_park` /
   `lodging` direct mappings may have absorbed a small number of
   entities — operator can verify via `python outputs/phase5_10_db_
   spot_check.py` once authored).

---

## §1 The scrape sequence — Google only, NARROW scope

Phase 5.10 is **single-layer** (no OSM dispatch — OSM scope is locked
to on-the-water per brief §3.2.e). **Scope is intentionally narrowed**
from the literal 16-label `lodging-vacation-rentals` bundle in
`DISCOVERY_CATEGORY_TO_DOMAINS` because of one structural collision:

1. **`lake_recreation` collision with Phase 5.2 (on-the-water).** The
   `lake_recreation` domain has 11 labels (20 if counting all
   marina/boat sub-labels). Phase 5.2 absorbed marinas / boat dealers /
   boat rentals / etc. into cat-3 on-the-water; the 5.2 `(None,
   "lake_recreation") → "on-the-water"` catch-all (at
   `scripts/places_load._DISCOVERY_DOMAIN_FALLBACK:216`) routes
   unmapped lake_recreation primary_types to cat-3. The lodging-shape
   labels in lake_recreation (RV parks / RV rentals / RV dealers /
   RV repair / campgrounds) are split:
   - `rv_park` → cat-10 via direct mapping (pre-Phase-5)
   - `rv_repair` → cat-9 auto-rv-fuel via direct mapping (per
     prereq §3.1.b lock — "where-you-stay" vs "auto-RV bundle")
   - `campground` — no direct mapping; would route to cat-3 via
     catch-all
   - RV dealer / RV rental Google primary_types — typically
     `car_dealer` / `car_rental`, which routes via auto domain
     mappings, NOT lake_recreation (so no conflict)
   **Defer the 11 lake_recreation labels to V1.5.** RV parks already
   in cat-10 from 5.2 (via `rv_park` direct map) stay there;
   campgrounds and RV dealers/rentals can be re-evaluated per-label
   in V1.5.

This leaves **5 labels in scope for 5.10 §1:**

| Bucket | Labels (5) | Domain |
|---|---|---|
| **Lodging** | hotels, motels, resorts, vacation rentals, bed and breakfast | lodging |

### Layer 1 — Google Places

```
python outputs/phase5_10_narrow_label_filter.py --dry-run
python outputs/phase5_10_narrow_label_filter.py
python -m scripts.places_enrichment --limit 200
python -m scripts.places_load --category lodging-vacation-rentals --dry-run
python -m scripts.places_load --category lodging-vacation-rentals
```

**Why `--limit 200` on enrichment?** 5 labels × ~10-15 per label
≈ 50-75 raw hits; the cumulative enrichment cache (5.0/5.1/5.2/5.3/
5.4/5.5/5.6/5.7/5.8/5.9) is ~2,644+ records. Most will cache-hit
(LHC lodging entities may overlap with 5.2's on-the-water cache
for waterfront resorts). Expected new enrichments: ~20-50.

⚠️ **The `--category lodging-vacation-rentals` flag will filter
`places_categories.json` by `DISCOVERY_CATEGORY_TO_DOMAINS` which
returns BOTH `lodging` AND `lake_recreation` (two-domain bundle).**
This will pull in all 16 labels by default — including the 11
we want to defer. **Two paths** to honor the Narrow scope (same
shape as 5.7/5.8/5.9 Path A vs Path B decision):

- **Path A (recommended — minimal code change):** Author a one-shot
  filter script `outputs/phase5_10_narrow_label_filter.py` that
  short-circuits the discovery loop to only the 5 in-scope labels.
  Mirrors `outputs/phase5_9_narrow_label_filter.py` shape exactly —
  same Path A.2 pattern (standalone outputs/ wrapper, no production
  code touched). ~30 lines.
- **Path B (broader change):** Temporarily filter the 5 labels at
  the production-code level — riskier; not recommended.

**Default to Path A unless operator picks B.**

### Sustainability layer — TBD per §1 dispatch findings

**Pre-existing direct `_PRIMARY_TYPE_MAP` entries for cat-10:**
- `"lodging": ("lodging-vacation-rentals", "commercial")` — generic catch-all (always-present in lodging-shape types[])
- `"rv_park": ("lodging-vacation-rentals", "commercial")` — RV parks

**Google's actual primary_types for lodging:** `hotel`, `motel`,
`resort_hotel`, `extended_stay_hotel`, `bed_and_breakfast`,
`vacation_rental` (rare), `lodging` (generic — usually appears as a
secondary type in `types[]` for any lodging-shape place).

**Critical resolver behavior** (per
`app/contrib/google_types_mapping.py:201-209`): `map_google_types_to_
slug_and_place_type` iterates the `types[]` array (primary first) and
returns the FIRST match. So even if a hotel's primary_type is `hotel`
(not in `_PRIMARY_TYPE_MAP`), the secondary type `lodging` (almost
always present) catches it via the existing direct mapping.

**Forecast:** the existing `lodging` direct mapping may catch every
5.10 entry via the secondary `types[]` match — sustainability work
could be ZERO. **Decision deferred:** check §1 load output for
`category_id unmapped (operator queue)`. If 0, no sustainability
commit needed. If non-zero, author sustainability commit per Option
A pattern below.

**Three options if sustainability IS needed** (operator picks at §1
dispatch time; recommended default is **Option A**):

**(A — recommended) Add direct `_PRIMARY_TYPE_MAP` entries** for
the expected lodging primary_types. Example shape (`app/contrib/
google_types_mapping.py` `_PRIMARY_TYPE_MAP`):

```python
# lodging-vacation-rentals (cat-10) primary types — 5.10 §1
# sustainability extension if §1 load surfaces unmapped rows.
"hotel": ("lodging-vacation-rentals", "commercial"),
"motel": ("lodging-vacation-rentals", "commercial"),
"resort_hotel": ("lodging-vacation-rentals", "commercial"),
"extended_stay_hotel": ("lodging-vacation-rentals", "commercial"),
"bed_and_breakfast": ("lodging-vacation-rentals", "commercial"),
```

Plus a safety-net catch-all:
```python
# scripts/places_load._DISCOVERY_DOMAIN_FALLBACK
(None, "lodging"): "lodging-vacation-rentals",
```

The new `(None, "lodging")` catch-all is NEW (no prior phase
populated this domain). It covers any unmapped lodging primary_types
Google emits.

**(B) Catch-all only** — just add the `(None, "lodging") →
"lodging-vacation-rentals"` fallback. Simpler but loses the
commercial-vs-place distinction (catch-all defaults entity_type via
`map_google_types_to_slug_and_place_type` which returns None for the
slug branch — operator may need to override entity_type
post-creation).

**(C — hybrid)** — both A + B. Most explicit + future-proof.

**Recommended: Option A.** If sustainability IS needed (forecast: may
not be).

**Sustainability-layer commit shape (if needed):** mirror `0af5f73`
(Phase 5.9 sustainability) — a single focused `fix(scripts)` commit
that adds the 5 `_PRIMARY_TYPE_MAP` entries + 1 catch-all + regression
tests in `tests/test_phase5_10_places_load_resolver.py` (~10
parametrized asserts: 5 for the new primary types + 5 defensive
preservation of prior phases' fallbacks). Land BEFORE the §1 Layer 1
dispatch (sustainability-first pattern from 5.5 / 5.6 / 5.7 / 5.8 /
5.9). **Skip entirely if §1 load shows 0 unmapped.**

### Layer 5 — Manual recovery (deferred to operator)

Per `docs/maintainability/manual_recovery_checklist.md`. Surface for
5.10:

- Airbnb / VRBO short-term rentals not indexed by Google as venues
  (most Airbnb listings only appear as "vacation_rental" type when
  the host has claimed a Google Business Profile — uncommon)
- Boutique/historic B&Bs that operate by reservation only (may have
  no Google listing)
- Houseboat rentals (5.2 lane absorbed houseboat dealers under
  on-the-water; the actual rental-vessel-as-lodging is a niche
  cat-10 carry — defer to V1.5)
- Corporate-housing / extended-stay properties (often unlisted on
  Google Maps)
- HOA private vacation rentals (privacy-protected; not Google-indexed)

Not gate-blocking for V1 ship.

---

## §2 Ambiguous-queue review — moderate volume + cross-category overlap expected

Lodging-vacation-rentals is the **tenth non-empty-DB load** (after
5.1-5.9). Reconciler will match against **~1,266+ existing entities**
(post-5.9: 287 eat-drink + 119 on-the-water + 230 HPS + 265 HWC + 140
auto-rv-fuel + 76 shopping-essentials + 27 outdoors-parks-trails + 20
events + 1 public-civic-resources + 31 classes-sports-recreation +
several pre-existing cat-10 from 5.2 + 86 unverified HWC carry).
Expected ambiguous hits: **20-50 per run** (range covers moderate
label coverage offset by significant cross-cat overlap risk with
cat-1 eat-drink (hotels have restaurants), cat-2 events (resorts
host weddings), cat-3 on-the-water (waterfront resorts)).

**Special audit categories expected for 5.10:**

| Existing entity | 5.10 candidate it'll likely match | V1 policy |
|---|---|---|
| Waterfront resorts on Lake Havasu (e.g., London Bridge Resort) — may already be in cat-3 on-the-water from 5.2 | resorts / hotels (cat-10) | **review** — likely FLIP or DUAL (hotel-with-marina) |
| Restaurants at hotels (cat-1 from 5.1) | hotels with same address (cat-10) | likely **stay in cat-1** if food-primary; cross-link if hotel-restaurant is the marketing draw |
| Event venues at resorts (cat-2 from 5.8) | resorts (cat-10) | **review** — typically the resort is the primary entity; the event venue is sub-amenity |
| RV parks currently in cat-10 (from 5.2 via `rv_park` direct map) | (no new 5.10 label maps directly — defer to V1.5) | KEEP cat-10 (already correctly placed) |
| Houseboat rentals (cat-3 on-the-water from 5.2) | vacation rentals (cat-10) — if rental-vessel-as-lodging | V1.5 dual-cat consideration |

**Cross-cat sweep with cat-3 (Phase 5.2) — primary 5.10 audit focus:**

5.2's `(None, "lake_recreation") → "on-the-water"` catch-all swept
waterfront entities into cat-3. Most LHC resorts on the lake (London
Bridge Resort, Havasu Springs, Nautical Beachfront Resort, Heat Hotel)
are likely already in cat-3. The 5.10 §1 scrape may re-discover them
under the lodging domain → primary_type=`lodging` → resolver →
cat-10 → preserve-existing-cat keeps them at cat-3.

**5.10 §2 audit decisions for waterfront resorts:**
- **Option A:** FLIP cat-3 → cat-10 (lodging primary identity)
- **Option B:** DUAL cat-3 + cat-10 (waterfront resort = both lake
  property AND lodging)
- **Option C:** KEEP cat-3 (lake-access is the primary draw)

**Recommended V1 policy: DUAL cat-3 + cat-10** for waterfront resorts.
Lake access IS the primary draw for tourists visiting LHC, but the
property IS a hotel. Dual-cat lets both `/category/on-the-water` and
`/category/lodging-vacation-rentals` surfaces serve the user. Mirror
5.9 Slice D pattern (Our Lady of the Lake Catholic School DUAL cat-12
+ cat-13).

Mirror the 5.9 audit pattern: post-load audit pulls cross-category +
same-category; an apply-script batches the misroute decisions if
any. **Expected outcome based on 5.4/5.5/5.6/5.7/5.8/5.9 history:
0 real misroutes** in the cross-cat ambig pool (benign geo-proximity
false positives), plus 2-5 DUAL-cat adds for waterfront resorts +
possibly 1-2 NEW creates for hotels not yet in DB.

If a single load produces **>50** ambiguous hits, consider tuning
`GEO_PROXIMITY_THRESHOLD_M` (currently `50.0`) per brief §4.g — but
prior phases have all stayed under the tune threshold despite
exceeding 50.

### Cross-category sweep — `_DISCOVERY_DOMAIN_FALLBACK` catch-all behavior

Per 5.6 + 5.7 + 5.8 + 5.9 close-outs: the `(None, "<domain>")`
catch-all routes ALL unmapped primary_types under that domain. 5.2's
`(None, "lake_recreation") → "on-the-water"` stays in place; 5.10's
Option A direct mappings (if shipped) beat it for the 5 cat-10-native
lodging primary_types. The new `(None, "lodging") → "lodging-vacation-
rentals"` catch-all (if shipped) covers any unmapped lodging
primary_types.

Apply-script `outputs/apply_phase5_10_lodging_audit.py` if any
DUAL-cat or FLIPs needed. Expected size: ~10-30 rows reviewed, likely
2-5 DUAL-cat adds for waterfront resorts + 0-3 NEW creates (mirroring
5.9 §2 Slice D + E pattern).

### DB-VERIFY discipline (5.8 + 5.9 lesson)

Author `outputs/phase5_10_dupe_check.py` EARLY in §2 audit (before
finalizing the audit doc) to verify all cross-cat move premises:
- Which waterfront resorts ARE in cat-3 currently? (informs DUAL
  candidate list)
- Which 5.10 candidates have geo-co-located cat-1 restaurants?
  (informs cross-link decisions)
- Are there RV park entities in cat-10 from 5.2? (informs gate-1
  baseline)
- Hotels with same name but different place_ids? (5.8 + 5.9 lesson —
  could be franchise locations like Holiday Inn Express vs Holiday
  Inn Express & Suites — distinct entities)

The 5.8 Slice B-1 lesson and 5.9 Aquatic Center reframe both
underscore: assume nothing about existing DB state until verified.

---

## §3 Layer-4 verifier surface — Option C resolved (deferred to V1.5)

**5.10 has no pre-built verifier** (unlike 5.3's `az_roc_verify` and
5.4's `npi_verify`). Three narrow options exist; this kickoff
resolves §3 as **Option C** per the structural reasoning in the
header. The other two paths are documented here for V1.5 pickup.

### Option A — AZ Dept of Revenue transient lodging tax registry (DEFERRED to V1.5)

URL: `https://azdor.gov/transaction-privilege-tax-tpt` — AZDOR
collects TPT (transient lodging tax) on hotels / motels / B&Bs /
short-term rentals. License lookup is via search form
(scraping-shape). Coverage of LHC: high for hotels + motels +
licensed B&Bs; lower for vacation rentals (many are unlicensed or
operate under HOA-only rules).

Coverage: ~70-90% of cat-10 hotel/motel/B&B candidates; ~30-50% of
vacation rentals. Sets `Provider.verified=True`,
`verification_method='azdor_tpt'`, `attributes.azdor={...license_no,
expires}`.

**Cost-of-build:** ~4-6 hours (Playwright scrape of the AZDOR
search form). **Coverage is good for hotels/motels but vacation
rental coverage is fragmented.**

### Option B — AZ Dept of Real Estate vacation-rental license registry (DEFERRED to V1.5)

URL: `https://azre.gov/PropertyManagement` — AZRE licenses property
managers handling vacation rentals + short-term lets. Covers managed
properties; misses owner-operated rentals. ~3-5 hours build.
Coverage too narrow for V1.

### Option C — Defer verifier surface to V1.5 ✅ SELECTED

Gate item 3 rephrased to **"Layer-4 verifier surface scoped — built
or explicitly deferred to V1.5"**. Document AZDOR + AZRE + LHC
Tourism Board paths in this kickoff and ship 5.10 without verifier
surface. Lowest-friction shape; mirrors 5.5 + 5.6 + 5.7 + 5.8 + 5.9
outcome.

**Rationale:** lodging verification has low V1 utility (consumer
discovery doesn't need an "AZDOR-verified" badge on a Holiday Inn;
chain trust comes from the brand); the available paths are all
scraping-shape not API-shape; coverage is fragmented across multiple
surfaces. Better to defer the whole verifier surface to V1.5 when
the right shape can be designed against fuller scope.

---

## §4 Operator-curated field entry — Lodging rubric

Lighter operator surface than 5.4 (no NPI verification) + 5.6 (no
brand-name normalization); on par with 5.7/5.8/5.9 shape but with a
**mixed heat_exposure default** (vs 5.6's `indoor` and 5.7's
`outdoor`):

- **`heat_exposure`** — **`indoor` for most 5.10 entries** (hotels,
  motels, B&Bs, vacation rental units are all indoor-by-definition).
  **`outdoor` overrides** expected for: resort properties with
  outdoor pool / spa / beach access as the primary draw (London
  Bridge Resort, Nautical Beachfront Resort, Heat Hotel, Havasu
  Springs). **`water_adjacent` overrides** expected for: any
  waterfront-facing resort/lodging. Mirror
  `outputs/apply_phase5_8_events_heat_exposure.py` shape: default
  `indoor` + populate `OUTDOOR_OVERRIDES` + `WATER_ADJACENT_OVERRIDES`
  lists. Expected override count: **3-8** (mix of outdoor + water_
  adjacent for resort properties + lake_adjacent lodging).
- **`crowd_notes`** — short-form for typical entries; long-form for
  the top-10 by review count. Lodging reviewer signals tend to be:
  staff helpfulness, room cleanliness, view, location relative to
  attractions, amenities (pool / spa / restaurant / parking / free
  breakfast), boat slip access (for waterfront), value for price,
  noise level, family-friendliness, business-traveler suitability.

Drafts source: **`Provider.google_review_snippets` (own column, not
`attributes`)** — per the 5.4 close-out §4 source-path correction.
Expected snippet coverage: **~85-95%** (lodging review density is
high — hotels especially have abundant reviews; B&Bs less so).

**`is_mobile_service`** is NOT a gate item for 5.10 by default —
cat-10 is venue-based. Skip the `is_mobile_service` apply-script for
5.10.

**`attributes`** JSON — can be extended with cat-10-specific keys:
`pool` (bool), `pool_heated` (bool), `outdoor_pool` (bool), `boat_
slip` (bool), `room_count` (int), `pet_friendly` (bool), `breakfast_
included` (bool), `wifi_free` (bool), `parking_free` (bool),
`waterfront` (bool). Brief §3.4 has the suggestion shape. **Note: if
waterfront/lake-access is a primary draw, consider the boat_access
JSON shape from 5.2 instead** (`docs/operations/boat_access_rubric.md`)
— for waterfront resort properties with their own marinas/docks.

### §4.5 sidebar — `parks-rec-scrapes` prune-fix dispatch (optional)

The scheduled `parks-rec-scrapes` GitHub Actions workflow has been
❌ on cron triggers since at least Phase 5.3. Root cause identified
in Phase 5.7 §4.5 sidebar: Postgres FK constraint violation in
`scripts/parks_rec_prune.py`. **3 fix options** surfaced in
`outputs/phase5_7_session_closeout.md` §3 — alembic migration
adding `ON DELETE SET NULL` (recommended), prune-script `WHERE NOT
EXISTS` clause, or ON DELETE CASCADE.

**Operator decision at 5.10 §0 dispatch time:** include the prune-fix
in 5.10 scope (sidebar lane), OR keep deferred to Phase 6 / separate
sidecar. **Default recommendation: defer to a separate sidecar
dispatch** unless operator wants to cover it opportunistically.

---

## §5 Daily / weekly rhythm (brief §5)

Similar cadence to 5.5/5.6/5.7/5.8/5.9 but possibly without a
sustainability PIVOT pre-flight step (TBD based on §1 load):

| Day | Work |
|---|---|
| 1 | (Conditional) Sustainability-layer commit (Option A — 5 `_PRIMARY_TYPE_MAP` entries + 1 `(None, "lodging") → "lodging-vacation-rentals"` fallback) BEFORE Layer 1 — only if §1 load reveals unmapped rows; then Google scrape run + scrape log (`docs/scrape_logs/lodging-vacation-rentals_<YYYY-MM-DD>.md`) + Narrow-scope filter script (Path A) |
| 2 | Ambiguous-queue triage + data-quality audit (cross-category review per §2; primary axis cat-3 on-the-water for waterfront resorts; DB-verify via early dupe-check) |
| 3 | Verifier surface — Option C deferral confirmed in §3; document V1.5 paths |
| 3-4 | `crowd_notes` for top-10 + `heat_exposure` sweep (indoor default + OUTDOOR_OVERRIDES + WATER_ADJACENT_OVERRIDES for waterfront resorts) |
| 4 | Optional: `parks-rec-scrapes` prune-fix sidebar (§4.5) if Decision 4 included in 5.10 scope |
| 5 | Optional Layer 5 manual recovery (boutique B&Bs, Airbnb hosts with claimed Business Profiles, houseboat rentals) |
| 6 | QA spot-check — 10 random entries vs. the §4 rubric |

**Expected Phase 5.10 total: 5-9 hours over 1 week.** Lighter than
5.9's 7-12h because (a) smaller scope (5 labels vs 9), (b) possibly
no sustainability PIVOT, and (c) fewer cross-cat axes (mainly cat-3).

---

## §6 Acceptance gate — Phase 5.10 closes when ALL of:

- [ ] **20+ entries** in `lodging-vacation-rentals` post-load
      (modest target — LHC lodging density is high given tourism
      focus; realistic 25-50 net-new from Layer 1 + 0-5 pre-existing).
      Gate-1 query MUST use the
      `(e.entity_type != 'commercial' OR provider-visible)` shape
      from `outputs/phase5_2_gate_verification.py` /
      `outputs/phase5_7_gate_verification.py` /
      `outputs/phase5_8_gate_verification.py` /
      `outputs/phase5_9_gate_verification.py` to correctly count
      `place`-typed entries (though for cat-10 all entries are
      expected to be `commercial`).
- [ ] All Google ↔ existing-entity ambiguous reconciler hits
      reviewed (with cross-category review per §2 — especially the
      cat-3 on-the-water primary axis for waterfront resorts + the
      cat-1 eat-drink secondary axis for hotel restaurants + the
      cat-2 events tertiary axis for resort event venues).
- [ ] **Layer-4 verifier surface scoped — Option C explicitly
      deferred to V1.5** (per §3). AZDOR + AZRE + LHC Tourism Board
      paths documented in this kickoff §3 for V1.5 pickup.
- [ ] Top-10 by review count have long-form `crowd_notes`.
- [ ] `heat_exposure` set on every entry (`indoor` for most;
      `outdoor` + `water_adjacent` for resort properties — expected
      override count 3-8).
- [ ] Phase 6 `/category/lodging-vacation-rentals` renders **≥15**
      per default filter.

**Note: 6 gate items (not 7).** `is_mobile_service` is dropped by
default (venue-based scope).

When the gate is met: commit the scrape log, Phase 5.10 gets its
SHIPPED ledger line on `master_build_plan.md` §4 (coordinate with
Phase 6 lane via the now-5-deep amend backlog at
`outputs/claude_code_dispatch_phase6_amend5_to_8.md` — operator may
want to extend this consolidated dispatch to amend5-10 OR ship as
amend5-8 first then a separate amend9-10), and **Phase 5.11 (likely
`pets` — the last remaining 5.x slug)** dispatches next.

---

## §7 Reference

- `outputs/phase5_9_session_closeout.md` (the just-shipped 5.9 state
  index — carries the apply-script + audit + sustainability layer
  playbooks 5.10 reuses, especially the §2 DUAL-cat pattern from
  5.9 Slice D and the early-dupe-check discipline)
- `outputs/phase5_9_classes_sports_recreation_kickoff.md` (the 5.9
  runbook this document mirrors)
- `outputs/phase5_2_gate_verification.py` (gate template for
  `entity_type='place'` query shape — though for 5.10 all entries
  are expected commercial, the OR-clause shape is still required for
  the route-render match)
- `outputs/phase5_9_gate_verification.py` (template for the
  equivalent 5.10 gate-verification script — note: 6 items not 7;
  no `is_mobile_service` check; threshold ≥20)
- `outputs/phase5_9_classes_audit.md` (combined pre+post audit
  template for the equivalent 5.10 audit doc — especially Slice D
  DUAL-cat pattern)
- `docs/scrape_logs/classes-sports-recreation_2026-05-17.md` (template
  for the equivalent 5.10 scrape log — author by hand at session
  start if absent)
- `app/contrib/google_types_mapping.py` (lodging types — already has
  `lodging` + `rv_park` direct mappings; extend per §1 Option A if
  needed; current state carries 5.9's 9 cat-12 direct mappings + 5.8's
  7 events + 5.7's golf_course + medical_clinic widenings)
- `app/contrib/google_places_scraper.py:87`
  (`DISCOVERY_CATEGORY_TO_DOMAINS["lodging-vacation-rentals"]` — the
  source of the `lodging + lake_recreation` two-domain bundle)
- `scripts/places_load.py` (`_resolve_category_id` sustainability
  layer + 5.2 lake_recreation catch-all stays in place; 5.10 Option
  A may add direct `_PRIMARY_TYPE_MAP` entries + new `(None,
  "lodging")` catch-all — same shape as `0af5f73` did for 5.9
  childcare_education)
- `outputs/diagnose_category_id_gap.py` (re-usable diagnostic)
- `outputs/apply_phase5_9_classes_audit.py` (5.9 audit apply template
  — 5.10's likely-substantial Slice D DUAL-cat for waterfront
  resorts + possible Slice E NEW creates; especially the
  `_dual_add_category` function for Slice D pattern)
- `outputs/apply_phase5_9_classes_heat_exposure.py` (5.9 heat sweep
  template — for 5.10 default stays `indoor`; populate
  `OUTDOOR_OVERRIDES` + new `WATER_ADJACENT_OVERRIDES` for waterfront
  resorts)
- `outputs/apply_phase5_9_classes_crowd_notes.py` (5.9 crowd_notes
  template — pass dict directly to JSON column per 5.3 `f35d5e4`
  gotcha, F401/F541/I001-clean imports per 5.3 `bff4a79` + 5.7
  `5f8fe08` + 5.8 inline-import lessons; ASCII-only print stdout
  per 5.9 cp1252-codec lesson)
- `outputs/phase5_9_ambig_audit_dump.py` (5.9 ambig audit dump
  script — direct copy with paths/slug swap for 5.10; two-domain
  filter for `lodging + lake_recreation`)
- `outputs/phase5_9_top10_discovery.py` (5.9 top-10 discovery
  helper for crowd_notes drafting — direct copy with slug swap)
- `outputs/phase5_9_narrow_label_filter.py` (5.9 Path A wrapper —
  template for 5.10's equivalent; two-domain bundle accommodation
  pattern already in place)
- `outputs/phase5_9_dupe_check.py` (5.9 dupe-check template —
  direct copy with name-list swap for 5.10's waterfront resort
  DB-verify pattern)
- `docs/operations/boat_access_rubric.md` (for any waterfront
  resort properties with their own marinas/docks — 5.2 lock)

---

## §8 Hand-off context from the Phase 5.9 session

**Important context that's NOT in this kickoff but the new agent
should read in the 5.9 close-out:**

- 3-commit Phase 5.9 lane chain `4856020 → 4527ca1` (`0af5f73`
  sustainability + `a99e2c4` wrapper-bundle + `4527ca1` SHIP), plus
  `bc08bf6` SHA-cleanup. Plus 4 DB-only writes (1 load + 1 audit
  apply + 1 heat + 1 crowd_notes).
- **5.9 §0 4-file shape check** — `places_categories.json` +
  `places_load.py` + `models.py` + `google_types_mapping.py` was
  empty Windows-side at §0 (sandbox bash was stale and showed
  spurious deletions — confirmed mount-staleness pattern). 7th-
  recurrence forecast did NOT materialize. Continue the 4-file
  check in 5.10 §0.
- **5.3 `f35d5e4` JSON-column gotcha was avoided in 5.4 + 5.5 + 5.6
  + 5.7 + 5.8 + 5.9** by passing dict directly to
  `Entity.crowd_notes` — no `json.dumps()`. Internalize.
- **5.3 `bff4a79` F401 + 5.7 `5f8fe08` F541 + 5.8 inline-import I001
  + 5.9 cp1252-codec footguns:** `# noqa: E402` silences E402 only.
  F401 (unused imports), F541 (`f"..."` with no placeholders), I001
  (un-sorted imports, including inline `from x import y` blocks
  inside functions), AND PowerShell cp1252 encoding (can't encode
  `→` U+2192 — causes script crash) all still fail / cause issues.
  5.9 hit cp1252 once on the dump script's V1.5 carry-candidate
  section — fix is to use ASCII `->` instead of `→`. The `§` and
  `—` characters mojibake but don't crash. **Cleanest discipline:
  avoid all non-ASCII in script stdout; route Unicode to JSON files
  instead (UTF-8 by default).**
- **Sandbox bash git-index gotchas** — use `git rev-parse` / `git
  show HEAD:` for index-free reads. Operator runs index-dependent
  ops (incl. `git restore`) Windows-side via PowerShell.
- **Sandbox bash MOUNT-STALENESS gotcha** (recurring since 5.5; 5.6
  hit it twice; 5.7 hit it three times; 5.8 hit it twice; **5.9 hit
  it at §0 first git diff**). The Read tool is authoritative;
  sandbox bash file-shape queries + `git diff` are unreliable for
  any working-tree state query. Use Windows-side `python` + `git
  status` / `git diff` for all such queries.
- **PowerShell `\"` escape footgun (5.7-discovered, 5.8/5.9-avoided):**
  Use single-quoted `-m '...'` flags for git commit messages when
  the body contains `"` or `/` characters; PS single quotes are
  literal (no interpolation, no escaping). 5.9 used this discipline
  throughout.
- **5.9 lesson — DB-verify the "existing entity in cat-X" premise
  BEFORE finalizing audit doc.** 5.9 §2 caught it prospectively via
  `outputs/phase5_9_dupe_check.py` — Lake Havasu City Aquatic Center
  was framed as a FLIP candidate in the kickoff §2 but dupe-check
  confirmed 0 entities in DB; reclassified as NEW-create. Saves
  mid-apply correction (vs 5.8 Slice B-1 which caught it mid-apply).
  **For 5.10:** author `outputs/phase5_10_dupe_check.py` EARLY in
  §2 audit, before finalizing the audit doc. Verify waterfront
  resort cat-3 placements + RV park cat-10 placements + any other
  pre-existing cat-10 entries before authoring Slice decisions.
- **DB-write apply-scripts:** stop the FastAPI dev server if running
  (events.db lock).
- **`Provider.google_review_snippets` is its OWN COLUMN** — not
  inside `attributes` JSON. Drafts for top-10 long-form `crowd_notes`
  source from this column. 5.9's top-10 had 100% snippet coverage
  on 9 of 10 (Hilltop Learning Center at 3); 5.10 forecast 85-95%
  (lodging reviews abundant).
- **CI can be flaky on intermediate commits** — 5.5 / 5.7-session-1 /
  5.8 all saw the same pattern (one ✓ + one ❌ on the same commit
  ID, short elapsed time = runner-orchestration flake not code).
  5.9 didn't hit it. Try `gh run rerun <ID>` before shipping a fix
  commit. Final tree-state CI green is the ship-readiness signal.
- **`_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a domain-wide
  catch-all** at `places_load.py:368-371`. 5.2's `(None,
  "lake_recreation") → "on-the-water"` stays in place for 5.10
  (covers the deferred lake_recreation labels). 5.10 §1 Option A
  may add `(None, "lodging") → "lodging-vacation-rentals"` as a NEW
  catch-all if §1 load surfaces unmapped lodging primary_types.
- **5.9 §2 DUAL-cat pattern (Slice D)** — 1 entity (Our Lady of
  the Lake Catholic School) got cat-13 added while preserving cat-12.
  5.10 forecast: waterfront resorts may need similar DUAL cat-3 +
  cat-10. Reuse the `_dual_add_category` function from
  `outputs/apply_phase5_9_classes_audit.py`.
- **5.9 §2 in-session reporting bug** — apply-script's "Post-apply
  EntityCategory rows" count showed 27 immediately after changes,
  but actual DB state was 31 (autoflush quirk in in-session COUNT
  query). For 5.10 fix: use `select(func.count())` instead of
  `.all()` length; or add explicit `session.flush()` before the
  COUNT query.

**Carry-forwards from the 5.9 session** the new agent should action:

- 🚨 **Phase 6 lane — consolidated amend5-8 dispatch** —
  `outputs/claude_code_dispatch_phase6_amend5_to_8.md` ready for
  Claude Code parallel agent. Lands Phase 5.5/5.6/5.7/5.8 SHIPPED
  ledger lines. **Operator may want to extend to amend5-9 or
  amend5-10** before dispatching (would need additional sections for
  5.9 + 5.10 SHIPPED).
- **`parks-rec-scrapes` prune-fix sidecar** — root cause + 3 fix
  options in 5.7 close-out §3. Optional inclusion at §4.5 (see
  above); default defer to separate sidecar dispatch.
- **V1.5 Layer-4 verifier surface for 5.9** — AZDHS childcare-
  license + franchise gym chain APIs + LHC Parks & Rec paths
  documented in `phase5_9_classes_audit.md` §3 + kickoff §3.
- **V1.5 sustainability layer extensions** — add `athletic_field` /
  `educational_institution` / `primary_school` / `church` direct
  mappings per the 5.9 audit doc §9.
- **V1.5 dual-cat reviews** — 26 cat-5 HWC §1-updates; Sand
  Volleyball; Ark Center; Aquatic Center civic cross-link.
- **5.9 §9 V1.5 carry candidates** — RV parks + campgrounds
  (deferred per 5.10 Narrow scope decision); Universal Sonics
  Gymnastics + Shah Racquetball Club; Bridge Body Fitness + Feelin'
  Good Fitness; River City Music; Nomadic / Lions Dog / Main Street
  Commons.
- **86 of 265 HWC providers remain `verified=False`** — carry-over
  from 5.4. Operator-driven DBA→NPI follow-up surface (optional
  V1.5).
- **Operator: prune `data/events.db.bak-*` files** when comfortable
  — carry-over from 5.3 + 5.4 + 5.5 + 5.6 + 5.7 + 5.8 + 5.9.
- **Google Places API key rotation** — deferred per operator ("all
  keys will be changed at conclusion of this project").

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.9 session 1
(2026-05-17) post-`4527ca1` SHIP + `bc08bf6` SHA-cleanup, pre-§0
hand-off artifact. Commit inline before §0 pre-flight dispatches.
Cowork primary picks up at §0 pre-flight after reading
`outputs/phase5_9_session_closeout.md` first and
`outputs/phase5_10_next_agent_boot_prompt.md` second.*
