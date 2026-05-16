# Phase 5.4 — Health, Wellness & Care — Post-load ambiguous-queue audit

> Mirrors `outputs/phase5_3_home_property_pre_load_audit.md` shape with a
> 5.4-specific override: this doc runs in ONE pass (post-load) because
> `health-wellness-care` had **0 pre-existing entries** before the 5.4 §1
> Layer 1 scrape. The audit reviews all 114 ambiguous reconciler skips
> from the load run and documents the verdict for each bucket.
>
> **TL;DR:** No misroutes among existing entities. The 114 ambig hits
> are the **medical-plaza false-ambig pattern** — health/fitness
> businesses geo-colliding (within 50m) with non-related businesses in
> adjacent suites/storefronts. The reconciler verdict ("ambig") is
> conservative-correct under V1 policy; no apply-script needed.
> Gate-2 met by review.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.4 session
> (2026-05-16) post-fallback-extension commit (`fc51940`-ish).

---

## §1 Summary

Phase 5.4 §1 Layer 1 produced **396 ZIP-filtered Google Places
candidates** through the reconciler. Outcomes:

| Reconciler action | Count | Disposition |
|---|---|---|
| `insert` (new entity) | 282 | Loaded — see §1 close (`health-wellness-care` = 265 post-fallback) |
| `update` (existing place_id) | 0 | (none — first time `health-wellness-care` is being populated) |
| `ambig` (geo+name conflict) | **114** | This audit's subject |
| `merge` (geo proximity + name match) | 0 | n/a |

Of the 114 ambig hits:

| Bucket | Count | Match shape | Decision |
|---|---|---|---|
| **A — cross-category** | 87 | Candidate geo-matches an entity currently in a different Tier-1 slug (eat-drink ×44, home-property-services ×33, auto-rv-fuel ×7, shopping-essentials ×2, on-the-water ×1) | KEEP-SKIP (V1 — see §3.1) |
| **B — same-category** | 25 | Candidate geo-matches an entity already in `health-wellness-care` (same medical plaza) | KEEP-SKIP (V1 — see §3.2) |
| **C — orphans (no-geo-match)** | 2 | Candidate has lat/lng but no entity within 75m; reconciler matched via "name only no geo" branch | KEEP-SKIP (V1 — see §3.3) |
| **Total reviewed** | **114** | | gate-2 cleared by review |

**Cross-list policy (V1):** unchanged from 5.3 — each entity gets exactly
one EntityCategory row. Where a candidate "should" arguably appear in
multiple Tier-1 slugs (e.g., a medical spa as both `health-wellness-care`
and `beauty-personal-care` post-Phase-5.6), the V1 decision is
single-primary, deferred dual-list to Phase 6 / V1.5.

**Net effect on Phase 5.4 gate-1:** None — the 114 candidates were
already excluded by reconciler at load time. `/category/health-wellness-care`
renders 265 entries (gate-1 target was ≥80; cleared 3.3×).

---

## §2 The medical-plaza false-ambig pattern

### Why 114 is much higher than 5.3's 75

Phase 5.3 (home-property-services) produced 75 ambig hits — most resolved
to legitimate self-storage duplicates + a few cross-category misroutes
(Stanley Steemer carpet-cleaning had been mis-tagged as `shopping-essentials`).

Phase 5.4 produces 114 ambig hits with a categorically different shape:
**health/fitness businesses cluster in medical plazas and strip-mall
suites**, putting many *different* businesses within 50m of each other.
The reconciler's geo-50m + name-mismatch check fires once per geo
collision regardless of whether the candidate and matched entity are
the same business.

Distance distribution of the 87 cross-category hits (the bucket where
this pattern is most visible):

| Distance band | Count |
|---|---|
| `<10m` | 27 |
| `10–25m` | 30 |
| `25–50m` | 30 |
| `50–75m` | 0 |
| `≥75m` | 0 |

**100% of cross-category hits are <50m.** That's the medical-plaza
adjacency pattern — suite-to-suite distances in a typical Havasu medical
plaza.

### Why this is conservative-correct under V1

The reconciler's verdict ("ambig") routes these candidates to the
operator-review queue rather than auto-inserting. Under V1 single-primary
EntityCategory policy, conservative-skip is safer than auto-insert
because:

- Auto-inserting risks double-counting if the matched entity is in fact a
  duplicate Google listing for the same business (rare but possible).
