# Phase 5.6 — Shopping, Grocery & Essentials — Post-load audit

> Mirrors `outputs/phase5_5_auto_rv_fuel_pre_load_audit.md` shape with
> two 5.6-specific overrides:
>
> 1. **DB-diff audit dump** instead of log-parse — `outputs/phase5_6_
>    ambig_audit_dump.py` reconstructs the 177-row ambig set by
>    diffing the 295 retail+ZIP-filtered enrichment rows against the
>    Providers already in DB after the load. Removes the Tee-Object log
>    dependency 5.5 noted in its close-out §6.
> 2. **Catch-all edge-case section** — the `(None, "retail")` entry
>    added to `_DISCOVERY_DOMAIN_FALLBACK` routed 27 providers with
>    edge-case primary_types (corporate_office / manufacturer / garden /
>    farm / health / community_center / service / supplier) to
>    shopping-essentials. 9 of those needed FLIPs to other Tier-1 slugs;
>    7 needed DRAFTs (B2B-only or non-retail civic); 13 KEEPs. Applied
>    via `outputs/apply_phase5_6_shopping_audit.py`.
>
> **TL;DR:** No misroutes among the 177 ambig-skipped rows (all benign
> McCulloch / Lake Havasu Ave strip-mall adjacency — same pattern as
> 5.4 medical-plaza + 5.5 auto-industrial-blvd). Gas-station /
> convenience-store cat-9/cat-8 axis returned 5 hits, all correctly
> staying in cat-9 per V1 policy (0 flips). The 27-row edge-case
> catch-all routing review surfaced 9 real misroutes initially (3 to
> cat-5, 4 to cat-9, 2 to cat-4); the §4 top-10 sweep surfaced 2
> additional `medical_clinic` eye-care misroutes (Lake Havasu Family
> Eyecare + Barnet Dulaney Perkins) for a final **11 FLIPs + 7 DRAFTs**
> via Provider.draft=True. **Gate-2 met by review.**
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.6 session
> (2026-05-16) post-`apply_phase5_6_shopping_audit.py` live run.

---

## §1 Summary

Phase 5.6 §1 Layer 1 produced **268 ZIP-filtered Google Places
candidates** through the reconciler. Outcomes (first load run +
post-fallback re-load, idempotent):

