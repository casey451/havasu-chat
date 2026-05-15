# Phase 5.2 Kickoff — On the Water (`on-the-water`)

> **What this is:** a single paste-and-go operator runbook for Phase 5.2, the second
> Tier 1 category. Consolidates the brief §3.2 per-category playbook, the §0 baseline
> checks, and the §5 daily/weekly rhythm into one page. This is the first **multi-layer**
> category — Google Places *plus* OSM Overpass — and the one where the `boat_access` JSON
> entry rhythm gets built (it feeds the V1 boat-mode UI). Pre-staged by Cowork primary.
>
> **GATE 1 — do not start until Phase 5.1 (Eat & Drink) has closed** its acceptance gate
> (`outputs/phase5_1_eat_drink_kickoff.md` §6). Per brief §3.2.d, categories run one at a
> time.
>
> **GATE 2 — do not run the OSM load step (§1 step 6) until `osm_overpass_load.py` is
> priority-fixed.** See the ⚠️ callout in §1. This is task #5 in the Cowork task list.
>
> **Authored by:** Cowork primary, Phase 5 lane, new-chat post-`5d429aa` session
> (2026-05-14). Brand-new `outputs/` file — safe under the parallel-chat scope lock.

---

## §0 Pre-flight (do once, at Phase 5.2 dispatch)

1. **`git log --oneline -12`** — origin should top at the Phase 5.1 close-out chain. Read
   any unfamiliar commits (the parallel Phase 6 agent may have pushed).
