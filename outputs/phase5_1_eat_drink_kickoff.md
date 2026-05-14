# Phase 5.1 Kickoff — Eat & Drink (`eat-drink`)

> **What this is:** a single paste-and-go operator runbook for Phase 5.1, the
> warm-up category of Tier 1 data gathering. It consolidates the brief §3.1
> per-category playbook, the §0 baseline checks, and the §5 daily/weekly rhythm
> into one place so the operator doesn't have to cross-reference three docs at
> dispatch time. Pre-staged by Cowork primary while Phase 5.0 closes — ready the
> moment the gate opens.
>
> **GATE — do not start until all four Phase 5.0 items have closed:**
> 1. B1 — Lane B Cursor dispatch complete (10 verifications + 3 tooling scripts, both HALTs committed)
> 2. B2-a — Google Places API billing confirmed active + spend cap set *(hard blocker — §8 of the Lane B briefing)*
> 3. B2-b — Phase 4 Railway redeploy done (prod alembic walked to `0a1b2c3d4e5f`)
> 4. B2-c — `heat_exposure_priority_30_list.md` operator-amended + committed
>
> If any of the four is open, Phase 5.1 is not dispatchable yet. See
> `outputs/new_chat_kickoff_phase_5_0.md` for the punch list and
> `outputs/phase5_0_readiness_audit.md` for the disk-state verification.
>
> **Authored by:** Cowork primary, Phase 5 lane, new-chat post-`dc11430` session
> (2026-05-14). Brand-new `outputs/` file — safe under the parallel-chat scope lock.

---

## §0 Pre-flight (do once, at Phase 5.1 dispatch)

Confirm before the first scrape command:

1. **`git log --oneline -12`** — origin should top at the Phase 5.0 close-out chain
   (the Lane B Phase B commit + the three operator-action commits). If the tree
   looks unfamiliar, the parallel Phase 6 agent has pushed — read the unfamiliar
   commits before proceeding.
2. **`git status`** — clean.
3. **`python -m alembic heads`** — single head `0a1b2c3d4e5f`. Phase 5.1 ships **no
   migrations**.
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — record the real
   baseline. As of 2026-05-14 it is **1820** (post-Phase-6.1), plus whatever the
   Lane B Phase B tooling tests added. Do not trust the "1795" / "~1803" figures in
   the older briefs — they predate Phase 6.1.
5. **Prod deploy** — confirm B2-b landed: prod alembic is `0a1b2c3d4e5f`, the
   `outbox` table exists, the `with_retry` wrappers are live. Real scrape failures
   should land in the Outbox redrive surface, not vanish.
6. **Google Places key** — confirm B2-a: key active, Places API (New) enabled,
   spend cap set (~$200/mo recommended). The Eat & Drink run costs roughly
   ~$5–9 discovery + ~$100 enrichment depending on row count.

---

## §1 The scrape sequence

Per-category, in order — discover → enrich → load → review. The locked sequencing
(brief §3.2.d) is per-category for blast-radius reasons; Eat & Drink is the
warm-up that proves the pipeline.

```
# 1. Sanity check — dry-run discovery, ~$1, no DB writes
python -m scripts.places_discovery --category eat-drink --dry-run

# 2. Full discovery for the eat-drink vertical
python -m scripts.places_discovery --category eat-drink
#    → writes scripts/output/places_pull/discovery_unique.jsonl

# 3. Enrich the discovered rows (Place Details + reviews/photos field mask)
python -m scripts.places_enrichment --limit 200
#    → resume-safe; writes scripts/output/places_pull/enrichment_enriched.jsonl
#    → ~$0.040/call; for ~150 eat-drink rows that's ~$6

# 4. Dry-run the load — parse + ZIP-filter only, no DB writes
python -m scripts.places_load --dry-run

# 5. Load into the DB with the reconciler
python -m scripts.places_load
#    → upserts by google_place_id; runs each hit through reconcile_hit;
#      emits reconcile_skipped_ambiguous / reconcile_merged_geo counts
```