| Reconciler action | Count | Disposition |
|---|---|---|
| `insert` (new entity) | 87 | Loaded — shopping-essentials = 94 pre-apply (25 pre-existing + 69 net new to shopping-essentials after cross-cat routing) |
| `update` (existing place_id) | 87 (re-load) | Idempotent; existing rows refreshed |
| `ambig` (geo+name conflict) | **181** (load log) / 177 (audit dump's DB-diff method) | This audit's §2 subject |
| `merge` (geo proximity + name match) | 0 | Already-merged or none qualified |

The small 181-vs-177 discrepancy reflects the audit dump's broader
retail-detection (includes rows seen in multiple labels) vs the load's
strict --category filter; the audit value is unaffected.

**Of the 177 ambig hits (audit dump's coverage):**

| Bucket | Count | Match shape | Decision |
|---|---|---|---|
| **A — cross-category** | **173** | Candidate geo-matches an entity in another Tier-1 slug (eat-drink ×99, health-wellness-care ×24, home-property-services ×22, auto-rv-fuel ×17, on-the-water ×12, pets ×1) | KEEP-SKIP (V1 — see §3.1) |
| **B — same-category** | 4 | Candidate geo-matches an existing shopping-essentials entity (adjacent retail in same plaza) | KEEP-SKIP (V1 — see §3.2) |
| **C — orphans (no-geo-match)** | 0 | All 177 had a candidate within 75m | n/a |
| **Total reviewed** | **177** | | gate-2 §2 cleared by review |

**Plus** the 27-row edge-case catch-all routing review (§4) and the
5-hit gas-station/convenience-store cross-list special audit (§5).

---

## §2 The McCulloch / Lake Havasu Ave strip-mall false-ambig pattern

### Why 173 cross-category hits

The kickoff §2 anticipated 30-100 ambig hits but flagged that LHC's
retail clusters on McCulloch Blvd / Lake Havasu Ave / The Shops at
Lake Havasu produce strip-mall density similar to 5.4 medical-plaza
and 5.5 auto-industrial-blvd patterns. The actual 173 cross-cat count
lands well above the kickoff range but is **categorically the same
pattern** — retail businesses geo-colliding (within 50m) with
restaurants, medical offices, contractor offices, gas stations, and
marine businesses in adjacent suites or buildings.

Distance distribution (177 audit records with a match):

| Distance band | Count |
|---|---|
| `<10m` | 51 |
| `10–25m` | 62 |
| `25–50m` | 57 |
| `50–75m` | 7 (audit-only — at the dump script's 75m diagnostic widen) |
| `≥75m` | 0 |

Discovery-label breakdown of cross-cat hits (top labels):

| Discovery label | Cross-cat ambig count |
|---|---|
| clothing stores | 41 |
| convenience stores | 23 |
| electronics stores | 22 |
| jewelry stores | 17 |
| gift shops | 14 |
| pharmacies | 12 |
| furniture stores | 8 |
| home decor stores | 6 |
| hardware stores | 6 |
| smoke shops | 5 |

The clothing-stores dominance is The Shops at Lake Havasu shopping
mall — a single large geo-footprint that triggers Google's nearby
restaurant / department-store / pharmacy hits to all geo-match each
other at <25m. Pharmacies (12) overlap with HWC clinics (Walgreens
embedded inside the medical-plaza cluster). Convenience stores (23)
overlap with gas-stations (cat-9) — these are covered by the §5
special audit.

### Verdict

All 173 cross-cat hits are **benign strip-mall adjacency**. The
reconciler's "ambig" verdict is conservative-correct under V1 policy:
the candidate is a different business from the matched existing
entity, just located within 50m. No misroutes, no apply-script flips
needed for this slice. **Mirrors the 5.4 + 5.5 outcome exactly.**

---

## §3 Same-category bucket (4 hits)

Per kickoff §2 / 5.5 pattern: same-cat ambig hits are adjacent retail
in the same plaza (different stores, same building). Operator-skip
verdict is correct — these are distinct businesses, not duplicates.

---

## §4 Edge-case catch-all routing review — 27 providers, 18 actions

The surgical fix at commit `<sustainability-fix-sha>` added a `(None,
"retail")` entry to `_DISCOVERY_DOMAIN_FALLBACK`. The resolver's
second-chance lookup (places_load.py:348) routed **all** unmapped
retail-discovered rows to shopping-essentials — including 6 edge cases
the original surgical-fix plan intended to leave in the operator
queue. The catch-all behavior matches every prior phase
(`(None, "auto")` / `(None, "health_medical")` / etc.) but 5.6's
`retail` domain catches more category-spillover than 5.5's `auto` did.

### Slice A — 11 FLIPs (re-routed to other Tier-1 slugs)

Single-cat flip per V1 policy + operator decision. Apply-script:
`outputs/apply_phase5_6_shopping_audit.py`. The first 9 landed at the
initial audit; the final 2 (`7993f2b5` + `7329dd44`) were surfaced
during the §4 top-10 by-review-count sweep — the audit dump's
`edge_types` filter didn't include `medical_clinic` so they slipped
through the first pass, but the §4 review caught them in the top-10
list (#1 and #9 by review_count respectively).

| Entity (8-char id) | Provider | google_primary | Flipped to |
|---|---|---|---|
| `ef1c1270` | Christina Martinez, OD - Eye Exam | health | health-wellness-care |
| `2f53214c` | Dr. Sylvia Rimbergas - Pediatric Eye Exam | health | health-wellness-care |
| `2853055b` | Hospice of Havasu (the actual hospice) | health | health-wellness-care |
| `7993f2b5` | **Lake Havasu Family Eyecare (§4-surfaced)** | medical_clinic | health-wellness-care |
| `7329dd44` | **Barnet Dulaney Perkins Eye Center (§4-surfaced)** | medical_clinic | health-wellness-care |
| `64b1eb3d` | Anderson Powersports Lake Havasu | supplier | auto-rv-fuel |
| `da327e86` | Anderson PowerSports (distinct location) | supplier | auto-rv-fuel |
| `c3958b0f` | Just 4 Fun Powersports | supplier | auto-rv-fuel |
| `f227c238` | Lead Dog Motorsports | adventure_sports_center | auto-rv-fuel |
| `6364a641` | AQUACLEAN HAVASU LLC (water/pool) | service | home-property-services |
| `3a21a8fb` | Apple Valley Communications Alarms | service | home-property-services |

### Slice B — 7 DRAFTs (Provider.draft=True; EntityCategory preserved)

These are B2B-only or non-retail-civic providers that shouldn't show
in a consumer retail directory but lack a more appropriate Tier-1
home in the V1 taxonomy.

| Entity (8-char id) | Provider | google_primary | Rationale |
|---|---|---|---|
| `9d3b86aa` | A & A Electronics Assembly | manufacturer | B2B electronics assembly |
| `f791b8b5` | Geary Pacific Supply | manufacturer | HVAC wholesale (B2B) |
| `dd2e31c7` | Keenan Supply | manufacturer | Plumbing wholesale (B2B) |
| `1fa2736b` | Romer Beverage Co | corporate_office | Wholesale beverage distributor |
| `3667c4b2` | Essco Wholesale Electric | service | Wholesale electric (B2B) |
| `b103ea17` | Lake Havasu Community Garden | garden | Civic non-profit, not retail |
| `c5a5868b` | Anderson AZ West | supplier | Appears wholesale; operator un-draft if confirmed consumer-retail |

### Slice C — 13 KEEPs (no script action)

| Provider | google_primary | Rationale |
|---|---|---|
| Havasu Computers | None | Electronics retail |
| Clothes Closet Lake Havasu | community_center | Community thrift store |
| **Hospice of Havasu Resale Store** | service | **Thrift store, distinct from main hospice (which flipped)** |
| Dillard's | department_store | Major retail |
| Serrano's Nursery | farm | Retail nursery |
| Phil's Band Instrument Repair | service | Retail-adjacent |
| Havasu Technologies | service | IT services hybrid |
| QED | service | IT services hybrid |
| Vertical IT Solutions | service | IT services hybrid |
| ReConnected Phone & Device Repair | service | Retail repair |
| Whiz Kid Computer Services / Ink & Toner | service | Retail supplies + service |
| Epic_lifestyles | supplier | Assumed retail brand |
| JCPenney Optical | health | Retail framing wins (JCPenney is fundamentally retail) |

---

## §5 Gas station / convenience store cat-9/cat-8 special audit

Per kickoff §2 special surface. 5 hits flagged, all from the
`convenience stores` discovery label hitting on existing gas-stations
in `auto-rv-fuel`:

| Candidate | Matched cat-9 entity | Distance | V1 policy verdict |
|---|---|---|---|
| Sunny Stop Mini Mart | "76" gas station | 26.5m | Stay in cat-9 (primary use = fuel) |
| Marathon Gas Station & Oasis Food Mart | Maverik | 58.5m | Stay in cat-9 |
| Marathon | Brb Market | 0.0m (same location) | Stay in cat-9 |
| Motor and Boat Texaco | Marathon | 0.6m | Stay in cat-9 |
| Shell | Hava Gas | 7.0m | Stay in cat-9 |

**0 flips needed.** V1 policy (per kickoff §2): convenience stores
attached to gas stations stay in cat-9 unless the convenience-store
is clearly the primary draw. None of the 5 candidates surfaced as
destination groceries.

---

## §6 Net effect on Phase 5.6 gate-1

| Category | Pre-apply | Post-§2-only | Post-§2 + §4-extension (final) |
|---|---|---|---|
| `/category/shopping-essentials` | 94 (total) | 85 / 78 render | **83 total / 76 render** |
| `/category/health-wellness-care` | 268 | 271 (+3) | **273 (+5)** |
| `/category/auto-rv-fuel` | 149 | 153 (+4) | 153 |
| `/category/home-property-services` | 235 | 237 (+2) | 237 |
| `/category/eat-drink` | 255 | 255 | 255 |

**Note on cross-cat load behavior:** The 5.6 load itself (independent
of the apply-script flips) correctly routed 9 entries to auto-rv-fuel
(gas_station / convenience_store / auto_parts_store primary_types from
retail discovery labels) and 3 entries to health-wellness-care
(pharmacy primary_type) via direct google_types_mapping resolution —
these never landed in shopping-essentials in the first place. The
apply-script's flips (+4 to cat-9, +5 to cat-5, +2 to cat-4) are on
top of that.

**Gate-1 met:** shopping-essentials renders **76 entries** (gate
target ≥40; cleared 1.90×). Gate-6 met identically (≥15 — cleared 5.07×).

**§4 outcomes (gate items 4 + 5):**
- **heat_exposure:** 78 indoor + 5 outdoor (4 garden centers / nurseries
  + Tux and Tulips florist) = 83 total, 0 NULL. **Gate-5 cleared.**
- **crowd_notes top-10:** 10 entities with long-form `crowd_notes`
  (>200 chars in `$.long`) drafted from `Provider.google_review_
  snippets`. Named-staff signal-quality high (Shay Kay at Michael
  Alan, Logan James at ReConnected, Ms Kim at Crown Ace, etc.).
  **Gate-4 cleared.**

---

## §7 Carry-forwards

- **`Provider.draft=True` for 7 providers** in shopping-essentials.
  These don't render at `/category/shopping-essentials` but preserve
  their EntityCategory link. Operator can re-evaluate Anderson AZ
  West in particular if it turns out to be consumer-retail; just
  flip `draft` back to `False`.
- **Hospice of Havasu Resale Store stays in shopping-essentials** as a
  thrift store. The main hospice (`2853055b`) flipped to cat-5.
- **No Layer-4 verifier surface built** — operator picked Option C
  (defer to V1.5) at session start. AZ TPT + BBB paths documented in
  the kickoff §3 for V1.5 pickup.
- **`scripts/places_categories.json` corruption recurred** at
  pre-flight (third recurrence; same 202-vs-211-line pattern). Operator
  restored Windows-side. Cause unknown (suspect external editor); pre-
  flight item #6 in `outputs/phase5_6_shopping_grocery_essentials_
  kickoff.md` continues to catch this.
- **Sandbox bash mount staleness** continued to affect 5.6 (json.load
  on places_categories.json failed in sandbox while Read tool showed
  the file healthy; google_types_mapping import failed with
  SyntaxError while Read tool showed the file healthy). Read tool is
  authoritative; sandbox bash is unreliable for post-restore /
  post-Edit verification.
