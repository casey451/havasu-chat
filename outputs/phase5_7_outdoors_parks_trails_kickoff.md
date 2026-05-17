# Phase 5.7 Kickoff — Outdoors, Parks & Trails (`outdoors-parks-trails`)

> **What this is:** a single paste-and-go operator runbook for Phase 5.7,
> the seventh Tier 1 category. Mirrors
> `outputs/phase5_6_shopping_grocery_essentials_kickoff.md` shape with
> 5.7-specific overrides. **Single-layer scrape** (Google only — OSM
> scope is locked to on-the-water per brief §3.2.e, even though
> `osm_overpass_client.py:123` defaults its category_slug to
> `outdoors-parks-trails`; OSM is not dispatched in this lane).
>
> **GATE 1 — Phase 5.6 SHIPPED** at `7609a01` (2026-05-16) with all 6
> gate items cleared. ✅ Met.
>
> **GATE 2 — no pre-built verifier surface for 5.7.** There is no
> consolidated public registry for "parks and trails" the way AZ ROC
> covers contractors or NPI covers medical providers. Three narrow
> options exist (AZ State Parks public site, NPS public-lands API, LHC
> Parks & Rec municipal pages) but none cover the full V1 surface, all
> are scraping-shape not API-shape, and the V1 utility of a "verified
> via NPS" badge for a city park is low. **This kickoff resolves §3 as
> Option C** (defer Layer-4 verifier surface to V1.5; document the three
> paths). Mirrors 5.5 + 5.6 outcome.
>
> **GATE 3 — pre-flight integrity gotcha (now FOURTH recurrence):**
> `scripts/places_categories.json` has drifted locally on every 5.x
> session since 5.5. The 5.7 boot session ALSO surfaced a **wider drift
> pattern** — `scripts/places_load.py`, `app/db/models.py`, and
> `app/contrib/google_types_mapping.py` were all truncated in the
> working tree (suspected stale checkout / external-editor crash;
> `.git/index.lock` was present in the sandbox view of the repo
> Windows-side hadn't fixed yet). Operator restored via
> `git restore .` Windows-side after sandbox `rm .git/index.lock`
> failed with `Operation not permitted`. Pre-flight item #6 below is
> WIDENED for 5.7 to check the four-file shape, not just
> `places_categories.json`.
>
> **🚨 BOOT-PROMPT FRAMING NOTE:** The Phase 5.7 boot prompt at
> `outputs/phase5_7_next_agent_boot_prompt.md` references an
> `outdoor_recreation` domain in `scripts/places_categories.json`. **That
> domain does not exist.** The actual mapping per
> `app/contrib/google_places_scraper.py:86` is
> `"outdoors-parks-trails": frozenset({"fitness_sports",
> "entertainment_attractions"})` — a two-domain bundle. The boot
> prompt's anticipated label set (parks, trails, viewpoints,
> campgrounds, playgrounds, dog parks, skateparks, picnic areas) is
> ASPIRATIONAL — none of those labels are in
> `places_categories.json` except `parks` (under
> `entertainment_attractions`). Adjustments per §1 below.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.7 boot session
> (2026-05-16) post-`b3acb03`, pre-§0. Pastable as-is; commit inline
> before §0 pre-flight dispatches per the established cadence.

---

## §0 Pre-flight (do once, at Phase 5.7 dispatch)

1. **`git log --oneline -15`** — origin should top at `b3acb03` (Phase
   5.7 boot prompt) over `7609a01` (Phase 5.6 SHIPPED) or later if
   Phase 6 lane has shipped Amendment 6 between sessions (in-line a la
   `0addb63` for 5.4 OR via Claude Code parallel dispatch).
2. **`git status`** — clean. **Sandbox bash note:** `git status` hits
   the index-format gotcha (`fatal: unknown index entry format
   0xffff0000`); run Windows-side via PowerShell. Carry-over untracked
   from 5.6: `hava_api_catalog.docx` + `~$va_api_catalog.docx` Word
   lock + 2 historical `outputs/ci_*_log_failed.txt` files +
   `outputs/_deltest` — all unrelated to lane; operator prunes when
   comfortable. **NEW pre-flight gotcha (5.7 boot-session
   discovery):** sandbox may report a stale `.git/index.lock` that
   doesn't exist Windows-side (the mount-staleness pattern, but for
   git internal state). If sandbox-side `git restore .` fails with
   `Unable to create '.git/index.lock'`, the Windows-side path is
   clear — operator simply runs `git restore .` in PowerShell and
   sandbox's stale lock view does not block work.