**`types[]` coverage is already in place** — `google_types_mapping.py` carries all
17 Eat & Drink types (`restaurant`, `cafe`, `bar`, `bakery`, `meal_delivery`,
`meal_takeaway`, `fast_food_restaurant`, `dessert_shop`, `wine_bar`, `pub`,
`pizza_restaurant`, `seafood_restaurant`, `mexican_restaurant`,
`breakfast_restaurant`, `barbecue_restaurant`, `coffee_shop`, `ice_cream_shop`),
all mapping to `("eat-drink", "commercial")`. Verified on disk — see
`outputs/phase5_0_readiness_audit.md` §2.1. No tooling-touchup needed before the
first scrape.

**Supplemental layers for Eat & Drink:** none. No Layer 2 (OSM thin for
restaurants), no Layer 3, no Layer 4. Single-layer Google + Layer 5 manual
recovery only. This is why Eat & Drink is the warm-up — it isolates the core
pipeline from the cross-reference tooling.

**Write a scrape log** after the run: `docs/scrape_logs/eat-drink_<YYYY-MM-DD>.md`
per the `docs/operations/scrape_logs_template.md` template — counts, cost,
ambiguous-hit count, anything surprising.

> **⚠ Operational question to settle on the first run:** the per-category
> sequencing assumes `discovery_unique.jsonl` and `enrichment_enriched.jsonl` are
> safe to treat per-category. Discovery dedupes by Place ID; enrichment is
> append-mode + resume-safe. Before running the **second** category (5.2 On the
> Water), confirm whether you want to (a) archive/clear the eat-drink JSONLs first
> so each category's files are clean, or (b) let them accumulate and rely on the
> load step's `google_place_id` upsert idempotency. Either works, but decide
> deliberately — don't let category 2's discovery silently append onto category
> 1's file and then re-enrich the whole pile. Recommended: archive the eat-drink
> JSONLs to `scripts/output/places_pull/archive/eat-drink/` after load, start 5.2
> clean.

---

## §2 Ambiguous-queue review (locked: direct DB query, no admin form)

After the load, review what the reconciler flagged. Per brief §3.2.f — no admin
form in Phase 5, direct DB query:

```sql
SELECT id, name, source, created_at
FROM entities
WHERE source LIKE 'google_places%'
ORDER BY created_at DESC
LIMIT 50;
```

The `log_ambiguous_reconcile` calls also structure the `places_load` log output,
so `grep "ambiguous" docs/scrape_logs/eat-drink_*.md` is a workable secondary path.

- Expect ~20–40 ambiguous hits for a first category run; that's normal.
- **If >50 ambiguous "geo-within-50m + name-mismatch" hits:** pause. Tune
  `GEO_PROXIMITY_THRESHOLD_M` (currently `50.0` in `app/contrib/ingest_reconciler.py`)
  before continuing — a small Cursor dispatch per brief §4.g. Eat & Drink's English
  Village cluster is dense; 30m may fit better there.
- Eat & Drink is single-layer (Google only), so cross-source ambiguity should be
  *low* — most ambiguity here is Google-vs-existing-DB rows. If it's high, that's a
  signal worth understanding before scaling to multi-layer categories.

---

## §3 Layer 5 manual recovery

Things Google doesn't carry. Field-work prompts (where to look / what to record)
are in `docs/maintainability/manual_recovery_checklist.md` — for Eat & Drink:

- **Food trucks + meet-ups** — `manual_recovery_checklist.md` §4 "Food truck
  regulars + meet-ups." Lake Havasu food-truck Facebook groups; weekly meet-up
  venues; Friday-night gathering spots.
- **River Scene magazine restaurant features** — sample-issue scan, cross-reference
  against the Google output.
- **Seasonal vendors** — winter-only RV-park restaurants; capture `seasonal_hours`.
- **Dock-and-dine spots without Google listings** — operator boat survey; these
  also need `boat_access` JSON per `docs/operations/boat_access_rubric.md` §4
  (shoreline commercial shape).

The `manual_recovery_checklist.md` §7 field-trip planner puts the **English Village
+ Channel sweep** as second-highest-value — that sweep catches the channel-side
dock-and-dine restaurants, which is most of the Eat & Drink Layer-5 surface.

---

## §4 Operator-curated field entry — Eat & Drink rubric

