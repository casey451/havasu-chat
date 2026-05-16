# Phase 5.5 Kickoff — Auto, RV & Fuel (`auto-rv-fuel`)

> **What this is:** a single paste-and-go operator runbook for Phase 5.5,
> the fifth Tier 1 category. Mirrors
> `outputs/phase5_4_health_wellness_care_kickoff.md` shape with
> 5.5-specific overrides. **Single-layer scrape** (Google only — OSM
> scope is locked to on-the-water per brief §3.2.e).
>
> **GATE 1 — do not start until Phase 5.4 has closed** its acceptance
> gate (`outputs/phase5_4_gate_verification.py` outputs `ALL 6 ITEMS
> CLEARED`). Per brief §3.2.d, categories run one at a time.
> ✅ **Met at `c13dfff` (Phase 5.4 SHIPPED), close-out doc at `a9a680a`**.
>
> **GATE 2 — no pre-built verifier surface for 5.5** (unlike 5.3's AZ
> ROC and 5.4's NPI registry). The Layer-4 candidate is the **AZ MVD
> Dealer Locator** (`https://azmvd.gov/mvd/locator/Dealers`) which has
> a public search. This kickoff §3 documents the build-or-defer choice.
>
> **Authored by:** Cowork primary, Phase 5 lane, end of Phase 5.4 session
> (2026-05-16) post-`a9a680a`. Hand-off to the next session.

---

## §0 Pre-flight (do once, at Phase 5.5 dispatch)

1. **`git log --oneline -15`** — origin should top at `a9a680a` (Phase
   5.4 close-out) or later if Phase 6 lane has shipped Amendment 4
   between sessions.
2. **`git status`** — clean. **Sandbox bash note:** `git status` hits
   the index-format gotcha (`fatal: unknown index entry format
   0xffff0000`); run Windows-side.
3. **`python -m alembic current`** — confirm local `data/events.db` at
   `0a1b2c3d4e5f`. If behind, `python -m alembic upgrade head`. (No
   migrations expected on the 5.5 lane.)
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — record
   baseline. Phase 5.4 closed at **1909 collected**. Verify no drift.
5. **`python outputs/diagnose_category_id_gap.py`** — confirm Phase
   5.1, 5.2, 5.3, and 5.4 categorization is intact and the
   `auto-rv-fuel` slug exists in the `categories` table.
6. **Google Places key + spend cap** — operator has deferred rotation
   until project end; still in `.env`, still capped. No mid-session
   rotation needed unless the operator opts in.
7. **CI state** — check GitHub Actions on `a9a680a`. Should be ✅ green
   (Phase 5.4 closed at green CI on `c13dfff`). If red, investigate
   before starting 5.5 (`outputs/claude_code_dispatch_red_ci_investigation.md`
   pattern).

---

## §1 The scrape sequence — Google only

Phase 5.5 is **single-layer** (no OSM; OSM scope is locked to
on-the-water only per brief §3.2.e). Layer 1 Google Places handles the
discovery. **Modest sweep** — 14 labels in the `auto` discovery domain
per `app/contrib/google_places_scraper.py:84`
(`"auto-rv-fuel": frozenset({"auto"})`).

### Layer 1 — Google Places

```
python -m scripts.places_discovery --category auto-rv-fuel --dry-run
python -m scripts.places_discovery --category auto-rv-fuel
python -m scripts.places_enrichment --limit 400
python -m scripts.places_load --category auto-rv-fuel --dry-run
python -m scripts.places_load --category auto-rv-fuel
```

**Why `--limit 400` on enrichment?** 14 labels × ~30 per label ≈ 420
raw hits; the cumulative enrichment cache (5.0/5.1/5.2/5.3/5.4) is
already large enough that most of those will cache-hit. Expected new
enrichments: ~20-40.

The 14 discovery labels (from `scripts/places_categories.json` lines
91-104, all `domain: "auto"`):

| Label | Expected hits | Mobile-service candidate? |
|---|---|---|
| auto repair | 25-35 | partial (some shops have mobile lines) |
| oil change | 15-20 | low |
| tire shops | 10-15 | low |
| car wash | 8-12 | very low (car-wash is brick-and-mortar) |
| auto detailing | 6-12 | **HIGH** — many LHC detailers are mobile-only |
| auto body shops | 8-12 | low |
| car dealerships | 8-15 | very low (brick-and-mortar) |
| used car dealers | 10-20 | very low |
| motorcycle dealers | 2-5 | very low |
| motorcycle repair | 4-8 | partial |
| auto parts stores | 5-10 | very low |
| gas stations | 15-25 | n/a (not a service) |
| towing services | 6-12 | **HIGH by definition** (towing IS mobile) |
| car rentals | 4-8 | very low |

**Volume projection:**

| Stage | Expected |
|---|---|
| Discovery requests | ~42 (14 × 3 pages) |
| Discovery cost | ~$1.35 |
| Unique places (raw) | ~200-400 |
| After ZIP filter | ~150-300 |
| Inserts (new) | ~80-180 |
| Ambig-skips | ~20-50 |
| Enrichment cost | ~$0.50-1.20 (most cache-hits) |
| **Total Layer 1 cost** | **~$2-3** |

**Sustainability layer extension expected.** The `auto` domain will
likely surface catch-all primary_types (`service`, `point_of_interest`,
`store`, possibly `None`). After the first load surfaces an operator
queue count, extend `_DISCOVERY_DOMAIN_FALLBACK` in
`scripts/places_load.py` per the same pattern that 5.3 (`7c994aa`) and
5.4 (`fc51940`) used. Anticipated entries:

```python
# Anticipated 5.5 fallback entries (extend after Layer 1 surfaces specific gaps)
(None, "auto"): "auto-rv-fuel",
("service", "auto"): "auto-rv-fuel",
("point_of_interest", "auto"): "auto-rv-fuel",
("store", "auto"): "auto-rv-fuel",
```

### Layer 5 — Manual recovery (deferred to operator)

Per `docs/maintainability/manual_recovery_checklist.md`. The master
plan §4 Phase 5.5 ledger calls out **"RV-specific Layer 5 coverage"**
specifically — Google's `auto` domain does NOT include RV parks /
rentals / dealers / repair (those live under `lake_recreation` per
`scripts/places_categories.json` lines 61-64, and 5.2's on-the-water
scrape already pulled the RV parks). Layer 5 surface for 5.5:

- LHC RV dealer directory (chamber of commerce + LHC.com)
- Mobile RV repair operators (often sole-proprietors without Google
  listings)
- RV-specific Layer 5 may not be gate-blocking for V1 if the existing
  `lake_recreation`-loaded RV parks/dealers stay in `on-the-water`
  category per V1 single-primary policy (see §2 audit).

---

## §2 Ambiguous-queue review — expect moderate volume + RV cross-category

Auto-rv-fuel is the **fifth non-empty-DB load** (after 5.1+5.2+5.3+5.4).
Reconciler will match against 255 + 119 + 230 + 265 = **869 existing
entities**. Expected ambiguous hits: **15-50 per run** (lower than 5.4
because LHC's auto sector has less geo-clustering than the
Mesquite-Ave medical corridor).

**Special audit category: RV cross-list.** 5.2 loaded RV parks (and
some RV dealers/rentals/repair) under `on-the-water`. 5.5 will
re-discover them under the `auto` discovery domain. Three possible
outcomes per row:

| Existing `lake_recreation` row | Reconciler hits 5.5 candidate | V1 policy |
|---|---|---|
| RV park (Crazy Horse, Cattail Cove, etc.) | yes (geo+name) | **stay in on-the-water** (primary use is lake-adjacent camping) |
| RV dealer (e.g. Beaudry RV) | yes (name) | **flip to auto-rv-fuel** if name-match score >85 — actual dealer business |
| RV rental | yes (name) | **case-by-case** — operator decision |
| RV repair | yes (name) | **flip to auto-rv-fuel** — actual service business |

Mirror the 5.4 `phase5_4_health_wellness_pre_load_audit.md` pattern:
post-load audit pulls cross-category + same-category, and an
apply-script batches the misroute decisions. **Note:** the 5.3 Stanley
Steemer-style audit re-route apply-script is the template
(`outputs/apply_phase5_3_home_property_audit.py`); 5.4 had zero
misroutes so no audit apply-script was needed.

If a single load produces **>50** ambiguous hits, consider tuning
`GEO_PROXIMITY_THRESHOLD_M` (currently `50.0`) per brief §4.g. 5.4
documented the medical-plaza false-ambig pattern as a normal-not-tune
signal; 5.5 may surface a similar pattern at the LHC strip-mall
clusters (McCulloch / Lake Havasu Ave corridor).

---

## §3 Layer-4 verifier surface — build, scope-light, or defer

**5.5 has no pre-built verifier** (unlike 5.3's
`scripts/az_roc_verify.py` at `420f893` and 5.4's
`scripts/npi_verify.py` at `5d429aa`). Three options for gate item 3:

### Option A — AZ MVD Dealer Locator (Playwright)

URL: `https://azmvd.gov/mvd/locator/Dealers`. Public search by ZIP /
license number / business name. Mirror the 5.3 AZ ROC pattern:

- `scripts/az_mvd_verify.py` — Playwright-based, sub-trade allowlist
  filter (`car_dealer`, `used_car_dealer`, `motorcycle_dealer`,
  `rv_dealer`).
- 15s no-results timeout per row (5.3's `420f893` pattern).
- Sets `Provider.verified=True`, `verification_method='az_mvd'`,
  `attributes.az_mvd={'license_number': str, 'class': str, 'status': str}`.
- Expected match rate: high for the brick-and-mortar dealer subset
  (~10-25 verified out of ~30-50 dealer-typed candidates).

**Cost-of-build:** ~2-4 hours; high reuse value for any future
state-level dealer-licensing surface. Recommended if the operator
wants gate item 3 to mirror 5.3+5.4's "verification run completed"
phrasing.

### Option B — Towing carrier permit cross-reference (light)

AZ Corporation Commission's "permitted carriers" directory exposes a
JSON search at `https://www.azcc.gov/oai/cc/permitted-carriers` (REST,
no Playwright). Lighter than Option A but narrower coverage (~3-8
verified out of ~6-12 towing candidates).

### Option C — Defer verifier surface to V1.5

Gate item 3 rephrased to **"Layer-4 verifier surface scoped — built or
explicitly deferred to V1.5"**. Document the AZ MVD + AZCC paths in
this kickoff and ship 5.5 without verifier surface. Lowest-friction
shape; aligned with master plan §4 Phase 5.5's lighter scope.

**Recommended:** Option C unless the operator has a strong "verify
everything" preference. The 5.3 + 5.4 verifier surfaces were
gate-required because licensed-trade verification has high
operator-value (consumer trust signal); auto dealer licensing is
lower-stakes for a directory-discovery V1.

---

## §4 Operator-curated field entry — Auto, RV & Fuel rubric

Lighter operator surface than 5.2's `boat_access` field-trip lift;
roughly on par with 5.3/5.4. Three surfaces:

- **`is_mobile_service`** — Boolean on Entity (defaults `False` per
  `app/db/models.py:672-674`). For most auto venues (dealers, gas
  stations, tire shops, brick-and-mortar repair) → leave `False`. For
  the explicit-mobile subset (mobile detailers, mobile mechanics,
  mobile RV techs, towing services) → set `True`. **Acceptance gate
  reading:** "populated on every entry" is trivially met because the
  default is `False`; the curation lift is identifying the `True`
  rows. Mechanical sweep + `MOBILE_SERVICE_OVERRIDES: dict[entity_id_prefix, bool]`
  apply-script mirroring `outputs/apply_phase5_4_health_wellness_heat_exposure.py`
  exactly. Anticipated `True` count: 5-15 entities.
- **`heat_exposure`** — `indoor` for most auto venues (showrooms,
  service bays, parts stores, repair shops). `outdoor` for gas pump
  islands (the dispensing area; the convenience-store inside still
  counts as `indoor` — but `heat_exposure` is per-entity so the
  decision is "what's the dominant surface a customer interacts
  with"). For pure car-wash bays / outdoor detailing → `outdoor`.
  Mirror `outputs/apply_phase5_4_health_wellness_heat_exposure.py`
  exactly; populate `OUTDOOR_OVERRIDES` for the 5-15 gas-station /
  outdoor-detailing entities.
- **`crowd_notes`** — short-form for typical entries; long-form for
  the top-10 by review count. Auto-trade reviewer signals: technician
  names (auto-shops are name-heavy in reviews), warranty work,
  diagnostic accuracy, fair pricing, time-to-completion. For RV
  techs: mobile-service signal, willingness to work at the RV park.
  For gas stations: fuel quality, snack selection, restroom condition,
  fuel pump reliability. Drafts source: **`Provider.google_review_snippets`
  (own column, not `attributes`)** — per the 5.4 close-out §4
  source-path correction.

---

## §5 Daily / weekly rhythm (brief §5)

Similar cadence to 5.3/5.4:

| Day | Work |
|---|---|
| 1 | Google scrape run + scrape log (`docs/scrape_logs/auto-rv-fuel_<YYYY-MM-DD>.md`) + sustainability layer extension if needed |
| 2 | Ambiguous-queue triage + data-quality audit (RV cross-list decisions per §2) |
| 3 | Verifier surface (Option A/B/C — operator decides upfront) |
| 4-5 | `crowd_notes` for top-10 + `heat_exposure` sweep + `is_mobile_service` curation (combined apply-script possible — both are mechanical sweeps with small operator-override sets) |
| 6 | Optional Layer 5 manual recovery (RV-specific per master plan callout) |
| 7 | QA spot-check — 10 random entries vs. the §4 rubric |

**Expected Phase 5.5 total: 8-14 hours over 1 week.** Lighter than 5.4
because of the smaller label sweep (14 vs 28) + no pre-built verifier
surface (or a lightweight option B/C).

---

## §6 Acceptance gate — Phase 5.5 closes when ALL of:

- [ ] **30+ entries** in `auto-rv-fuel` post-load (per master plan
      ledger; aligned with 5.5's ~50-100 target)
- [ ] All Google ↔ existing-entity ambiguous reconciler hits reviewed
      (including the RV cross-list decisions per §2)
- [ ] Layer-4 verifier surface scoped — **built (Option A/B) or
      explicitly deferred to V1.5 (Option C)**. If built: verification
      run completed for the relevant sub-trades.
- [ ] Top-10 by review count have long-form `crowd_notes`
- [ ] `is_mobile_service` populated on every entry (trivially met by
      default `False`; the gate-meaningful sub-bullet is the
      operator-curated `True` set for mobile detailers / mobile RV
      techs / towing services — apply-script committed)
- [ ] `heat_exposure` set on every entry (`indoor` for most, `outdoor`
      for gas pumps / outdoor detailing — same shape as 5.3/5.4)
- [ ] Phase 6 `/category/auto-rv-fuel` renders **≥15** per default
      filter

When the gate is met: commit the scrape log, Phase 5.5 gets its
SHIPPED ledger line on `master_build_plan.md` §4 (coordinate with
Phase 6 lane via `outputs/claude_code_dispatch_phase6_amend5.md`),
and **Phase 5.6 (Shopping, Grocery & Essentials)** dispatches next.

---

## §7 Reference

- `outputs/cursor_brief_phase_5_tier_1_data.md` §3.5 (Auto, RV & Fuel
  playbook — if it exists; else this kickoff is authoritative)
- `outputs/phase5_4_session_closeout.md` (the just-shipped 5.4 state
  index — read first; carries the apply-script + audit + sustainability
  layer playbooks 5.5 reuses verbatim)
- `outputs/phase5_4_health_wellness_care_kickoff.md` (the 5.4 runbook
  this document mirrors)
- `outputs/phase5_4_gate_verification.py` (template for the equivalent
  5.5 gate-verification script)
- `outputs/phase5_4_health_wellness_pre_load_audit.md` (combined pre+post
  audit template for the equivalent 5.5 audit doc — RV cross-list
  decisions are the 5.5-specific surface)
- `docs/scrape_logs/health-wellness-care_2026-05-16.md` (template for
  the equivalent 5.5 scrape log)
- `app/contrib/google_types_mapping.py` (auto types — extend if new
  types surface)
- `scripts/places_load.py` (`_resolve_category_id` sustainability layer
  + 5.3 + 5.4 fallback extensions; extend `_DISCOVERY_DOMAIN_FALLBACK`
  for `auto` catch-alls — likely needed)
- `outputs/diagnose_category_id_gap.py` (re-usable diagnostic)
- `outputs/apply_phase5_4_health_wellness_heat_exposure.py` (5.4 heat
  sweep template — for 5.5 add `OUTDOOR_OVERRIDES` for gas-station /
  outdoor-detailing entities)
- `outputs/apply_phase5_4_health_wellness_crowd_notes.py` (5.4
  crowd_notes template — pass dict directly to JSON column per 5.3
  `f35d5e4` gotcha, F401-clean imports per 5.3 `bff4a79` lesson)
- `outputs/apply_phase5_3_home_property_audit.py` (5.3 audit
  apply-script — template for 5.5 equivalent if RV cross-list flips
  any rows)

---

## §8 Hand-off context from the Phase 5.4 session

**Important context that's NOT in this kickoff but the new agent should
read in the 5.4 close-out:**

- 12-commit chain from `ef23456` → `c13dfff` with 5 surgical fixes
  shipped mid-session (`8d37b86` / `b683ad7` / `fc51940` /
  `fbdd002` + `700fa3f` / `58bc580`).
- **5.3 `f35d5e4` JSON-column gotcha was AVOIDED this session** by
  passing dict directly to `Entity.crowd_notes` — no `json.dumps()`.
  Internalize: `Entity.crowd_notes` is a JSON-typed SQLAlchemy column.
  Pass the dict directly; SQLAlchemy serializes on commit.
- **5.3 `bff4a79` F401 footgun:** `# noqa: E402` silences E402 only.
  Audit apply-script imports for unused `json` / `Category` /
  `EntityCategory` before committing.
- **Sandbox bash git-index gotchas** — use `git rev-parse` / `git show
  HEAD:` for index-free reads. Operator runs index-dependent ops
  Windows-side via PowerShell.
- **DB-write apply-scripts:** stop the FastAPI dev server if running
  (events.db lock).
- **`Provider.google_review_snippets` is its OWN COLUMN** — not inside
  `attributes` JSON. The 5.4 close-out §4 documented this correction;
  drafts for top-10 long-form `crowd_notes` source from this column.
  187/265 5.4 providers had non-empty snippets; expect similar
  coverage for 5.5.
- **PowerShell `git commit -m "" ...` footgun:** empty `-m ""` between
  multiple `-m "..."` flags is treated as a pathspec by some shells.
  Use multiple `-m "..."` flags WITHOUT empty separators; git inserts
  blank lines between them automatically.

**Carry-forwards from the 5.4 session** the new agent should action:

- 🚨 **Phase 6 lane — Phase 5.5 SHIPPED ledger amendment** —
  `outputs/claude_code_dispatch_phase6_amend5.md` to be authored at
  the end of the 5.5 session (mirrors `phase6_amend4` shape).
- **Operator: 86 of 265 HWC providers remain `verified=False`** — no
  NPI match found (mostly DBA-only practices). Kickoff §3 anticipated;
  not gate-blocking. Operator-driven DBA→NPI follow-up surface
  (optional V1.5).
- **Operator: prune `data/events.db.bak-*` files when comfortable** —
  carried over from 5.3 + 5.4 sessions.
- **`parks-rec-scrapes` scheduled CI** — X on cron triggers throughout
  5.3 + 5.4. Likely pre-existing. Possibly Phase 5.5 / 5.6 scope to
  investigate.
- **Google Places API key rotation** — deferred per operator
  ("all keys will be changed at the conclusion of this project").

---

*Authored by Cowork primary, Phase 5 lane, end of Phase 5.4 session
(2026-05-16) post-`a9a680a`. Hand-off artifact only — Cowork primary
for the next session picks up at §0 pre-flight after reading
`outputs/phase5_4_session_closeout.md` first.*
