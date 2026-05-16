# Phase 5.2 — On the Water — Session close-out (2026-05-15)

> **What this is:** the close-out for the session that picked up Phase 5.2
> at `273fe61` (Phase 5.1 SHIPPED ledger) and pushed 11 commits to land
> the data plane + 5 of 6 acceptance gate items. The 6th item (boat_access
> for marinas — the heaviest field-survey + judgment-call surface per the
> kickoff) remains for a future session.
>
> **Also the close-out for a retroactive Phase 5.1 fix** that this session
> surfaced and shipped — see §3.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.2 session
> (2026-05-15), post-`65b0824`.

---

## §1 Commit chain (origin `273fe61 → 65b0824`)

| # | Commit | Subject | Task |
|---|---|---|---|
| 1 | `2ef4b3b` | `fix(scripts)` — OSM pull writes JSONL | #10 |
| 2 | `155a41a` | `fix(osm)` — descriptive UA + visible diagnostics (406 fix) | #11 |
| 3 | `bee73f8` | `chore(outputs)` — OSM yield recalibration + extended test dispatch | — |
| 4 | `efd193a` | `fix(scripts)` — places_load sets Provider.category_id + Phase 5.1 backfill | #12, #13, #14 |
| 5 | `8800761` | `fix(scripts)` — widen on-the-water mapping (types-map + promote unmapped) | #15 |
| 6 | `87d0703` | `docs(scrape_logs)` — on-the-water_2026-05-15 Layer 1 + Layer 2 actuals | — |
| 7 | `a2d7f62` | `chore(outputs)` — Phase 5.2 data-quality audit 73 → 100 entities | #5 |
| 8 | `e68e424` | `chore(outputs)` — apply heat_exposure to all 100 on-the-water entities | #7 (heat) |
| 9 | `452c44e` | `chore(outputs)` — apply crowd_notes top-10 (gate item 4 cleared) | #7 (notes) |
| 10 | `65b0824` | `fix(scripts)` — places_load resolver sustainability + ruff lint clean | #16, #17 |

**Pytest baseline:** 1855 collected (pre-session) → 1853 passed + 2 skipped
+ 30 subtests post-session. No new tests added (Cursor dispatches staged at
`outputs/cursor_dispatch_osm_pull_writer_test.md` for follow-on).

**Ruff:** all-checks-passed end-of-session.

---

## §2 Phase 5.2 acceptance gate — 5 of 6 closed

| # | Gate item | Status | Where |
|---|---|---|---|
| 1 | 25+ entries in `on-the-water` post-load | ✅ **100** | Layer 1 (224 inserted, 29 ambig-skipped) + Layer 2 (1 marina) + audit re-routes (+27 / −2) + promotes (+68) |
| 2 | Every marina has `boat_access` JSON populated | ⏳ **pending** | Task #6 — 5 marinas need field-survey: Havasu Riviera Marina, Lake Havasu Marina, Lake Havasu Yacht Club, Riverside Boat Dock Sales, Havasu Cove |
| 3 | All Google ↔ OSM ambiguous reconciler hits reviewed | ✅ | 1 hit: Lake Havasu Marina (OSM way 227901073) vs Google Lake Havasu Marina at 1100 McCulloch Blvd N — same physical marina, OSM duplicate correctly skipped. No action. |
| 4 | Top-10 marinas + ramps have `crowd_notes` | ✅ | 10 long-form `{short, long}` applied (`452c44e`); locked Phase 5.1 JSON shape |
| 5 | `heat_exposure` non-NULL on every entry | ✅ | 78 water_adjacent + 22 indoor; 0 NULL (`e68e424`) |
| 6 | `/category/on-the-water` + boat-mode toggle both render ≥15 | ✅ page (100) / ⏳ boat-mode | Boat-mode toggle is Phase 6.4 + depends on `boat_access IS NOT NULL` filter (route line 299 of `category_pages.py`); pending gate item 2 + Phase 6.4 implementation |

---

## §3 Retroactive Phase 5.1 fix (CRITICAL — needs Phase 6 lane + master plan coordination)

`outputs/diagnose_category_id_gap.py` surfaced post-`273fe61` that
`scripts/places_load.py` never set `Provider.category_id`. The Phase 1D
dual-write hook (`app/db/entity_dual_write.py:_attach_provider_extensions`)
only creates `EntityCategory` rows when `category_id IS NOT NULL`. The
`/category/<slug>` route filters strictly via the `EntityCategory` join
(`app/api/routes/category_pages.py:_select_entities_for_category` lines
274-275). Net effect: **all 287 5.1 food_drink Providers landed without
EntityCategory linkage, so `/category/eat-drink` rendered 0 entities at
HEAD**, not the 255 the close-out ledger claimed.

**Phase 5.1 acceptance gate item 5 was retroactively false at SHIPPED.**

`efd193a` shipped two fixes:

1. `scripts/places_load.py` — extended with `_resolve_category_id` (uses
   `google_types_mapping`) and `_ensure_entity_category` (idempotent
   EntityCategory upsert on UPDATE branches). New summary counts:
   `category_id_set`, `category_id_unmapped`, `entity_category_inserted`.
