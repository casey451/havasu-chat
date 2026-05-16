# Phase 5.4 Kickoff — Health, Wellness & Care (`health-wellness-care`)

> **What this is:** a single paste-and-go operator runbook for Phase 5.4,
> the fourth Tier 1 category. Mirrors `outputs/phase5_3_home_property_services_kickoff.md`
> shape with 5.4-specific overrides. **Single-layer scrape** (Google only —
> OSM scope is locked to on-the-water per brief §3.2.e). The new surface
> for 5.4 is **NPI registry verification** via the CMS NPPES public REST
> API (built at `5d429aa`, no Playwright needed — much lighter than 5.3's
> AZ ROC surface).
>
> **GATE 1 — do not start until Phase 5.3 has closed** its acceptance gate
> (`outputs/phase5_3_gate_verification.py` outputs `ALL 6 ITEMS CLEARED`).
> Per brief §3.2.d, categories run one at a time. ✅ **Met at `805a38c`
> (Phase 5.3 SHIPPED), plus `bff4a79` lint cleanup.**
>
> **GATE 2 — NPI verifier is REST-based**, not browser-based. No
> `playwright install` step needed (5.3's heaviest §0 prerequisite is
> gone). Just verify `rapidfuzz` is installed (it's in `requirements.txt`,
> used for name-matching at threshold 86).
>
> **Authored by:** Cowork primary, Phase 5 lane, end of Phase 5.3 session
> (2026-05-16) post-`bff4a79`. Hand-off to the next session.

---

## §0 Pre-flight (do once, at Phase 5.4 dispatch)

1. **`git log --oneline -15`** — origin should top at the Phase 5.3 SHIPPED
   chain (`bff4a79` or later if Phase 6 lane pushes coordination updates
   between sessions).
2. **`git status`** — clean.
3. **`python -m alembic current`** — confirm local `data/events.db` at
   `0a1b2c3d4e5f`. If behind, `python -m alembic upgrade head`.
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — record
   baseline. Phase 5.3 added 27 regression tests via Cursor dispatches at
   `6ef5ea8` + `30bff52`. **Expected: 1882 collected.** Verify no drift.
5. **`python -c "import rapidfuzz; print(rapidfuzz.__version__)"`** —
   confirm rapidfuzz is installed (NPI verifier dep; should be ≥3.x).
6. **Run the diagnostic** —
   `python outputs/diagnose_category_id_gap.py` to confirm Phase 5.1, 5.2,
   and 5.3 categorization is still intact and to surface what's in the
   `categories` table (Phase 5.4 target slug `health-wellness-care` =
   id=5 per `outputs/diagnose_category_id_gap.py` Q4).
7. **Google Places key + spend cap** — should be ROTATED post-5.3 close
   (the previous key leaked to chat transcript). If not yet done,
   operator rotates first.
8. **CI state** — check GitHub Actions on `bff4a79`. Should be GREEN
   (Claude Code's F401 fix at `98bc9aa` + Cowork's F401 fix at `bff4a79`
   cleared both pre-existing ruff failures). If still red, investigate
   before starting 5.4 (`outputs/claude_code_dispatch_red_ci_investigation.md`
   pattern).

---

## §1 The scrape sequence — Google only

Phase 5.4 is **single-layer** (no OSM; OSM scope is locked to on-the-water
only per brief §3.2.e). Layer 1 Google Places handles the discovery.
**Larger sweep than 5.3** — 28 labels across two discovery domains
(17 `health_medical` + 11 `fitness_sports`).

### Layer 1 — Google Places

```
python -m scripts.places_discovery --category health-wellness-care --dry-run
python -m scripts.places_discovery --category health-wellness-care
python -m scripts.places_enrichment --limit 600
python -m scripts.places_load --category health-wellness-care --dry-run
python -m scripts.places_load --category health-wellness-care
```

**Why `--limit 600` on enrichment?** 28 labels × ~30 per label ≈ 840
raw hits; after the cumulative cache and dedup, expect ~400-600 new
enrichments. The kickoff §1 of 5.3 prescribed 200 and we had to bump it
to 400; for 5.4 start at 600.

**`--category health-wellness-care` is required on `places_load`.** Maps
to discovery domains `{"health_medical", "fitness_sports"}` per
`app/contrib/google_places_scraper.py:DISCOVERY_CATEGORY_TO_DOMAINS`
line 83.

The 28 discovery labels (from `scripts/places_categories.json`):