3. **`python -m alembic current`** — confirm local `data/events.db` at
   `0a1b2c3d4e5f`. If behind, `python -m alembic upgrade head`. (No
   migrations expected on the 5.7 lane.)
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — record
   baseline. Phase 5.6 closed at **1932 collected** (5.5 baseline 1920
   + 12 in-lane regression guards for the `44e8097` retail fallback
   extension). Verify no drift.
5. **`python outputs/diagnose_category_id_gap.py`** — confirm Phases
   5.1, 5.2, 5.3, 5.4, 5.5, and 5.6 categorization is intact and the
   `outdoors-parks-trails` slug exists in the `categories` table (id
   should be 7 per `alembic/versions/e1f2a3b4c5d6_phase3_data_pass.py:
   63`).
6. **🚨 WIDENED four-file shape check** (5.7 boot session surfaced the
   wider drift pattern):
   ```powershell
   git diff --stat scripts/places_categories.json scripts/places_load.py app/db/models.py app/contrib/google_types_mapping.py
   ```
   MUST be empty. If ANY of the four shows deletions in the working
   tree, restore via `git restore .` Windows-side before §1. The
   expected HEAD line counts are (sanity reference, not validation
   targets — content over shape):
   - `scripts/places_categories.json`: 211 lines
   - `scripts/places_load.py`: 639 lines
   - `app/db/models.py`: 1539 lines
   - `app/contrib/google_types_mapping.py`: 153 lines
7. **Google Places key + spend cap** — operator has deferred rotation
   until project end; still in `.env`, still capped. No mid-session
   rotation needed unless the operator opts in.
8. **CI state** — check GitHub Actions on the top commit. Should be
   ✅ green on `7609a01` (the 5.6 SHIP commit) and `b3acb03` (docs-only
   boot prompt commit; CI should pass trivially). If red, investigate
   before starting 5.7. The `parks-rec-scrapes` scheduled cron has
   been ❌ since 5.3 — **5.7 §4.5 sidebar investigates this AFTER
   gate-2 audit clears** (Decision 3); does NOT block §0 dispatch.
9. **DB state spot-check** — `shopping-essentials` should show **83
   entries / 0 verified / 78 indoor + 5 outdoor / 76 render (7
   drafted) / 10 long-form crowd_notes** (the 5.6 SHIPPED state).
   `outdoors-parks-trails` should show **6 entries pre-load** (Avalon
   Park, Cattail Cove State Park, Dick Samp Memorial, Lake Havasu
   State Park, Rotary Community Park & Playgrounds, SARA Park — all
   `entity_type='commercial'` not `'place'`; all source
   `google_places`; sideways-collected from prior 5.x phases under
   other labels). 5.7 needs to net at least **+14** new entries to
   clear the 20-entry gate (see §6).

---

## §1 The scrape sequence — Google only, NARROW scope

Phase 5.7 is **single-layer** (no OSM dispatch). **Scope is
intentionally narrowed** from the literal 21-label
`outdoors-parks-trails` bundle in
`DISCOVERY_CATEGORY_TO_DOMAINS` because of two structural collisions:

1. **`fitness_sports` collision with Phase 5.4 (HWC).** Phase 5.4
   already absorbed gyms / yoga studios / pilates studios / crossfit
   gyms / martial arts / jiu-jitsu / dance studios into
   `health-wellness-care`. The existing fallback
   `(None, "fitness_sports") → "health-wellness-care"` in
   `_DISCOVERY_DOMAIN_FALLBACK` codifies that mapping. Scraping any
   `fitness_sports` label in 5.7 would either (a) double-categorize
   existing HWC entities via the ambig path, or (b) fight the existing
   fallback. **Defer all 11 fitness_sports labels to V1.5.**
2. **Indoor entertainment is semantically wrong for "outdoors, parks
   & trails."** Movie theaters, bowling alleys, arcades, museums, art
   galleries, live music venues, and event venues are clearly indoor
   entertainment and don't belong in a parks-and-trails surface.
   **Defer those 7 entertainment_attractions labels to a future
   "indoor entertainment" or "civic-resources" phase.**

This leaves **3 labels in scope for 5.7 §1:**

| Bucket | Labels (3) | Domain |
|---|---|---|
| **Parks** | parks | entertainment_attractions |
| **Golf** | golf courses, mini golf | entertainment_attractions |

Plus an **implicit fourth label via Google's primary_type catch-all**:
any Google response under `parks` whose `primary_type` is `dog_park`
will route correctly via `_PRIMARY_TYPE_MAP["dog_park"]` to
`("outdoors-parks-trails", "place")` — no separate label needed.
Same for `park` primary_type. So dog parks ARE in scope without an
explicit label.

### Layer 1 — Google Places

