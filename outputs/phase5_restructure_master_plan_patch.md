# Phase 5 Restructure — `master_build_plan.md` §4 Patch

> **Purpose:** restructure Phase 5 from one monolithic 4-8 week phase into **Phase 5.0 (shared lead-up & tooling) + Phase 5.1–5.6 (one per Tier 1 category)**. This gives legible progress signal, clean partial-close semantics, and lets the parallel Phase 6 agent consume Phase 5 data per-category as each sub-phase ships.
>
> **Why this is a patch artifact, not a direct edit:** `docs/maintainability/master_build_plan.md` is a shared-surface doc the parallel Phase 6 agent is currently touching. Editing it from the Phase 5 chat while Phase 6 is also in it = guaranteed gotcha-#18 collision. This artifact holds the exact old→new block so it can be applied by whoever has a clean window: the operator directly (~2 min), the Phase 6 agent (already in the file), or the fresh Phase 5 agent as its first action.
>
> **Authored:** Cowork primary, new-chat post-`23a6a1c` session, 2026-05-14.

---

## §1 How to apply

In `docs/maintainability/master_build_plan.md`, find the block starting at `### Phase 5 — Tier 1 data gathering` (currently ~line 244) and ending at the `---` separator immediately before `### Phase 6 — Tier 1 UI build` (currently ~line 271). Replace that entire block with the §3 NEW BLOCK below.

No other part of `master_build_plan.md` changes. The §5 dependency graph already shows `Phase 4 ──→ Phase 5` + `Phase 5/6 overlap` — that stays accurate. The §6 operator-workload row + §7 risk row 10 (heat_exposure) + §9 calendar all still reference "Phase 5" generically and remain correct under the sub-phase structure.