Per brief §3.1 + the locked rubrics. Enter via direct DB SQL or the existing
`admin/*` HTML surfaces (no Phase 5 admin form).

- **`heat_exposure`** — `outdoor` for patio-only / outdoor-seating-prevalent
  venues; `water_adjacent` for shoreline restaurants; `shaded` for covered patios;
  `indoor` is the default for everything else. **Only tag off-default for entities
  on the amended `heat_exposure_priority_30_list.md`** — don't second-guess the
  default across every row. The priority-30 list includes the English Village
  waterfront restaurant cluster (each restaurant entity → `water_adjacent`) and a
  few notable shaded patios.
- **`crowd_notes`** — short-form (1 sentence) for typical venues; long-form
  (multi-paragraph) only for the top-20 highest-volume venues — English Village
  restaurants, Aquatic Park dock-and-dines, Friday-night BBQ spots.
- **`boat_access`** — only for shoreline restaurants. Use the shoreline-commercial
  shape: `{"dockable": bool, "ramp_walkable_m": N}` per `boat_access_rubric.md` §4.
- **`seasonal_hours`** — critical for any snowbird-schedule venue; JSON schema is
  summer / winter / shoulder blocks.

---

## §5 Daily / weekly rhythm (brief §5)

Phase 5 burns operators out if structured poorly. Cap field-entry sessions at
~2h/day. Suggested week:

| Day | Work |
|---|---|
| 1 | Scrape run (~30 min incl. review) + scrape log markdown |
| 2 | Ambiguous-queue triage via direct DB query (~30–60 min) |
| 3–5 | Operator-curated field entry, ~1.5h × 3 sessions ≈ 5h |
| 6 | Layer 5 manual-recovery hour |
| 7 | QA spot-check — 20 random entries validated against the §4 rubric |

≈7–9 operator hours/week. **Expected Eat & Drink total: 10–25 hours over 1–2
weeks** (~3h scrape + review, ~7–22h field entry depending on long-form
`crowd_notes` coverage). Reward landmark: every 50 entries field-entered = ✓.

---

## §6 Acceptance gate — Phase 5.1 closes when ALL of:

- [ ] **60+ entries** in `eat-drink` post-load (low end of the 90–140 estimate)
- [ ] All ambiguous reconciler hits reviewed via direct DB query
- [ ] Top-20 entries have long-form `crowd_notes` populated
- [ ] `heat_exposure` set on every entry (no NULL — default `indoor` counts)
- [ ] Phase 6 `/category/eat-drink` smoke renders **15+ entries per default filter**

When the gate is met: commit the final scrape log(s), and Phase 5.1 gets its
SHIPPED ledger line on `master_build_plan.md` §4. Then **Phase 5.2 On the Water**
dispatches as the next per-category sub-phase — that one is multi-layer (Google +
OSM via the new `osm_overpass_load.py` from the Lane B Phase B dispatch) and is
where the `boat_access` JSON entry rhythm gets built.

---

## §7 Reference

- `outputs/cursor_brief_phase_5_tier_1_data.md` §3.1 (the source playbook) + §5 (rhythm) + §9 (sequencing)
- `outputs/phase5_0_readiness_audit.md` (disk-state verification of the §3 lock-batch)
- `docs/operations/scrape_logs_template.md` (the per-run log template)
- `docs/operations/boat_access_rubric.md` §4 (shoreline-commercial shape for dock-and-dines)
- `docs/maintainability/manual_recovery_checklist.md` §4 + §7 (Layer-5 prompts + field-trip planner)
- `outputs/heat_exposure_priority_30_list.md` (the tag-or-default decision tree — must be operator-amended first, B2-c)

---

*Pre-staged by Cowork primary, Phase 5 lane, new-chat post-`dc11430` session
(2026-05-14), while Phase 5.0 closes. Lives at `outputs/phase5_1_eat_drink_kickoff.md`
— brand-new `outputs/` file, safe under the parallel-chat scope lock. Not a Cursor
dispatch — Phase 5.1 is operator-driven scrape + field work per the brief §10
"no Phase 5 dispatch prompt artifact" note; this runbook just collapses the
cross-references into one page.*
