# Phase 5.3 Kickoff — Home & Property Services (`home-property-services`)

> **What this is:** a single paste-and-go operator runbook for Phase 5.3,
> the third Tier 1 category. Mirrors `outputs/phase5_2_on_the_water_kickoff.md`
> shape with category-specific overrides. **Single-layer scrape** (Google
> only — OSM scope is locked to on-the-water per brief §3.2.e). The new
> surface for 5.3 is **AZ ROC contractor-license verification** (gate item
> shipped 5.1's task #6 at `fa0fddd`, Option A Playwright).
>
> **GATE 1 — do not start until Phase 5.2 has closed** its acceptance gate
> (`outputs/phase5_2_gate_verification.py` outputs `ALL 6 ITEMS CLEARED`).
> Per brief §3.2.d, categories run one at a time. ✅ **Met at `b71cf0e`.**
>
> **GATE 2 — `playwright install chromium` must run on the operator's
> machine before any live `az_roc_verify.py` run.** Built at `fa0fddd` but
> chromium binary install was deferred to 5.3 dispatch (one-shot, ~150MB).
>
> **Authored by:** Cowork primary, Phase 5 lane, end of Phase 5.2 session
> (2026-05-15) post-`b71cf0e`. Hand-off to the next session.

---

## §0 Pre-flight (do once, at Phase 5.3 dispatch)

1. **`git log --oneline -12`** — origin should top at the Phase 5.2 SHIPPED
   chain (`b71cf0e` or later if Phase 6 lane pushed coordination updates).
2. **`git status`** — clean.
3. **`python -m alembic current`** — confirm local `data/events.db` at
   `0a1b2c3d4e5f`. If behind, `python -m alembic upgrade head`.
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — record
   baseline (1855 at start of Phase 5.2; verify no drift).
5. **`playwright install chromium`** — installs the Chromium binary
   Playwright needs for `scripts/az_roc_verify.py`. One-shot,
   ~150MB. Skip if already installed (`playwright --version` should also
   work; if it fails, `pip install -r requirements.txt` first).
6. **Run the diagnostic** —
   `python outputs/diagnose_category_id_gap.py` to confirm Phase 5.1 +
   5.2 categorization is still intact and to surface what's in the
   `categories` table (Phase 5.3 target slug `home-property-services` =
   id=4 per `outputs/diagnose_category_id_gap.py` Q4 from this session).
7. **Google Places key + spend cap** — still active from Phase 5.0 B2-a.

---

## §1 The scrape sequence — Google only

Phase 5.3 is **single-layer** (no OSM; OSM scope is locked to on-the-water
only per brief §3.2.e). Layer 1 Google Places handles the discovery.

### Layer 1 — Google Places

```
python -m scripts.places_discovery --category home-property-services --dry-run
python -m scripts.places_discovery --category home-property-services
python -m scripts.places_enrichment --limit 200
python -m scripts.places_load --category home-property-services --dry-run
python -m scripts.places_load --category home-property-services
```

**`--category home-property-services` is required on `places_load`.** Maps
to discovery domain `home_services` per
`app/contrib/google_places_scraper.py:DISCOVERY_CATEGORY_TO_DOMAINS` line
81. `enrichment_enriched.jsonl` already carries ~? enriched
`home_services` rows from prior comprehensive scrapes (verify count at
load dry-run time).

**Sustainability layer (`65b0824`) already wired.** `_resolve_category_id`
in `scripts/places_load.py` will auto-categorize via google_types_mapping
(plumber, electrician, hvac_contractor, general_contractor,
roofing_contractor, painter, locksmith, moving_company, storage,
lawn_care_service, home_inspection, pest_control_service,
cleaning_service, appliance_repair — 14 types). Catch-all primary_types
(`service`, `<none>`, etc.) for the `home_services` discovery domain may
still need fallback entries in `_DISCOVERY_DOMAIN_FALLBACK` — see §4 of
the Phase 5.2 close-out for the extension pattern. Decide after the load
dry-run distribution surfaces which catch-alls land in operator queue.

### Layer 5 — Manual recovery (deferred to operator)

Per `docs/maintainability/manual_recovery_checklist.md` §1 + §3
(Community + Property services). Smaller field-trip surface than 5.2 —
mostly desk research finding:

- Mom-and-pop trades without Google listings
- AZ ROC-licensed contractors that don't show on Google Maps
- HOA-recommended preferred providers

Not gate-blocking for V1 ship.

---

## §2 Ambiguous-queue review — expect moderate volume

Home & Property is the **second non-empty-DB load** (after 5.2's first
non-empty-DB load that surfaced the reconciler counts via `d34d4c3`).
Reconciler will match against 100+ on-the-water rows from 5.2 + 255
eat-drink rows from 5.1. Expected ambiguous hits: **2-10 per run**
(brief §3.3 estimate). Review via direct DB query (locked, brief §3.2.f):

```sql
SELECT id, name, source, created_at
FROM entities
WHERE source LIKE 'google_places%'
ORDER BY created_at DESC
LIMIT 50;
```

If a single load produces **>50** ambiguous hits, tune
`GEO_PROXIMITY_THRESHOLD_M` (currently `50.0`) per brief §4.g.

---

## §3 AZ ROC contractor-license verification — the NEW 5.3 surface

`scripts/az_roc_verify.py` (built at `fa0fddd`, Option A Playwright)
cross-references loaded Providers against the AZ ROC contractor database.
On match, sets:

- `Provider.verified = True`
- `Provider.verification_method = 'az_roc'`
- `Provider.attributes` JSON updated with license_number, license_class,
  license_expires, license_status

### Run sequence

```
# After places_load completes:
python -m scripts.az_roc_verify --dry-run --limit 20
python -m scripts.az_roc_verify --limit 200
```

### What's verifiable vs not

| Sub-trade | Has AZ ROC license? | Verify? |
|---|---|---|
| Plumber, electrician, HVAC, general contractor, roofing | YES — all licensed | YES |
| Painter, locksmith, lawn care, cleaning, pest control | mostly NO (handyman class) | skip / handyman-class check |
| Moving, storage | NO (different licensing) | skip |
| Appliance repair, home inspection | varies | per-row decision |

Operator may want to extend the apply-script after verification to mark
unmatched-but-expected-licensed rows for follow-up (e.g., contractor
operating without active license — surface as `pending_review=True`).

### Gotcha #16 (PowerShell `-m` quoting)

If you hit the `python -m scripts.az_roc_verify` issue from Phase 5.1's
handoff §4 drift #3, the workaround is documented in
`outputs/phase5_1_field_entry_handoff.md` §4 (use explicit module name
without space, or `python scripts/az_roc_verify.py` direct).

---

## §4 Operator-curated field entry — Home & Property rubric

Less heavy than 5.2's `boat_access` since there's no equivalent
field-survey-dominant column. The operator-curated surface here is:

- **`heat_exposure`** — `indoor` for essentially everything in this
  category (their work is at customer homes; the BUSINESS venue is
  typically an office or service yard, indoor). Mechanical sweep: default
  `indoor`, exceptions for outdoor service yards if any surface (rare).
- **`crowd_notes`** — short-form `{short}` for typical entries; long-form
  `{short, long}` for the top-10 by review count (mirrors 5.1 pattern).
  Focus on signals like "owner-operated", "24-hour emergency", "Spanish-
  speaking", "free estimate" — useful for the directory user picking a
  trade.
- **`attributes`** JSON — populated automatically by `az_roc_verify` for
  ROC-licensed trades. Operator can extend with curated values like
  `service_area` ("Lake Havasu City + Parker"), `emergency_service`
  (bool), `years_in_business`. Brief §3.3 has the suggested key set.
- **`boat_access`** — NULL (not applicable to inland service venues).

---

## §5 Daily / weekly rhythm (brief §5)

Similar cadence to 5.1/5.2:

| Day | Work |
|---|---|
| 1 | Google scrape run + scrape log (`docs/scrape_logs/home-property-services_<YYYY-MM-DD>.md`) |
| 2 | Ambiguous-queue triage + data-quality audit |
| 3 | AZ ROC verification run + manual review of unmatched-licensed rows |
| 4-5 | `crowd_notes` for top-10 + heat_exposure sweep |
| 6 | Optional Layer 5 manual recovery (mom-and-pops Google missed) |
| 7 | QA spot-check — 10 random entries vs. the §4 rubric |

**Expected Phase 5.3 total: 8-15 hours over 1 week.** Lighter than 5.2
because no boat_access field-survey work.

---

## §6 Acceptance gate — Phase 5.3 closes when ALL of:

- [ ] **60+ entries** in `home-property-services` post-load (brief §3.3
      estimate)
- [ ] All Google ↔ existing-entity ambiguous reconciler hits reviewed
- [ ] AZ ROC verification run completed for trades that map to a ROC
      class (plumbers, electricians, HVAC, GC, roofing as minimum)
- [ ] Top-10 by review count have long-form `crowd_notes`
- [ ] `heat_exposure` set on every entry (`indoor` for most)
- [ ] Phase 6 `/category/home-property-services` renders **≥15** per
      default filter

When the gate is met: commit the scrape log, Phase 5.3 gets its SHIPPED
ledger line on `master_build_plan.md` §4 (coordinate with Phase 6 lane —
out of scope for this chat per the kickoff scope-lock), and **Phase 5.4
(Health, Wellness & Care)** dispatches next — that one introduces the
NPI registry cross-reference (`scripts/npi_verify.py` built at `5d429aa`).

---

## §7 Reference

- `outputs/cursor_brief_phase_5_tier_1_data.md` §3.3 (Home & Property
  playbook)
- `outputs/phase5_2_session_closeout.md` (the just-shipped 5.2 state
  index — read first; carries the apply-script + audit + sustainability
  layer playbooks 5.3 reuses verbatim)
- `outputs/phase5_2_on_the_water_kickoff.md` (the 5.2 runbook shape this
  document mirrors)
- `outputs/phase5_2_gate_verification.py` (template for the equivalent
  5.3 gate-verification script)
- `docs/scrape_logs/on-the-water_2026-05-15.md` (template for the
  equivalent 5.3 scrape log)
- `docs/operations/boat_access_rubric.md` (NOT applicable to 5.3 —
  reference only)
- `scripts/az_roc_verify.py` + `app/contrib/az_roc_client.py` (the new
  5.3 surface, built at `fa0fddd`)
- `app/contrib/google_types_mapping.py` (14 home_services types already
  mapped; extend if new types surface)
- `scripts/places_load.py` (`_resolve_category_id` sustainability layer at
  `65b0824` will auto-categorize; extend `_DISCOVERY_DOMAIN_FALLBACK`
  for home_services catch-alls if needed)
- `outputs/diagnose_category_id_gap.py` (re-usable diagnostic — Q4
  surfaces `home-property-services` = id=4)
- `outputs/apply_provider_category_id_backfill.py` (`home_services` →
  `home-property-services` already in `LEGACY_TO_SLUG`; no new
  backfill needed since 5.3 is a fresh load)
- `outputs/apply_on_the_water_*.py` (the 5.2 apply-script suite —
  template the 5.3 equivalents will mirror verbatim per the
  established Cowork pattern)

---

## §8 Hand-off context from the Phase 5.2 session

**Important context that's NOT in this kickoff but the new agent should
read in the 5.2 close-out:**

- The retroactive Phase 5.1 fix surfaced + shipped at `efd193a` (5.1's
  gate item 5 was retroactively false at HEAD; now true)
- The sustainability layer at `65b0824` (new `_resolve_category_id`)
- The `apply_provider_category_id_backfill.py` template for if 5.3
  surfaces an analogous gap (it shouldn't — places_load fix landed first
  for 5.3)
- The data-quality audit pattern (`apply_phase5_2_on_the_water_audit.py`)
  that re-routed 29 boat businesses
- The 11-commit chain that built the V1 directory pivot for on-the-water

**Carry-forwards from the 5.2 session** the new agent may want to wrap up
in parallel with 5.3:

- Cursor dispatch artifact for OSM tests at
  `outputs/cursor_dispatch_osm_pull_writer_test.md` (uncommitted Cursor
  work — operator dispatches when convenient)
- 8 `data/events.db.bak-*` files in the working tree (operator prunes
  when comfortable that 5.1 + 5.2 fixes are stable in production)
- Trip A + Trip B per `outputs/phase5_2_lakefront_field_trip_plan.md`
  (operator field-trip; upgrades 3 `{}` placeholder marinas to fully
  populated; not gate-blocking for 5.3)
- Coordination with Phase 6 lane for `master_build_plan.md` + `STATE.md`
  Phase 5.1 retro + Phase 5.2 SHIPPED amendments

---

*Authored by Cowork primary, Phase 5 lane, end of Phase 5.2 session
(2026-05-15) post-`b71cf0e`. Hand-off artifact only — Cowork primary
for the next session picks up at §0 pre-flight after reading
`outputs/phase5_2_session_closeout.md` first.*