| Domain | Labels |
|---|---|
| `health_medical` (17) | doctors offices, family medicine, pediatricians, urgent care, dentists, orthodontists, optometrists, chiropractors, physical therapy, dermatologists, veterinarians, mental health counselors, medical clinics, hospitals, audiologists, podiatrists, senior living |
| `fitness_sports` (11) | gyms, personal trainers, yoga studios, pilates studios, crossfit gyms, martial arts, jiu-jitsu, dance studios, swimming pools, tennis courts, pickleball |

**Volume projection (estimate based on 5.3 scaling):**

| Stage | Expected |
|---|---|
| Discovery requests | ~84 (28 × 3 pages) |
| Discovery cost | ~$2.69 |
| Unique places (raw) | ~500-800 |
| After ZIP filter | ~400-600 |
| Inserts (new) | ~300-500 |
| Ambig-skips | ~50-150 |
| Enrichment cost | ~$1.70-3.40 (most cache-hits from prior comprehensive scrapes) |
| **Total Layer 1 cost** | **~$4-7** |

**Sustainability layer extension expected.** `health_medical` + `fitness_sports` will surface catch-all primary_types (`service`, `point_of_interest`, etc.) that aren't yet in `_DISCOVERY_DOMAIN_FALLBACK` (only `lake_recreation` + `home_services` are there as of `7c994aa`). After Layer 1 load surfaces an `operator queue` count, extend `_DISCOVERY_DOMAIN_FALLBACK` per the same pattern (mirror the `7c994aa` commit shape). Likely candidates:

```python
# Anticipated 5.4 fallback entries (extend after Layer 1 surfaces specific gaps)
(None, "health_medical"): "health-wellness-care",
("service", "health_medical"): "health-wellness-care",
("point_of_interest", "health_medical"): "health-wellness-care",
(None, "fitness_sports"): "health-wellness-care",
("service", "fitness_sports"): "health-wellness-care",
```

### Layer 5 — Manual recovery (deferred to operator)

Per `docs/maintainability/manual_recovery_checklist.md`. Smaller field-
trip surface than 5.2 — primarily mom-and-pop practitioners without
Google listings, sole-practitioner offices, and concierge-only providers.
Not gate-blocking for V1 ship.

---

## §2 Ambiguous-queue review — expect moderate-to-high volume

Health & Wellness is the **third non-empty-DB load** (after 5.2 + 5.3).
Reconciler will match against 255 eat-drink + 119 on-the-water + 230
home-property-services rows. Expected ambiguous hits: **20-80 per run**
(higher than 5.3's 75 because of broader cross-category overlaps —
chiropractor's office tagged `point_of_interest` might match a previously-
loaded entity at the same address; pilates studio might overlap with a
fitness retailer in shopping-essentials).

Review via the same `outputs/phase5_3_home_property_pre_load_audit.md`
pattern: post-load audit pulls 9-cross-category + N-same-category, and
the apply-script batches the misroute decisions.

If a single load produces **>100** ambiguous hits, tune
`GEO_PROXIMITY_THRESHOLD_M` (currently `50.0`) per brief §4.g.

---

## §3 NPI registry verification — the NEW 5.4 surface

`scripts/npi_verify.py` (built at `5d429aa`, REST-based via CMS NPPES
public API at `https://npiregistry.cms.hhs.gov/api/`) cross-references
loaded Providers against the NPI registry. **No auth, no Playwright, no
captchas** — much simpler than 5.3's AZ ROC surface.

On match, sets:

- `Provider.verified = True`
- `Provider.verification_method = 'npi_registry'`
- `Provider.attributes['npi_number']` (string; no dedicated column)

Match logic: `rapidfuzz` token-sort similarity ≥ `MATCH_THRESHOLD = 86`
between the Provider's `provider_name` and the NPI entry's basic name
fields (`organization_name`, `first_name` + `last_name` for individual
practitioners).

### Run sequence

```
# After places_load completes:
python -m scripts.npi_verify --dry-run --limit 20
python -m scripts.npi_verify --limit 500
```

**No `--limit 200` cap** like AZ ROC — NPI's REST API is fast (60s
timeout per page request, but most queries return in <1s). Pull all
candidates in one pass.

### What's verifiable vs not

