# Scrape log -- `lodging-vacation-rentals` -- 2026-05-17

Per `docs/operations/scrape_logs_template.md`. First per-category
scrape run for Phase 5.10 (tenth sub-phase of the Phase 5 restructure,
post-5.9 SHIPPED 2026-05-17 at `4527ca1` + SHA-cleanup at `bc08bf6` +
5.10 kickoff at `ef8325d` + boot-prompt SHA-cleanup at `d597ef9`).
**Single-layer scrape** (Google only -- OSM scope locked to
on-the-water per brief 3.2.e; lodging has no OSM surface). **No
Layer-4 verifier** for 5.10 -- kickoff 3 resolved Option C (defer
AZDOR transient-lodging tax + AZRE vacation-rental license + LHC
Tourism Board paths to V1.5).

**Narrow scope** -- 5 of the lodging-domain labels are in-scope
(hotels, motels, resorts, vacation rentals, bed and breakfast); 24
lake_recreation-domain labels deferred because 5.2 already absorbed
marina/boat shape via on-the-water + pre-Phase-5 `rv_park` direct
mapping + secondary-types[] first-match on existing `lodging` direct
mapping already catches campgrounds / mobile_home_park /
camping_cabin in cat-10.

---

## 0 Pre-flight (closed)

| Check | Result |
|---|---|
| `git log -1 --oneline` | `d597ef9` (5.10 boot-prompt SHA-cleanup) over `ef8325d` 5.10 kickoff over `bc08bf6` 5.9 SHA-cleanup over `4527ca1` 5.9 SHIP |
| `python -m alembic current` | `0a1b2c3d4e5f` (unchanged across all 5.x phases) |
| `python -m pytest --collect-only` | **1985 collected** (5.9 baseline; pre-`bf24e16` sustainability commit) |
| `python outputs/diagnose_category_id_gap.py` | `lodging-vacation-rentals` slug present at id=10; all 5.1-5.9 cats intact |
| `gh run list --branch main --limit 5` | Top 4 runs green on main; `parks-rec-scrapes` cron continues to fail per 5.7 4.5 root-cause (out of 5.10 scope) |
| Google Places key + spend cap | In `.env`; spend cap active. Operator declined rotation per "all keys will be changed at conclusion of this project" |
| Playwright | Not needed for 5.10 (Option C -- no Layer-4 verifier built) |
| Widened four-file shape check (5.7 0 carry) | `git diff --stat` empty across `places_categories.json` + `places_load.py` + `models.py` + `google_types_mapping.py`; 7th-recurrence forecast did NOT materialize |
| Working tree clean | (untracked carry-over from 5.9: `hava_api_catalog.docx`, `~$va_api_catalog.docx` Word lock, 2 historical `outputs/ci_*_log_failed.txt`, `outputs/_deltest`) |
| DB baseline | `lodging-vacation-rentals`: **31 entries** (MAJOR FINDING -- not the kickoff-forecast 0-5; pre-existing via 5.2 absorption + pre-Phase-5 direct mappings); `classes-sports-recreation`: 31; `events`: 20 |

**One 0 surprise:** the kickoff forecast 0-5 cat-10 entries pre-1;
actual count is **31** (14 rv_park + 7 lodging-primary vacation
rentals + 6 campground + 2 mobile_home_park + 1 camping_cabin + 1
service). All caught via the existing pre-Phase-5 `lodging` and
`rv_park` direct mappings + secondary-types[] first-match behavior on
the `lodging` mapping. Gate-1 (>=20) was already met before 1.
This reframed the 5.10 scope: still run the full 1 scrape to add
hotels/motels/resorts/B&Bs (currently 0 of these), but cross-cat axis
forecast revises (no pre-existing waterfront resorts in cat-3 to
DUAL/FLIP).

---

## 1 Layer 1 -- Google Places (only scrape layer for 5.10)

### Narrow-scope wrapper (Path A.2 -- standalone, no production code touched)

`outputs/phase5_10_narrow_label_filter.py` -- short-circuits the
discovery loop to only the 5 in-scope lodging-domain labels: hotels,
motels, resorts, vacation rentals, bed and breakfast. Mirrors
`outputs/phase5_9_narrow_label_filter.py` exactly.

### Discovery -- dry-run

