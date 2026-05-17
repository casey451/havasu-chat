# Phase 5.9 Kickoff — Classes, Sports & Recreation (`classes-sports-recreation`)

> **What this is:** a single paste-and-go operator runbook for Phase
> 5.9, the ninth Tier 1 category. Mirrors
> `outputs/phase5_8_events_kickoff.md` shape with 5.9-specific
> overrides. **Single-layer scrape** (Google only — OSM scope is
> locked to on-the-water per brief §3.2.e) over a Narrow-scope subset
> of the combined `childcare_education` + `fitness_sports` domains
> (the 5 childcare labels in-scope + 4 fitness labels deferred to V1.5
> via 5.4 HWC absorption).
>
> **GATE 1 — Phase 5.8 SHIPPED** at `2808146` (2026-05-17) with all 6
> gate items cleared, plus SHA-cleanup at `209e99f`. ✅ Met.
>
> **GATE 2 — no pre-built verifier surface for 5.9.** There is no
> consolidated public registry for fitness studios + childcare
> facilities the way AZ ROC covers contractors or NPI covers medical
> providers. Three narrow paths exist (AZ Dept of Health Services
> childcare-license registry; gym/yoga chain APIs for franchise
> entities like Anytime Fitness / Snap Fitness; LHC Parks & Rec
> municipal pages for tennis/pickleball/pool court schedules) but none
> cover the full V1 surface, all are scraping-shape not API-shape, and
> the V1 utility of a "verified via AZDHS" badge for a gym is low.
> **This kickoff resolves §3 as Option C** (defer Layer-4 verifier
> surface to V1.5; document the three paths). Mirrors 5.5 + 5.6 + 5.7
> + 5.8 outcome.
>
> **GATE 3 — pre-flight integrity gotcha (now SIXTH+ recurrence
> watch):** `scripts/places_categories.json` has drifted locally on
> sessions 5.5 / 5.6 / 5.7-boot / 5.7-session-2-pre-flight. The
> 5.7 + 5.8 sessions found the four-file shape check
> (places_categories.json + places_load.py + models.py +
> google_types_mapping.py) clean at §0. The 5th + 6th recurrence
> forecasts did NOT materialize but the pattern remains watch-worthy.
> Pre-flight item #6 below is the same four-file check.
>
> **🚨 BOOT-PROMPT FRAMING NOTE:** The Phase 5.9 boot prompt at
> `outputs/phase5_9_next_agent_boot_prompt.md` correctly identifies
> the 3-category choice + recommends `classes-sports-recreation`.
> This kickoff commits to that choice. Per
> `app/contrib/google_places_scraper.py:90`,
> `"classes-sports-recreation": frozenset({"childcare_education",
> "fitness_sports"})` is a **two-domain mapping** — not single-domain
> like 5.8's events. Adjustments per §1 below.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.8 session 1
> (2026-05-17) post-`2808146` SHIP + `209e99f` SHA-cleanup, pre-§0.
> Pastable as-is; commit inline before §0 pre-flight dispatches per
> the established cadence.

---

## §0 Pre-flight (do once, at Phase 5.9 dispatch)

1. **`git log --oneline -15`** — origin should top at `<this commit>`
   (Phase 5.9 kickoff doc pre-stage) over `209e99f` (5.8 SHA-cleanup)
   over `ffa9808` (5.8 partial SHA-cleanup) over `2808146` (5.8 SHIP)
   or later if Phase 6 lane has shipped Amendment 8 between sessions
   (in-line a la `0addb63` for 5.4 OR via Claude Code parallel
   dispatch). The 5.8 lane chain since 5.7's `4b20e37` SHA-cleanup:
   `8dfa2a2 → 0b426e1 → f139be7 → 2808146 → ffa9808 → 209e99f`.
2. **`git status`** — clean. **Sandbox bash note:** `git status` hits
   the index-format gotcha (`fatal: unknown index entry format
   0xffff0000`); run Windows-side via PowerShell. Carry-over untracked
   from 5.8: `hava_api_catalog.docx` + `~$va_api_catalog.docx` Word
   lock + 2 historical `outputs/ci_*_log_failed.txt` files +
   `outputs/_deltest` — all unrelated to lane; operator prunes when
   comfortable.
3. **`python -m alembic current`** — confirm local `data/events.db` at
   `0a1b2c3d4e5f`. If behind, `python -m alembic upgrade head`. (No
   migrations expected on the 5.9 lane unless the parks-rec-scrapes
   prune-fix sidecar lands — that would add an `ON DELETE SET NULL`
   migration on `contributions.created_event_id`.)
4. **`python -m pytest -q --collect-only 2>&1 | Select-Object -Last 3`**
   — record baseline. Phase 5.8 closed at **1964 collected** (5.7
   baseline 1932 + 18 in-lane regression guards for the `0b426e1`
   `_PRIMARY_TYPE_MAP` extension for the 7 events primary_types).
   Verify no drift.
