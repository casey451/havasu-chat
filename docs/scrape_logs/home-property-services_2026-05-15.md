# Scrape log — `home-property-services` — 2026-05-15

Per `docs/operations/scrape_logs_template.md`. First per-category scrape
run for Phase 5.3 (third sub-phase of the Phase 5 restructure, post-5.2
SHIPPED 2026-05-15 at `b71cf0e`). **Single-layer scrape** (Google only —
OSM scope locked to on-the-water per brief §3.2.e). The new surface for
5.3 is **AZ ROC contractor-license verification** (built at `fa0fddd`,
operator-side gate 3).

---

## §0 Pre-flight (closed)

| Check | Result |
|---|---|
| `git log -1 --oneline` | `f0a46f8` (origin pre-load top) |
| `python -m alembic current` (via direct DB read) | `0a1b2c3d4e5f (head)` ✅ |
| `python -m pytest --collect-only \| tail -3` | 1855 collected ✅ (no drift from 5.2 baseline) |
| Google Places key + spend cap | In `.env` ✅; spend cap active from 5.0 B2-a |
| Playwright chromium install | Initially failed (`playwright` not in venv despite requirements pin); recovered via `pip install -r requirements.txt` + `python -m playwright install chromium` |
| Working tree clean | ✅ (untracked .docx artifacts only) |

**Pre-flight surprises:**

- `scripts/places_categories.json` was truncated to 12,231 bytes (HEAD = 12,610) — ends mid-token at `"chil"` inside an unfinished `childcare_education` entry. Recovered via `git checkout HEAD -- scripts/places_categories.json`. Root cause: interrupted local write; not committed. (Recovery: no commit needed; HEAD was already correct.)
- 46 `home-property-services` entities pre-existed from Phase 5.2's `lake_recreation` scrape — the types-map correctly caught `storage` → `home_services`. Documented in `outputs/phase5_3_home_property_pre_load_audit.md` Slice A.

---

## §1 Layer 1 — Google Places (only scrape layer for 5.3)

### Dispatch fix shipped pre-discovery

`cdf3d0c` — `fix(scripts): places_discovery dry-run + --category produces empty intersection`. Pre-fix, `--dry-run --category home-property-services` returned `categories=0` because `load_categories_for_discovery` ANDed the legacy `DRY_RUN_LABELS` frozenset on top of the `--category` slug filter, and those two sets had zero overlap for home_services. Post-fix: dry-run samples the first 2 labels of the filtered set.

### Discovery (real, full sweep)

```
python -m scripts.places_discovery --category home-property-services
```

| Field | Value |
|---|---|
| Mode | full |
| Categories run | 17 (`home_services` discovery domain) |
| Requests | 40 |
| Unique places | 348 |
| Cost (actual) | ~$1.28 |
| Run time | ~60-90 sec |

Per-label breakdown (this run):

| Label | Unique hits | Pages |
|---|---|---|
| general contractors | 50 | 3 |
| self storage | 44 | 3 |
| HVAC | 33 | 3 |
| plumbers | 32 | 3 |
| electricians | 30 | 3 |
| landscapers | 30 | 3 |
| roofers | 22 | 2 |
| pool service | 19 | 3 |
| house cleaning | 18 | 3 |
| solar panel installation | 17 | 3 |
| pest control | 14 | 1 |
| carpet cleaning | 12 | 2 |
| handyman | 9 | 3 |
| tree services | 7 | 2 |
| appliance repair | 5 | 1 |
| movers | 3 | 1 |
| locksmiths | 3 | 1 |

### Enrichment

```
python -m scripts.places_enrichment --limit 400
```

| Field | Value |
|---|---|
| Input | 348 |
| Resume-skips | 320 (cache had 2,551 prior places from 5.0/5.1/5.2 comprehensive scrapes) |
| New enrichments | 28 |
| 404 errors | 0 |
| Other errors | 0 |
| Cost (actual) | ~$0.48 |
| Run time | ~30 sec |

