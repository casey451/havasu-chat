# Phase 5.8 Kickoff — Events (`events`)

> **What this is:** a single paste-and-go operator runbook for Phase 5.8,
> the eighth Tier 1 category. Mirrors
> `outputs/phase5_7_outdoors_parks_trails_kickoff.md` shape with
> 5.8-specific overrides. **Single-layer scrape** (Google only — no OSM
> path for events) over a Narrow-scope subset of the
> `entertainment_attractions` domain (the 7 labels deferred in 5.7).
>
> **GATE 1 — Phase 5.7 SHIPPED** at `e60b051` (2026-05-17) with all 6
> gate items cleared, plus the SHA-cleanup commit at `4b20e37`. ✅ Met.
>
> **GATE 2 — no pre-built verifier surface for 5.8.** There is no
> consolidated public registry for "events" the way AZ ROC covers
> contractors or NPI covers medical providers. Three narrow paths exist
> (AZ event aggregators like visitarizona.com / eventbrite-local;
> LHC Tourism Board at golakehavasu.com; local newspaper events
> sections) but none cover the full V1 surface, all are
> scraping-shape not API-shape, and the V1 utility of a "verified
> via tourism board" badge for an art gallery is low. **This kickoff
> resolves §3 as Option C** (defer Layer-4 verifier surface to V1.5;
> document the three paths). Mirrors 5.5 + 5.6 + 5.7 outcome.
>
> **GATE 3 — pre-flight integrity gotcha (now FIFTH+ recurrence
> watch):** `scripts/places_categories.json` has drifted locally on
> every 5.x session since 5.5 (5.5 / 5.6 / 5.7-boot / 5.7-session-2-
> pre-flight). The 5.7 boot session widened the check to a **four-file
> shape check** (places_categories.json + places_load.py + models.py
> + google_types_mapping.py); 5.7 session 2 found the four-file shape
> clean at §0. The fifth recurrence forecast did NOT materialize but
> the pattern remains watch-worthy. Pre-flight item #6 below is the
> same four-file check.
>
> **🚨 BOOT-PROMPT FRAMING NOTE (none for 5.8):** Unlike the 5.7 boot
> prompt which referenced a nonexistent `outdoor_recreation` domain,
> the 5.8 boot prompt at
> `outputs/phase5_8_events_next_agent_boot_prompt.md` framing is
> verified accurate per `app/contrib/google_places_scraper.py:89` —
> `"events": frozenset({"entertainment_attractions"})` is a real
> single-domain mapping. No framing-correction note needed.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.7 session 2
> (2026-05-17) post-`e60b051` + `4b20e37` SHA-cleanup, pre-§0.
> Pastable as-is; commit inline before §0 pre-flight dispatches per
> the established cadence.

---

## §0 Pre-flight (do once, at Phase 5.8 dispatch)

1. **`git log --oneline -15`** — origin should top at `4b20e37`
   (Phase 5.7 SHA-cleanup) over `e60b051` (Phase 5.7 SHIP) or later
   if Phase 6 lane has shipped Amendment 7 between sessions (in-line
   a la `0addb63` for 5.4 OR via Claude Code parallel dispatch). The
   5.7 session 2 lane chain since 5.7 session 1's `c2bdb6d`:
   `5f8fe08 → e60b051 → 4b20e37`.
2. **`git status`** — clean. **Sandbox bash note:** `git status` hits
   the index-format gotcha (`fatal: unknown index entry format
   0xffff0000`); run Windows-side via PowerShell. Carry-over
   untracked from 5.7: `hava_api_catalog.docx` + `~$va_api_catalog.docx`
   Word lock + 2 historical `outputs/ci_*_log_failed.txt` files +
   `outputs/_deltest` — all unrelated to lane; operator prunes when
   comfortable.
3. **`python -m alembic current`** — confirm local `data/events.db` at
   `0a1b2c3d4e5f`. If behind, `python -m alembic upgrade head`. (No
   migrations expected on the 5.8 lane unless the parks-rec-scrapes
   prune-fix sidecar lands — that would add an `ON DELETE SET NULL`
   migration on `contributions.created_event_id`.)
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — record
   baseline. Phase 5.7 closed at **1946 collected** (5.6 baseline 1932
   + 14 in-lane regression guards for the `1dfd28e`
   `_DISCOVERY_DOMAIN_FALLBACK` + `_PRIMARY_TYPE_MAP` extensions for
   the `entertainment_attractions` domain catch-all). Verify no
   drift.
5. **`python outputs/diagnose_category_id_gap.py`** — confirm Phases
   5.1, 5.2, 5.3, 5.4, 5.5, 5.6, and 5.7 categorization is intact and
   the `events` slug exists in the `categories` table (id=2 per the
   diagnose script output from session 1).
