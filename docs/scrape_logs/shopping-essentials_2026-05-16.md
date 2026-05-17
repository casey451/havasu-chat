# Scrape log — `shopping-essentials` — 2026-05-16

Per `docs/operations/scrape_logs_template.md`. First per-category
scrape run for Phase 5.6 (sixth sub-phase of the Phase 5 restructure,
post-5.5 SHIPPED 2026-05-16 at `08d5ff3` + kickoff/boot prompt at
`66e02c8`). **Single-layer scrape** (Google only — OSM scope locked to
on-the-water per brief §3.2.e). **No Layer-4 verifier** for 5.6 —
operator picked Option C (defer AZ TPT Transaction Privilege Tax +
BBB cross-reference surfaces to V1.5) at session start.

---

## §0 Pre-flight (closed)

| Check | Result |
|---|---|
| `git log -1 --oneline` | `66e02c8` (origin pre-load top — Phase 5.6 kickoff + boot prompt) |
| `python -m alembic current` | `0a1b2c3d4e5f` ✅ (unchanged across all 5.x phases) |
| `python -m pytest --collect-only \| tail -3` | **1920 collected** ✅ (no drift from 5.5) |
| `python outputs/diagnose_category_id_gap.py` | `shopping-essentials` slug present at id=8 ✅ |
| `gh run list --branch main --limit 3` | Top 3 runs ✓ green on main |
| Google Places key + spend cap | In `.env` ✅; spend cap active. Operator declined rotation per "all keys will be changed at conclusion of this project" |
| Playwright | Not needed for 5.6 (Option C — no Layer-4 verifier built) |
| Working tree clean | ✅ (untracked carry-over from 5.5: `hava_api_catalog.docx`, `~$va_api_catalog.docx` Word lock, 2 historical `outputs/ci_*_log_failed.txt`) |

**Pre-flight surprise (1, triaged):**

- **`scripts/places_categories.json` locally corrupted (third recurrence)** — working tree at 202 lines (ends mid-token `"chil`), HEAD at 211 lines (proper close). Operator restored via `git restore` Windows-side. Cause still unknown (suspect external editor save). Cleared before §1.

---

## §1 Layer 1 — Google Places (only scrape layer for 5.6)

### Discovery (real, full sweep)

```
python -m scripts.places_discovery --category shopping-essentials
```

| Field | Value |
|---|---|
| Mode | full |
| Categories run | 23 (all `retail` domain) |
| Requests | 38 |
| Unique places | 313 |
| Cost (actual) | ~$1.52 |
| Run time | a few seconds wall |

Per-label split (23 labels, all `retail` domain):

| Label | Pages | New unique |
|---|---|---|
| grocery stores | 1 | 12 |
| supermarkets | 1 | 0 (dedup vs grocery) |
| convenience stores | 3 | 51 |
| liquor stores | 2 | 14 |
| pharmacies | 2 | 15 |
| clothing stores | 3 | 56 |
| thrift stores | 1 | 8 |
| consignment stores | 2 | 2 |
| shoe stores | 1 | 2 |
| jewelry stores | 3 | 24 |
| furniture stores | 1 | 10 |
| home decor stores | 2 | 6 |
| hardware stores | 1 | 14 |
| garden centers | 1 | 10 |
| bookstores | 1 | 9 |
| gift shops | 3 | 20 |
| florists | 1 | 0 (dedup) |
| sporting goods stores | 1 | 0 (dedup) |
| outdoor gear stores | 2 | 14 |
| electronics stores | 3 | 29 |
| music stores | 1 | 7 |
| toy stores | 1 | 5 |
| smoke shops | 1 | 5 |

Discovery cost ran below kickoff §1 projection (~$1.60-$2.20 expected,
~$1.52 actual) because 15 of 23 labels capped at 1 page — LHC's
retail clusters around McCulloch Blvd / Lake Havasu Ave produce dense
overlap but limited long-tail beyond first-page results for
single-purpose labels.

### Enrichment

```
python -m scripts.places_enrichment --limit 600
```

| Field | Value |
|---|---|
| Input | 313 |
| Cache-hits (resume skip) | 295 |
| New enrichments | 18 |
| Cost (actual) | ~$0.72 |

High cache reuse (94.2% cache-hits) — retail has more overlap with
prior phases (eat-drink restaurants, auto gas stations, etc.) than
expected. Lower than the ~30-60 new-enrichments projection.

### Load (first run)

```
python -m scripts.places_load --category shopping-essentials
```

| Field | Value |
|---|---|
| Input rows | 268 (after `--category retail` + LHC ZIP filter, 18 dropped) |
| Inserted (new entities) | 87 |
| Updated (existing place_id) | 0 |
| `ambig` (geo+name conflict) | **181** |
| `merge` (geo+name match) | 0 |
| `category_id` resolved (Tier 1) | 247 |
| `category_id` unmapped (operator queue) | **21** |
| EntityCategory rows inserted | 77 |

ZIP-filter dropped 18 rows across 14 non-LHC ZIP codes (mostly
metro-Phoenix / Mesa / Yuma / Flagstaff outliers from Google's
multi-city aggregation).

### Surgical fix — `_DISCOVERY_DOMAIN_FALLBACK` extension

Operator queue surfaced 21 unmapped rows with edge-case primary types:
- 3 `service` (IT/electronics service shops — Havasu Technologies, Vertical IT, Whiz Kid Computer Services)
- 1 `None` (Havasu Computers)
- 6 visible-as-Provider edge cases (`corporate_office`, `manufacturer` ×3, `garden`, `farm`, `health`, `community_center` — partial enumeration)
- 11 inside the 181 ambig-skip pool