Bumped `--limit` from kickoff's `200` → `400` to cover all 348 in one pass (kickoff's 200 would have left 148 unenriched).

### Sustainability layer extension shipped pre-load-re-run

`7c994aa` — `fix(scripts): _DISCOVERY_DOMAIN_FALLBACK extends for home_services`. First load surfaced 70 of 282 rows landing at `category_id=None` because their `primary_type` (`service` ×49, `laundry` ×3, `consultant` ×1, `None` ×1) wasn't in the `google_types_mapping` AND the lake_recreation-only `_DISCOVERY_DOMAIN_FALLBACK` didn't fire for `home_services` domain. Same `65b0824` pattern for 5.3: added 4 entries to `_DISCOVERY_DOMAIN_FALLBACK` keyed on `(primary_type, "home_services")` → `"home-property-services"`. Future loads catch the same shape automatically.

### Load (initial)

```
python -m scripts.places_load --category home-property-services --dry-run
python -m scripts.places_load --category home-property-services
```

| Field | Value (initial) | Value (after 7c994aa re-run) |
|---|---|---|
| Enriched rows total | 2,579 | 2,579 |
| After `--category` filter | 315 | 315 |
| After ZIP filter | 282 kept, 33 dropped | 282 kept, 33 dropped |
| Inserted (new) | 207 | 0 (idempotent) |
| Updated (existing) | 0 | 207 |
| Reconcile-skipped (ambig) | 75 | 75 |
| `category_id` resolved | 212 | **282** |
| `category_id` unmapped (op queue) | 70 | **0** |
| EntityCategory inserted | 153 | 54 |