2. **`git status`** — clean.
3. **`python -m alembic current`** — confirm the *local DB* is actually at
   `0a1b2c3d4e5f`, not just that the migration files' head is. If it is behind, run
   **`python -m alembic upgrade head`**. Phase 5.2 ships **no migrations**, but the local
   `data/events.db` must be migration-current before any `places_load` run — Phase 5.1 lost
   a session to a DB stamped behind its schema (see `outputs/phase5_1_field_entry_handoff.md`
   §4, drift #3/#4).
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — record the real baseline
   (1825+ as of the Phase 5.0 tooling commit `5d429aa`; verify — Phase 6 + the §1 task-#5
   fix may have moved it).
5. **Confirm the OSM tooling chain works end-to-end on a dry run** before the real pull:
   `python -m scripts.osm_overpass_pull --tag leisure --value marina` produces a JSONL,
   and `python -m scripts.osm_overpass_load --dry-run --tag leisure --value marina` reads
   it without error. Check that the pull's output path matches the load's `--input`
   (default `scripts/output/osm_pull/osm_elements.jsonl`) — pass `--input` explicitly if not.
6. **Google Places key + spend cap** — still active from Phase 5.0 B2-a.

---

## §1 The scrape sequence — Google first, then OSM

On the Water is multi-layer. Run **Google fully first**, then **OSM** — that order matters
for the reconciler (see the ⚠️ callout below).

### Layer 1 — Google Places

```
python -m scripts.places_discovery --category on-the-water --dry-run        # sanity check
python -m scripts.places_discovery --category on-the-water                  # full discovery
python -m scripts.places_enrichment --limit 200                             # enrich
python -m scripts.places_load --category on-the-water --dry-run             # parse + ZIP + category filter
python -m scripts.places_load --category on-the-water                       # load with reconciler
```

**`--category on-the-water` is required on `places_load`** (the flag was added in Phase
5.1, commit `7455848`). `enrichment_enriched.jsonl` is shared across all categories and
already carries rows from prior scrapes — without the flag, `places_load` loads every
domain. The slug resolves to the `lake_recreation` discovery domain. The enrichment file
already holds ~280 enriched `lake_recreation` rows from a prior comprehensive scrape, so
enrichment here will be mostly resume-skips, and the load picks those up too.

`types[]` coverage is already in place — `google_types_mapping.py` carries `marina`,
`beach`, `harbor`, `boat_dealer`, `boat_rental` for this category (verified on disk,
`outputs/phase5_0_readiness_audit.md` §2.1). Note: marinas/beaches map to `place`,
dealers/rentals to `commercial` — Google's `types[]` doesn't always disambiguate, so
operator review of the place-vs-commercial split is expected.

### Layer 2 — OSM Overpass (the supplemental layer)

```
python -m scripts.osm_overpass_pull --tag leisure  --value marina
python -m scripts.osm_overpass_pull --tag man_made --value pier
python -m scripts.osm_overpass_pull --tag natural  --value beach
# then, for each pulled JSONL:
python -m scripts.osm_overpass_load --tag leisure  --value marina   # + --input if path differs
python -m scripts.osm_overpass_load --tag man_made --value pier
python -m scripts.osm_overpass_load --tag natural  --value beach
```

OSM scope is locked (brief §3.2.e) to exactly these three `(tag, value)` pairs for
`on-the-water` only — no other OSM tags in Phase 5.

> **⚠️ GATE 2 — fix `osm_overpass_load.py` before running the load step above.** The
> script's reconciler `update` branch blanket-overwrites the Provider with OSM data on a
> geo+name collision — and because OSM is a *lower-priority* source than Google, that
> clobbers `google_place_id → None`, `verified → False`, `source → osm`, and replaces good
> contact fields with OSM's sparser/None values. On-the-water is exactly where this bites:
> you've just loaded Google marinas, and OSM marinas will collide with them on "geo within
> 50m + name match." **Before the OSM load step, either:** (a) get the small priority-aware-
> update fix shipped — on an OSM `update`, fill-gaps-only and never downgrade
> `verified`/`google_place_id`/`source` (Cursor touchup, `scripts/`-only, task #5 in the
> Cowork list); **or** (b) accept it and manually re-fix any clobbered Google rows after the
> OSM load. Option (a) is strongly preferred — it's a ~30-minute fix and option (b) is
> error-prone. Verify `osm_overpass_load.py`'s update branch before you run it.

### Layer 3 — LHC Parks & Rec (city facility list)

Boat ramps + public beaches from the city — reuse the existing `parks-rec-scrapes.yml`
workflow output (the GitHub Actions cron). Lane B §10 found that workflow healthy
(recent runs green); cross-check its latest snapshot for ramp/beach rows.

**Write a scrape log** per run: `docs/scrape_logs/on-the-water_<YYYY-MM-DD>.md` per
`docs/operations/scrape_logs_template.md`.

---

## §2 Ambiguous-queue review — expect more volume here

On the Water is a **high-overlap category** — Google and OSM both cover marinas, piers,
and beaches, so the reconciler will surface more `ambiguous` hits than Eat & Drink did.
Brief §3.2 estimates **5–15 ambiguous hits per OSM run**. Review via direct DB query
(brief §3.2.f, locked — no admin form):

```sql
SELECT id, name, source, created_at
FROM entities
WHERE source LIKE 'google_places%' OR source LIKE 'osm%' OR source LIKE '%,osm%'
ORDER BY created_at DESC
LIMIT 50;
```

If a single OSM run produces **>50** "geo-within-50m + name-mismatch" ambiguous hits,
pause and tune `GEO_PROXIMITY_THRESHOLD_M` (currently `50.0` in
`app/contrib/ingest_reconciler.py`) before continuing — brief §4.g, small Cursor touchup.

---

## §3 Layer 5 manual recovery

Per `docs/maintainability/manual_recovery_checklist.md` §2 ("Boat ramps + marinas",
"Public beaches + lake-access points", "Fishing access points") — the most field-work-heavy
Layer-5 category. Prompts:

- BLM / state-land **primitive launches** not on Google or OSM
- **Private-property dock access** points the operator can legitimately surface (with owner consent)
- **Seasonal water-level spots** — cove access points that disappear at low lake
- Small **kayak launches** and unofficial beach access

The `manual_recovery_checklist.md` §7 field-trip planner puts the **Lakefront sweep** as
*highest-value first* — a full Saturday morning covering Lake Havasu State Park, Cattail
Cove, Site Six, Castle Rock beaches, Pittsburgh Point. That single sweep densely populates
this category's Layer 5.

---

## §4 Operator-curated field entry — On the Water rubric

This is the category where field entry is heaviest, because `boat_access` is the dominant
surface and it feeds the V1 boat-mode UI.

- **`heat_exposure`** — `water_adjacent` for essentially everything in this category (it's
  the defining attribute). Cross-check against the locked `heat_exposure_priority_30_list.md`
  §3 — most of that section is on-the-water venues.
- **`boat_access`** — **the dominant operator-curated surface for Phase 5.** Populate per the
  four canonical shapes in `docs/operations/boat_access_rubric.md`:
  - Marinas → `{"ramps": N, "slips": N, "fuel": bool, "haul_out": bool, "pump_out": bool, "transient_dock": bool}`
  - Public ramps → `{"trailer_ramp": bool, "kayak_launch": bool, "dock_walk_m": N|null, "parking_spaces": N}`
  - Beaches → `{"trailer_ramp": bool, "kayak_launch": bool, "swimming_marked": bool}`
  - Shoreline commercial → `{"dockable": bool, "ramp_walkable_m": N}`
  Remember the rubric's `null`-vs-`0`-vs-`{}` semantics — `{}` means "not yet field-verified,"
  don't guess booleans.
- **`crowd_notes`** — critical for weekend-busy marinas (parking, fuel-dock wait times);
  short-form for typical entries; skip for unofficial ramps. Long-form for the top-10
  marinas + ramps.
- **`seasonal_hours`** — most marinas/ramps stay open year-round but with reduced winter
  hours; document where the shift is material.

---

## §5 Daily / weekly rhythm (brief §5)

Same cadence as Phase 5.1 — ~2h/day field-entry cap, ~7–9 operator hours/week:

| Day | Work |
|---|---|
| 1 | Google scrape run + scrape log |
| 2 | OSM pull + load (after the GATE 2 fix) + ambiguous-queue triage |
| 3–5 | `boat_access` + field-entry sessions (~1.5h × 3 ≈ 5h) — the heavy part |
| 6 | Layer 5 — the Lakefront field-trip sweep |
| 7 | QA spot-check — 20 random entries vs. the §4 rubric |

**Expected On the Water total: 15–30 hours over 1–2 weeks** (~5h scrape + review incl.
OSM, ~10–25h field entry — `boat_access` entry is detail-heavy).

---

## §6 Acceptance gate — Phase 5.2 closes when ALL of:

- [ ] **25+ entries** in `on-the-water` post-load (low end of the 40–90 estimate)
- [ ] **Every marina has `boat_access` JSON populated**
- [ ] All Google ↔ OSM ambiguous reconciler hits reviewed via direct DB query
- [ ] Top-10 marinas + ramps have `crowd_notes`
- [ ] `heat_exposure` set on every entry (`water_adjacent` for most)
- [ ] Phase 6 `/category/on-the-water` **and** the boat-mode toggle smoke both render **≥15**

When the gate is met: commit the scrape logs, Phase 5.2 gets its SHIPPED ledger line on
`master_build_plan.md` §4, and **Phase 5.3 Home & Property Services** dispatches next —
that one introduces the AZ ROC cross-reference (task #6 — `az_roc_client.lookup_contractor`
is currently a stub and needs a real implementation or the manual-top-30 fallback before
5.3 can actually verify anything).

---

## §7 Reference

- `outputs/cursor_brief_phase_5_tier_1_data.md` §3.2 (source playbook) + §3.2.e (OSM scope lock) + §5 (rhythm) + §9 (sequencing)
- `outputs/phase5_1_eat_drink_kickoff.md` (the prior category's runbook — same shape)
- `outputs/phase5_0_readiness_audit.md` §3 (the `osm_overpass_load.py` priority caveat origin)
- `docs/operations/boat_access_rubric.md` (the 4 canonical `boat_access` shapes — the core reference for §4)
- `docs/operations/scrape_logs_template.md` (per-run log template)
- `docs/maintainability/manual_recovery_checklist.md` §2 + §7 (Layer-5 prompts + the Lakefront field-trip sweep)
- `outputs/heat_exposure_priority_30_list.md` §3 (the water_adjacent priority venues)
- `scripts/osm_overpass_pull.py` + `scripts/osm_overpass_load.py` (the Layer-2 pull + load chain)

---

*Pre-staged by Cowork primary, Phase 5 lane, new-chat post-`5d429aa` session (2026-05-14),
while Phase 5.0 closes. Lives at `outputs/phase5_2_on_the_water_kickoff.md` — brand-new
`outputs/` file, safe under the parallel-chat scope lock. Not a Cursor dispatch — Phase 5.2
is operator-driven scrape + field work; this runbook collapses the cross-references into
one page and surfaces the two gates (Phase 5.1 must close first; `osm_overpass_load.py`
must be priority-fixed before the OSM load step).*