5. **`python outputs/diagnose_category_id_gap.py`** — confirm Phases
   5.1-5.8 categorization is intact and the `classes-sports-recreation`
   slug exists in the `categories` table (id=12 per the diagnose
   script output).
6. **🚨 WIDENED four-file shape check** (carried from 5.7 + 5.8 §0):
   ```powershell
   git diff --stat scripts/places_categories.json scripts/places_load.py app/db/models.py app/contrib/google_types_mapping.py
   ```
   MUST be empty. If ANY of the four shows deletions in the working
   tree, restore via `git restore .` Windows-side before §1. The
   expected HEAD line counts post-`209e99f` (sanity reference, not
   validation targets — content over shape):
   - `scripts/places_categories.json`: 211 lines
   - `scripts/places_load.py`: 664+ lines (carries 5.7 `1dfd28e`
     extensions)
   - `app/db/models.py`: 1539+ lines
   - `app/contrib/google_types_mapping.py`: 210+ lines (carries 5.7's
     `golf_course` + `medical_clinic` widenings + 5.8's 7 events
     primary_types from `0b426e1`)
7. **Google Places key + spend cap** — operator has deferred rotation
   until project end; still in `.env`, still capped. No mid-session
   rotation needed unless the operator opts in.
8. **CI state** — check GitHub Actions on the top commit. Should be
   ✅ green on `209e99f` (the 5.8 SHA-cleanup commit, docs-only) and
   `2808146` (the 5.8 SHIP commit; one CI-flake X on a duplicate run
   per the 5.5/5.7 known pattern — the green run is authoritative).
   If red, investigate before starting 5.9. The `parks-rec-scrapes`
   scheduled cron has been ❌ since 5.3 — root cause identified at
   5.7 §4.5 sidebar; **NOT in 5.9 scope** unless operator opts to
   dispatch the parks-rec-prune sidecar fix as part of this lane.
9. **DB state spot-check** — `events` should show **20 entries / 0
   verified / 17 indoor + 3 outdoor / 20 render (1 drafted but
   place-typed renders) / 10 long-form crowd_notes** (the 5.8 SHIPPED
   state). `classes-sports-recreation` should show **0 entries pre-load**
   (the cat-12 slug exists but no entities are linked yet — 5.4's
   HWC absorption took the natural cat-12 candidates; 5.9 reclaims
   them via the Narrow scope + sustainability PIVOT decision below).

---

## §1 The scrape sequence — Google only, NARROW scope

Phase 5.9 is **single-layer** (no OSM dispatch). **Scope is
intentionally narrowed** from the literal 16-label
`classes-sports-recreation` bundle in
`DISCOVERY_CATEGORY_TO_DOMAINS` because of one structural collision:

1. **`fitness_sports` collision with Phase 5.4 (HWC).** Phase 5.4
   already absorbed gyms / yoga studios / pilates studios / crossfit
   gyms / martial arts / jiu-jitsu / dance studios into
   `health-wellness-care` (7 of the 11 fitness_sports labels). The
   existing fallback `(None, "fitness_sports") → "health-wellness-care"`
   in `_DISCOVERY_DOMAIN_FALLBACK` codifies that mapping. Scraping
   those 7 labels in 5.9 would either (a) double-categorize existing
   HWC entities via the ambig path, or (b) fight the existing fallback.
   **Defer the 7 HWC-absorbed fitness_sports labels to V1.5.**

This leaves **9 labels in scope for 5.9 §1:**

| Bucket | Labels (9) | Domain |
|---|---|---|
| **Childcare + Education** | daycare, preschools, tutoring, music lessons, driving schools | childcare_education |
| **Fitness — cat-12 native** | personal trainers, swimming pools, tennis courts, pickleball | fitness_sports |

### Layer 1 — Google Places

```
python outputs/phase5_9_narrow_label_filter.py --dry-run
python outputs/phase5_9_narrow_label_filter.py
python -m scripts.places_enrichment --limit 200
python -m scripts.places_load --category classes-sports-recreation --dry-run
python -m scripts.places_load --category classes-sports-recreation
```

**Why `--limit 200` on enrichment?** 9 labels × ~10 per label ≈ 90
raw hits; the cumulative enrichment cache (5.0/5.1/5.2/5.3/5.4/5.5/
5.6/5.7/5.8) is ~2,644+ records. Most will cache-hit. Expected new
enrichments: ~30-60.

⚠️ **The `--category classes-sports-recreation` flag will filter
`places_categories.json` by `DISCOVERY_CATEGORY_TO_DOMAINS` which
returns BOTH `childcare_education` AND `fitness_sports` (two-domain
bundle).** This will pull in all 16 labels by default — including
the 7 we want to defer. **Two paths** to honor the Narrow scope
(same shape as 5.7's + 5.8's Path A vs Path B decision):

- **Path A (recommended — minimal code change):** Author a one-shot
  filter script `outputs/phase5_9_narrow_label_filter.py` that
  short-circuits the discovery loop to only the 9 in-scope labels.
  Mirrors `outputs/phase5_8_narrow_label_filter.py` shape from 5.8
  exactly — same Path A.2 pattern (standalone outputs/ wrapper, no
  production code touched). ~30 lines.
