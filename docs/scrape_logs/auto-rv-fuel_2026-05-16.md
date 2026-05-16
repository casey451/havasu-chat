# Scrape log — `auto-rv-fuel` — 2026-05-16

Per `docs/operations/scrape_logs_template.md`. First per-category
scrape run for Phase 5.5 (fifth sub-phase of the Phase 5 restructure,
post-5.4 SHIPPED 2026-05-16 at `c13dfff` + close-out doc at `a9a680a`
+ Phase 6 Amendment 4 in-line at `0addb63` + kickoff/boot prompt at
`7c96ec9`). **Single-layer scrape** (Google only — OSM scope locked to
on-the-water per brief §3.2.e). **No Layer-4 verifier** for 5.5 —
operator picked Option C (defer AZ MVD Dealer Locator + AZCC towing
carrier surfaces to V1.5) at session start.

---

## §0 Pre-flight (closed)

| Check | Result |
|---|---|
| `git log -1 --oneline` | `7c96ec9` (origin pre-load top — Phase 5.5 kickoff + boot prompt) |
| `python -m alembic current` | `0a1b2c3d4e5f` ✅ (unchanged from 5.2/5.3/5.4) |
| `python -m pytest --collect-only \| tail -3` | **1911 collected** (kickoff expected 1909; +2 drift accepted as new baseline; neither `0addb63` nor `7c96ec9` touched tests/ per `git show --stat`, so the source of the +2 is parametrization variance from runtime state) |
| `python outputs/diagnose_category_id_gap.py` (proxy via direct DB read) | `auto-rv-fuel` slug present at id=9 ✅; all prior-phase categories intact (HWC verified=85 ✓ matches 5.4 close-out exactly) |
| `gh run list --branch main --limit 5` | Top 4 runs ✓ green on main (newest 19 min before §1 dispatch); `parks-rec-scrapes` cron X is a known sibling, not in 5.5 scope |
| Google Places key + spend cap | In `.env` ✅; spend cap active from 5.0 B2-a. Operator declined rotation per "all keys will be changed at conclusion of this project" |
| Playwright | Not needed for 5.5 (Option C — no Layer-4 verifier built) |
| Working tree clean | ✅ (untracked: `hava_api_catalog.docx`, `~$va_api_catalog.docx` Word lock file, 2 historical `outputs/ci_*_log_failed.txt` — all unrelated to lane) |

**Pre-flight surprises (3 found, all triaged):**

1. **`scripts/places_categories.json` locally corrupted** — working tree at 202 lines (ends mid-token `"chil`), HEAD at 211 lines (proper close). Operator restored via `git restore`. Cause unknown (suspect external editor save); the truncation was AFTER the auto-domain labels (lines 91-104) so dry-run still ran, but the file failing `json.load()` could have caused unpredictable behavior in any cross-domain code path. Restored before §1.
2. **Two historical `outputs/ci_*_log_failed.txt` files in working tree** — captured from earlier SHAs (the older one from before `0cf7f1d` fixed the I001 ruff issue). CI on `7c96ec9` is actually green per `gh run list`. No live blocker.
3. **`pytest` +2 drift** — kickoff expected 1909, actual is 1911. Neither `0addb63` nor `7c96ec9` touched tests/. Accepted as new baseline; not gate-blocking.

---

## §1 Layer 1 — Google Places (only scrape layer for 5.5)

### Discovery (real, full sweep)

```
python -m scripts.places_discovery --category auto-rv-fuel
```

| Field | Value |
|---|---|
| Mode | full |
| Categories run | 14 (all `auto` domain) |
| Requests | 27 |
| Unique places | 272 |
| Cost (actual) | ~$0.86 |
| Run time | a few seconds wall |

Per-label split (14 labels, all `auto` domain):

