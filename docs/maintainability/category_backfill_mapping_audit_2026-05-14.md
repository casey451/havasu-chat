# Category Backfill Mapping — Audit Memo (2026-05-14)

> **Authored:** sub-agent investigation lane dispatched by Cowork primary, 2026-05-14.
> **Inputs read:** `docs/maintainability/category_backfill_mapping_DRAFT.md`; `outputs/chatgpt_taxonomy_research_synthesis.md` §1 + §6; `alembic/versions/e7f8a9b0c1d2_directory_v1_schema.py`; `docs/maintainability/master_build_plan.md` §3 + §4 Phase 3; `docs/STRATEGY_PIVOT_2026-05-12.md` §8.1.
> **Premise confirmed:** the DRAFT exists, is non-empty, maps 41 distinct legacy strings to the *original* 12 slugs (the ones seeded by `e7f8a9b0c1d2`), and was authored 2026-05-13 — one day before the ChatGPT taxonomy synthesis locked a structurally restructured 12 on 2026-05-14.

---

## §1 — Inventory: original 12 vs new 12

The seeded list in `e7f8a9b0c1d2` (production DB right now) and the locked list in synthesis §1 are both "12 categories" but only partially overlap.

| Original slug (seeded) | New slug (synthesis §1) | Relationship |
|---|---|---|
| `eat-and-drink` | `eat-drink` | **Rename, same scope** ("tighter boundaries") |
| `events` | `events` | **Identical** (kept, ship-later priority) |
| `family` | — | **DELETED** ("too broad/fuzzy; reborn as cross-cutting filter") |
| `home-services` | `home-property-services` | **Rename + broaden scope** |
| `health` | `health-wellness-care` | **Rename + broaden** |
| `on-the-water` | `on-the-water` | **Identical slug**, broadened scope (full boating stack) |
| `outdoors-and-parks` | `outdoors-parks-trails` | **Rename + broaden** (adds trails) |
| `shopping` | `shopping-essentials` | **Rename + reframe** ("essentials-first"; absorbs grocery) |
| `auto-and-gas` | `auto-rv-fuel` | **Rename + broaden** (adds RV) |
| `lodging` | `lodging-vacation-rentals` | **Rename + broaden** (absorbs vacation rentals) |
| `pets` | `pets` | **Identical slug**, broader scope |
| `community` | — | **DELETED** ("catch-all bucket with no clean schema; split into Public & Civic + Events + Classes/Sports") |
| — | `classes-sports-recreation` | **NEW** (replaces Family as schedulable activity inventory) |
| — | `public-civic-resources` | **NEW** (splits from Community; trust/retention) |

**Structural delta:** 3 identical slugs, 7 renames (1 trivial + 6 rename-plus-scope-change), 2 deletions, 2 net-new. The 12-count is preserved by a 2-for-2 swap, not by a clean rename map.

---

## §2 — DRAFT mapping audit against the new 12

The 41 legacy strings group into buckets by audit outcome. All 41 DRAFT targets resolve cleanly against the ORIGINAL 12 — confirmed; the DRAFT was authored against the seeded list. The interesting work is projecting forward against the new 12.

### Bucket A — Carries forward unchanged (rename-only at the target)

These strings mapped to a slug that survives in the new taxonomy with the same conceptual scope. Only the slug *string* changes downstream. **No operator decision required.**

| Legacy string(s) | DRAFT target (orig) | New-taxonomy target | Notes |
|---|---|---|---|
| `health_medical` | `health` | `health-wellness-care` | Direct carry. |
| `food_drink`, `food`, `restaurant`, `bakery` | `eat-and-drink` | `eat-drink` | Direct carry; "tighter boundaries" doesn't displace these. |
| `home_services`, `general_contractor`, `plumbing`, `services` (test) | `home-services` | `home-property-services` | Direct carry; scope expanded but legacy contents fit. |
| `retail` | `shopping` | `shopping-essentials` | Direct carry; essentials-inclusive. |
| `lake_recreation`, `boat_repair`, `boat_rental` | `on-the-water` | `on-the-water` | Identical slug; on-the-water broadens. |
| `auto` | `auto-and-gas` | `auto-rv-fuel` | Direct carry; RV addition doesn't break existing mappings. |
| `lodging` | `lodging` | `lodging-vacation-rentals` | Direct carry; VR absorption expands scope. |
| `pet`, `pets`, `veterinary` | `pets` | `pets` | Identical slug, broader scope. |
| `event_venue`, `music` (test) | `events` | `events` | Identical slug. |
| `uncategorized`, `misc`, `other`, `svc`, `fun`, `bmx`/`bmxcaptest`/`onxcat`, `space_pirates` | `NULL` (operator queue) | `NULL` (operator queue) | No-change recommendation; review queue is taxonomy-agnostic. |