- **Path B (broader change):** Temporarily filter the 9 labels at
  the production-code level — riskier; not recommended.

**Default to Path A unless operator picks B.**

### Sustainability layer PIVOT — Required before §1 Layer 1

**The 5.4 `fc51940` sustainability commit added `(None, "fitness_sports")
→ "health-wellness-care"` as a domain-wide catch-all.** For 5.9 this
routes the wrong way for the 4 cat-12-native fitness_sports primary
types (personal_trainer / swimming_pool / tennis_court / pickleball_court)
— they would land in HWC instead of cat-12.

Also, the 5 childcare_education primary types (`child_care_agency`,
`preschool`, `tutor` or `educational_consultant`, `music_school`,
`driving_school`) have NO existing mappings — they would land at
`category_id=NULL` (operator queue) without intervention.

**Three options** (operator picks at §1 dispatch time; recommended
default is **Option A**):

**(A — recommended) Add direct `_PRIMARY_TYPE_MAP` entries** for the
expected cat-12 primary_types. Direct mappings beat catch-all per
resolver order, so the 7 HWC-absorbed fitness_sports primary_types
(gym, yoga_studio, pilates_studio, crossfit_gym, martial_arts_school,
jiu_jitsu_school, dance_studio) stay routed to HWC via the catch-all
while the 9 in-scope types route to cat-12. Example shape (`app/contrib/
google_types_mapping.py` `_PRIMARY_TYPE_MAP`):

```python
# childcare_education primary types
"child_care_agency": ("classes-sports-recreation", "commercial"),
"preschool": ("classes-sports-recreation", "commercial"),
"music_school": ("classes-sports-recreation", "commercial"),
"driving_school": ("classes-sports-recreation", "commercial"),
"tutor": ("classes-sports-recreation", "commercial"),
# fitness_sports primary types — cat-12 native (4 entries)
"personal_trainer": ("classes-sports-recreation", "commercial"),
"swimming_pool": ("classes-sports-recreation", "place"),  # public pools
"tennis_court": ("classes-sports-recreation", "place"),   # public courts
"pickleball_court": ("classes-sports-recreation", "place"),
```

The `commercial`-vs-`place` distinction follows 5.7's pattern: venues
that charge admission / membership = `commercial`; venues that are
primarily-public-good (city pools, public tennis courts) = `place`.
**Operator note:** the existing `(None, "fitness_sports") →
"health-wellness-care"` catch-all stays in place; the 7 HWC-absorbed
fitness types are NOT directly mapped, so they continue to route to
HWC. This preserves 5.4's HWC scope without disturbance.

**(B) Re-route the catch-all** — change `(None, "fitness_sports") →
"health-wellness-care"` to `... → "classes-sports-recreation"`, then
add explicit cat-5 mappings for the 7 HWC-absorbed types. Reverses
the default but requires 7+ explicit entries on the HWC side.

**(C — hybrid)** — add the 9 cat-12 primary_types via Option A, AND
re-route the catch-all to cat-12 via Option B. Most explicit +
future-proof but biggest surface area.