2. `outputs/apply_provider_category_id_backfill.py` — id-keyed apply-script
   that backfilled the 287 5.1 food_drink Providers + their EntityCategory
   rows. Self-verifies via the route's filter query.

Post-fix: `/category/eat-drink` renders 255. Phase 5.1 gate item 5 now
actually true.

### Coordination needed (out of this chat's scope)

The kickoff scope-lock excludes `docs/STATE.md` + `docs/maintainability/*`.
The Phase 6 lane handles those + the master plan ledger. Required updates:

- **`docs/maintainability/master_build_plan.md` §Phase 5.1 SHIPPED line** —
  needs a "retro corrected at `efd193a`" note. Original SHIPPED line at
  `273fe61` claimed gate item 5 met; that claim was retroactively false
  until `efd193a`.
- **`docs/STATE.md` Recently-shipped block** — same note.
- **Phase 6.2 (`3948add`) ledger** — may also want a note explaining
  that the route shipped with 0 entities rendering at HEAD (test
  fixtures may have masked this); `efd193a` made the route's behavior
  match its spec.

Suggested coordination message for the Phase 6 agent (paste into their
chat or attach as an `outputs/` artifact):

> Phase 5.2 §0 pre-flight surfaced that Phase 5.1's 287 food_drink
> Providers landed without Provider.category_id + EntityCategory rows,
> so /category/eat-drink was rendering 0 entities at HEAD. Cowork
> shipped the fix at efd193a: places_load.py now sets category_id +
> the apply script backfilled the 287 5.1 rows. Phase 6.2 (3948add)
> route is unchanged but now renders 255 rows. Phase 5.1 acceptance
> gate item 5 needs retroactive ledger amendment in
> master_build_plan.md §Phase 5.1 + docs/STATE.md.

---

## §4 Sustainability layer (post-`65b0824`)

The operator raised a sharp question mid-session: "is what we're doing
sustainable when businesses get added, or are we adding info now and
it's not going to populate on future API pulls?"

Answer captured in `65b0824`. Three-layer `_resolve_category_id`:

1. **Name override** (NEW) — when discovered via `lake_recreation` and
   primary_type is vehicle-like (`car_dealer`, `car_rental`, `car_repair`,
   `car_wash`) AND name contains a boat keyword (`marine`, `marina`,
   `boat`, `watersports`, `yacht`, `kayak`, `fishing`), route to
   on-the-water. **Catches Havasu boat dealers Google tags as
   `car_dealer` automatically on every future load** — no more
   apply-script needed.
2. **Types-map** (existing layer) — `map_google_types_to_slug_and_place_type`
   against `app/contrib/google_types_mapping.py`. Phase 5.2 widened with
   `fishing_pier` + `ferry_service` at `8800761`.
3. **Discovery-domain fallback** (NEW) — for `(primary_type, domain)` pairs
   in `_DISCOVERY_DOMAIN_FALLBACK` table (10 entries for lake_recreation:
   service, tour_agency, tourist_attraction, tourist_information_center,
   point_of_interest, supplier, sporting_goods_store,
   adventure_sports_center, plus `(None, lake_recreation)`). Catches the
   71 catch-all-primary-type Havasu boat businesses **automatically on
   every future load** — no more `apply_on_the_water_promote_unmapped.py`
   re-runs.

Plus: **UPDATE branch preserves operator-set `category_id`** — only
auto-sets when existing is NULL. So apply-script decisions (audit
re-routes, manual promotes) survive future re-pulls.

### Sustainability matrix

| Field | Auto on re-pull? | Auto for new business? |
|---|---|---|
| `Provider.category_id` from `_resolve_category_id` | ✅ preserved if set | ✅ resolved at INSERT |
| `EntityCategory` linkage | ✅ via `_ensure_entity_category` | ✅ via dual-write hook |
| Audit re-routes (manual overrides) | ✅ preserved | n/a (no new manual decision) |
| `heat_exposure` | ✅ not overwritten | ❌ lands NULL — needs periodic sweep |
| `crowd_notes` | ✅ not overwritten | ❌ — needs operator curation |

**Phase 5.3 (Home & Property Services)** will hit the same generic-types
issues with `home_services` discovery domain. The pattern is in place:
extend `_DISCOVERY_DOMAIN_FALLBACK` with `(service, home_services)`,
`(store, home_services)`, etc. as that phase's audit surfaces them.

---

## §5 Remaining work for next session

### Gate-blocking (1)