```
python -m scripts.places_discovery --category outdoors-parks-trails --dry-run
python -m scripts.places_discovery --category outdoors-parks-trails
python -m scripts.places_enrichment --limit 200
python -m scripts.places_load --category outdoors-parks-trails --dry-run
python -m scripts.places_load --category outdoors-parks-trails
```

**Why `--limit 200` on enrichment?** 3 labels × ~30 per label ≈ 90
raw hits; the cumulative enrichment cache (5.0/5.1/5.2/5.3/5.4/5.5/
5.6) is large (likely ~2700+ records post-5.6). Most of those will
cache-hit. Expected new enrichments: ~20-40 (smaller than 5.6's 23-
plus because parks have less geo-density than retail strip-malls and
fewer distinct labels).

⚠️ **The `--category outdoors-parks-trails` flag will filter
`places_categories.json` by `DISCOVERY_CATEGORY_TO_DOMAINS` which
returns BOTH `fitness_sports` AND `entertainment_attractions`.** This
will pull in all 21 labels by default — including the 18 we want to
defer. **Two paths** to honor the Narrow scope:

- **Path A (recommended — minimal code change):** Author a one-shot
  filter script `outputs/phase5_7_narrow_label_filter.py` that
  short-circuits the discovery loop to only the 3 in-scope labels.
  Mirrors the `apply_*` script shape but for discovery filtering.
  ~20 lines.
- **Path B (broader change):** Temporarily edit
  `DISCOVERY_CATEGORY_TO_DOMAINS` to `frozenset({"entertainment_
  attractions"})` for the duration of the 5.7 scrape, revert before
  ship. Riskier (touches a production-facing constant); not
  recommended.

**Default to Path A unless operator picks B.**

### Sustainability layer extensions expected

The `entertainment_attractions` domain has **zero entries** in
`_DISCOVERY_DOMAIN_FALLBACK` today. Layer 1 will surface several
catch-all primary_types that don't appear in `_PRIMARY_TYPE_MAP`:

- `golf_course` (NOT in _PRIMARY_TYPE_MAP — every golf course will
  land at `category_id=None` without intervention)
- `tourist_attraction` (used by Google for state parks, scenic
  viewpoints, mini golf, etc.)
- `amusement_park` (mini golf often)
- `point_of_interest` (generic catch-all)
- `establishment` (generic catch-all)
- `None` (no primary_type)

**Anticipated extensions** to `_DISCOVERY_DOMAIN_FALLBACK` after
Layer 1 surfaces specific gaps (mirror the `44e8097`/`4d41944`/
`fc51940`/`7c994aa` surgical-fix shape exactly):

```python
# Anticipated 5.7 fallback entries (extend after Layer 1 surfaces specific gaps)
(None, "entertainment_attractions"): "outdoors-parks-trails",
("tourist_attraction", "entertainment_attractions"): "outdoors-parks-trails",
("amusement_park", "entertainment_attractions"): "outdoors-parks-trails",
("point_of_interest", "entertainment_attractions"): "outdoors-parks-trails",
("establishment", "entertainment_attractions"): "outdoors-parks-trails",
```

**Plus a 1-line widening to `app/contrib/google_types_mapping.py`
`_PRIMARY_TYPE_MAP`** to catch golf courses correctly regardless of
discovery domain (V1.5 surface for `medical_clinic` from 5.4 + 5.6
gets cousin-treatment here):

```python
"golf_course": ("outdoors-parks-trails", "commercial"),
```

(Note: `commercial` not `place` — golf courses charge fees, employ
staff, have business hours; they're commercial entities even though
they're outdoor. Same shape as how Cattail Cove State Park currently
sits as commercial with source `google_places`.)

**Sustainability-layer commit shape:** mirror `44e8097` — a single
focused `fix(scripts)` commit that adds the 5 fallback entries + the
1-line _PRIMARY_TYPE_MAP widening + regression tests in
`tests/test_phase5_7_places_load_resolver.py` (~6 parametrized
asserts: 5 for the new fallback entries + 1 for golf_course type
mapping + defensive preservation of the 5.2/5.3/5.4/5.5/5.6 entries).
Land BEFORE the §1 Layer 1 dispatch (sustainability-first pattern
from 5.5/5.6, not the 5.3/5.4 reactive surgical-fix).

**Optional combined widening:** if operator opts in, this same commit
can ALSO widen `medical_clinic` → `("health-wellness-care",
"commercial")` in `_PRIMARY_TYPE_MAP` (the V1.5 carry-over from 5.4
+ 5.6). Costs ~2 extra lines + 1 regression test; closes a soft-edge
both prior phases flagged. **Recommended:** include the
`medical_clinic` widening in this commit unless operator wants to
keep them separate.