```
python outputs/phase5_10_narrow_label_filter.py --dry-run
```

| Field | Value |
|---|---|
| Mode | dry-run (hotels only) |
| Categories run | 1 |
| Requests | 3 |
| Unique places | 60 |
| Cost (actual) | ~$0.10-0.15 |
| Smoke notes | sys.path bootstrap worked first-try; hotels alone produced 60 unique across 3 pages -- significantly higher than the ~10-15 forecast (LHC tourism density) |

### Discovery -- full 5-label sweep

```
python outputs/phase5_10_narrow_label_filter.py
```

| Field | Value |
|---|---|
| Mode | full |
| Categories run | 5 |
| Requests | 10 |
| Unique places | **86** |
| Cost (actual) | ~$0.30 (within revised forecast $0.30-0.60) |

Per-label split (5 labels, all `lodging` domain):

| Label | Pages | New unique |
|---|---|---|
| hotels | 3 | 60 |
| motels | 3 | 23 |
| resorts | 2 | 1 |
| vacation rentals | 1 | 0 |
| bed and breakfast | 1 | 2 |

Notes: Heavy cross-label dedup -- resorts and vacation rentals heavily
overlap with hotels (most LHC resorts are also branded as hotels;
vacation_rental Google primary_type is rare in LHC -- most vacation
rental properties carry `lodging` as primary and got captured under
hotels). 0 vacation rentals via the vacation rentals label is normal,
not a bug -- documented in audit 6.

### Enrichment

```
python -m scripts.places_enrichment --limit 200
```

| Field | Value |
|---|---|
| Input | 86 |
| Cache-hits (resume skip) | 85 |
| New enrichments | 1 |
| 404 errors | 0 |
| Other errors | 0 |

**98.8% cache reuse** -- highest cache-hit rate seen across 5.x
phases. Explanation: nearly every LHC lodging-shape place was already
in the cumulative enrichment cache from prior phases' scrapes (most
were never loaded as Entity rows because the prior phases' category
filters excluded them; the cache absorbs everything Google returns,
even if the load skips). The cumulative cache at 2,644 enriched rows
pre-load + 1 new = 2,645 post-load.

### Load -- dry-run

```
python -m scripts.places_load --category lodging-vacation-rentals --dry-run
```

| Field | Value |
|---|---|
| Enriched rows in cache | 2,645 |
| After `--category lodging-vacation-rentals` filter | 365 |
| After ZIP filter | **297 kept, 68 dropped** |
| ZIP-drop top buckets | 85344 (24), 92363 Parker (10), 86442 (5), 86401 (4), 86436 (3), 92242 (3), 85207 (2), 89029 (2), 86429 (2), 8 more buckets at 1 each |
| Dry-run notes | No DB writes; --dry-run stops after ZIP filter (no resolver/insert/update breakdown until actual load) |

Larger filter surface than expected because the
`lodging-vacation-rentals` bundle includes BOTH `lodging` AND
`lake_recreation` domains. The 297 includes ~119 5.2-absorbed
lake_recreation entities (marinas/boats/etc.) that will hit UPDATE
branch with cat-3 preserved.

### Load -- full (1.6 ORIGINAL pre-sustainability)

```
python -m scripts.places_load --category lodging-vacation-rentals
```

| Field | Value |
|---|---|
| Input rows | 297 |
| Skipped (no name) | 0 |
| **Inserted (new entities)** | **36** |
| **Updated (existing place_id)** | **224** |
| **Reconcile ambiguous (geo+name conflict)** | **37** |
| Reconcile merged (geo) | 0 |
| `category_id` resolved (Tier 1) | **295** (99.3%) |
| **`category_id` unmapped (operator queue)** | **2** |
| EntityCategory rows inserted | 35 (36 inserts - 1 NULL-cat Vanderpump) |