**Recommended: Option A.** Minimal diff, no need to revert 5.4's
catch-all (which was correct for 5.4's scope), direct mappings are
the cleanest pattern.

**Sustainability-layer commit shape:** mirror `0b426e1` (Phase 5.8
sustainability) — a single focused `fix(scripts)` commit that adds
the 9 `_PRIMARY_TYPE_MAP` entries + regression tests in
`tests/test_phase5_9_places_load_resolver.py` (~14 parametrized
asserts: 9 for the new primary types + 5 defensive preservation of
prior phases' fallbacks + golf_course / medical_clinic / events-7
preservation soft-edges). Land BEFORE the §1 Layer 1 dispatch
(sustainability-first pattern from 5.5 / 5.6 / 5.7 / 5.8).

### Layer 5 — Manual recovery (deferred to operator)

Per `docs/maintainability/manual_recovery_checklist.md`. Surface for
5.9:

- Senior centers offering classes (5.4 HWC may have absorbed; check
  cross-cat)
- Church-affiliated youth sports leagues (cat-13 public-civic-resources
  cross-list candidate)
- LHC Parks & Rec drop-in programs (registration-based; not typically
  Google-indexed as venues)
- HOA gyms / community pools (private-access; unlikely Google-indexed)
- Private music tutors / freelance instructors (LinkedIn-discoverable
  but not place_id-indexed)

Not gate-blocking for V1 ship.

---

## §2 Ambiguous-queue review — moderate volume + significant cross-category overlap expected

Classes-sports-recreation is the **ninth non-empty-DB load** (after
5.1-5.8). Reconciler will match against **~1,171+ existing entities**
(post-5.8: 287 eat-drink + 119 on-the-water + 230 HPS + 265 HWC + 140
auto-rv-fuel + 76 shopping-essentials + 27 outdoors-parks-trails + 20
events + 1 public-civic-resources + 86 unverified HWC carry). Expected
ambiguous hits: **30-70 per run** (range covers moderate label
coverage offset by significant cross-cat overlap risk with cat-5 HWC).

**Special audit categories expected for 5.9:**

| Existing entity | 5.9 candidate it'll likely match | V1 policy |
|---|---|---|
| Gyms in cat-5 HWC (from 5.4) | personal trainers (cat-12) | **review** — V1.5 may want to dual-cat gyms + personal-trainer services |
| Yoga studios in cat-5 HWC (from 5.4) | (deferred per Narrow scope) | n/a |
| Dance studios in cat-5 HWC (from 5.4) | music lessons (cat-12) — if dance lessons | review — same primary identity |
| Lake Havasu City Aquatic Center (5.8 §9 V1.5 carry — currently unmapped) | swimming pools (cat-12) | **FLIP candidate** — civic facility but primary identity is fitness/recreation |
| SARA Disc Golf Course (cat-7 from 5.7) | (no 5.9 label maps directly — defer to V1.5) | KEEP cat-7 |
| LHC Motocross Park (cat-7 from 5.7) | (no 5.9 label maps directly — defer to V1.5) | KEEP cat-7 |
| LHC Sportsman's Club (cat-7 from 5.7) | (no 5.9 label maps directly — defer to V1.5) | KEEP cat-7 |
| Nomadic coworking space (5.8 §9 V1.5 carry) | (no direct 5.9 label; could be V1.5 cat-12 if hosts classes) | review |
| Schools (cat-12 via existing _PRIMARY_TYPE_MAP `"school": ("classes-sports-recreation", "commercial")`) | preschools / driving schools (cat-12) | **same-cat update** — pre-existing `school` primary_type catches these already |
| Daycare at church (cat-13 public-civic-resources) | daycare (cat-12) | review — cross-link if both apply |

**Pre-existing school entities in cat-12** — let me verify in §0 DB
spot-check; the existing `_PRIMARY_TYPE_MAP["school"] →
("classes-sports-recreation", "commercial")` entry would have caught
any `school` primary_type from prior phases' scrapes. Expect 0-5
schools already in cat-12 pre-5.9.

Mirror the 5.8 audit pattern: post-load audit pulls cross-category +
same-category; an apply-script batches the misroute decisions if
any. **Expected outcome based on 5.4/5.5/5.6/5.7/5.8 history: 0 real
misroutes** in the cross-cat ambig pool (benign geo-proximity false
positives), plus same-cat updates to any pre-existing schools.

The 5.8 §1 NEW-create surface pattern (16 Slice A creates) may also
apply to 5.9 — many cat-12 candidates may be NEW entities not yet in
DB, requiring `create_provider_and_entity` dual-write via the
apply-script.

If a single load produces **>70** ambiguous hits, consider tuning
`GEO_PROXIMITY_THRESHOLD_M` (currently `50.0`) per brief §4.g — but
prior phases have all stayed under the tune threshold despite
exceeding 50.

### Cross-category sweep — `_DISCOVERY_DOMAIN_FALLBACK` catch-all behavior

Per 5.6 + 5.7 + 5.8 close-outs: the `(None, "<domain>")` catch-all
routes ALL unmapped primary_types under that domain. 5.4's `(None,
"fitness_sports") → "health-wellness-care"` stays in place; 5.9's
Option A direct mappings beat it for the 4 cat-12-native fitness
primary_types. Childcare_education has no existing catch-all today
— **5.9 §1 Option A should also add a `(None, "childcare_education")
→ "classes-sports-recreation"` catch-all** as a safety net for
unmapped childcare primary_types.

Apply-script `outputs/apply_phase5_9_classes_audit.py` if any FLIPs
needed. Expected size: ~10-30 rows reviewed, likely 5-15 NEW creates
(mirroring 5.8 §2 Slice A pattern — discovery surfaces candidates
the reconciler ambig-skips for cat-12).

---

## §3 Layer-4 verifier surface — Option C resolved (deferred to V1.5)

**5.9 has no pre-built verifier** (unlike 5.3's `az_roc_verify` and
5.4's `npi_verify`). Three narrow options exist; this kickoff
resolves §3 as **Option C** per the structural reasoning in the
header. The other two paths are documented here for V1.5 pickup.

### Option A — AZ Dept of Health Services childcare-license registry (DEFERRED to V1.5)

URL: `https://www.azdhs.gov/licensing/childcare-facilities/index.php`
— AZDHS maintains a public registry of licensed childcare facilities,
preschools, and family homes. License lookup via search form
(scraping-shape). Covers daycare + preschools comprehensively for
AZ.

Coverage: ~70-90% of 5.9 childcare candidates (most LHC daycare +
preschool entities are AZDHS-licensed). Sets
`Provider.verified=True`, `verification_method='azdhs_childcare'`,
`attributes.azdhs={...license_no, expires, capacity}`.

**Cost-of-build:** ~4-6 hours (Playwright scrape of the AZDHS search
form). **Coverage is good for childcare but doesn't address fitness
(which has no equivalent registry).**