### Layer 5 — Manual recovery (deferred to operator)

Per `docs/maintainability/manual_recovery_checklist.md`. Surface for
5.7:

- LHC trails not indexed by Google Maps (Crack-in-the-Mountain, SARA
  Park trails, Lake Havasu State Park trail system)
- BLM-managed public lands (Havasu NWR backcountry, Topock Gorge
  trailheads) — federal land often under-indexed
- Skateparks (Lake Havasu Skatepark at Rotary Community Park may
  already be covered by the parent park entity)
- Playgrounds (typically part of parent park entities; surface only
  if standalone)
- LHC City Parks & Rec micro-parks not on Google (small
  neighborhood parks)

Not gate-blocking for V1 ship.

---

## §2 Ambiguous-queue review — moderate volume + significant cross-category overlap expected

Parks/golf is the **seventh non-empty-DB load** (after 5.1+5.2+5.3+5.4
+5.5+5.6). Reconciler will match against **~1,124 existing entities**
(287 eat-drink + 119 on-the-water + 230 home-property-services + 265
health-wellness-care + 140 auto-rv-fuel + 83 shopping-essentials).
Expected ambiguous hits: **20-60 per run** (range covers low parks
geo-density offset by significant cross-category overlap risk).

**Special audit categories expected for 5.7:**

| Existing entity | 5.7 candidate it'll likely match | V1 policy |
|---|---|---|
| Lake Havasu State Park (cat-7 already) | parks (cat-7) | **same-cat update**; refresh boat_access if relevant |
| Cattail Cove State Park (cat-7 already) | parks (cat-7) | **same-cat update** |
| Rotary Community Park (cat-7 already) | parks (cat-7) | **same-cat update**; includes Lake Havasu Skatepark |
| Marina entities (cat-6 from 5.2) | parks at waterfront (cat-7) | likely **stay in cat-6** if marine-primary; cross-link if both apply |
| Golf course at resort (cat-12 lodging) | golf courses (cat-7) | edge case — golf may be sub-amenity of resort |
| Mini golf at family entertainment venue | mini golf (cat-7) | check if cat-7-only or also cat-? entertainment |
| Hotel with pool (cat-12 lodging) | (NONE — pools are deferred per Narrow scope) | n/a |
| Gym (cat-4 HWC from 5.4) | (NONE — gyms deferred per Narrow scope) | n/a |

**Pre-existing 6 entities in outdoors-parks-trails are
`entity_type='commercial'`** — `park` and `dog_park` primary_types
map to `place` per `_PRIMARY_TYPE_MAP`, but these 6 were ingested
under non-park labels (likely OSM Overpass which defaults
category_slug to outdoors-parks-trails per
`app/contrib/osm_overpass_client.py:123`, OR under
on-the-water/beach labels in 5.2) and inherited `commercial` from
their actual primary_type. **5.7 §2 audit should decide:** flip
these 6 to `entity_type='place'` (data correctness)? Or leave them
commercial (preserves audit trail)? Recommendation: **leave as
commercial for V1** — the gate-1 query uses the
`(e.entity_type != 'commercial' OR provider-visible)` shape that
handles both correctly; flipping is cosmetic + risks dual-write
re-promotion edge cases. Defer flip to V1.5.

Mirror the 5.6 audit pattern: post-load audit pulls cross-category
+ same-category; an apply-script batches the misroute decisions if
any. **Expected outcome based on 5.4/5.5/5.6 history: 0 real
misroutes**, plus same-cat updates to the 6 pre-existing entries
(name normalization, snippet refresh, etc.).

If a single load produces **>60** ambiguous hits, consider tuning
`GEO_PROXIMITY_THRESHOLD_M` (currently `50.0`) per brief §4.g — but
prior phases have all stayed under the tune threshold despite
exceeding 50.

### Cross-category sweep — `_DISCOVERY_DOMAIN_FALLBACK` catch-all behavior