6. **🚨 WIDENED four-file shape check** (carried from 5.7 §0):
   ```powershell
   git diff --stat scripts/places_categories.json scripts/places_load.py app/db/models.py app/contrib/google_types_mapping.py
   ```
   MUST be empty. If ANY of the four shows deletions in the working
   tree, restore via `git restore .` Windows-side before §1. The
   expected HEAD line counts post-`4b20e37` (sanity reference, not
   validation targets — content over shape):
   - `scripts/places_categories.json`: 211 lines
   - `scripts/places_load.py`: 639+ lines (carries 5.7 `1dfd28e`
     extensions)
   - `app/db/models.py`: 1539+ lines
   - `app/contrib/google_types_mapping.py`: 153+ lines (carries
     `golf_course` + `medical_clinic` widenings from `1dfd28e`)
7. **Google Places key + spend cap** — operator has deferred rotation
   until project end; still in `.env`, still capped. No mid-session
   rotation needed unless the operator opts in.
8. **CI state** — check GitHub Actions on the top commit. Should be
   ✅ green on `4b20e37` (the 5.7 SHA-cleanup commit, docs-only) and
   `e60b051` (the 5.7 SHIP commit; ✓ confirmed at session 2 close).
   If red, investigate before starting 5.8. The `parks-rec-scrapes`
   scheduled cron has been ❌ since 5.3 — root cause identified at
   5.7 §4.5 sidebar; **NOT in 5.8 scope** unless operator opts to
   dispatch the parks-rec-prune sidecar fix as part of this lane.
9. **DB state spot-check** — `outdoors-parks-trails` should show
   **27 entries / 0 verified / 26 outdoor + 1 indoor / 26 render (1
   drafted) / 10 long-form crowd_notes** (the 5.7 SHIPPED state).
   `events` should show **2 entries pre-load** (Buses By The Bridge,
   event_venue, annual bus festival; Desert Storm Headquarters,
   event_venue, annual boat poker run venue — both FLIPped from
   outdoors-parks-trails at 5.7 §2; both `entity_type='commercial'`;
   both source `google_places`). **5.8 needs to net at least +18
   new entries** to clear the 20-entry gate (see §6).

---

## §1 The scrape sequence — Google only, NARROW scope

Phase 5.8 is **single-layer** (no OSM dispatch — OSM Overpass doesn't
have an events surface). **Scope is intentionally narrowed** from the
literal 10-label `entertainment_attractions` bundle in
`DISCOVERY_CATEGORY_TO_DOMAINS["events"]` because of one structural
collision:

1. **Phase 5.7 already absorbed parks / golf courses / mini golf**
   into outdoors-parks-trails (cat-7). Re-scraping those 3 labels in
   5.8 would either (a) double-categorize the existing cat-7
   entities via the ambig path, or (b) fight the `1dfd28e`
   `(None, "entertainment_attractions") → "outdoors-parks-trails"`
   catch-all (which 5.8 will PIVOT — see below). **Defer the 3
   cat-7 labels.**

This leaves **7 labels in scope for 5.8 §1:**

| Bucket | Labels (7) | Domain |
|---|---|---|
| **Event venues + festivals** | event venues, live music venues | entertainment_attractions |
| **Arts + culture** | art galleries, museums | entertainment_attractions |
| **Indoor entertainment** | movie theaters, bowling alleys, arcades | entertainment_attractions |

### Layer 1 — Google Places

```
python -m scripts.places_discovery --category events --dry-run
python -m scripts.places_discovery --category events
python -m scripts.places_enrichment --limit 200
python -m scripts.places_load --category events --dry-run
python -m scripts.places_load --category events
```

**Why `--limit 200` on enrichment?** 7 labels × ~10 per label ≈ 70
raw hits; the cumulative enrichment cache (5.0/5.1/5.2/5.3/5.4/5.5/
5.6/5.7) is ~2,700+ records. Most will cache-hit. Expected new
enrichments: ~30-50.