After applying: this is a docs-only change, no migration, no pytest delta. Commit with a PowerShell-safe body (no embedded double-quotes per gotcha #16) — suggested:

```
git commit -m 'docs(master-plan): restructure Phase 5 into 5.0 lead-up + 5.1-5.6 per-category sub-phases' -m 'Phase 5 was one monolithic 4-8 week phase with no internal progress signal. Restructured into Phase 5.0 (shared lead-up and tooling -- the only Phase-4-style sub-phase with a clean engineering done) plus Phase 5.1-5.6 (one per Tier 1 category, independent parallel-capable tracks not a dependency chain). Each sub-phase gets its own SHIPPED ledger line. Partial close-out is now explicit -- if the 8-week ceiling hits, ship the sub-phases that pass their acceptance gate and defer the rest to V1.5. Lets the parallel Phase 6 agent consume each 5.X category as it ships rather than all-or-nothing. Per-category playbooks already live in outputs/cursor_brief_phase_5_tier_1_data.md section-3; this just formalizes the structure in the master plan ledger. Docs-only -- no migration, no pytest delta.'
```

---

## §2 OLD BLOCK (find this exact text)

```markdown
### Phase 5 — Tier 1 data gathering (4-8 weeks, parallel with Phase 6)

**Goal:** Populate Tier 1 categories (Home & Property Services + Health & Wellness + Eat & Drink + On the Water + Auto/RV/Fuel + Shopping). These are the resident-critical spine; making them dense first means the site is immediately useful for residents the moment Phase 6 UI ships.

**Workflow:**
1. **Run Layer 1 (Google Places) for each Tier 1 category** — operator-triggered single batch per category. Estimated 60-200 entities per category from Google.
2. **Run Layer 2 (OSM) where complementary** — primarily for On the Water (marinas + ramps + beaches), parks-adjacent commercial.
3. **Run Layer 3 (city open data) where applicable** — Home & Property gets AZ ROC license cross-referencing.
4. **Run Layer 4 (specialized APIs)** — Health gets NPI cross-reference (already integrated). Eat & Drink gets nothing meaningful (Tripadvisor not in scope).
5. **Manual recovery for Layer 5 gaps** — small mom-and-pop businesses, hobbyist venues, ephemeral locations. Per `manual_recovery_checklist.md` workflow. Estimated 20-40 manual-recovery items for Tier 1 categories.
6. **Operator-curated field entry** — heat_exposure, crowd_notes, boat_access details for restaurants and marinas, seasonal_hours where they differ. Each entity gets ~5-15 minutes of operator review.

**Estimated totals at end of Phase 5:**
- Home & Property Services: 120-220 entries
- Health, Wellness & Care: 30-70 entries
- Eat & Drink: 90-140 entries
- On the Water: 40-90 entries
- Auto, RV & Fuel: 50-100 entries
- Shopping, Grocery & Essentials: 60-120 entries
- **Total Tier 1: 390-740 entries**

**Dependencies:** Phase 4 (scrapers + admin form for operator entry). Runs in parallel with Phase 6 UI work.

**Effort estimate:** Operator workload ~60-100 hours spread over 4-8 weeks. Engineering effort minimal (admin form already shipping in Phase 4).

**Success criteria:** Each Tier 1 category has enough verified inventory that the corresponding category landing page (built in Phase 6) renders 15+ entries per default filter.

---
```

---

## §3 NEW BLOCK (replace with this)

```markdown
### Phase 5 — Tier 1 data gathering (4-8 weeks, parallel with Phase 6) — **restructured into 5.0 + 5.1–5.6 on 2026-05-14**

**Goal:** Populate Tier 1 categories (Home & Property Services + Health & Wellness + Eat & Drink + On the Water + Auto/RV/Fuel + Shopping). These are the resident-critical spine; making them dense first means the site is immediately useful for residents the moment Phase 6 UI ships.

**Structure (2026-05-14 restructure):** Phase 5 decomposes into a shared lead-up sub-phase (5.0) plus six per-category sub-phases (5.1–5.6). Unlike Phase 4's dependency chain, **5.1–5.6 are independent parallel-capable tracks** — the recommended sequence is for operator learning-curve + field-entry batching, not a hard ordering. Each sub-phase gets its own SHIPPED ledger line. **Partial close-out is explicit:** if the 8-week ceiling hits, ship the sub-phases that pass their acceptance gate and defer the rest to V1.5; Phase 6 renders empty-state copy for deferred categories. Per-category playbooks live in `outputs/cursor_brief_phase_5_tier_1_data.md` §3.1–§3.6; operator decisions are locked in that brief's §2 + `outputs/phase5_prereq_checklist.md` §3.5.

#### Phase 5.0 — Lead-up & shared tooling (~1-2 weeks) — gates 5.1–5.6

The only Phase-4-style sub-phase: it has a clean engineering "done."

- **§3 decision-locks** — 11 operator decisions sealed. **SHIPPED `acf5e2b`** (brief §2 + prereq §3.5).
- **Google types-mapping expansion** — ~54 Tier 1 `types[]` entries + beauty skip + RV-park boundary. **SHIPPED `62ab3b7`.**
- **Lead-up content** — `boat_access_rubric.md`, `manual_recovery_checklist.md` back-fill, `heat_exposure_priority_30_list.md` scaffold, Lane B verification briefing. **SHIPPED `b755b03` + `54ca07d` + `4ba29e4`.**
- **Lane B verifications + 3 tooling-touchup scripts** — `scripts/az_roc_verify.py` + `scripts/npi_verify.py` + `scripts/osm_overpass_load.py`, authored against verified endpoint shapes. Dispatch artifact `outputs/cursor_dispatch_prompt_phase5_leadup_tooling.md` **SHIPPED `23a6a1c`**; awaiting Cursor execution.
- **Operator-only actions** — Google Places billing cap (Cloud Console), Phase 4 Railway redeploy to alembic `0a1b2c3d4e5f`, `heat_exposure_priority_30_list.md` operator amendment (fill 22 LHC-venue placeholders).

**5.0 done when:** Lane B's 10 verifications are recorded, the 3 tooling scripts are pytest-green + ruff-clean, the Google Places billing cap is set, prod is redeployed, and the priority-30 list is operator-amended.

#### Phase 5.1 — Eat & Drink (~1-2 weeks) — warm-up category

Target 90-140 entries. Google Places only (no Layer 2/3/4). Pipeline: discovery → enrichment → load → ambiguous-queue triage → Layer 5 manual recovery → operator-curated field entry (`heat_exposure`, `crowd_notes`, `seasonal_hours`). **Acceptance gate:** 60+ entries loaded, all ambiguous hits reviewed, top-20 have long-form `crowd_notes`, every entry has `heat_exposure`, Phase 6 `/category/eat-drink` smoke renders 15+ per default filter.

#### Phase 5.2 — On the Water (~1-2 weeks)

Target 40-90 entries. Google Places + **OSM Layer 2** (`leisure=marina` + `man_made=pier` + `natural=beach`) + LHC Parks & Rec Layer 3. Heaviest operator-curated surface: `boat_access` JSON per `docs/operations/boat_access_rubric.md`. **Acceptance gate:** 25+ entries, every marina has `boat_access` populated, Google+OSM ambiguous hits reviewed, Phase 6 `/category/on-the-water` + boat-mode toggle both render ≥15.

#### Phase 5.3 — Home & Property Services (~2-3 weeks)

Target 120-220 entries (highest-volume category). Google Places + **AZ ROC Layer 3** license cross-reference via `scripts/az_roc_verify.py`. **Acceptance gate:** 80+ entries, AZ ROC coverage on every licensed-trade entry, `is_mobile_service` populated on every entry, Phase 6 `/category/home-property-services` renders ≥15.

#### Phase 5.4 — Health, Wellness & Care (~1-2 weeks)

Target 30-70 entries. Google Places + **NPI Layer 4** cross-reference via `scripts/npi_verify.py`. **Acceptance gate:** 20+ entries, NPI coverage on every practitioner-led practice, mental-health + alternative-medicine Layer 5 coverage, Phase 6 `/category/health-wellness-care` renders ≥15.

#### Phase 5.5 — Auto, RV & Fuel (~1-2 weeks)

Target 50-100 entries. Google Places + Layer 5. **Acceptance gate:** 30+ entries, `is_mobile_service` populated on every entry, RV-specific Layer 5 coverage, Phase 6 `/category/auto-rv-fuel` renders ≥15.

#### Phase 5.6 — Shopping, Grocery & Essentials (~1-2 weeks)

Target 60-120 entries. Google Places + Layer 5 + (conditional) LHC business-license Layer 3 if Lane B §3 surfaced a viable endpoint. **Acceptance gate:** 40+ entries, independent-boutique Layer 5 coverage, Phase 6 `/category/shopping-essentials` renders ≥15.

**Estimated totals at end of Phase 5:**
- Home & Property Services: 120-220 entries
- Health, Wellness & Care: 30-70 entries
- Eat & Drink: 90-140 entries
- On the Water: 40-90 entries
- Auto, RV & Fuel: 50-100 entries
- Shopping, Grocery & Essentials: 60-120 entries
- **Total Tier 1: 390-740 entries**

**Dependencies:** Phase 4 (layered-scrape framework + reconciler + Outbox — SHIPPED). Phase 5.1–5.6 each depend on Phase 5.0. Runs in parallel with Phase 6 UI work; Phase 6 consumes each 5.X category as it ships.

**Effort estimate:** Operator workload — original master estimate 60-100h; bottom-up audit (`outputs/phase5_prereq_checklist.md` §5) re-derives 83-351h; **realistic mid-range budget: 100-150h over 6-8 weeks.** The long pole is operator-curated field entry (390-740 entries × 5-15 min each). Engineering effort minimal — the 3 tooling-touchup scripts in 5.0, plus reactive `GEO_PROXIMITY_THRESHOLD_M` tuning if a scrape surfaces >50 ambiguous hits.

**Success criteria:** Each of 5.1–5.6 meets its per-category acceptance gate (15+ entries per default filter on the corresponding Phase 6 category landing page). Phase 5 SHIPPED when all six pass; partial close-out (ship the passing sub-phases, defer the rest to V1.5) is acceptable at the 8-week ceiling.

---
```

---

## §4 Notes on what does NOT change

- **§5 dependency graph** — `Phase 3 ──→ Phase 4 ──┬─→ Phase 5 / └─→ Phase 6` stays accurate; sub-phase structure is internal to Phase 5.
- **§6 operator-workload schedule** — the "Field-trip Layer 5 manual recovery / Phase 5 / ~30-50 hours" row stays correct.
- **§7 risk register row 10** — heat_exposure dependency still references "Phase 5/6"; correct.
- **§9 calendar** — Month 3/4/5 Phase 5 references stay correct under the sub-phase structure.
- **§2 "What's already shipped"** + **§10 decision log** — optionally add a decision-log entry for the 2026-05-14 restructure, but not required for the patch to be valid.

---

*Authored by Cowork primary at the new-chat post-`23a6a1c` session (2026-05-14). Lives at `outputs/phase5_restructure_master_plan_patch.md` — brand-new outputs/ file, safe under the parallel-chat lock. Apply to `master_build_plan.md` from a clean window on that shared doc.*