**2 unmapped counter increments** triggered the 1.7 sustainability
branch. Investigation via `outputs/phase5_10_post_load_check.py`
revealed:
- 1 NEW INSERT with NULL category_id: **Vanderpump Rules Lake Havasu
  Luxury Villa** (primary=`service`, _first_seen_domain=`lodging`,
  types[] without `lodging` secondary -- escaping both the existing
  `lodging` direct map's first-match behavior AND any catch-all)
- 1 UPDATE-branch counter increment without DB effect: **JR RV
  Rentals** (primary=`service`, existing cat-10 preserved per
  `places_load.py:537-538` rule)

### Sustainability commit (CONDITIONAL -- triggered by unmapped > 0)

`bf24e16` -- `fix(scripts): _PRIMARY_TYPE_MAP +
_DISCOVERY_DOMAIN_FALLBACK extend for Phase 5.10 sustainability layer`.

Added 5 direct `_PRIMARY_TYPE_MAP` entries in
`app/contrib/google_types_mapping.py`:

```python
"hotel": ("lodging-vacation-rentals", "commercial"),
"motel": ("lodging-vacation-rentals", "commercial"),
"resort_hotel": ("lodging-vacation-rentals", "commercial"),
"extended_stay_hotel": ("lodging-vacation-rentals", "commercial"),
"bed_and_breakfast": ("lodging-vacation-rentals", "commercial"),
```

Plus 1 new `_DISCOVERY_DOMAIN_FALLBACK` catch-all:

```python
(None, "lodging"): "lodging-vacation-rentals",
```

The 5 direct mappings are defensive vs Google types[] array changes
(most lodging-shape entries route correctly via the existing
pre-Phase-5 `lodging` direct mapping's secondary-types[] first-match
behavior -- empirically validated by 4 distinct non-mapped primary
types already in cat-10 today: campground / mobile_home_park /
camping_cabin / service). The NEW `(None, "lodging")` catch-all is
the actual fix for the Vanderpump-style edge case.

Regression tests at `tests/test_phase5_10_places_load_resolver.py` --
**17 collection items** (5 parametrized cat-10 primary_type asserts +
1 catch-all assert + 11 preservation guards). Pytest 1985 -> 2002.
CI green on `bf24e16` (post-push verified).

### Load -- 1.7c re-run POST-sustainability

```
python -m scripts.places_load --category lodging-vacation-rentals
```

| Field | Value |
|---|---|
| Input rows | 297 |
| Inserted (new entities) | 0 (everything in DB from 1.6) |
| Updated (existing place_id) | 260 (224 + 36 newly-in-DB) |
| Reconcile ambiguous | 37 (stable across re-runs) |
| `category_id` resolved (Tier 1) | **297** (100%) |
| **`category_id` unmapped (operator queue)** | **0** |
| EntityCategory rows inserted | 1 (Vanderpump villa flipped NULL -> cat-10) |

**Sustainability commit validation:** 0 unmapped of 297. The 5
direct mappings + 1 new catch-all + existing pre-Phase-5
`lodging`/`rv_park` direct mappings + secondary-types[] first-match
behavior + 5.2 `(None, "lake_recreation") -> "on-the-water"`
catch-all together covered every primary_type Google emitted.

**Post-1.7c cat-10 state:** 67 entities (31 pre-1 baseline + 35 1.6
inserts that landed in cat-10 + 1 Vanderpump flip).

### Total 1 cost

| Step | Cost |
|---|---|
| Discovery (dry-run) | ~$0.10-0.15 |
| Discovery (full) | ~$0.30 |
| Enrichment | ~$0.02 (1 new enrichment) |
| **Total Layer 1** | **~$0.32** |

Under the kickoff 1 revised projection ($0.30-0.60) -- 98.8% cache
reuse + Narrow scope kept burn small.

---

## 2-4 outcomes (summarized; details in `outputs/phase5_10_lodging_audit.md`)

### 2 audit -- Slice plan

| Slice | Action | Count | Records |
|---|---|---|---|
| A | KEEP (no apply) | 67 + many | All 67 cat-10 entries + HEAT Bar stays in cat-1 + lake_rec entries stay in cat-3 |
| B | FLIP cat-X -> cat-10 | 0 | (HEAT Bar named "HEAT Bar" -- identity is a bar) |
| C | FLIP cat-10 -> cat-X | 0 | |
| D | DUAL ADD cat-3 to cat-10 | **0** | (kickoff forecast 2-5; dupe-check confirmed 0 waterfront-primary candidates -- all 3 named candidates are inland coordinates) |
| **E** | NEW creates in cat-10 | **6** | Heat Hotel (406r) + Travelodge by Wyndham (901r) + Knights Inn (266r) + LAKE PLACE INN (64r) + Holiday Inn Express by IHG (619r) + Queens Bay Resort Condominiums (69r) |
| F | KEEP ambig (no apply) | 31 | 29 lake_rec geo-noise + Havasu Suites + Xanadu (both V1.5 carry) |
| G | DRAFT / DELETE | 0 | |

**0 real misroutes** in the 37 ambig records. Notable observations:
- **HEAT Bar <-> Heat Hotel dual-place_id** (5.7/5.8 pattern): same
  physical building (8.6m apart), 2 distinct Google place_ids; both
  kept distinct per primary identity. V1.5 carry for cross-link
  consideration.
- **Havasu Dunes Resort <-> GetAways at Havasu Dunes Resort
  dual-place_id**: same address/coords (620 Lake Havasu Ave), 2
  distinct listings, both cat-10 resort_hotel. V1.5 carry for
  consolidation.
- **Cross-cat axes empirically reframed:** 0 lodging-domain hits on
  cat-3 (the 3 cat-3 ambig hits are all lake_recreation-domain boat
  businesses; no waterfront resorts pre-exist in cat-3 to DUAL).
  1 real cat-1 hit (Heat Hotel <-> HEAT Bar); 24 geo-noise. 0 real
  cat-2 hits; 5 adjacency-only at 73m.

Apply-script `outputs/apply_phase5_10_lodging_audit.py` -- only Slice
E NEW creates fire. Used `select(func.count())` + `session.flush()`
for accurate post-apply count (5.9 reporting-bug FIX). Post-apply
count: 67 -> 73 (delta +6).

### 4 heat_exposure

`outputs/apply_phase5_10_lodging_heat_exposure.py` -- 73 entities
processed:

| Value | Count | Notes |
|---|---|---|
| indoor (default) | 53 | hotels/motels/cottages/vacation rentals/B&Bs/guest_house/camping_cabin/mobile_home_park/service-typed |
| outdoor | 19 | 14 rv_park + 5 inland desert campgrounds |
| water_adjacent | 1 | Lake Havasu State Park Campground (literal waterfront state-park campground) |

0 NULL of 73; gate-5 cleared.

### 4 crowd_notes

`outputs/apply_phase5_10_lodging_crowd_notes.py` -- 10 top-10 entries
got hand-curated short+long. **100% snippet coverage** (5 snippets
each). Top-10 mix: 7 chain hotels (Quality Inn, Hampton, Days Inn,
Travelodge, Studio 6, Sway, Super 8) + 1 chain motel (Studio 6) + 1
campground (Crazy Horse) + 1 resort (Havasu Dunes) + 1 independent
hotel (Island Suites). Highest-rated: Havasu Dunes at 4.4*; lowest:
Super 8 at 3.0*.

### 5 gate verification

`outputs/phase5_10_gate_verification.py` -- 6/6 PASS:
1. 73 entities (target >=20) -- **3.65x target**
2. 0 NULL category_id; 37 ambig reviewed
3. Option C audit doc exists; 0 providers verified via
   azdor/azre/lhc-tourism (no verifier ran)
4. 10 entities with long-form crowd_notes (target >=10)
5. 0 NULL heat_exposure; 53/19/1 mix
6. 73 entities render (target >=15) -- **4.87x target**

"PHASE 5.10 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED -- READY TO SHIP"

---

## Open questions / carry-forward

All carry-forward items documented in `outputs/phase5_10_session_
closeout.md` 6:
- Phase 6 lane amend5-X dispatch (consider extending amend5-8 to
  amend5-10)
- `parks-rec-scrapes` cron fix (carry from 5.7+5.8+5.9)
- V1.5 AZDOR/AZRE/LHC Tourism verifier surfaces
- HEAT Bar / Havasu Dunes dual-place_id consolidations
- Havasu Suites / Xanadu identity verification (uncertain in Slice F)
- 5 waterfront-suggestive RV/campground candidates for water_adjacent
  override review
- 29 lake_recreation-domain ambig records (V1.5 cat-3 NEW creates if
  5.2 lane re-opened)
- Sustainability extensions (`camping_cabin` / `cottage` /
  `mobile_home_park` / `guest_house` direct mappings)

---

*Final scrape log -- populated at 5.10 SHIP time. Phase 5.10
SHIPPED at `<SHIP-COMMIT>` 2026-05-17.*