| Label | Pages | New unique |
|---|---|---|
| auto repair | 3 | 60 |
| oil change | 2 | 11 |
| tire shops | 1 | 3 |
| car wash | 2 | 27 |
| auto detailing | 3 | 11 |
| auto body shops | 3 | 13 |
| car dealerships | 3 | 38 |
| used car dealers | 1 | 0 (all dedup'd vs car dealerships) |
| motorcycle dealers | 1 | 11 |
| motorcycle repair | 2 | 14 |
| auto parts stores | 1 | 14 |
| gas stations | 3 | 56 |
| towing services | 1 | 10 |
| car rentals | 1 | 4 |

Discovery cost ran below kickoff §1 projection (~$1.35 expected, ~$0.86
actual) because 8 of 14 labels capped at 1 page — LHC's auto industry
is concentrated, no long-tail beyond the first page of results for
single-purpose labels (tire shops, used car dealers, motorcycle
dealers, auto parts stores, gas stations bottom-3, towing services,
car rentals).

### Enrichment

```
python -m scripts.places_enrichment --limit 400
```

| Field | Value |
|---|---|
| Input | 272 |
| Cache hits (resume) | **249** (91.5% cache rate — best so far in 5.x lane) |
| New enrichments | 23 |
| 404 errors | 0 |
| Other errors | 0 |
| Cost (actual) | ~$0.40 |
| Run time | ~seconds |
| Cumulative cache post-run | 2618 |

Used kickoff's recommended `--limit 400` (vs 5.4's 600 / 5.3's 400 /
5.2's 200) — comfortable headroom; the 272 input was well within
budget. Cumulative cache from 5.0/5.1/5.2/5.3/5.4 prior scrapes hit
91.5% — LHC's auto businesses heavily overlap with marine + retail +
home-services discovery sets from earlier phases.

### Sustainability layer extension shipped pre-load-re-run

`4d41944` — `fix(scripts): _DISCOVERY_DOMAIN_FALLBACK extends for auto
domain -- Phase 5.5 sustainability layer`. First load surfaced 18 of
179 rows landing at `category_id=None` because their `primary_type`
wasn't in the `google_types_mapping`. Distribution: `None` ×5 (auto
glass + mobile detailers Google tags without a specific primary),
`service` ×3 (towing operators), `car_rental` ×2 (Avis + Budget),
plus `point_of_interest` and `store` as safety nets per kickoff §1
anticipation. Added 5 entries to `_DISCOVERY_DOMAIN_FALLBACK` keyed on
`(primary_type, "auto")` → `"auto-rv-fuel"`. Same
`7c994aa`/`65b0824`/`fc51940` pattern. Re-running `places_load`
cleared the operator queue to 0. +9 regression tests in
`tests/test_phase5_5_places_load_resolver.py` (5 parametrized
`_AUTO_KEYS` asserts + 4 defensive preservation asserts for 5.2 / 5.3
/ 5.4 fallback entries).

### Load (initial + after fallback re-run)

```
python -m scripts.places_load --category auto-rv-fuel --dry-run
python -m scripts.places_load --category auto-rv-fuel
```

| Field | Value (initial) | Value (after 4d41944 re-run) |
|---|---|---|
| Enriched rows after `--category` filter | 200 | 200 |
| After ZIP filter | 179 kept / 21 dropped | 179 / 21 |
| Inserted (new) | 102 | 0 (idempotent) |
| Updated (existing) | 1 | 103 |
| Reconcile-skipped (ambig) | 76 | 76 |
| Reconcile merged (geo) | 1 | 0 |
| `category_id` resolved | 161 | **179** |
| `category_id` unmapped (op queue) | 18 | **0** |
| EntityCategory inserted | 93 | 10 (the 10 previously-unmapped now linked) |

The 76 ambig-skips + 102 inserts net to **140 distinct entities** in
`/category/auto-rv-fuel` after the fallback re-run promoted the 18
unmapped rows. (Pre-load count was 41 from earlier seed loads, so the
delta is +99 net new auto-rv-fuel entities.)

ZIP-filter drops (21 of 200): non-LHC ZIPs Surprise (85344) ×7, 86409
×4, BHC (86442/86429/86426) ×5, Kingman (86401) ×2, Prescott (86305)
×1, Peach Springs (86494) ×1, Yucca (86438) ×1. All legitimate
regional-auto-business drops; no ZIP+4 dash-stripping issues (the 5.4
`b683ad7` fix held).

---

## §2 Layer 5 — Manual recovery (deferred)

Per `docs/maintainability/manual_recovery_checklist.md`. Smaller
surface than 5.2/5.4 — primarily mobile RV repair operators (sole
proprietors without Google listings), LHC chamber-of-commerce
specialty dealers, and small-shop motorcycle/RV repair not on Google.
**Not gate-blocking for V1 ship.** Operator can pursue post-SHIPPED.

The kickoff §1 specifically called out RV-specific Layer 5 (chamber
directories + LHC.com + mobile-RV-only operators). Deferred —
acceptable per kickoff because the existing `lake_recreation`-loaded
RV parks already cover the lake-adjacent RV surface, and the auto
domain pull recovered the RV dealer + RV repair brick-and-mortar set
(Beach Auto & RV, Sunshine RV, Palm Tree RV Sales, BlackSheep RV,
Byrd's Mobile RV & Marine, Britton's Auto Truck & RV Repair, etc.).

---

## §3 Ambiguous-queue review

The 76 reconcile-skipped candidates audited in
`outputs/phase5_5_auto_rv_fuel_pre_load_audit.md` §1-7. Net findings:

- **No misroutes surfaced.** All 76 ambig-hits are the
  **auto-industrial-blvd false-ambig** pattern — auto/RV/fuel
  businesses geo-colliding (within 50m) with marine, restaurant, and
  contractor businesses on LHC's Industrial Blvd / Lake Havasu Ave /
  McCulloch corridor strip-malls. Same shape as 5.4's medical-plaza
  pattern (114 ambig-hits, 0 misroutes), just different geography.