Per 5.6 close-out §3, the `(None, "<domain>")` catch-all routes ALL
unmapped primary_types under that domain (not just rows with
`primary_type=None`). 5.6's `(None, "retail")` swept 27 edge-case
providers into shopping-essentials. **5.7's `(None,
"entertainment_attractions")` is expected to sweep a smaller pool
(~5-15 rows)** because Narrow scope means we're only scraping 3
labels, not the full domain. Likely edge cases:

- `golf_course` primary_types if the _PRIMARY_TYPE_MAP widening is
  NOT applied (golf_course primary_type → falls back to (None,
  "entertainment_attractions") → outdoors-parks-trails). **Same row
  twice via two paths if widening applied — first via
  _PRIMARY_TYPE_MAP, second via fallback — but the fallback only
  fires when _PRIMARY_TYPE_MAP returns (None, None), so no
  double-routing.**
- `tourist_attraction` primary_type catches state parks (Cattail
  Cove, Lake Havasu) which Google often tags as `tourist_attraction`
  rather than `park`.
- `point_of_interest` / `establishment` are generic catch-alls.

Apply-script `outputs/apply_phase5_7_parks_audit.py` if any FLIPs
needed. Expected size: ~5-15 rows reviewed, likely 0 FLIPs (Narrow
scope minimizes spillover).

---

## §3 Layer-4 verifier surface — Option C resolved (deferred to V1.5)

**5.7 has no pre-built verifier** (unlike 5.3's `az_roc_verify` and
5.4's `npi_verify`). Three narrow options exist; this kickoff
resolves §3 as **Option C** per the structural reasoning in the
header. The other two paths are documented here for V1.5 pickup.

### Option A — AZ State Parks + NPS public lands (DEFERRED to V1.5)

URLs:
- AZ State Parks: `https://azstateparks.com` — site lists each AZ
  state park with location, fees, amenities. No public API; would
  require Playwright. Covers Lake Havasu State Park + Cattail Cove
  State Park for LHC area.
- NPS public-lands API: `https://www.nps.gov/subjects/digital/
  nps-data-api.htm` — REST API with park-by-park metadata. Covers
  federal land like Havasu NWR.

Coverage: ~2-4 of the 6 pre-existing entries + 0-2 new entries from
5.7's scrape (LHC has very limited federal land; Havasu NWR
overlaps the city's lake-shore edges). Sets `Provider.verified=True`,
`verification_method='az_state_parks'` or `'nps'`,
`attributes.az_state_parks={...}` / `attributes.nps={...}`.

**Cost-of-build:** ~2-4 hours (NPS REST is straightforward; AZ State
Parks Playwright is more involved). **Coverage is too narrow for V1
to justify the build.**

### Option B — LHC Parks & Recreation municipal pages (DEFERRED to V1.5)

URL: `https://www.lhcaz.gov/parks-recreation` — municipal park
listings with amenities (playgrounds, pavilions, restrooms, sports
fields). Site is JavaScript-rendered (need
Claude-in-Chrome-style render to scrape). Covers ~12-15 LHC city
parks comprehensively but no state/federal land.

**Cost-of-build:** ~3-5 hours (JS-rendered HTML, no obvious API
surface). Coverage maps best to the 6 pre-existing entries + 5.7's
likely "parks" label net-new entries (~8-12 new city parks).
**Highest value of the three but still V1.5 territory.**

### Option C — Defer verifier surface to V1.5 ✅ SELECTED

Gate item 3 rephrased to **"Layer-4 verifier surface scoped — built
or explicitly deferred to V1.5"**. Document AZ State Parks + NPS +
LHC Parks & Rec paths in this kickoff and ship 5.7 without verifier
surface. Lowest-friction shape; mirrors 5.5 + 5.6 outcome.

**Rationale:** parks-and-trails verification has low V1 utility
(consumer discovery doesn't need a "verified by NPS" badge on a city
park to be useful); the three available paths are all scraping-shape
not API-shape; coverage is fragmented across three sources. Better
to defer the whole verifier surface to V1.5 when the right shape
(e.g., LHC Parks & Rec municipal scrape + selective state/federal
overlay) can be designed against fuller scope.

---

## §4 Operator-curated field entry — Parks rubric

Lighter operator surface than 5.5 (no `is_mobile_service` to curate
— parks are place-based, not service businesses); roughly on par
with 5.3/5.4/5.6 shape but with a different `heat_exposure` default:

- **`heat_exposure`** — **`outdoor` for the vast majority** of 5.7
  entries (parks, golf courses, mini golf, dog parks — all
  outdoor-by-definition). Notable exceptions: **none expected** in
  the Narrow scope. (If a hypothetical "indoor mini golf" surfaces,
  that's an `INDOOR_OVERRIDES` candidate, but LHC almost certainly
  has none.) Mirror `outputs/apply_phase5_6_shopping_heat_exposure.
  py` exactly but **flip the default** to `outdoor` and populate
  `INDOOR_OVERRIDES` instead of `OUTDOOR_OVERRIDES`. Expected
  override count: **0-2** (vs 5.6's 5 outdoor overrides on indoor
  default).