- A skip is recoverable in a follow-up apply-script; a wrong auto-insert
  requires a delete pass.
- Phase 5.4's gate-1 (≥80 entries) is met handily at 265 without
  recovering the 114 — no completeness pressure for V1.

The cost is that 114 valid candidates remain unloaded. The Phase 5.4
close-out flags this as a soft-edge for Phase 5.5+ (see §5).

---

## §3 Per-bucket analysis

### 3.1 Bucket A — 87 cross-category geo-collisions

**Distribution by matched-entity slug:**

| Matched slug | Count | Pattern |
|---|---|---|
| eat-drink | 44 | Medical plaza next to restaurants (typical Havasu strip-mall mix) |
| home-property-services | 33 | Medical office adjacent to contractor/storage businesses |
| auto-rv-fuel | 7 | Health office near auto businesses |
| shopping-essentials | 2 | Health office near retail |
| on-the-water | 1 | Edge case — single co-location with a marina entity |

**Name similarity distribution (jaccard chars):**

| Similarity band | Count | Interpretation |
|---|---|---|
| `≥0.8` (very similar) | 1 | False-positive — chars overlap by chance ("Bullen and Beckstrand" vs "The Cleaning B's"). Clearly different businesses on inspection. |
| `0.6–0.8` (similar) | 4 | Different businesses; some shared words from chain names or local naming conventions |
| `0.4–0.6` (moderate) | 39 | Different businesses; shared common words |
| `0.2–0.4` (weak) | 38 | Clearly different |
| `<0.2` (different) | 5 | Clearly different |

**Example collisions (representative — full data in `outputs/phase5_4_ambig_audit_data.json`):**

| Candidate (health/fitness) | Matched (other slug) | Distance | Sim |
|---|---|---|---|
| Beacon Of Health Family Chiropractic | Majik Bistro & Milkshakes | 25.0m | 0.50 |
| Optima Medical - West Lake Havasu City | Mohave Electric | 29.0m | 0.56 |
| Mountain View Health Clinic | Cummins Construction Co Inc | 12.9m | 0.47 |
| Serenity Dental, Lake Havasu City Dentist | Lobster 3 Ways Food Truck | 44.7m | 0.55 |
| Dental Specialists of NW Arizona | PrimePest Solutions | 16.0m | 0.53 |
| Dr Julia Carlson DDS | London Bridge Electric | 17.0m | 0.47 |
| Bullen and Beckstrand Orthodontics | The Cleaning B's House Cleaners | 32.7m | 0.81 |

All seven examples are clearly distinct businesses in the same plaza.

**Verdict:** KEEP-SKIP. No re-route action on existing entities; no
force-insert of candidates under V1.

### 3.2 Bucket B — 25 same-category geo-collisions

The candidate geo-matches an entity already in `health-wellness-care`.
The pattern is **multi-practice medical plazas** — Shader Vision plaza,
Lakeview Family Dental plaza, Thrive Healthcare plaza each have 3+
adjacent practices that all surface separately under different label
searches.

**Sample collisions:**

| Candidate (health) | Matched (already h-w-c) | Distance | Sim |
|---|---|---|---|
| Optima Medical - South Lake Havasu City | Shader Vision Cataract & LASIK | 24.9m | 0.74 |
| FPS Medical Center | Shader Vision Cataract & LASIK | 4.5m | 0.50 |
| Advanced Women's Care - Lakeview Women's Health Center | Lakeview Family Dental | 21.9m | 0.61 |
| Sunrise Family Healthcare - Tiarra Sitzer FNP | Thrive Healthcare FNP | 34.6m | 0.65 |
| FPS Primary Care of Lake Havasu | Shader Vision Cataract & LASIK | 24.9m | 0.65 |

All matched entities have **distinct Google place_ids** from the
candidates → guaranteed different businesses (Google does not reuse
place IDs). The collision is pure geo-proximity within the same plaza.