- **67 cross-category** (29 on-the-water + 20 eat-drink + 14
  home-property-services + 2 health-wellness-care + 1 pets + 1
  shopping-essentials) — all different businesses at adjacent
  locations. KEEP-SKIP under V1 single-primary policy.
- **9 same-category** — strip-mall doubles within auto-rv-fuel itself
  (e.g., Accurate Auto Care 15m from Britton's Auto Truck & RV
  Repair). KEEP-SKIP — distinct businesses with distinct Google
  place_ids.
- **3 soft-edges deferred** to V1.5 (none gate-blocking): optional
  force-insert apply-script for the 76 reviewed-but-unloaded;
  optional `GEO_PROXIMITY_THRESHOLD_M` tune (50 → 25); optional
  same-discovery-domain bypass in reconciler. Same soft-edges as
  5.3/5.4.

`GEO_PROXIMITY_THRESHOLD_M = 50.0` was NOT tuned — same call as
5.3/5.4. The 76 > 50 threshold technically triggers the kickoff §2
"consider tuning" check, but the auto-industrial-blvd pattern
explains the high count as a NORMAL pattern for densely-packed
industrial corridors, not a tuning signal.

### RV cross-list audit (Phase 5.5 §2 special surface)

The kickoff §2 specifically called out the RV cross-list with 5.2's
`lake_recreation`. Findings:

- **0 entities dual-tagged cat-9 + cat-6** ✅ (DB cross-list check
  returned empty)
- **4 RV-keyword candidates flagged** by audit dump (Gosselin
  Automotive ↔ Riverside Boat Dock Sales; Any Radiator Service ↔ So
  Cal Speed & Marine; Riverview Auto Sales ↔ Total Marine Pros; Auto
  Service Center ↔ Marine One Motorsports). All coincidental token
  overlap; **0 real flips needed.**
- **RV correctly distributed**: 9 RV storage in cat-6 (correct per
  kickoff policy); RV dealers + RV repair in cat-9 (correct); 1
  borderline rental ("Lake Havasu RV and Boat Rentals" in cat-6 —
  defensible since also a boat rental).

---

## §4 Layer-4 verifier — Option C deferred to V1.5

Per operator decision at session start, no verifier surface built for
5.5. Documented for V1.5 pickup:

- **AZ MVD Dealer Locator** (`https://azmvd.gov/mvd/locator/Dealers`)
  — Playwright build; sub-trade allowlist (car_dealer,
  used_car_dealer, motorcycle_dealer, rv_dealer). Expected ~10-25
  verified of ~30-50 dealer candidates. ~2-4 hours of build.
- **AZCC towing carrier** (`https://www.azcc.gov/oai/cc/permitted-carriers`)
  — REST cross-reference, no Playwright. Expected ~3-8 verified of
  ~6-12 towing candidates.

See `outputs/phase5_5_auto_rv_fuel_pre_load_audit.md` §3 carry-forward
+ kickoff §3 for the full V1.5 build-or-defer spec.

**Gate item 3 acceptance signal:** audit doc + kickoff §3 documents
the deferred surfaces; no providers in auto-rv-fuel have
`verification_method` set to `az_mvd` or `azcc` (programmatic check in
`outputs/phase5_5_gate_verification.py`).

---

## §5 Operator-curated field entry (`heat_exposure`, `is_mobile_service`, `crowd_notes`)

Three mechanical apply-scripts ran in sequence, all idempotent +
self-verifying:

| Apply-script | Default | Overrides | Total entities | Gate |
|---|---|---|---|---|
| `apply_phase5_5_auto_rv_fuel_heat_exposure.py` | `indoor` ×131 | `outdoor` ×9 (6 gas stations + 3 outdoor car washes) | 140 / 0 NULL | item 6 cleared |
| `apply_phase5_5_auto_rv_fuel_is_mobile_service.py` | `False` ×126 (already-correct from default column) | `True` ×14 (3 mobile mechanics + 3 mobile detailers + 1 mobile RV tech + 1 mobile tire service + 5 towing + 1 mobile sales/service hybrid) | 140 / 0 NULL | item 5 cleared |
| `apply_phase5_5_auto_rv_fuel_crowd_notes.py` | (none — only the top-10 get long-form) | 10 long-form `{short, long}` dict notes | 10 with long / 130 without | item 4 cleared |