- **`crowd_notes`** — short-form for typical entries; long-form for
  the top-10 by review count. Parks reviewer signals tend to be:
  amenities (restrooms, pavilions, playgrounds, BBQ pits, parking),
  shade/lack-of-shade (Havasu summer relevance), water access
  (lake-adjacent parks), trail quality + difficulty, dog-friendly
  policies, lighting (evening use), seasonal events (concerts,
  festivals). For golf courses: course condition, pace of play,
  pro shop quality, lesson availability, twilight rates. For mini
  golf: family-friendliness, course difficulty, indoor/outdoor
  setup.

Drafts source: **`Provider.google_review_snippets` (own column, not
`attributes`)** — per the 5.4 close-out §4 source-path correction.
Expected snippet coverage: ~70-85% (parks tend to have abundant
reviews; golf courses very abundant; mini golf moderate).

**`is_mobile_service`** is NOT a gate item for 5.7 (parks/golf are
place-based; "mobile service" is meaningless for them). Skip the
`is_mobile_service` apply-script for 5.7.

**`attributes`** JSON — can be extended with park-specific keys:
`has_playground` (bool), `has_restrooms` (bool),
`has_picnic_areas` (bool), `dog_friendly` (bool), `lake_access`
(bool), `paved_paths` (bool), `lighted` (bool). For golf:
`holes_count` (int, 9 or 18), `driving_range` (bool),
`pro_shop` (bool). Brief §3.4 has the suggestion shape.

### §4.5 sidebar — `parks-rec-scrapes` CI workflow investigation (Decision 3)

The scheduled `parks-rec-scrapes` GitHub Actions workflow has been
❌ on cron triggers since at least Phase 5.3 — flagged in every
5.3/5.4/5.5/5.6 close-out as "Phase 5.7 should investigate." Per
Decision 3 (operator-confirmed at boot), investigate AFTER §2 audit
clears (not during §0):

1. `gh workflow list` to find the workflow file.
2. `gh run list --workflow <name> --limit 5` to see failure pattern.
3. `gh run view <id> --log-failed | head -50` to find the root cause.
4. Likely hypothesis: the workflow was authored against the
   `outdoors-and-parks` slug (pre-Phase-3.2 rename to
   `outdoors-parks-trails`) and the rename broke it. If so, a
   1-line slug-rename PR fixes it.
5. Alternative hypothesis: the workflow scrapes the
   `outdoors-parks-trails` slug and falls into the `(None,
   "entertainment_attractions")` gap we'd be patching in this
   phase's sustainability commit — so the fix may be retroactive
   green automatically once 5.7's §1 sustainability commit lands.

**Not gate-blocking for 5.7 ship.** Surface findings in §6 if the
fix lands; defer to a Phase 6 lane dispatch otherwise.

---

## §5 Daily / weekly rhythm (brief §5)

Similar cadence to 5.5/5.6 but lighter (fewer labels, smaller pool):

| Day | Work |
|---|---|
| 1 | Sustainability-layer commit (5 fallback entries + golf_course mapping + optional medical_clinic widening) BEFORE Layer 1; then Google scrape run + scrape log (`docs/scrape_logs/outdoors-parks-trails_<YYYY-MM-DD>.md`) + Narrow-scope filter script if Path A picked |
| 2 | Ambiguous-queue triage + data-quality audit (cross-category review per §2; sweep the 6 pre-existing entries for name/snippet refresh) |
| 3 | Verifier surface — Option C deferral confirmed in §3; document V1.5 paths |
| 3-4 | `crowd_notes` for top-10 + `heat_exposure` sweep (outdoor default + INDOOR_OVERRIDES) |
| 4 | `parks-rec-scrapes` CI workflow investigation (§4.5 sidebar) |
| 5 | Optional Layer 5 manual recovery (LHC trails, BLM land, skateparks, micro-parks) |
| 6 | QA spot-check — 10 random entries vs. the §4 rubric |

**Expected Phase 5.7 total: 6-10 hours over 1 week.** Lighter than
5.5/5.6 because Narrow scope drops most of the labels; offset
slightly by the §4.5 CI sidebar.

---

## §6 Acceptance gate — Phase 5.7 closes when ALL of:

- [ ] **20+ entries** in `outdoors-parks-trails` post-load (modest
      target — LHC parks-and-trails density is lower than retail or
      auto; 6 pre-existing + ≥14 net-new from Layer 1). Gate-1 query
      MUST use the `(e.entity_type != 'commercial' OR provider-
      visible)` shape from `outputs/phase5_2_gate_verification.py`
      and `outputs/phase5_6_gate_verification.py` to correctly
      count `place`-typed park entities (dog_park primary_type
      maps to `place`; the 6 pre-existing are `commercial`).
- [ ] All Google ↔ existing-entity ambiguous reconciler hits
      reviewed (with cross-category review per §2 — especially the
      cat-6/cat-7 on-the-water/parks axis for waterfront parks +
      the cat-12/cat-7 lodging/golf axis for resort golf).