### Option B — Franchise gym/yoga chain APIs (DEFERRED to V1.5)

URLs: Anytime Fitness club locator, Snap Fitness club locator, Orange
Theory studio locator, CycleBar locator. Each provides JSON club-
finder endpoints (with rate limits). Covers chain-affiliated cat-12
fitness entries but NOT independent gyms / yoga / pilates studios.

Coverage: ~10-20% of cat-12 fitness candidates (most LHC fitness is
independent, not chain-affiliated).

**Cost-of-build:** ~6-8 hours (per-chain API integration + dedup
logic). **Coverage too narrow for V1 to justify the build.**

### Option C — Defer verifier surface to V1.5 ✅ SELECTED

Gate item 3 rephrased to **"Layer-4 verifier surface scoped — built
or explicitly deferred to V1.5"**. Document AZDHS + franchise APIs +
LHC Parks & Rec paths in this kickoff and ship 5.9 without verifier
surface. Lowest-friction shape; mirrors 5.5 + 5.6 + 5.7 + 5.8 outcome.

**Rationale:** cat-12 verification has low V1 utility (consumer
discovery doesn't need a "verified by AZDHS" badge on a daycare to
be useful; parents look at reviews + visit in person); the available
paths are all scraping-shape not API-shape; coverage is fragmented
across 3 surfaces. Better to defer the whole verifier surface to V1.5
when the right shape can be designed against fuller scope.

---

## §4 Operator-curated field entry — Classes/Sports/Recreation rubric

Lighter operator surface than 5.4 (no NPI verification) + 5.6 (no
brand-name normalization); on par with 5.7/5.8 shape but with a
**mixed heat_exposure default** (vs 5.6's `indoor` and 5.7's
`outdoor`):

- **`heat_exposure`** — **mixed**: `indoor` for most cat-12 entries
  (daycare, preschools, music lessons, driving schools, personal
  trainers, tutoring), `outdoor` for swimming pools / tennis courts /
  pickleball courts. Mirror 5.8's pattern of default + override list,
  but the override list is BIGGER for 5.9 (4 outdoor labels vs 5.8's
  2-3 outdoor festivals). Probable shape:
  - Default: `indoor`
  - OUTDOOR_OVERRIDES: any entity whose primary identity is a
    swimming pool / tennis court / pickleball court (likely 5-10 of
    the ~20-30 5.9 entries). Plus the 5.8 §9 V1.5 carry Aquatic
    Center (if FLIPped to cat-12).
- **`crowd_notes`** — short-form for typical entries; long-form for
  the top-10 by review count. cat-12 reviewer signals tend to be:
  staff quality + safety supervision (childcare), program variety +
  schedule (gyms, classes), member-friendliness, equipment condition,
  parking + access, kid-friendliness, instructor quality + style
  (yoga, music, dance), open-pool hours (public pools).

Drafts source: **`Provider.google_review_snippets` (own column, not
`attributes`)** — per the 5.4 close-out §4 source-path correction.
Expected snippet coverage: **~70-85%** (cat-12 review density is
moderate to high for gyms + childcare; lower for tutoring + private
music lessons).

**`is_mobile_service`** is NOT a gate item for 5.9 by default —
cat-12 is mostly venue-based. Some categories (personal trainers,
music lessons) MIGHT be mobile-service (instructor travels to
client). Operator may opt to re-add `is_mobile_service` as a gate
item if many such entries surface, mirroring 5.5's HPS pattern.
Default: skip the `is_mobile_service` apply-script for 5.9.

**`attributes`** JSON — can be extended with cat-12-specific keys:
`age_range` (str: "infants" / "toddlers" / "preschool" /
"elementary" / "teens" / "adults"), `capacity` (int), `licensed`
(bool), `drop_in_allowed` (bool). For pools: `lap_lanes` (int),
`pool_heated` (bool), `outdoor_pool` (bool). For courts:
`court_count` (int), `lighted` (bool). For gyms: `24_hour_access`
(bool). Brief §3.4 has the suggestion shape.

### §4.5 sidebar — `parks-rec-scrapes` prune-fix dispatch (optional)

The scheduled `parks-rec-scrapes` GitHub Actions workflow has been
❌ on cron triggers since at least Phase 5.3. Root cause identified
in Phase 5.7 §4.5 sidebar: Postgres FK constraint violation in
`scripts/parks_rec_prune.py`. **3 fix options** surfaced in
`outputs/phase5_7_session_closeout.md` §3 — alembic migration
adding `ON DELETE SET NULL` (recommended), prune-script `WHERE NOT
EXISTS` clause, or ON DELETE CASCADE.

**Operator decision at 5.9 §0 dispatch time:** include the prune-fix
in 5.9 scope (sidebar lane), OR keep deferred to Phase 6 / separate
sidecar. **Default recommendation: defer to a separate sidecar
dispatch** unless operator wants to cover it opportunistically.

---

## §5 Daily / weekly rhythm (brief §5)