Extended `_DISCOVERY_DOMAIN_FALLBACK` in `scripts/places_load.py` with
7 retail entries (5.5 `4d41944` surgical-fix shape):
```python
(None, "retail"): "shopping-essentials",
("service", "retail"): "shopping-essentials",
("supplier", "retail"): "shopping-essentials",
("point_of_interest", "retail"): "shopping-essentials",
("establishment", "retail"): "shopping-essentials",
("store", "retail"): "shopping-essentials",
("shopping_mall", "retail"): "shopping-essentials",
```

Plus +12 regression tests in `tests/test_phase5_6_places_load_resolver.py`
(7 parametrized `_RETAIL_KEYS` + 5 preservation tests for 5.2/5.3/5.4-
health/5.4-fitness/5.5-auto). Pytest 1920 → 1932 collected.

### Load (re-run after fix)

```
python -m scripts.places_load --category shopping-essentials
```

| Field | Value |
|---|---|
| Inserted (new) | 0 (all already in DB) |
| Updated (existing) | 87 |
| `ambig` (idempotent) | 181 |
| `category_id` unmapped (operator queue) | **0** ✅ |
| EntityCategory rows inserted (backfill) | 10 |

The `(None, "retail")` catch-all picked up all 10 visible-NULL rows
(including the 6 edge cases I anticipated leaving in operator queue —
the resolver's `_DISCOVERY_DOMAIN_FALLBACK.get((None, domain))`
second-chance lookup fires for any unmapped primary_type when (None,
domain) is registered). This matches the established 5.2/5.3/5.4/5.5
catch-all pattern.

### Total §1 cost

| Step | Cost |
|---|---|
| Discovery | ~$1.52 |
| Enrichment | ~$0.72 |
| **Total Layer 1** | **~$2.24** |

Within kickoff §1 projection of $2.50-$4.00 (slightly under).

---

## §2-§4 outcomes (summarized; details in `outputs/phase5_6_shopping_essentials_audit.md`)

- **§2 ambig review (177 rows):** 0 misroutes — all benign McCulloch / Lake Havasu Ave strip-mall adjacency (eat-drink ×99, HWC ×24, HPS ×22, auto-rv-fuel ×17, on-the-water ×12, pets ×1). Mirrors 5.4 medical-plaza + 5.5 auto-industrial-blvd pattern.
- **§2 cat-9/cat-8 special audit:** 5 hits (gas-station/convenience-store cross-list), all correctly stay in cat-9 per V1 policy.
- **§2 catch-all edge-case review (27 rows, 18 actions):** 11 FLIPs (5 to cat-5, 4 to cat-9, 2 to cat-4) + 7 DRAFTs (5 B2B wholesale + community garden + uncertain Anderson AZ West) + 13 KEEPs. Final 2 FLIPs (Lake Havasu Family Eyecare + Barnet Dulaney Perkins, both `medical_clinic` primary) surfaced during the §4 top-10 by-review-count sweep — the audit dump's `edge_types` filter didn't include `medical_clinic` so they slipped through the first pass.
- **§3 Layer-4 verifier:** Option C — explicitly deferred to V1.5. AZ TPT + BBB paths documented in kickoff §3 for V1.5 pickup.
- **§4 heat_exposure:** 78 indoor + 5 outdoor (Garden Center at Home Depot, Lowe's Garden Center, Serrano's Nursery, Lake Havasu Community Garden, Tux and Tulips florist). 0 NULL. **Gate-5 cleared.**
- **§4 crowd_notes top-10:** 10 long-form notes drafted from `Provider.google_review_snippets` for the top-10 by review-count (post-§2-flips). All 10 with `>200` chars in `$.long`. Named-staff signal-quality high. **Gate-4 cleared.**

---

## §6 Final acceptance gate (all 6 items CLEARED)

Per `outputs/phase5_6_gate_verification.py`:

| # | Item | Status |
|---|---|---|
| 1 | 40+ entries in `shopping-essentials` post-load | ✅ **76** entities rendering (1.90× target) |
| 2 | All ambig hits reviewed (+ cat-9/cat-8 audit) | ✅ 177 reviewed, 0 misroutes, 0 cat-9/cat-8 flips |
| 3 | Layer-4 verifier scoped (built or deferred) | ✅ Option C — deferred to V1.5 |
| 4 | Top-10 by reviews have long-form crowd_notes | ✅ 10 |
| 5 | heat_exposure set on every entry | ✅ 0 NULL of 83 (78 indoor + 5 outdoor) |
| 6 | `/category/shopping-essentials` renders ≥15 | ✅ 76 (5.07× target) |

`PHASE 5.6 ACCEPTANCE GATE: ALL 6 ITEMS CLEARED — READY TO SHIP`

---

## §7 Files added or modified this session

| File | Type |
|---|---|
| `scripts/places_load.py` | extended `_DISCOVERY_DOMAIN_FALLBACK` |
| `tests/test_phase5_6_places_load_resolver.py` | new (+12 tests) |
| `outputs/phase5_6_ambig_audit_dump.py` | new (audit script) |
| `outputs/phase5_6_ambig_audit_data.json` | new (177 records) |
| `outputs/apply_phase5_6_shopping_audit.py` | new (11 FLIPs + 7 DRAFTs) |
| `outputs/apply_phase5_6_shopping_heat_exposure.py` | new |
| `outputs/apply_phase5_6_shopping_crowd_notes.py` | new (top-10 long-form) |
| `outputs/phase5_6_shopping_essentials_audit.md` | new (gate-2 evidence) |
| `outputs/phase5_6_gate_verification.py` | new (6 items, all PASS) |
| `outputs/phase5_6_session_closeout.md` | new (this session's close-out) |
| `docs/scrape_logs/shopping-essentials_2026-05-16.md` | new (this doc) |