- [ ] **Layer-4 verifier surface scoped — Option C explicitly
      deferred to V1.5** (per §3). AZ State Parks + NPS + LHC
      Parks & Rec paths documented in this kickoff §3 for V1.5
      pickup.
- [ ] Top-10 by review count have long-form `crowd_notes`
- [ ] `heat_exposure` set on every entry (`outdoor` for nearly all;
      `indoor` only for hypothetical indoor mini golf — expected
      override count 0-2)
- [ ] Phase 6 `/category/outdoors-parks-trails` renders **≥15** per
      default filter

**Note: 6 gate items (not 7).** `is_mobile_service` was 5.5-specific
and is dropped for 5.7 — parks/golf are place-based by definition
(same rationale as 5.6's retail).

When the gate is met: commit the scrape log, Phase 5.7 gets its
SHIPPED ledger line on `master_build_plan.md` §4 (coordinate with
Phase 6 lane via `outputs/claude_code_dispatch_phase6_amend7.md`),
and **Phase 5.8 (next Tier-1 category — likely `events` or
`classes-sports-recreation` per the remaining 12-slug list)**
dispatches next.

---

## §7 Reference

- `outputs/phase5_6_session_closeout.md` (the just-shipped 5.6 state
  index — carries the apply-script + audit + sustainability layer
  playbooks 5.7 reuses)
- `outputs/phase5_6_shopping_grocery_essentials_kickoff.md` (the 5.6
  runbook this document mirrors)
- `outputs/phase5_2_gate_verification.py` (gate template for
  `entity_type='place'` query shape — **critical for 5.7** since
  Narrow scope produces a mix of place + commercial entities)
- `outputs/phase5_6_gate_verification.py` (template for the
  equivalent 5.7 gate-verification script — note: 6 items not 7;
  no `is_mobile_service` check; threshold ≥20 not ≥40)
- `outputs/phase5_6_shopping_essentials_audit.md` (combined pre+post
  audit template for the equivalent 5.7 audit doc)
- `docs/scrape_logs/shopping-essentials_2026-05-16.md` (template for
  the equivalent 5.7 scrape log)
- `app/contrib/google_types_mapping.py` (entertainment_attractions
  + fitness_sports types — extend `golf_course` per §1; consider
  also widening `medical_clinic` as the V1.5 carry-over)
- `app/contrib/google_places_scraper.py:86` (`DISCOVERY_CATEGORY_TO_
  DOMAINS["outdoors-parks-trails"]` — the source of the
  fitness_sports + entertainment_attractions bundle)
- `app/contrib/osm_overpass_client.py:123` (OSM default
  category_slug is `outdoors-parks-trails` — relevant if the
  `parks-rec-scrapes` CI workflow turns out to be an OSM cron)
- `scripts/places_load.py` (`_resolve_category_id` sustainability
  layer + 5.3 + 5.4 + 5.5 + 5.6 fallback extensions; extend
  `_DISCOVERY_DOMAIN_FALLBACK` for `entertainment_attractions`
  catch-alls per §1)
- `outputs/diagnose_category_id_gap.py` (re-usable diagnostic)
- `outputs/apply_phase5_6_shopping_heat_exposure.py` (5.6 heat sweep
  template — for 5.7 flip default to `outdoor`, populate
  `INDOOR_OVERRIDES` instead of `OUTDOOR_OVERRIDES`)
- `outputs/apply_phase5_6_shopping_crowd_notes.py` (5.6 crowd_notes
  template — pass dict directly to JSON column per 5.3 `f35d5e4`
  gotcha, F401-clean imports per 5.3 `bff4a79` lesson)
- `outputs/phase5_6_ambig_audit_dump.py` (5.6 ambig audit dump
  script — direct copy with paths/slug swap for 5.7)

---

## §8 Hand-off context from the Phase 5.6 session

**Important context that's NOT in this kickoff but the new agent
should read in the 5.6 close-out:**

- 3-commit chain from `66e02c8` → `7609a01` with 1 surgical fix
  shipped mid-session (`44e8097` `_DISCOVERY_DOMAIN_FALLBACK`
  extension for `retail` domain — 7 entries). No AZ-TPT/BBB-style
  verifier build because operator picked Option C (defer).
- **5.6 §0 pre-flight surfaced `places_categories.json` corruption**
  (third recurrence). Restored via `git restore`. **The 5.7 boot
  session surfaced a FOURTH recurrence + a wider four-file drift
  pattern.** §0 item 6 above is widened accordingly.
- **5.3 `f35d5e4` JSON-column gotcha was avoided in 5.4 + 5.5 + 5.6**
  by passing dict directly to `Entity.crowd_notes` — no
  `json.dumps()`. Internalize.
- **5.3 `bff4a79` F401 footgun:** `# noqa: E402` silences E402 only.
  Audit apply-script imports for unused `json` / `Category` /
  `EntityCategory` before committing. 5.4/5.5/5.6 all avoided this
  by pre-commit ruff check Windows-side. Also watch for F541
  (`f"..."` with no placeholders) — surfaced once in 5.6 on the
  audit dump script.
- **Sandbox bash git-index gotchas** — use `git rev-parse` / `git
  show HEAD:` for index-free reads. Operator runs index-dependent
  ops (incl. `git restore`) Windows-side via PowerShell.
- **Sandbox bash MOUNT-STALENESS gotcha** (recurring since 5.5; 5.6
  hit it twice; 5.7 boot session hit it on the lock-file shape
  check + on post-restore `wc -l` not reflecting restored shapes).
  The Read tool is authoritative; sandbox bash file-shape queries
  (`wc -l`, `tail`, `json.load()`, `importlib`) are unreliable for
  post-Edit / post-restore verification.
- **DB-write apply-scripts:** stop the FastAPI dev server if running
  (events.db lock).
- **`Provider.google_review_snippets` is its OWN COLUMN** — not
  inside `attributes` JSON. Drafts for top-10 long-form `crowd_notes`
  source from this column.
- **PowerShell `git commit -m "" ...` footgun:** empty `-m ""`
  between multiple `-m "..."` flags is treated as a pathspec. Use
  multiple `-m "..."` flags WITHOUT empty separators; git inserts
  blank lines automatically.
- **CI can be flaky on intermediate commits** — 5.5 `6fb74ac`
  initially showed X red but a rerun went green. If a single
  intermediate commit is red on CI, try `gh run rerun <ID>` before
  shipping a fix commit. Final tree-state CI green is the
  ship-readiness signal.
- **`_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a domain-wide
  catch-all** at `places_load.py:368-371`, not a `primary_type=None`
  filter. When you add `(None, "entertainment_attractions"):
  "outdoors-parks-trails"`, you're routing ALL unmapped primary_types
  under `entertainment_attractions` to outdoors-parks-trails — not
  just rows where Google didn't tag a primary_type. With Narrow
  scope (3 labels only), the sweep should be small (~5-15 rows
  expected), but the §2 audit must still review for any spillover
  that should route elsewhere (e.g., a "park view restaurant" that
  Google primary-types as `establishment` should stay in eat-drink,
  not flip to parks).

**Carry-forwards from the 5.6 session** the new agent should action:

- 🚨 **Phase 6 lane — Phase 5.6 SHIPPED ledger amendment** —
  `outputs/claude_code_dispatch_phase6_amend6.md` is ready (operator
  may have already landed in-line per 5.4 `0addb63` precedent OR
  dispatched to Claude Code parallel agent — check `git log` for
  Amendment 6 commit).
- **V1.5 Layer-4 verifier surface for 5.6** — AZ TPT + BBB paths
  documented in `outputs/phase5_6_shopping_essentials_audit.md` §3
  carry-forward + 5.6 kickoff §3 for V1.5 pickup.
- **V1.5: `medical_clinic` widening in `google_types_mapping`** —
  surfaced as a soft-edge in 5.4 + 5.6 (`medical_clinic` only
  resolves via the health_medical fallback, not directly).
  **5.7 §1 sustainability commit is the right home for this 1-line
  widening if operator opts in** (closes a 2-phase carry-over with
  minimal added scope).
- **V1.5 carry-over: Anderson AZ West** — drafted as B2B wholesale
  by default; operator un-drafts if it turns out to be
  consumer-retail.
- **86 of 265 HWC providers remain `verified=False`** — carry-over
  from 5.4. Operator-driven DBA→NPI follow-up surface (optional
  V1.5).
- **Operator: prune `data/events.db.bak-*` files** when comfortable
  — carry-over from 5.3 + 5.4 + 5.5 + 5.6.
- **`parks-rec-scrapes` scheduled CI** — investigation deferred to
  §4.5 sidebar (Decision 3 — post-gate-2, not pre-§0).
- **Google Places API key rotation** — deferred per operator ("all
  keys will be changed at conclusion of this project").

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.7 boot session
(2026-05-16) post-`b3acb03`, pre-§0. Hand-off artifact — commit
inline before §0 pre-flight dispatches. Cowork primary picks up at
§0 pre-flight after reading `outputs/phase5_6_session_closeout.md`
first and `outputs/phase5_7_next_agent_boot_prompt.md` second.*