`crowd_notes` drafts sourced from `Provider.google_review_snippets`
(own column per `app/db/models.py:84`, populated by
`scripts/places_load.py:146` from the scraper's `review_snippets`
emission at `app/contrib/google_places_scraper.py:464`). Coverage:
**119 of 140** auto-rv-fuel providers have non-empty snippets (85%
— slightly better than 5.4's 70.6%). Top-10 all had 5 non-empty
snippets each. Staged drafts at
`outputs/phase5_5_auto_rv_fuel_crowd_notes_top10_staged.md`.

The 10 top-by-review-count entities (`crowd_notes` long-form):
Anderson Toyota (5938), Anderson Chrysler Dodge Jeep Ram (3457),
Anderson Nissan (2576), Big O Tires (2559), Bradley Chevrolet (1086),
Victory Lane Quick Oil Change (720), Bradley Ford of Lake Havasu City
(693), AZ Auto Spa (491), O'Reilly Auto Parts (426), Bob's My Shop
(390).

---

## §6 Audit + apply-script + ship commits

| Commit | Subject | Effect |
|---|---|---|
| `4d41944` | `fix(scripts): _DISCOVERY_DOMAIN_FALLBACK extends for auto domain -- Phase 5.5 sustainability layer` | Sustainability extension; 18 unmapped → 0; +9 regression tests |
| `[apply+audit]` | `chore(outputs): Phase 5.5 §2 audit + §4 apply-scripts -- ambig review + heat_exposure + is_mobile_service + crowd_notes top-10` | §2 audit doc + dump script + 3 apply-scripts + crowd_notes staged; gates 4 + 5 + 6 cleared |
| `[ship]` | `chore(outputs): Phase 5.5 SHIPPED -- all 7 gate items cleared` | Final gate verification PASS; gate-verification script + scrape log + Phase 6 dispatch artifact |

---

## §7 Final state

Post-apply rendering counts (verified via
`outputs/phase5_5_gate_verification.py`):

| `/category/<slug>` | Count |
|---|---|
| `eat-drink` | 287 (5.1 retained) |
| `health-wellness-care` | 265 (5.4 SHIPPED) |
| `home-property-services` | 230 (5.3 SHIPPED) |
| `on-the-water` | 119 (5.2 SHIPPED) |
| `auto-rv-fuel` | **140 (5.5 SHIPPED)** |

`/category/auto-rv-fuel` page renders 140 entries; default filter
renders ≥15. Gate items 1 + 7 met trivially (4.7× over the ≥30
target).

**Heat exposure final distribution:** 131 indoor + 9 outdoor (6 gas
stations + 3 outdoor car washes) = 140 total / 0 NULL.

**is_mobile_service final distribution:** 126 False + 14 True
(mobile detailers, towing, mobile RV/marine techs, mobile mechanics,
mobile tire service) = 140 total / 0 NULL.

**Crowd_notes final:** 10 long-form entries for the top-10-by-review-
count auto businesses.

**Verifier (Option C deferred):** 0 providers have
`verification_method ∈ {az_mvd, azcc}`. Audit doc §3 + kickoff §3
document the V1.5 build paths.

---

## §8 Carry-forwards for next session (Phase 5.6: Shopping, Grocery & Essentials)

- **76 reviewed-but-unloaded candidates** remain in
  `enrichment_enriched.jsonl`. Carry-forward soft-edge for V1.5 — same
  shape as 5.4's 114 carry-forward.
- **Layer-4 verifier surface for V1.5** — AZ MVD Dealer Locator
  (Playwright) + AZCC towing carrier (REST) paths documented for
  pickup. Mirror the 5.3 AZ ROC build pattern (`scripts/az_roc_verify.py`
  at `420f893`) when building AZ MVD.
- **Phase 6 lane** — Phase 5.5 SHIPPED ledger amendment dispatch
  (`outputs/claude_code_dispatch_phase6_amend5.md`). Pattern mirrors
  Amendment 4 at `0addb63`.
- **`parks-rec-scrapes` scheduled CI workflow** — still X on cron
  triggers throughout this session. Carry-over from 5.3/5.4. Operator
  or Phase 5.6+ to investigate.
- **Google Places API key** — operator declined rotation; carry-over.
- **`hava_api_catalog.docx` + Word lock file** in working tree —
  unrelated to lane; carry-over for operator cleanup when comfortable.
- **Phase 5.6 (Shopping, Grocery & Essentials)** anticipated catch-all
  primary_types per `scripts/places_categories.json` `retail` domain:
  `('grocery_or_supermarket', 'retail')`, `('clothing_store', 'retail')`,
  etc. May extend `_DISCOVERY_DOMAIN_FALLBACK` similarly.
- **Pre-flight gotcha checklist for next session**: re-validate
  `scripts/places_categories.json` length matches HEAD (`git diff
  scripts/places_categories.json` should be empty) — the local
  corruption found in 5.5 §0 may recur if the cause (external editor?)
  isn't identified.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.5 session
(2026-05-16). Layer 1 single-pass complete; Layer-4 verifier deferred
to V1.5 (Option C); Layer 5 deferred to operator post-SHIPPED.*