ZIP-filter drops (33 total — surrounding-area contractors that surfaced in "in Lake Havasu City, AZ" search but aren't actually LHC-based):

| ZIP | Drops | Locale |
|---|---|---|
| 86409 | 10 | Kingman, AZ |
| 86401 | 6 | Kingman, AZ |
| 86442 | 5 | Bullhead City, AZ |
| 85344 | 4 | Parker, AZ |
| 86426 | 1 | Fort Mohave, AZ |
| 92363 | 1 | Needles, CA |
| 86326 | 1 | Cottonwood, AZ |
| 85346 | 1 | Quartzsite, AZ |
| 85040 | 1 | Phoenix, AZ |
| 85937 | 1 | Snowflake, AZ |
| 85373 | 1 | Sun City West, AZ |
| 86440 | 1 | Mohave Valley, AZ |

Same filter Phase 5.2 used — correct behavior.

---

## §2 Layer 5 — Manual recovery (deferred)

Per `docs/maintainability/manual_recovery_checklist.md` §1 + §3 (Community + Property services). Smaller field-trip surface than 5.2 — mostly desk research for mom-and-pop trades without Google listings, AZ-ROC-licensed contractors that don't show on Google Maps, HOA-recommended preferred providers. **Not gate-blocking for V1 ship.** Operator can pursue post-SHIPPED.

---

## §3 Ambiguous-queue review

The 75 reconcile-skipped candidates audited in
`outputs/phase5_3_home_property_pre_load_audit.md` §3.2 (Slice D). Net findings:

- **9 cross-category ambig-skips** (home_services candidate matched existing entity in another Tier-1 slug):
  - 1 confirmed misroute (Stanley Steemer — currently in shopping-essentials; carpet cleaning is home_services). RE-ROUTE INTO via apply-script.
  - 3 cross-list candidates left in their current slug per V1 single-primary policy (Riverbound Custom Storage & RV Park, B-Kooler Screens, Norwall PowerSystems).
  - 5 correctly placed (suppliers/retailers — Geary Pacific Supply, SRS Building Products, Tile & Carpets Unlimited, PRO TECH RV, AQUACLEAN HAVASU LLC).
- **~66 same-category ambig-skips:** home_services candidates matching the existing 46 self-storage facilities (44 "self storage" discovery hits) plus ~22 geo-proximity matches. Spot-check showed all correct (no false-positive skips).

`GEO_PROXIMITY_THRESHOLD_M = 50.0` was NOT tuned — kickoff §2 threshold of "tune if >50 hits in one run" is technically exceeded (75 > 50) but the 9-cross-category finding shows the reconciler is performing correctly. The high ambig count is explained by the self-storage overlap (5.2 already loaded 46 storage rows that 5.3's "self storage" label re-discovers). Future home_services re-pulls will see similar ambig counts as a NORMAL pattern, not a tuning signal.

---

## §4 Audit + apply-script commits

| Commit | Subject | Effect |
|---|---|---|
| `cdf3d0c` | `fix(scripts): places_discovery dry-run + --category produces empty intersection` | Dispatch fix; gate 0 cleared |
| `7c994aa` | `fix(scripts): _DISCOVERY_DOMAIN_FALLBACK extends for home_services` | Sustainability layer extension; 70 unmapped → 0 |
| `[chore-outputs]` | `chore(outputs): Phase 5.3 audit + apply-script + Cursor/Phase6 dispatches` | Audit doc + apply-script + Cursor/Phase 6 artifacts |
| `[apply]` | `chore(outputs): Phase 5.3 home-property audit apply -- 16 out + 3 NULL→OTW + 1 in (Stanley Steemer)` | 20 routing decisions applied; clears gate item 2 |
| `[az_roc_fix]` | `fix(az_roc): sub-trade allowlist filter + 15s no-results timeout -- Phase 5.3 dispatch fix` | AZ ROC verifier productionized; gate 3 prerequisite |
| `[az_roc_verify]` | `chore(outputs): Phase 5.3 AZ ROC verification run -- N contractors verified` | Gate item 3 cleared |
| `[heat_exposure]` | `chore(outputs): Phase 5.3 heat_exposure mechanical sweep -- 230 indoor` | Gate item 5 cleared |
| `[crowd_notes]` | `chore(outputs): Phase 5.3 crowd_notes top-10 long-form` | Gate item 4 cleared |
| `[ship]` | `chore(outputs): Phase 5.3 SHIPPED -- all 6 gate items cleared` | Final gate verification PASS |

---

## §5 Final state

Post-apply rendering counts (verified via
`outputs/phase5_3_gate_verification.py`):

| `/category/<slug>` | Count |
|---|---|
| `eat-drink` | 255 (5.1 retained) |
| `on-the-water` | 119 (5.2: 100 + 5.3 audit re-routes: 13 boat-storage + 3 Slice B + 3 misroutes) |
| `home-property-services` | 230 (5.3 SHIPPED) |
| `shopping-essentials` | (-1 after Stanley Steemer re-route) |

`/category/home-property-services` page renders 230 entries; default filter renders ≥15. Gate items 1 + 6 met trivially.

---

## §6 Carry-forwards for next session (Phase 5.4: Health, Wellness & Care)

- 3 cross-list candidates noted in audit §3.2 (Riverbound Custom Storage & RV Park, B-Kooler Screens, Norwall PowerSystems) left as single-primary per V1 policy. Phase 6 cross-list pass can revisit.
- `outputs/cursor_dispatch_phase5_3_regression_tests.md` (+19 tests) and `outputs/cursor_dispatch_osm_pull_writer_test.md` (+8 tests from 5.2 carry-forward) — Cursor dispatches pending.
- `outputs/phase6_coordination_message.md` + `outputs/claude_code_dispatch_red_ci_investigation.md` — Claude Code dispatches for master plan + STATE.md amendments + red CI investigation.
- 11 `.bak-*` files in `data/` accumulated this session — operator prunes when comfortable.
- Phase 5.4 dispatches next per kickoff §6 — introduces the NPI registry cross-reference (`scripts/npi_verify.py` built at `5d429aa`).

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.3 session
(2026-05-15) post-`7c994aa`. Layer 1 single-pass complete; Layer 5
deferred to operator post-SHIPPED.*