⚠️ **The `--category events` flag will filter
`places_categories.json` by
`DISCOVERY_CATEGORY_TO_DOMAINS["events"]` which returns ONLY
`entertainment_attractions` (single-domain mapping).** This pulls in
all 10 entertainment_attractions labels by default — including the 3
we want to defer. **Two paths** to honor the Narrow scope (same shape
as 5.7's Path A vs Path B decision):

- **Path A (recommended — minimal code change):** Author a one-shot
  filter script `outputs/phase5_8_narrow_label_filter.py` that
  short-circuits the discovery loop to only the 7 in-scope labels.
  Mirrors `outputs/phase5_7_narrow_label_filter.py` shape from 5.7
  exactly — same Path A.2 pattern (standalone outputs/ wrapper, no
  production code touched). ~20 lines.
- **Path B (broader change):** Temporarily filter the 7 labels at
  the production-code level — riskier; not recommended.

**Default to Path A unless operator picks B.**

### Sustainability layer PIVOT — Required before §1 Layer 1

**The 5.7 `1dfd28e` sustainability commit added
`(None, "entertainment_attractions") → "outdoors-parks-trails"`
as a domain-wide catch-all.** For 5.8 this routes the wrong way —
5.8's `art_gallery` / `event_venue` / `live_music_venue` / `museum` /
`movie_theater` / `bowling_alley` / `amusement_arcade` primary_types
would land in outdoors-parks-trails instead of events.

**Three options** (operator picks at §1 dispatch time; recommended
default is **Option A**):

**(A — recommended) Add direct `_PRIMARY_TYPE_MAP` entries** for the
expected events primary_types. Direct mappings beat catch-all per
resolver order, so wildlife_refuge / golf_course stay in
outdoors-parks-trails while the new event primary_types route to
events. Example shape (`app/contrib/google_types_mapping.py`
`_PRIMARY_TYPE_MAP`):

```python
"event_venue": ("events", "commercial"),
"art_gallery": ("events", "place"),
"museum": ("events", "place"),
"live_music_venue": ("events", "commercial"),
"movie_theater": ("events", "commercial"),
"bowling_alley": ("events", "commercial"),
"amusement_arcade": ("events", "commercial"),
```

The `commercial`-vs-`place` distinction follows 5.7's pattern: venues
that charge admission / run shows = `commercial`; venues that are
primarily-public-good (free admission museums, public art galleries)
= `place`. **Operator note:** if LHC's museums and galleries charge
admission (most do), flip them to `commercial`. The above split is a
starting point.

**(B) Re-route the catch-all** — change `(None,
"entertainment_attractions") → "outdoors-parks-trails"` to `... →
"events"`, then add 1-2 `_PRIMARY_TYPE_MAP` entries for
`wildlife_refuge` and other 5.7-specific edge cases. Reverses the
default but preserves wildlife_refuge → cat-7 explicitly.

**(C — hybrid)** — add the 7 event primary_types via Option A, AND
re-route the catch-all to events via Option B. Most explicit +
future-proof but slightly bigger surface area.

**Recommended: Option A.** Minimal diff, no need to revert 5.7's
catch-all (which was correct for 5.7's scope), direct mappings are
the cleanest pattern.

**Sustainability-layer commit shape:** mirror `1dfd28e` /
`44e8097` — a single focused `fix(scripts)` commit that adds the 7
`_PRIMARY_TYPE_MAP` entries + regression tests in
`tests/test_phase5_8_places_load_resolver.py` (~10 parametrized
asserts: 7 for the new primary types + 3 defensive preservation of
prior phases' fallbacks + golf_course / medical_clinic / wildlife_refuge
soft-edges). Land BEFORE the §1 Layer 1 dispatch
(sustainability-first pattern from 5.5/5.6/5.7).

### Layer 5 — Manual recovery (deferred to operator)

Per `docs/maintainability/manual_recovery_checklist.md`. Surface for
5.8:

- Recurring annual festivals not indexed by Google Maps as venues
  (London Bridge Days, Lake Havasu Boat Show, Havasu Balloon Festival
  — these may exist only as historical event records on tourism
  pages, not Google place_ids).
- Outdoor concert series at parks (the Rotary Park amphitheater
  hosts seasonal music events that may surface under cat-7 parks
  rather than cat-2 events).
- LHC City Hall + Library cultural events (lecture series, gallery
  shows) — typically calendar entries, not place_ids.
- Pop-up event venues + private galleries not indexed by Google.

Not gate-blocking for V1 ship.

---

## §2 Ambiguous-queue review — moderate volume + cross-category overlap expected

Events is the **eighth non-empty-DB load** (after 5.1+5.2+5.3+5.4+
5.5+5.6+5.7). Reconciler will match against **~1,151+ existing
entities** (post-5.7: 287 eat-drink + 119 on-the-water + 230 HPS +
265 HWC + 140 auto-rv-fuel + 76 shopping-essentials + 27
outdoors-parks-trails + 2 events + 1 public-civic-resources +
others). Expected ambiguous hits: **20-60 per run** (range covers
moderate label coverage offset by significant cross-cat overlap risk
with cat-7 outdoors-parks-trails).

**Special audit categories expected for 5.8:**

| Existing entity | 5.8 candidate it'll likely match | V1 policy |
|---|---|---|
| Lake Havasu Museum of History (currently in on-the-water from 5.2 — surfaced in 5.7 §5 audit) | museums (cat-2) | **review** — may want to FLIP to cat-2 if museum is the primary draw |
| Art galleries currently in cat-7 outdoors-parks-trails (from 5.7) | art galleries (cat-2) | review — FLIP if any surfaced |
| Buses By The Bridge / Desert Storm HQ (currently in cat-2 from 5.7 §2 FLIPs) | event venues (cat-2) | **same-cat update** (refresh address / snippets) |
| Event venue at hotel / resort (cat-10 lodging) | event venues (cat-2) | edge case — events may be sub-amenity of resort |
| Live music venue at restaurant / bar (cat-1 eat-drink) | live music venues (cat-2) | likely **stay in cat-1** if food-primary; cross-link if both apply |
| Bowling alley at family entertainment center | bowling alleys (cat-2) | KEEP cat-2 |
| Arcade at bowling alley | arcades (cat-2) | review — combo venue may already be cat-2 from bowling label |

**Cross-cat sweep with cat-7 (Phase 5.7) — primary 5.8 audit focus:**

5.7's `(None, "entertainment_attractions") → "outdoors-parks-trails"`
catch-all swept 9 edge-case primary_types into cat-7 (5.7 audit doc
§4 Slice C — Bill Williams NWR / SARA Disc Golf / Motocross Park /
Ofd Racing / Thompson Bay Beach / Sportsman's Club / Butterfly Garden
/ 2 Sara hiking trail entries). **None of those 9 should re-route to
cat-2 events.** The cat-7 → cat-2 cross-cat check is mostly about
catching what's NEW in 5.8's scrape that overlaps with what 5.7
already loaded.

**Pre-existing 2 entities in events are `entity_type='commercial'`** —
event_venue primary_type maps to `(events, commercial)` per the
Option A sustainability extension. These 2 were ingested as cat-7
entries from 5.7's `entertainment_attractions` discovery, then
FLIPped to cat-2 via the 5.7 §2 apply-script (which only changes
EntityCategory linkage, not entity_type). **5.8 §2 audit should
decide:** leave as commercial for V1 (recommended — same shape as
5.7's cat-7 entries).

Mirror the 5.7 audit pattern: post-load audit pulls cross-category +
same-category; an apply-script batches the misroute decisions if
any. **Expected outcome based on 5.4/5.5/5.6/5.7 history: 0 real
misroutes**, plus same-cat updates to the 2 pre-existing entries
(name normalization, snippet refresh, etc.).

If a single load produces **>60** ambiguous hits, consider tuning
`GEO_PROXIMITY_THRESHOLD_M` (currently `50.0`) per brief §4.g — but
prior phases have all stayed under the tune threshold despite
exceeding 50.

### Cross-category sweep — `_DISCOVERY_DOMAIN_FALLBACK` catch-all behavior

Per 5.6 close-out §3 / 5.7 close-out §5: the
`(None, "<domain>")` catch-all routes ALL unmapped primary_types
under that domain (not just rows with `primary_type=None`). 5.7's
`(None, "entertainment_attractions")` swept ~5 edge-case providers
into cat-7 outdoors-parks-trails. **5.8 needs to PIVOT this catch-
all per §1** — Option A's direct `_PRIMARY_TYPE_MAP` entries route
the 7 expected event primary_types via direct mapping, NOT via the
catch-all (which stays pointing at cat-7).

Apply-script `outputs/apply_phase5_8_events_audit.py` if any FLIPs
needed. Expected size: ~5-15 rows reviewed, likely 0 FLIPs (direct
mapping prevents most spillover).

---

## §3 Layer-4 verifier surface — Option C resolved (deferred to V1.5)

**5.8 has no pre-built verifier** (unlike 5.3's `az_roc_verify` and
5.4's `npi_verify`). Three narrow options exist; this kickoff
resolves §3 as **Option C** per the structural reasoning in the
header. The other two paths are documented here for V1.5 pickup.

### Option A — AZ event aggregators (DEFERRED to V1.5)

URLs:
- `https://www.visitarizona.com/events` — statewide event calendar;
  filterable by region. Covers state-level festivals + tourism
  events that include LHC.
- `https://www.eventbrite.com/d/az--lake-havasu-city/all-events/` —
  ticketed events in LHC. Less curated; high noise.

Coverage: ~5-10 of 5.8's likely entries (most LHC events are local-
only and don't make state aggregators).

**Cost-of-build:** ~3-5 hours (visitarizona.com is JavaScript-
rendered, would need Playwright; eventbrite has anti-bot measures).
**Coverage is too narrow for V1 to justify the build.**

### Option B — LHC Tourism Board (DEFERRED to V1.5)

URL: `https://www.golakehavasu.com` — LHC's official tourism site
with event calendar. JavaScript-rendered (would need Playwright).
Covers major LHC events comprehensively (Boat Show, London Bridge
Days, Balloon Festival, etc.) but not venue-level entries.

**Cost-of-build:** ~4-6 hours. Coverage maps best to recurring annual
events (which are mostly already in cat-2 from 5.7's FLIPs and
Layer 5 manual recovery candidates), not venue-level Provider rows.
**Highest value of the three for events-the-thing (vs venues-where-
events-happen) but still V1.5 territory.**

### Option C — Defer verifier surface to V1.5 ✅ SELECTED

Gate item 3 rephrased to **"Layer-4 verifier surface scoped — built
or explicitly deferred to V1.5"**. Document AZ aggregators + LHC
Tourism Board paths in this kickoff and ship 5.8 without verifier
surface. Lowest-friction shape; mirrors 5.5 + 5.6 + 5.7 outcome.

**Rationale:** events verification has low V1 utility (consumer
discovery doesn't need a "verified by visit arizona" badge on a
local bowling alley to be useful); the available paths are all
scraping-shape not API-shape; coverage is fragmented. Better to
defer the whole verifier surface to V1.5 when the right shape can
be designed against fuller scope.

---

## §4 Operator-curated field entry — Events rubric

Lighter operator surface than 5.7 (no `is_mobile_service` to curate
— events are venue-based); roughly on par with 5.6/5.7 shape but
with a **mixed heat_exposure default** (vs 5.6's `indoor` default
and 5.7's `outdoor` default):

- **`heat_exposure`** — **`indoor` for most 5.8 entries** (movie
  theaters, bowling alleys, arcades, art galleries, museums are all
  indoor by-definition). **`outdoor` overrides** expected for: the 2
  pre-existing event_venue FLIPs from 5.7 (Buses By The Bridge =
  festival = outdoor; Desert Storm Headquarters = outdoor boat poker
  run venue), plus any open-air amphitheater / outdoor concert
  venue that surfaces in §1. Mirror
  `outputs/apply_phase5_6_shopping_heat_exposure.py` exactly: default
  `indoor` + populate `OUTDOOR_OVERRIDES` list. Expected override
  count: **2-5** (the 2 carried + 0-3 new from §1 scrape).
- **`crowd_notes`** — short-form for typical entries; long-form for
  the top-10 by review count. Events reviewer signals tend to be:
  staff helpfulness, seating quality (theaters), ambiance / lighting
  (galleries, music venues), pricing / value, parking, event
  frequency, kid-friendliness (bowling / arcades), age range, alcohol
  service. For museums: exhibit quality, kid-engagement,
  wheelchair-accessibility, gift shop, restrooms. For event venues:
  staff coordination, capacity, food + beverage options, parking,
  sound quality.

Drafts source: **`Provider.google_review_snippets` (own column, not
`attributes`)** — per the 5.4 close-out §4 source-path correction.
Expected snippet coverage: **~70-85%** (event venues have moderate
review density; movie theaters + bowling alleys typically abundant;
art galleries less abundant; festivals very abundant if recurring).

**`is_mobile_service`** is NOT a gate item for 5.8 (events are
venue-based; "mobile service" is meaningless for an art gallery).
Skip the `is_mobile_service` apply-script for 5.8.

**`attributes`** JSON — can be extended with events-specific keys:
`has_food_concession` (bool), `accepts_alcohol` (bool),
`wheelchair_accessible` (bool), `kid_friendly` (bool),
`parking_type` (str), `seating_type` (str). For museums:
`exhibits_rotate` (bool), `gift_shop` (bool). For movie theaters:
`screen_count` (int), `imax` (bool). Brief §3.4 has the suggestion
shape.

### §4.5 sidebar — `parks-rec-scrapes` prune-fix dispatch (optional)

The scheduled `parks-rec-scrapes` GitHub Actions workflow has been
❌ on cron triggers since at least Phase 5.3. Root cause was
identified in 5.7 §4.5 sidebar: Postgres FK constraint violation
in `scripts/parks_rec_prune.py` — DELETE on `events` table blocked
by `contributions.created_event_id` FK. **3 fix options** surfaced
in `outputs/phase5_7_session_closeout.md` §3:

1. **Alembic migration** adding `ON DELETE SET NULL` on
   `contributions.created_event_id` FK (recommended; least
   destructive).
2. **`parks_rec_prune.py`** adds `WHERE NOT EXISTS (SELECT 1 FROM
   contributions ...)` clause — preserves both rows; events stay
   forever if cited by a contribution.
3. **`ON DELETE CASCADE`** — destructive; deletes contributions
   when referenced event is pruned. Probably wrong UX, listed for
   completeness.

**Operator decision at 5.8 §0 dispatch time:** include the prune-fix
in 5.8 scope (sidebar lane), OR keep deferred to Phase 6 / separate
sidecar. The fix is small (1 alembic migration + maybe 2 lines in
parks_rec_prune.py) but lands in a totally different code path
from 5.8's data plane. **Default recommendation: defer to a
separate sidecar dispatch** unless operator wants to cover it
opportunistically.

If included: author the migration + commit BEFORE §1 dispatch.
Migration file: `alembic/versions/<sha>_phase5_8_contributions_fk_
set_null.py`. Apply via `python -m alembic upgrade head` locally
(no-op on existing rows since no contributions point to deleted
events yet); deploys via CI. Mark as Decision 4 if included.

---

## §5 Daily / weekly rhythm (brief §5)

Similar cadence to 5.5/5.6/5.7 but with a sustainability PIVOT pre-
flight step:

| Day | Work |
|---|---|
| 1 | Sustainability-layer commit (Option A — 7 `_PRIMARY_TYPE_MAP` entries) BEFORE Layer 1; then Google scrape run + scrape log (`docs/scrape_logs/events_<YYYY-MM-DD>.md`) + Narrow-scope filter script if Path A picked |
| 2 | Ambiguous-queue triage + data-quality audit (cross-category review per §2; sweep the 2 pre-existing entries for name/snippet refresh) |
| 3 | Verifier surface — Option C deferral confirmed in §3; document V1.5 paths |
| 3-4 | `crowd_notes` for top-10 + `heat_exposure` sweep (indoor default + OUTDOOR_OVERRIDES) |
| 4 | Optional: `parks-rec-scrapes` prune-fix sidebar (§4.5) if Decision 4 included in 5.8 scope |
| 5 | Optional Layer 5 manual recovery (recurring festivals, outdoor concerts at parks, pop-up venues) |
| 6 | QA spot-check — 10 random entries vs. the §4 rubric |

**Expected Phase 5.8 total: 6-10 hours over 1 week.** Lighter than
5.5/5.6 because Narrow scope drops 3 of 10 labels; offset slightly
by the §4.5 prune-fix sidebar if included.

---

## §6 Acceptance gate — Phase 5.8 closes when ALL of:

- [ ] **20+ entries** in `events` post-load (modest target — LHC
      event venue density is moderate; 2 pre-existing + ≥18 net-new
      from Layer 1). Gate-1 query MUST use the
      `(e.entity_type != 'commercial' OR provider-visible)` shape
      from `outputs/phase5_2_gate_verification.py` and
      `outputs/phase5_6_gate_verification.py` /
      `outputs/phase5_7_gate_verification.py` to correctly count
      `place`-typed entries (art_gallery / museum primary_types map
      to `place` per the Option A sustainability extension; the 2
      pre-existing are `commercial`).
- [ ] All Google ↔ existing-entity ambiguous reconciler hits
      reviewed (with cross-category review per §2 — especially the
      cat-7/cat-2 outdoors-parks-trails/events axis for venues
      already in cat-7 + the cat-1/cat-2 eat-drink/live-music axis
      for restaurants with live music).
- [ ] **Layer-4 verifier surface scoped — Option C explicitly
      deferred to V1.5** (per §3). AZ event aggregators + LHC
      Tourism Board paths documented in this kickoff §3 for V1.5
      pickup.
- [ ] Top-10 by review count have long-form `crowd_notes`.
- [ ] `heat_exposure` set on every entry (`indoor` for nearly all;
      `outdoor` only for festival/outdoor-venue entries — expected
      override count 2-5).
- [ ] Phase 6 `/category/events` renders **≥15** per default filter.

**Note: 6 gate items (not 7).** `is_mobile_service` was 5.5-specific
and is dropped for 5.8 — events are venue-based by definition (same
rationale as 5.6's brick-and-mortar retail and 5.7's place-based
parks).

When the gate is met: commit the scrape log, Phase 5.8 gets its
SHIPPED ledger line on `master_build_plan.md` §4 (coordinate with
Phase 6 lane via `outputs/claude_code_dispatch_phase6_amend8.md`),
and **Phase 5.9 (next Tier-1 category — likely
`classes-sports-recreation` or `pets` per the remaining 4-slug list)**
dispatches next.

---

## §7 Reference

- `outputs/phase5_7_session_closeout.md` (the just-shipped 5.7 state
  index — carries the apply-script + audit + sustainability layer
  playbooks 5.8 reuses)
- `outputs/phase5_7_outdoors_parks_trails_kickoff.md` (the 5.7
  runbook this document mirrors)
- `outputs/phase5_2_gate_verification.py` (gate template for
  `entity_type='place'` query shape — relevant for 5.8 since
  art_gallery / museum primary_types map to `place`)
- `outputs/phase5_7_gate_verification.py` (template for the
  equivalent 5.8 gate-verification script — note: 6 items not 7;
  no `is_mobile_service` check; threshold ≥20)
- `outputs/phase5_7_parks_audit.md` (combined pre+post audit
  template for the equivalent 5.8 audit doc)
- `docs/scrape_logs/outdoors-parks-trails_2026-05-17.md` (template
  for the equivalent 5.8 scrape log — author by hand at session
  start if absent)
- `app/contrib/google_types_mapping.py` (entertainment_attractions
  + fitness_sports types — extend per §1 Option A; current state
  carries 5.7's `golf_course` + `medical_clinic` widenings from
  `1dfd28e`)
- `app/contrib/google_places_scraper.py:89`
  (`DISCOVERY_CATEGORY_TO_DOMAINS["events"]` — the source of the
  `entertainment_attractions` single-domain mapping)
- `scripts/places_load.py` (`_resolve_category_id` sustainability
  layer + 5.3 + 5.4 + 5.5 + 5.6 + 5.7 fallback extensions; 5.8
  Option A adds direct `_PRIMARY_TYPE_MAP` entries — same shape as
  `1dfd28e` did for `golf_course`)
- `outputs/diagnose_category_id_gap.py` (re-usable diagnostic)
- `outputs/apply_phase5_7_parks_audit.py` (5.7 audit apply template
  — 5.8's FLIPs + DRAFTs)
- `outputs/apply_phase5_7_parks_heat_exposure.py` (5.7 heat sweep
  template — for 5.8 flip default to `indoor` mirroring 5.6, populate
  `OUTDOOR_OVERRIDES` instead of `INDOOR_OVERRIDES`)
- `outputs/apply_phase5_7_parks_crowd_notes.py` (5.7 crowd_notes
  template — pass dict directly to JSON column per 5.3 `f35d5e4`
  gotcha, F401/F541-clean imports per 5.3 `bff4a79` + 5.7 `5f8fe08`
  lessons)
- `outputs/phase5_7_ambig_audit_dump.py` (5.7 ambig audit dump
  script — direct copy with paths/slug swap for 5.8)
- `outputs/phase5_7_top10_discovery.py` (5.7 top-10 discovery
  helper for crowd_notes drafting — direct copy with slug swap)
- `outputs/phase5_7_narrow_label_filter.py` (5.7 Path A wrapper —
  template for 5.8's equivalent if Path A is picked)

---

## §8 Hand-off context from the Phase 5.7 session

**Important context that's NOT in this kickoff but the new agent
should read in the 5.7 close-out:**

- 2-commit session-2 chain from `c2bdb6d` → `e60b051` → `4b20e37`
  (the F541 fix `5f8fe08` between sessions, then the SHIP commit
  `e60b051`, then the SHA-cleanup `4b20e37`). Total 5.7 lane:
  `f5d1062 → 1dfd28e → 0c011ae → c2bdb6d → 5f8fe08 → e60b051 →
  4b20e37`. Plus 4 DB-only writes (2 loads + 3 apply-scripts).
- **5.7 §0 widened to a 4-file shape check** —
  `places_categories.json` + `places_load.py` + `models.py` +
  `google_types_mapping.py`. The fifth-recurrence forecast for
  `places_categories.json` did NOT materialize at 5.7 session 2 §0.
  Continue the 4-file check in 5.8 §0.
- **5.3 `f35d5e4` JSON-column gotcha was avoided in 5.4 + 5.5 + 5.6
  + 5.7** by passing dict directly to `Entity.crowd_notes` — no
  `json.dumps()`. Internalize.
- **5.3 `bff4a79` F401 footgun + 5.7 `5f8fe08` F541 footgun:**
  `# noqa: E402` silences E402 only. F401 AND F541 still fail ruff.
  Audit apply-script imports for unused `json` / `Category` /
  `EntityCategory` before committing. **5.7 hit F541 in 9 places on
  the dump script** — watch for f-strings in concatenated
  `print(f"abc" f"def")` patterns where individual pieces may lack
  `{}` interpolation.
- **Sandbox bash git-index gotchas** — use `git rev-parse` / `git
  show HEAD:` for index-free reads. Operator runs index-dependent
  ops (incl. `git restore`) Windows-side via PowerShell.
- **Sandbox bash MOUNT-STALENESS gotcha** (recurring since 5.5; 5.6
  hit it twice; 5.7 hit it THREE TIMES with new depth — `.git/
  index.lock` view, `git diff` output, `data/events.db` mtime). The
  Read tool is authoritative; sandbox bash file-shape queries +
  SQLite DB inspection unreliable for post-Edit / post-restore /
  post-commit verification. Use Windows-side `python` for all DB
  queries.
- **PowerShell `git commit -m "" ...` footgun:** empty `-m ""`
  between multiple `-m "..."` flags is treated as a pathspec by
  git's flag parser. Use multiple `-m "..."` flags WITHOUT empty
  separators; git inserts blank lines automatically.
- **NEW for 5.7: PowerShell `\"` escape footgun.** `\"` inside a
  PowerShell `"..."` string is NOT an escape; embedding `\"\"\"` in
  a `git commit -m "..."` body causes git to parse subsequent
  tokens as pathspecs (`fatal: /: '/' is outside repository`). Use
  **single-quoted `-m '...'`** flags for git commit messages when
  the body contains `"` or `/` characters; PS single quotes are
  literal (no interpolation, no escaping).
- **DB-write apply-scripts:** stop the FastAPI dev server if running
  (events.db lock).
- **`Provider.google_review_snippets` is its OWN COLUMN** — not
  inside `attributes` JSON. Drafts for top-10 long-form `crowd_notes`
  source from this column. 5.7's top-10 had 100% snippet coverage
  (5 snippets each); 5.8 forecast 70-85% (event venues less abundant
  than parks).
- **CI can be flaky on intermediate commits** — 5.5 / 5.7-session-1
  both saw the same pattern (one ✓ + one ❌ on the same commit ID,
  short elapsed time = runner-orchestration flake not code). Try
  `gh run rerun <ID>` before shipping a fix commit. Final
  tree-state CI green is the ship-readiness signal.
- **`_DISCOVERY_DOMAIN_FALLBACK` `(None, <domain>)` is a domain-wide
  catch-all** at `places_load.py:368-371`, not a `primary_type=None`
  filter. 5.6 routed 27 edge-case providers via `(None, "retail")`;
  5.7's `(None, "entertainment_attractions")` swept ~5 edge cases
  into cat-7. **5.8 pivots away from this** via Option A direct
  `_PRIMARY_TYPE_MAP` entries — the catch-all stays pointing at
  cat-7 but the direct mappings beat it per resolver order.

**Carry-forwards from the 5.7 session** the new agent should action:

- 🚨 **Phase 6 lane — Phase 5.7 SHIPPED ledger amendment** —
  `outputs/claude_code_dispatch_phase6_amend7.md` is **NOT yet
  authored** (5.7 close-out §6 flagged it as a carry-forward).
  Either author it at 5.8 §0 OR delegate to Claude Code parallel
  agent. Operator decides.
- **`parks-rec-scrapes` prune-fix sidecar** — root cause + 3 fix
  options in 5.7 close-out §3. Optional inclusion at §4.5 (see
  above); default defer to separate sidecar dispatch.
- **V1.5 Layer-4 verifier surface for 5.7** — AZ State Parks + NPS
  + LHC Parks & Rec paths documented in `phase5_7_parks_audit.md`
  §9 carry-forward + kickoff §3 for V1.5 pickup.
- **V1.5: `wildlife_refuge` direct mapping** — soft-edge from 5.7
  (Bill Williams NWR caught by catch-all). 1-line addition same
  shape as `golf_course` widening. Defer.
- **V1.5 soft-edges from 5.7 §6 + §7:** 5 entries flagged for V1.5
  dual-cat consideration (SARA Disc Golf / Motocross / Ofd Racing /
  Thompson Bay Beach / Sportsman's Club). Sara Park Hiking Trail ↔
  Trail Head ~16m-apart pair. Butterfly Garden investigation. ASU
  SWANSON FIELDS name normalization.
- **86 of 265 HWC providers remain `verified=False`** — carry-over
  from 5.4. Operator-driven DBA→NPI follow-up surface (optional
  V1.5).
- **Operator: prune `data/events.db.bak-*` files** when comfortable
  — carry-over from 5.3 + 5.4 + 5.5 + 5.6 + 5.7.
- **Google Places API key rotation** — deferred per operator ("all
  keys will be changed at conclusion of this project").

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.7 session 2
(2026-05-17) post-`e60b051` + `4b20e37` SHA-cleanup, pre-§0. Hand-off
artifact — commit inline before §0 pre-flight dispatches. Cowork
primary picks up at §0 pre-flight after reading
`outputs/phase5_7_session_closeout.md` first and
`outputs/phase5_8_events_next_agent_boot_prompt.md` second.*