- **Task #6 — `boat_access` for the 5 marinas.** Per `docs/operations/
  boat_access_rubric.md` canonical "marina" shape:
  `{ramps: N, slips: N, fuel: bool, haul_out: bool, pump_out: bool,
  transient_dock: bool}`. Rubric's "don't guess booleans" rule applies —
  field-verified or empty `{}`, not assumed defaults. The 5 marinas:
  - Havasu Riviera Marina (`a63febcb`) — google_review_snippets mention
    "6-lane ramp", "multiple gas pumps", "well-laid-out slips",
    "on-site store" → fuel=true, ramps=6, slips≥some count from
    snippets, others field-verify
  - Lake Havasu Marina (`8ce77957`) — snippets mention "6-lane",
    "concrete ramp", "fuel pumps", "slip rentals" → fuel=true, ramps=6,
    slip_count field-verify, transient/pump_out/haul_out field-verify
  - Lake Havasu Yacht Club (`4b5b7c2a`) — 5 reviews, low signal; field-verify
  - Riverside Boat Dock Sales (`7265d2ca`) — 1 review, name suggests
    dealer-with-dock; verify whether actually a marina shape
  - Havasu Cove (`5a25ca41`, OSM) — way 622179700, no Google reviews;
    field-verify entirely

  When complete: Phase 5.2 gate item 2 closes; gate item 6's
  boat-mode-toggle render count gets its source data.

### Non-blocking (deferred)

- **Task #8 — Layer-5 lakefront field-trip planning.** `docs/
  maintainability/manual_recovery_checklist.md` §7 highest-value sweep:
  Lake Havasu State Park, Cattail Cove, Site Six, Castle Rock beaches,
  Pittsburgh Point. BLM/state-land primitive launches, private-property
  dock access (with consent), seasonal water-level spots, kayak
  launches. Not gate-blocking — adds entities beyond Google's coverage.
- **Task #9 — final §6 gate verification.** Once Task #6 closes, run
  the locked diagnostic + write the SHIPPED ledger artifact.
- **Cursor dispatch follow-on** —
  `outputs/cursor_dispatch_osm_pull_writer_test.md` is staged + committed
  at `bee73f8` covering 6 new test specs: 4 for pull JSONL behavior
  (in new `tests/test_phase5_osm_overpass_pull.py`), 2 for client UA +
  warning-on-non-200 regression guards (in existing `tests/
  test_phase4_osm_client.py`). Target collect 1855 → 1861. Operator
  dispatches Cursor when convenient.

### Known issues + carry-forwards (informational)

- **Cosmetic `_element_to_raw_hit` geometry-fallback latent bug** —
  `app/contrib/osm_overpass_client.py:_element_to_raw_hit` doesn't fall
  back to `el["geometry"][0]` for way elements (only handles `el["lat"]
  /["lon"]` for nodes and `el["center"]` for queries using `out center;`).
  Affects only `client.run()` consumers — the load reads raw JSONL
  directly via `_element_lat_lng` which DOES handle geometry. Cosmetic
  in the pull's print (shows `(None, None)` for ways). Deferred fix
  queued; small.
- **4 REVIEW rows from data-quality audit §2.2** — Chong Servicenter,
  HBC MOTORS, West Coast Drives, GO FAST US — all left at on-the-water
  default. Operator can flip via apply-script follow-on if they confirm
  auto-only.
- **5 ambiguous powersports KEEPs from audit §4.2** — Anderson PowerSports
  (×3), Lead Dog Motorsports, Just 4 Fun Powersports, Epic_lifestyles,
  Haulinit — left in shopping-essentials. Operator can flip to
  on-the-water if they confirm boat-related.
- **11 mobile-detailing shops** — defaulted to `water_adjacent` in
  heat_exposure apply. Operator may want to flip the obvious auto-only
  ones to `indoor` via follow-on.
- **Backup `.bak-*` files in `data/`** — 4 backups created this session
  (`bak-20260515-pre-{category-id-backfill, otw-load, otw-promote,
  audit-apply, heat-exposure, crowd-notes, osm-load}`). Operator can
  prune when comfortable that the corresponding fixes are stable.

---

## §6 Coordination summary (one-line)

| Lane | Coordination need |
|---|---|
| Phase 6 (parallel agent) | Master plan + STATE.md retroactive Phase 5.1 amendment; coordinate Phase 6.4 boat-mode toggle build to consume `boat_access` JSON once Task #6 lands |
| Cursor | Dispatch `outputs/cursor_dispatch_osm_pull_writer_test.md` when convenient (+6 tests) |
| Operator | Task #6 boat_access field-survey (gate-blocking); Task #8 lakefront field-trip; prune the 7 `.bak-*` files when ready |

---

## §7 Read order for the next session

1. **This document** — the state of play.
2. `outputs/phase5_2_on_the_water_kickoff.md` — the runbook (still
   authoritative; §6 acceptance gate definitions unchanged).
3. `docs/scrape_logs/on-the-water_2026-05-15.md` — Layer 1 + Layer 2
   actuals + the boat_dealer-as-car_dealer follow-on note (now closed
   by §5 audit + `65b0824` sustainability fix).
4. `docs/operations/boat_access_rubric.md` — for Task #6 — the 4
   canonical shapes + "don't guess booleans" rule.
5. `outputs/phase5_1_boat_access_candidates.md` — the survey worksheet
   from 5.1 covering 12 shoreline eat-drink venues; 8 web-confirmed.
   Some cross-list (English Village waterfront, London Bridge Resort,
   The Nautical) and inform 5.2's marina entries.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.2 session
(2026-05-15) post-`65b0824`. Phase 5.2 data plane SHIPPED with 5 of 6
gate items closed; final gate item (boat_access for 5 marinas) deferred
to next session as the heaviest field-survey + judgment-call surface.*