Similar cadence to 5.5/5.6/5.7/5.8 but with a sustainability PIVOT
pre-flight step:

| Day | Work |
|---|---|
| 1 | Sustainability-layer commit (Option A — 9 `_PRIMARY_TYPE_MAP` entries + 1 `(None, "childcare_education") → "classes-sports-recreation"` fallback) BEFORE Layer 1; then Google scrape run + scrape log (`docs/scrape_logs/classes-sports-recreation_<YYYY-MM-DD>.md`) + Narrow-scope filter script (Path A) |
| 2 | Ambiguous-queue triage + data-quality audit (cross-category review per §2; sweep any pre-existing schools / cat-12 entries) |
| 3 | Verifier surface — Option C deferral confirmed in §3; document V1.5 paths |
| 3-4 | `crowd_notes` for top-10 + `heat_exposure` sweep (indoor default + OUTDOOR_OVERRIDES for pools/courts) |
| 4 | Optional: `parks-rec-scrapes` prune-fix sidebar (§4.5) if Decision 4 included in 5.9 scope |
| 5 | Optional Layer 5 manual recovery (senior centers, HOA gyms, private tutors) |
| 6 | QA spot-check — 10 random entries vs. the §4 rubric |

**Expected Phase 5.9 total: 7-12 hours over 1 week.** On par with
5.8's 6-10h estimate but slightly heavier due to the larger Narrow
scope (9 labels vs 5.8's 7) + dual-domain bundle.

---

## §6 Acceptance gate — Phase 5.9 closes when ALL of:

- [ ] **20+ entries** in `classes-sports-recreation` post-load (modest
      target — cat-12's overlap with 5.4 HWC means many natural
      candidates are already in HWC; the 5.9 lane focuses on NET-NEW
      entries from the 9 in-scope labels + any cross-cat FLIPs from
      the §2 audit). Gate-1 query MUST use the
      `(e.entity_type != 'commercial' OR provider-visible)` shape
      from `outputs/phase5_2_gate_verification.py` /
      `outputs/phase5_7_gate_verification.py` /
      `outputs/phase5_8_gate_verification.py` to correctly count
      `place`-typed entries (swimming_pool / tennis_court /
      pickleball_court map to `place`).
- [ ] All Google ↔ existing-entity ambiguous reconciler hits
      reviewed (with cross-category review per §2 — especially the
      cat-5 HWC primary axis for gym/yoga/dance overlaps + the
      cat-7 outdoors-parks-trails axis for sports-park overlaps).
- [ ] **Layer-4 verifier surface scoped — Option C explicitly
      deferred to V1.5** (per §3). AZDHS + franchise APIs + LHC
      Parks & Rec paths documented in this kickoff §3 for V1.5
      pickup.
- [ ] Top-10 by review count have long-form `crowd_notes`.
- [ ] `heat_exposure` set on every entry (`indoor` for most;
      `outdoor` for pools/courts — expected override count 5-10).
- [ ] Phase 6 `/category/classes-sports-recreation` renders **≥15**
      per default filter.

**Note: 6 gate items (not 7).** `is_mobile_service` is dropped by
default (venue-based scope). Operator may opt to re-add as a 7th
gate item if many mobile-service entries surface (mirror 5.5 HPS
pattern).

When the gate is met: commit the scrape log, Phase 5.9 gets its
SHIPPED ledger line on `master_build_plan.md` §4 (coordinate with
Phase 6 lane via `outputs/claude_code_dispatch_phase6_amend9.md`),
and **Phase 5.10 (next Tier-1 category — likely
`lodging-vacation-rentals` or `pets` per the remaining ~3-slug list)**
dispatches next.

---

## §7 Reference

- `outputs/phase5_8_session_closeout.md` (the just-shipped 5.8 state
  index — carries the apply-script + audit + sustainability layer
  playbooks 5.9 reuses, especially the §2 NEW-create pattern)
- `outputs/phase5_8_events_kickoff.md` (the 5.8 runbook this document
  mirrors)
- `outputs/phase5_2_gate_verification.py` (gate template for
  `entity_type='place'` query shape — relevant for 5.9 since
  swimming_pool / tennis_court / pickleball_court map to `place`)
- `outputs/phase5_8_gate_verification.py` (template for the
  equivalent 5.9 gate-verification script — note: 6 items not 7;
  no `is_mobile_service` check; threshold ≥20)
- `outputs/phase5_8_events_audit.md` (combined pre+post audit
  template for the equivalent 5.9 audit doc — especially Slice A
  NEW-create pattern)
- `docs/scrape_logs/events_2026-05-17.md` (template for the
  equivalent 5.9 scrape log — author by hand at session start if
  absent)
- `app/contrib/google_types_mapping.py` (fitness_sports +
  childcare_education types — extend per §1 Option A; current state
  carries 5.7's `golf_course` + `medical_clinic` + 5.8's 7 events
  widenings)
- `app/contrib/google_places_scraper.py:90`
  (`DISCOVERY_CATEGORY_TO_DOMAINS["classes-sports-recreation"]` —
  the source of the `childcare_education + fitness_sports` bundle)
- `scripts/places_load.py` (`_resolve_category_id` sustainability
  layer + 5.3 + 5.4 + 5.5 + 5.6 + 5.7 + 5.8 fallback extensions;
  5.9 Option A adds direct `_PRIMARY_TYPE_MAP` entries — same shape
  as `0b426e1` did for events)
- `outputs/diagnose_category_id_gap.py` (re-usable diagnostic)
- `outputs/apply_phase5_8_events_audit.py` (5.8 audit apply template
  — 5.9's likely-substantial Slice A NEW creates + cross-cat
  reviews; especially the `create_provider_and_entity` dual-write
  pattern)
- `outputs/apply_phase5_8_events_heat_exposure.py` (5.8 heat sweep
  template — for 5.9 default stays `indoor`; populate
  `OUTDOOR_OVERRIDES` for the 5-10 expected pool/court entries)
- `outputs/apply_phase5_8_events_crowd_notes.py` (5.8 crowd_notes
  template — pass dict directly to JSON column per 5.3 `f35d5e4`
  gotcha, F401/F541/I001-clean imports per 5.3 `bff4a79` + 5.7
  `5f8fe08` + 5.8 inline-import lessons)
- `outputs/phase5_8_ambig_audit_dump.py` (5.8 ambig audit dump
  script — direct copy with paths/slug swap for 5.9)
- `outputs/phase5_8_top10_discovery.py` (5.8 top-10 discovery
  helper for crowd_notes drafting — direct copy with slug swap)
- `outputs/phase5_8_narrow_label_filter.py` (5.8 Path A wrapper —
  template for 5.9's equivalent)

---

## §8 Hand-off context from the Phase 5.8 session

**Important context that's NOT in this kickoff but the new agent
should read in the 5.8 close-out:**

- 3-commit Phase 5.8 lane chain `8dfa2a2 → 2808146` (`0b426e1`
  sustainability + `f139be7` narrow-scope wrapper + `2808146` SHIP),
  plus `ffa9808` partial SHA-cleanup (with `$ship` literal typo in
  commit body — cosmetic, audit-trail) + `209e99f` correct SHA-
  cleanup. Plus 5 DB-only writes (1 load + 2 audit applies + 1
  heat + 1 crowd_notes).
- **5.8 §0 4-file shape check** — `places_categories.json` +
  `places_load.py` + `models.py` + `google_types_mapping.py` was
  empty (no drift). 5th-recurrence forecast did NOT materialize.
  Continue the 4-file check in 5.9 §0.
- **5.3 `f35d5e4` JSON-column gotcha was avoided in 5.4 + 5.5 + 5.6
  + 5.7 + 5.8** by passing dict directly to `Entity.crowd_notes` —
  no `json.dumps()`. Internalize.
- **5.3 `bff4a79` F401 + 5.7 `5f8fe08` F541 + 5.8 inline-import
  I001 footguns:** `# noqa: E402` silences E402 only. F401 (unused
  imports), F541 (`f"..."` with no placeholders), AND I001 (un-
  sorted imports, including inline `from x import y` blocks inside
  functions) all still fail ruff. 5.8 hit I001 once on inline
  imports inside `main()` — fix is to move them to the top of the
  file. Watch for inline `from x import y` blocks in apply-scripts.
- **Sandbox bash git-index gotchas** — use `git rev-parse` / `git
  show HEAD:` for index-free reads. Operator runs index-dependent
  ops (incl. `git restore`) Windows-side via PowerShell.
- **Sandbox bash MOUNT-STALENESS gotcha** (recurring since 5.5; 5.6
  hit it twice; 5.7 hit it three times; **5.8 hit it twice** —
  `wc -l` on Edit'd file showed stale count; post-Edit verification
  unreliable). The Read tool is authoritative; sandbox bash
  file-shape queries are unreliable for post-Edit / post-restore /
  post-commit verification. Use Windows-side `python` for all DB
  queries.
- **PowerShell `\"` escape footgun (5.7-discovered, 5.8-avoided):**
  `\"` inside a PowerShell `"..."` string is NOT an escape; embedding
  `\"\"\"` in a `git commit -m "..."` body causes git to parse
  subsequent tokens as pathspecs (`fatal: /: '/' is outside
  repository`). **Use single-quoted `-m '...'`** flags for git commit
  messages when the body contains `"` or `/` characters; PS single
  quotes are literal (no interpolation, no escaping). 5.8 used this
  discipline throughout.
- **`5.8` lesson — DB-verify the "existing entity in cat-X" premise
  before authoring cross-cat moves.** 5.8 §2 Slice B-1 originally
  classified Lake Havasu Museum of History as a cat-6 → cat-2 move,
  based on misreading the kickoff §2 framing. DB query (`Entity.name
  LIKE '%Museum%'`) confirmed no such entity existed in DB. The 5.7
  §1 ambig pool had a museum candidate but "0 flips needed" per 5.7
  close-out §4 meant the candidate was KEPT-ambig, not flipped. **For
  5.9 §2 audit:** query DB for `Entity.name LIKE '%<keyword>%'`
  before authoring cross-cat moves, especially for any
  5.7/5.8 audit-noted entities (Aquatic Center, Nomadic, SARA Disc
  Golf, etc.).
- **DB-write apply-scripts:** stop the FastAPI dev server if running
  (events.db lock).
- **`Provider.google_review_snippets` is its OWN COLUMN** — not
  inside `attributes` JSON. Drafts for top-10 long-form `crowd_notes`
  source from this column. 5.8's top-10 had 100% snippet coverage
  (5 each); 5.9 may have moderate-to-high coverage (gyms + childcare
  tend to have abundant reviews; tutoring + music lessons less so).
- **CI can be flaky on intermediate commits** — 5.5 / 5.7-session-1
  / **5.8** all saw the same pattern (one ✓ + one ❌ on the same
  commit ID, short elapsed time = runner-orchestration flake not
  code). Try `gh run rerun <ID>` before shipping a fix commit. Final
  tree-state CI green is the ship-readiness signal.
- **`_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a domain-wide
  catch-all** at `places_load.py:368-371`. 5.4's `(None,
  "fitness_sports") → "health-wellness-care"` stays in place for
  5.9 (covers the 7 HWC-absorbed fitness types). 5.9 §1 Option A
  ADDS `(None, "childcare_education") →
  "classes-sports-recreation"` as a NEW catch-all for the
  childcare_education domain (no prior phase populated this).
- **5.8 §2 NEW-create pattern (16 Slice A entries)** — much larger
  than 5.7's 4-entry §2 surface. 5.9 may follow a similar shape if
  Layer 1 surfaces many cat-12 ambig candidates. The
  `create_provider_and_entity` dual-write from `app/db/entity_dual_
  write.py` is the canonical NEW-entity creation pattern (writes
  Entity + Location + EntityCategory + ContactPoint + SourceEvidence
  + Hours from a Provider instance).

**Carry-forwards from the 5.8 session** the new agent should action:

- 🚨 **Phase 6 lane — Phase 5.8 SHIPPED ledger amendment** —
  `outputs/claude_code_dispatch_phase6_amend8.md` is **NOT yet
  authored** (5.8 close-out §6 flagged it as a carry-forward).
  Either author it at 5.9 §0 OR delegate to Claude Code parallel
  agent. Operator decides.
- **`parks-rec-scrapes` prune-fix sidecar** — root cause + 3 fix
  options in 5.7 close-out §3. Optional inclusion at §4.5 (see
  above); default defer to separate sidecar dispatch.
- **V1.5 Layer-4 verifier surface for 5.8** — AZ event aggregators
  + LHC Tourism Board paths documented in `phase5_8_events_audit.md`
  §9 carry-forward + 5.8 kickoff §3 for V1.5 pickup.
- **V1.5: art_gallery + museum entity_type re-evaluation** (5.8
  starting point chose `place`; most LHC museums + galleries charge
  admission and may want `commercial`). Defer.
- **V1.5: Lake Havasu Museum of History place_id unification** —
  two Google place_ids for the same business (5.7-ambig +
  5.8-created); operator picks primary, archives the other.
- **V1.5: Simply Savage Designs DRAFT review** — operator decides
  un-DRAFT or DELETE.
- **V1.5: `wildlife_refuge` direct mapping** — 1-line addition per
  5.7's `golf_course` pattern. Defer.
- **5.8 §9 V1.5 dual-cat candidates for cat-12 in 5.9 §2 audit:**
  - **Lake Havasu City Aquatic Center** (currently unmapped; 595
    reviews; swimming_pool primary) — **strong FLIP candidate** for
    5.9 cat-12.
  - **Nomadic coworking space** (currently unmapped; 17 reviews)
    — possible cat-12 if hosts classes; defer if pure workspace.
  - **SARA Park Disc Golf Course, LHC Motocross Park, Ofd Racing,
    Sportsman's Club, Thompson Bay Beach** (currently cat-7) — V1.5
    dual-cat candidates. For 5.9: review during §2 audit but likely
    KEEP cat-7 (no 5.9 in-scope label directly maps to these).
- **86 of 265 HWC providers remain `verified=False`** — carry-over
  from 5.4. Operator-driven DBA→NPI follow-up surface (optional
  V1.5).
- **Operator: prune `data/events.db.bak-*` files** when comfortable
  — carry-over from 5.3 + 5.4 + 5.5 + 5.6 + 5.7 + 5.8.
- **Google Places API key rotation** — deferred per operator ("all
  keys will be changed at conclusion of this project").

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.8 session 1
(2026-05-17) post-`2808146` SHIP + `209e99f` SHA-cleanup, pre-§0
hand-off artifact. Commit inline before §0 pre-flight dispatches.
Cowork primary picks up at §0 pre-flight after reading
`outputs/phase5_8_session_closeout.md` first and
`outputs/phase5_9_next_agent_boot_prompt.md` second.*