**Bucket A count: ~24 of 41 strings. The bulk of the DRAFT carries forward as a slug-string find/replace.**

### Bucket B — DRAFT pointed at a DELETED original slug (mapping is BROKEN)

The DRAFT chose `family` or `community` as the target — both gone in the new taxonomy.

| Legacy string | DRAFT target | Status under new 12 | Recommended new destination |
|---|---|---|---|
| `childcare_education` (places) | `family` (High) | BROKEN | `classes-sports-recreation` — childcare/preschool/tutoring/music lessons/driving schools are exactly the "schedulable activity inventory" Classes-Sports-Rec replaces Family with. Strong fit. |
| `education` (catalog + test) | `family` (Medium) | BROKEN | `classes-sports-recreation`. Driving school / music lessons / adult ed all fit. **OPERATOR DECISION:** is K-12 / charter / public school under Civic Resources or Classes-Sports-Rec? Synthesis §1 doesn't specify. |
| `edu` (test) | `family` (Medium) | BROKEN | Same as `education` → `classes-sports-recreation` likely, but test fixture; recommend NULL operator queue. |
| `religion_community` | `community` (High) | BROKEN | `public-civic-resources` is the obvious destination (synthesis explicitly names "civic orgs" in Phase 8 deliverables; faith orgs fit the trust/retention bucket). |
| `insurance` | `community` (Medium) | BROKEN — and arguably broken in original too | No clean target in the new 12. Synthesis §7 Q5 explicitly defers professional services (lawyers/accountants/insurance) to V1.5+. Recommend NULL operator queue (defer). |
| `financial` | `community` (Medium) | BROKEN | Same as `insurance` — no clean home; defer to operator queue per §7 Q5. |
| `legal` | `community` (Medium) | BROKEN | Same — defer per §7 Q5. |
| `real_estate` | `community` (Low, flagged §3) | BROKEN | Still no clean home. Synthesis doesn't add a real-estate category. Recommend NULL operator queue; revisit at V1.5. |
| `professional_services` (places) | `community` (Medium, flagged §3) | BROKEN — high-volume catch-all | The genuinely painful one. Photographers → `events`. Banks/accountants/lawyers → defer per §7 Q5. Real estate agents → defer. **OPERATOR DECISION REQUIRED:** NULL operator queue for the whole bucket; follow-up triage using `google_primary_category` as splitter (same pattern DRAFT §3 #5 proposed for `entertainment_attractions`). |
| `barbershop` (test) | `community` (Medium) | BROKEN | No clean target. Beauty-personal-care unresolved; same problem. See Bucket C. |

**Bucket B count: 10 strings.** Half become CLEANER under the new taxonomy (`childcare_education`/`education` → `classes-sports-recreation` is a much better fit than `family`; `religion_community` → `public-civic-resources` is clean). The other half (`insurance`/`financial`/`legal`/`real_estate`/`professional_services`/`barbershop`) get WORSE — `community` was the explicit catch-all and the new taxonomy doesn't have one.

### Bucket C — DRAFT was already ambiguous (§3 of DRAFT) — re-audited against new 12

| Legacy string | DRAFT §3 recommendation | New-taxonomy outcome |
|---|---|---|
| `beauty_personal_care` | `community` for V1 (or file 13th category) | BROKEN. New taxonomy has no `community`; `health-wellness-care` does NOT cleanly absorb personal-care (framed as medical+wellness, not salons). **OPERATOR DECISION:** force into `health-wellness-care` (defensible — spa/massage framing), file 13th category, or NULL operator queue. |
| `fitness_sports` | `health` for V1, manual triage later | PARTIAL improvement. New `health-wellness-care` covers gyms/yoga/pilates cleanly. The recreational subset (tennis courts, pickleball, swimming pools) now has better home: `classes-sports-recreation` for scheduled use or `outdoors-parks-trails` for facility-only. **The new taxonomy actually helps here.** |
| `real_estate` | `community` or 13th category | See Bucket B — still broken. |
| `tourism` | NULL for operator triage | NO change; still no clean home. New `lodging-vacation-rentals` absorbs hotels; `events` absorbs attractions; `public-civic-resources` absorbs visitor-info. Operator triage stands. |
| `entertainment_attractions` (places) | NULL + follow-up regex on `google_primary_category` | NEW taxonomy improves splittability: parks → `outdoors-parks-trails`; movie theaters/bowling/arcades → likely `classes-sports-recreation` (entertainment-as-activity); live music → `events`; museums/galleries → `public-civic-resources`. **OPERATOR DECISION:** is recreational-entertainment (bowling, arcade, mini golf) "class/sport/recreation"? |
| `professional_services` | `community` catch-all for V1 | See Bucket B — broken; no catch-all exists. |

**Bucket C count: 6 strings.** The new taxonomy moves 2 toward resolution (`fitness_sports`, `entertainment_attractions` — both got better split targets) and leaves 4 in worse shape (no `community` fallback).

### Bucket E — One legacy string the audit improves

`recreation` (test fixture) — DRAFT mapped to `outdoors-and-parks` (Low confidence). Under the new 12, this could map to **`classes-sports-recreation`** instead (slug literally contains "recreation"). Test-only, but worth noting the slug name change makes the mapping more obvious.

### §2 Summary

| Outcome under new 12 | Count |
|---|---|
| Carries forward cleanly (slug rename only) | ~24 strings |
| BROKEN but new taxonomy provides a cleaner target | 5 strings (`childcare_education`, `education`, `religion_community`, `fitness_sports`, part of `entertainment_attractions`) |
| BROKEN and new taxonomy makes it WORSE (no catch-all) | 5 strings (`insurance`, `financial`, `legal`, `real_estate`, `professional_services`) + `barbershop` test fixture |
| Operator decision sharper under new 12 | 3 strings (`beauty_personal_care`, `tourism`, `professional_services` — overlaps Bucket B) |
| NULL queue regardless | 7-ish synthetic strings |

**The headline:** the DRAFT's High-confidence mappings nearly all carry forward as slug-string renames; the Medium/Low confidence ones get *sharper* not softer. The new taxonomy resolves some old ambiguity (Classes-Sports-Rec gives `childcare_education` a real home) but creates new pain by removing the `community` catch-all that the DRAFT used to absorb 5+ professional-services strings.

---

## §3 — Category table seed update implication

### (a) When should the Category seed update happen?

**Recommendation: Phase 3 v1.1 schema pass per master plan §4.**

Rationale:
- Phase 1 (ENTITY schema, in-flight) is already a heavy lane. Adding a seeded-category rewrite mixes two unrelated concerns: ENTITY-shape migration and taxonomy-content migration. Risk of conflation.
- Phase 1B "during the data migration" is viable since the legacy `Provider.category` text column gets read into `entity_categories` rows during Phase 1's Provider→ENTITY move. But injecting taxonomy-rewrite scope into a lane that's already moving is risky.
- A standalone Phase 1.5 ticket is acceptable but adds an extra migration. Phase 3 is already an additive-schema migration; bundling the category-seed-rewrite into it is one less alembic revision in the chain.
- Phase 3 timing aligns with operator-curated district authoring (which Phase 3 already requires ~1 hr of), so operator review of the new category seed list can happen in the same focus block.

**Caveat:** if the backfill (legacy `Provider.category` string → `category_id` FK) is also slated for Phase 3 — and it should be, because it's the only window where (a) ENTITY exists and (b) the new taxonomy is seeded — then Phase 3 does three things: additive schema, district seed authoring, AND category seed rewrite + backfill. That's a bigger Phase 3 than master plan §4 currently describes (~3-5 days dispatch + 1 hour operator).

### (b) Is this called out in master plan §4 Phase 3?

**No. This is a hole in the master plan worth flagging.**

Phase 3 deliverables list 11 schema additions (heat_exposure, crowd_notes, is_mobile_service, boat_access, seasonal_hours, districts table, district_id FK, featured flag, alert_subscriptions, alerts_dispatched, external_conditions_cache, preferred_mode, peer_recommendations). **There is NO mention of:**
- Updating the seeded category rows in the `categories` table
- Renaming the 7 original slugs to the new slugs
- Deleting `family` and `community` rows
- Inserting `classes-sports-recreation` and `public-civic-resources` rows
- Running the (now-different) backfill from `Provider.category` text → new `category_id` FK

§10 decision log captured the decision but the operational implication (seeded category rows are stale relative to locked taxonomy) didn't propagate to §4 Phase 3 deliverables. §6 operator workload still treats this as "anytime, 1-2 hours" review pass, not a re-author against changed taxonomy.

**This memo is the surfacing of that hole.**

### (c) Migration sketch (high level — no code)

1. **Rename surviving slugs (7 rows):** `eat-and-drink` → `eat-drink`; `home-services` → `home-property-services`; `health` → `health-wellness-care`; `outdoors-and-parks` → `outdoors-parks-trails`; `shopping` → `shopping-essentials`; `auto-and-gas` → `auto-rv-fuel`; `lodging` → `lodging-vacation-rentals` (also update display name strings).
2. **Slug-identical rows (3 rows):** `events`, `on-the-water`, `pets` — slug unchanged; `name` strings may update slightly (content question).
3. **Delete 2 rows:** `family`, `community`. **Pre-flight check:** ensure no `entities.category_id` (or `providers.category_id` / `programs.category_id`) FKs reference these rows before delete; if any do, re-point per the audit in §2 above, or NULL them out and surface in operator review queue. Migration needs a guard.
4. **Insert 2 rows:** `classes-sports-recreation`, `public-civic-resources`. Reset `sort_order` per synthesis §1 Tier ordering (Tier 1 first, Tier 2 next, Tier 3 last).
5. **Re-run backfill** of legacy `Provider.category` text → new `category_id` FK using the **audited** mapping (§2 above), not the original DRAFT.

The migration touches `categories` plus the FK-referencing columns. The CATEGORY_LABELS hard-coding at `app/home/queries.py:27-55` (referenced in DRAFT §4 #6) needs a parallel update.

---

## §4 — Recommended next actions

### Lock now (operator decision, 1-2 minutes each)

1. **Confirm Phase 3 is the right home** for (a) category seed rewrite, (b) backfill re-audit, (c) backfill migration. Alternatives: standalone Phase 1.5 ticket OR defer to V1.5+. Recommendation: Phase 3. **LOCKED 2026-05-14: Phase 3** (operator decision; folded into master plan §4 Phase 3 amendment + §10 decision log).
2. **Amend master_build_plan §4 Phase 3** to include the three new deliverables and bump effort estimate from "S-M (~3-5 days dispatch) + ~1 hour operator" to roughly "M (~5-8 days dispatch) + ~2-3 hours operator." **LOCKED 2026-05-14:** master plan §4 Phase 3, §6 operator workload, §10 decision log all amended 2026-05-14 by Cowork primary.
3. **Lock disposition for the 5 "no-catch-all" strings** (`insurance`, `financial`, `legal`, `real_estate`, `professional_services`): accept §7 Q5 deferral (NULL operator queue → V1.5+) or force into imperfect home? Recommendation: accept Q5 deferral. **LOCKED 2026-05-14: accept §7 Q5 deferral. NULL category_id during Phase 3 backfill; surface in operator queue; Phase 13 V1.5 revisits if cold-pitch demand justifies dedicated Professional Services category.**
4. **Confirm `religion_community` → `public-civic-resources`** mapping (cleanest single new-taxonomy improvement). **OPEN** — trivial confirmation; lock at Phase 3 start.
5. **Confirm `childcare_education`/`education` → `classes-sports-recreation`** mapping (similar — clean fit). **OPEN** — trivial confirmation; lock at Phase 3 start.

### Lock during Phase 3 (in-flight)

6. **`beauty_personal_care` final disposition** (force `health-wellness-care`, 13th category, or NULL queue).
7. **`tourism` final disposition** (operator triage per DRAFT recommendation).
8. **`professional_services` (places-domain bucket) split strategy** — apply DRAFT §3 #5/#6 pattern; split by `google_primary_category` post-backfill.
9. **K-12 / charter / public schools** — Classes-Sports-Rec or Public-Civic?
10. **Validator vocab update** at `scripts/ingest/validate_enrichment_csv.py` (DRAFT §4 #6) — same Phase 3 window once new slugs seeded.

### Lock during Phase 5 (operator data entry)

11. **`entertainment_attractions` per-row triage** using `google_primary_category`.
12. **`fitness_sports` recreational subset triage** (tennis courts, pickleball, swimming pools — pull out of `health-wellness-care` into `classes-sports-recreation` or `outdoors-parks-trails`).
13. **Production `SELECT DISTINCT category FROM providers`** — DRAFT §4 #4 said run before locking; admin form free-text at `app/admin/router.py:1439`.

---

## §5 — Open questions for operator

1. ~~Master plan §4 Phase 3 effort estimate reset (3-5 days → 5-8 days; 1 hr → 2-3 hr operator) acceptable, or move category-seed-rewrite + backfill to standalone Phase 1.5 ticket between Phase 1 and Phase 2?~~ **RESOLVED 2026-05-14: Phase 3 absorbs the rewrite + backfill at the bumped effort estimate.**
2. ~~The 5 professional-services strings: confirm V1.5 deferral (NULL operator queue) vs. forced imperfect home in V1?~~ **RESOLVED 2026-05-14: accept §7 Q5 deferral. NULL category_id during Phase 3 backfill.**
3. `beauty_personal_care`: force into `health-wellness-care`, NULL queue for V1, or file a 13th category? **OPEN — lock at Phase 3.**
4. K-12 / charter / public schools: `classes-sports-recreation` or `public-civic-resources`? **OPEN — lock at Phase 3.**
5. Bowling alleys / arcades / mini golf: `classes-sports-recreation` or different home? **OPEN — lock at Phase 3.**
6. Does `events` need a display-name update under the new taxonomy? **OPEN — content question; lock at Phase 3 or defer to Phase 9 schedule-heavy work.**
7. The DRAFT §5 caveat about `Contribution.submission_category_hint` (third free-text category surface) — in scope for Phase 3 backfill or separate ticket? **OPEN — lock at Phase 3 start.**