**Verdict:** KEEP-SKIP. These are duplicate candidates for what is
already a covered medical plaza — gate-1 lists those plazas via the
inserted entries. Adding the candidates would surface multiple
practices per plaza (which is correct *information* but adds list
density that V1 hasn't explicitly designed for).

### 3.3 Bucket C — 2 orphan ambig hits

Two candidates have lat/lng but no entity within 75m (so geo-proximity
didn't fire). The reconciler matched them via the "name only no geo"
branch — fuzzy name similarity above threshold to some existing entity
elsewhere in LHC.

| Candidate | Primary | Domain | lat/lng |
|---|---|---|---|
| Learn to Thrive Life | medical_clinic | health_medical | 34.5099, -114.3275 |
| The Study Yoga Studio | yoga_studio | fitness_sports | 34.5099, -114.3275 |

Both are at the **same exact lat/lng** — a shared wellness suite. Each
matched a different existing entity by name fuzz (likely "Thrive
Healthcare FNP" for the first, indeterminate for the second).

**Verdict:** KEEP-SKIP. Same V1 policy as bucket A — name-fuzz match
without geo collocation is conservative-correct.

---

## §4 Apply-script — none for V1

Unlike the 5.3 audit which prescribed
`outputs/apply_phase5_3_home_property_audit.py` for the 16
re-route-out + 3 re-route-in + 1 misroute-flip, the 5.4 audit
**prescribes no apply-script**:

- Bucket A — no existing entity to re-route (all matched entities are
  correctly slug-routed); no force-insert under V1 conservative policy.
- Bucket B — same (no re-route; candidates remain skipped).
- Bucket C — same.

Gate-2 met by review per the kickoff §6 wording: *"All Google ↔
existing-entity ambiguous reconciler hits reviewed."* All 114 reviewed,
all 114 disposed.

---

## §5 Soft-edges for Phase 5.5+ and the close-out

### 5.1 Optional: force-insert apply-script (deferred to follow-up)

A Phase-5.5-or-later follow-up could recover the 87 cross-category
candidates by force-insert (bypassing the reconciler's ambig verdict
for the medical-plaza pattern). Sketch:

- Filter `outputs/phase5_4_ambig_audit_data.json` to the 87 cross-cat
  hits.
- For each, build Provider kwargs from the enrichment cache + run
  `create_provider_and_entity` (Phase 1D dual-write hook).
- Self-verify via `/category/health-wellness-care` rendering count
  (target jump: 265 → ~352).
- Skip bucket B (the 25 same-category) on the conservative principle
  that they'd surface "duplicate-feeling" entries per plaza.

Not gate-blocking for V1. Defer until V1.1 if list-density
shortcomings surface in Phase 6 / 7 testing.

### 5.2 Optional: tune `GEO_PROXIMITY_THRESHOLD_M` to 25m

The reconciler at `app/contrib/ingest_reconciler.py` uses 50m as the
proximity threshold for the geo-match-name-mismatch ambig action. For
the medical-plaza pattern, 25m would be more appropriate (a typical
medical-suite footprint is 5-15m wide, so 25m catches "same suite" but
not "next-door-but-different-business").

Risk: regressing 5.1/5.2/5.3 reconciler behavior on entity classes that
*do* benefit from 50m (boat ramps near marinas, etc.). Need to verify
no harm against existing entities before tuning. **Not in scope for
Phase 5.4.**

### 5.3 Optional: same-discovery-domain bypass in reconciler

A more surgical fix would be: if geo within 50m AND name mismatch AND
the candidate's `_first_seen_domain` does NOT map to the matched
entity's current slug, treat as INSERT (different business in same
plaza) instead of AMBIG.

This bypasses 87 of the 114 hits (the cross-category bucket) without
affecting 5.1/5.2/5.3 ambig logic. Out of scope for Phase 5.4;
candidate fix for Phase 5.5 or a separate refactor session.

---

## §6 Reference

- `outputs/phase5_4_ambig_audit_data.json` — full structured dump of all
  114 ambig hits with matched entities (geo distance, name similarity,
  current slug per match).
- `outputs/phase5_4_ambig_audit_dump.py` — the diagnostic script that
  produced the JSON (auto-detects UTF-16 BOM in PS Tee-Object logs;
  reusable for Phase 5.5+).
- `outputs/phase5_4_load_real_v2.log` — Tee'd output of the real load
  (UTF-16 LE) — source of the 114 raw ambig log lines.
- `outputs/phase5_3_home_property_pre_load_audit.md` — the audit shape
  this doc mirrors.
- `app/contrib/ingest_reconciler.py` (`GEO_PROXIMITY_THRESHOLD_M = 50.0`,
  `reconcile_hit`) — the reconciler whose verdict we're auditing.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.4 session
(2026-05-16). Phase 5.4 gate-2 met by review of all 114 ambig hits.
No apply-script needed for V1. Three soft-edges flagged for Phase 5.5+
(force-insert, threshold tune, same-domain bypass) — none gate-blocking.*