| Sub-trade | Has NPI? | Verify? |
|---|---|---|
| Doctors offices, family medicine, pediatricians, urgent care, dentists, orthodontists, optometrists, chiropractors, physical therapy, dermatologists, podiatrists, audiologists | YES (individual NPIs) | YES |
| Medical clinics, hospitals, senior living | YES (organizational NPIs) | YES |
| Mental health counselors | partial (some LCSWs/LPCs have NPIs, others don't) | YES — skip non-matches |
| Veterinarians | NO (NPI is for human-medicine practitioners; vets use different licensing) | skip — no match expected |
| Gyms, personal trainers, yoga, pilates, crossfit, martial arts, dance studios, swimming, tennis, pickleball | NO (fitness/sports — no NPI) | skip — no match expected |

**Anticipated 5.4 sub-trade filter (defensive, mirroring 5.3 pattern):**

```python
# Add to scripts/npi_verify.py if dry-run shows lots of no-match warnings
NPI_LICENSED_PRIMARY_TYPES: frozenset[str] = frozenset({
    "doctor", "dentist", "chiropractor", "physical_therapist", "optometrist",
    "dermatologist", "pediatrician", "urgent_care", "medical_clinic",
    "hospital", "veterinary_care",  # vet won't match but harmless
    # Generic catch-alls for health domain
    "health", "medical_service",
})
```

But — unlike AZ ROC where each timeout cost 90 seconds, NPI lookups are
sub-second. Even 100 no-match queries cost <2 minutes total. **The
sub-trade filter is optional for 5.4 — only add it if the dry-run
output is too noisy.** Compare with 5.3's `420f893` fix which was
mandatory due to the 90s-per-row blast radius.

### Gotcha — sole proprietors vs DBA names

NPI registers practitioners under their legal name (e.g.,
"Smith, Jane MD"), while Google Places lists DBA names (e.g., "Havasu
Family Practice"). The `rapidfuzz` token-sort handles common variations
but not all. Operator may surface specific DBA → NPI mappings via
follow-up apply-script if match rate < 50%.

---

## §4 Operator-curated field entry — Health & Wellness rubric

Similar in shape to 5.3 (no equivalent of 5.2's `boat_access` field-survey
heavy lift). The operator-curated surface here is:

- **`heat_exposure`** — `indoor` for essentially all medical/dental/fitness
  venues. Exceptions: outdoor pools, tennis courts, pickleball courts →
  `outdoor`. Mechanical sweep with a small handful of operator overrides.
  Mirror `outputs/apply_phase5_3_home_property_heat_exposure.py` exactly,
  populate `OUTDOOR_OVERRIDES` with the 5-10 outdoor venues that surface.
- **`crowd_notes`** — short-form for typical entries; long-form for the
  top-10 by review count (mirrors 5.1/5.2/5.3 pattern). For doctors,
  reviewer signals tend to be: bedside manner, wait times, scheduling
  availability, specific provider names (Dr. X, NP Y). For fitness:
  class quality, instructor names, equipment age, locker room state.
- **`attributes`** JSON — populated automatically by `npi_verify` for
  matched practitioners (`npi_number`). Operator can extend with curated
  values like `accepting_new_patients` (bool), `accepts_medicare` (bool),
  `languages_spoken` (list). Brief §3.4 has the suggested key set.
- **`boat_access`** — NULL (not applicable to inland health venues).

---

## §5 Daily / weekly rhythm (brief §5)

Similar cadence to 5.1/5.2/5.3:

| Day | Work |
|---|---|
| 1 | Google scrape run + scrape log (`docs/scrape_logs/health-wellness-care_<YYYY-MM-DD>.md`) + sustainability layer extension if needed |
| 2 | Ambiguous-queue triage + data-quality audit |
| 3 | NPI verification run + manual review of low-match-rate rows |
| 4-5 | `crowd_notes` for top-10 + `heat_exposure` sweep (with `OUTDOOR_OVERRIDES`) |
| 6 | Optional Layer 5 manual recovery (mom-and-pop practitioners Google missed) |
| 7 | QA spot-check — 10 random entries vs. the §4 rubric |

**Expected Phase 5.4 total: 10-18 hours over 1 week.** Slightly heavier
than 5.3 because of the larger label sweep (28 vs 17) + the audit having
more dual-use cases to navigate.

---

## §6 Acceptance gate — Phase 5.4 closes when ALL of:

- [ ] **80+ entries** in `health-wellness-care` post-load (higher than 5.3's
      60+ because of the broader label sweep)
- [ ] All Google ↔ existing-entity ambiguous reconciler hits reviewed
- [ ] NPI verification run completed for trades that map to NPI-licensed
      categories (doctors, dentists, chiropractors, PT as minimum)
- [ ] Top-10 by review count have long-form `crowd_notes`
- [ ] `heat_exposure` set on every entry (`indoor` for most, `outdoor`
      for the handful of outdoor venues)
- [ ] Phase 6 `/category/health-wellness-care` renders **≥15** per
      default filter

When the gate is met: commit the scrape log, Phase 5.4 gets its SHIPPED
ledger line on `master_build_plan.md` §4 (coordinate with Phase 6 lane —
out of scope for this chat per the kickoff scope-lock), and **Phase 5.5
(Outdoors, Parks & Trails)** dispatches next.

---

## §7 Reference

- `outputs/cursor_brief_phase_5_tier_1_data.md` §3.4 (Health & Wellness
  playbook — if it exists; else this kickoff is authoritative)
- `outputs/phase5_3_session_closeout.md` (the just-shipped 5.3 state
  index — read first; carries the apply-script + audit + sustainability
  layer playbooks 5.4 reuses verbatim)
- `outputs/phase5_3_home_property_services_kickoff.md` (the 5.3 runbook
  this document mirrors)
- `outputs/phase5_3_gate_verification.py` (template for the equivalent
  5.4 gate-verification script)
- `outputs/phase5_3_home_property_pre_load_audit.md` (combined pre+post
  audit template for the equivalent 5.4 audit doc)
- `docs/scrape_logs/home-property-services_2026-05-15.md` (template for
  the equivalent 5.4 scrape log)
- `scripts/npi_verify.py` + `app/contrib/npi_client.py` (the new
  5.4 surface, built at `5d429aa`)
- `app/contrib/google_types_mapping.py` (health_medical + fitness_sports
  types — extend if new types surface)
- `scripts/places_load.py` (`_resolve_category_id` sustainability layer at
  `65b0824` + 5.3 extension at `7c994aa`; extend `_DISCOVERY_DOMAIN_FALLBACK`
  for `health_medical` and `fitness_sports` catch-alls — likely needed)
- `outputs/diagnose_category_id_gap.py` (re-usable diagnostic — Q4
  surfaces `health-wellness-care` = id=5)
- `outputs/apply_phase5_3_home_property_audit.py` (5.3 audit apply-script
  — template for 5.4 equivalent)
- `outputs/apply_phase5_3_home_property_heat_exposure.py` (5.3 heat sweep
  — template; for 5.4 add `OUTDOOR_OVERRIDES` for outdoor pools/courts)
- `outputs/apply_phase5_3_home_property_crowd_notes.py` (5.3 crowd_notes
  — template; note the JSON-column gotcha at `f35d5e4`: pass the dict
  directly, do NOT json.dumps first)

---

## §8 Hand-off context from the Phase 5.3 session

**Important context that's NOT in this kickoff but the new agent should
read in the 5.3 close-out:**

- 12-commit chain from `f0a46f8` (kickoff) → `bff4a79` (final lint
  cleanup) with 3 surgical fixes shipped mid-session (`cdf3d0c`,
  `7c994aa`, `f35d5e4`)
- The red CI mystery — diagnosed by Claude Code at `98bc9aa` (F401
  unused `EntityCategory` import silenced by E402-only `# noqa`), plus
  follow-up Cowork fix at `bff4a79` (F401 unused `json` + `Category` in
  crowd_notes apply-script)
- The crowd_notes JSON-column double-encoding gotcha (`f35d5e4`) —
  Entity.crowd_notes is JSON-typed; pass the dict directly, NOT
  `json.dumps(dict)`
- The AZ ROC verifier productionization pattern (`420f893`) — when
  building a new verifier, add sub-trade allowlist filter + short
  no-results timeout from the start. NPI doesn't need this (REST-based,
  sub-second responses) but the pattern is good to know.
- Parallel agent dispatches — Cursor (+27 tests at `6ef5ea8` + `30bff52`)
  + Claude Code (Phase 6 ledger amendments at `b7bf91d` + red CI fix at
  `98bc9aa`) — all landed cleanly in topological order.

**Carry-forwards from the 5.3 session** the new agent should action:

- 🚨 **Operator: rotate Google Places API key** — leaked in chat
  transcript mid-5.3 session.
- **Operator: manual fix Craig Plumbing AZ ROC mismatch** — verifier
  matched against "A-14 Asphalt Paving" (name collision). Not gate-
  blocking; quick `attributes.az_roc` correction.
- **Operator: prune 11 `data/events.db.bak-*` files** when comfortable.
- **Phase 6 lane: amend ledger for Phase 5.3 SHIPPED at `805a38c`** —
  Amendment 3 of `outputs/phase6_coordination_message.md` was deferred
  per brief; needs dispatch after 5.4 starts.

---

*Authored by Cowork primary, Phase 5 lane, end of Phase 5.3 session
(2026-05-16) post-`bff4a79`. Hand-off artifact only — Cowork primary
for the next session picks up at §0 pre-flight after reading
`outputs/phase5_3_session_closeout.md` first.*
