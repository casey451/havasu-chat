# Cursor Dispatch Prompt — Phase 5 Lead-Up Tooling (Lane B verifications + 3 tooling-touchup scripts)

> **Operator note:** paste the fenced block below into a fresh Cursor chat. This dispatch covers the Phase 5 lead-up work that needs **live web access** — which the Cowork chat structurally cannot do (WebFetch is provenance-locked there; bash curl is forbidden). Cursor has live web access, so it can execute the Lane B external verifications AND author the 3 tooling-touchup scripts against *verified* endpoint shapes rather than guessed ones.
>
> **Scope discipline:** this is NOT the full Phase 5 (which is operator-driven multi-week field work). This is the bounded lead-up tooling: Lane B's 10 verifications + the §4.b/§4.c/§4.d tooling-touchup scripts. After this dispatch HALTs, the operator still owns Lane D Railway redeploy, the priority-30 list amendment, §8 Google Places billing, and the per-category scrape + field-entry execution.
>
> **Before pasting:** make sure the working tree is clean (`git status` Windows-side). The parallel Phase 6 Cowork chat has active uncommitted work — commit or stash that first so this Cursor dispatch starts from a clean tree and the parallel-execution file-scope lock holds.
>
> **Parallel-execution lock (gotcha #18):** this Cursor dispatch touches `scripts/*` + `app/contrib/*` + `outputs/*` ONLY. It must NOT touch `app/templates/*`, `app/static/*`, `app/providers/*`, `app/api/routes/*`, `app/db/*`, or `tests/test_phase6_*` — those belong to the parallel Phase 6 lane.

---

```
You are a Cursor session executing the Phase 5 lead-up tooling for the havasu-chat project — a Lake Havasu City, Arizona local-business directory. Phase 4 SHIPPED (layered-scrape framework + reconciler + Outbox); Phase 5 is the operator-driven Tier 1 data-gathering phase. This dispatch handles the two lead-up tasks that need live web access: (A) execute Lane B's 10 external-source verifications, and (B) author 3 tooling-touchup scripts against the verified endpoint shapes.

## §0 Baseline + reads

Before starting, confirm + report:

1. `git log --oneline -10` — origin/main should top at the Phase 5 lead-up chain. Recent floor: `0331102` (busted-quote cleanup) → `4ba29e4` (Lane B briefing) → `8fe6321` (Phase 6 forward-positioning) → `54ca07d` (heat_exposure priority-30 scaffold) → `acf5e2b` (§3 decision-locks) → `b755b03` → `62ab3b7` → `08bca69` → `ac94b6c`. If the floor doesn't match, STOP and report — the parallel Phase 6 chat may have pushed; pull origin/main first.
2. `git status` — MUST be clean. If the parallel Phase 6 chat's work is uncommitted in the tree, STOP and ask the operator to commit or stash it first. This dispatch needs a clean starting tree.
3. `python -m alembic heads` — single head `0a1b2c3d4e5f`. This dispatch ships NO migrations.
4. `python -m pytest -q --collect-only 2>&1 | tail -3` — record the baseline collected count (expected ~1803 from `62ab3b7`, but verify — the parallel Phase 6 chat may have added tests). This dispatch adds a small number of tooling-touchup tests; report the delta at close-out.
5. Read these docs end-to-end before starting:
   - `outputs/phase5_lane_b_verification_briefing.md` — the spec for Phase A; 10 verification sections with test procedures + finding templates + fallbacks
   - `outputs/phase5_prereq_checklist.md` §4 (the 10 verifications) + §3.5 (lock state)
   - `outputs/cursor_brief_phase_5_tier_1_data.md` §2 (locked decisions) + §3.3 (home-property AZ ROC) + §3.4 (health NPI) + §3.2 (on-the-water OSM)
   - `docs/maintainability/layered_scrape_strategy.md` (the 5-layer pattern + reconciler logic)
6. Read these source files so the tooling-touchups resolve cleanly:
   - `app/contrib/ingest_base.py` (the `BaseIngestClient` abstract interface — the 3 new scripts should follow its conventions where applicable)
   - `app/contrib/ingest_reconciler.py` (`reconcile_hit` + `SOURCE_PRIORITY` + `log_ambiguous_reconcile`)
   - `scripts/places_load.py` (the Layer-1 JSONL → DB pipeline — `osm_overpass_load.py` mirrors this shape)
   - `scripts/osm_overpass_pull.py` (the Layer-2 OSM pull wrapper that produces the JSONL `osm_overpass_load.py` consumes)
   - `app/contrib/osm_overpass_client.py` (`OsmOverpassClient` + `build_query`)
   - `app/contrib/npi/` (the existing NPI client surface — `npi_verify.py` wraps this)
   - `app/contrib/google_places_scraper.py` (Layer-1 client — for understanding the Provider/Entity write path the verify scripts update)

Report all baseline values. HALT and report if anything materially mismatches.

## §1 Why this dispatch exists

The Phase 5 Cowork chat authored the lead-up artifacts (§3 decision-locks, heat_exposure priority-30 scaffold, Lane B verification briefing) but structurally could NOT execute Lane B — the Cowork environment's WebFetch is provenance-locked and bash curl is forbidden. Cursor has live web access. This dispatch closes that gap: execute Lane B for real, then use the verified endpoint shapes to author the 3 tooling-touchup scripts that the brief §4 deferred to "authored as needed during Phase 5 execution."

Authoring the scripts AFTER live verification (not before) is the whole point — if AZ ROC turns out to be a Salesforce XHR portal requiring headless-browser, `az_roc_verify.py` must be built that way; if it's plain HTML, simpler. The Cowork chat couldn't know which. Cursor can.

## §2 Phase A — Execute Lane B (10 external-source verifications)

Work through `outputs/phase5_lane_b_verification_briefing.md` §1-§10. For each of the 10 sources, follow the test procedure in that doc, then fill the inline "Finding" cells (Date verified / Outcome / Actual URL / result shape / etc.) directly in the briefing file. The 10 sources:

1. §1 AZ ROC (Arizona Registrar of Contractors) — license search; the key open question is HTML vs Salesforce-XHR (determines `az_roc_verify.py` design)
2. §2 City of Lake Havasu City Parks & Recreation — facility list URL + format
3. §3 Lake Havasu City business licenses — does a public search endpoint exist?
4. §4 Mohave County GIS — commercial-business data beyond parcels?
5. §5 NPI registry — verify the API endpoint shape `https://npiregistry.cms.hhs.gov/api/?city=Lake+Havasu+City&state=AZ&version=2.1` still returns the expected JSON shape; confirm the existing `app/contrib/npi/` client still matches
6. §6 USAPickleball Places-to-Play — LHC court coverage
7. §7 PDGA course directory — LHC disc-golf course coverage (SARA Park expected)
8. §8 Google Places API billing posture — **operator-only; this needs Google Cloud Console auth. Mark §8 as "⏸ Deferred — operator action" and do NOT attempt it.**
9. §9 OSM Overpass rate posture — run the 3 LHC bbox queries (`leisure=marina`, `man_made=pier`, `natural=beach`) against `https://overpass-api.de/api/interpreter`; record element counts + tag shapes (this directly informs `osm_overpass_load.py`)
10. §10 parks-rec-scrapes.yml workflow health — check the GitHub Actions runs for the `parks-rec-scrapes` workflow on the repo; the workflow YAML is already confirmed correctly configured (cron `15 */6 * * *`)

For each: mark the outcome (✅ Verified / ⚠️ Caveats / ❌ Blocked / ⏸ Deferred) and fill the finding cells. Then update `outputs/phase5_prereq_checklist.md` §4 — add an outcome icon to each of the 10 rows in the table.

**HALT BOUNDARY 1:** after Lane B is done, report a summary table of the 10 outcomes. The operator commits the populated briefing + prereq update before you proceed to Phase B. This HALT matters because Phase B's script designs depend on Phase A's findings — the operator should sanity-check the findings before you build against them.

## §3 Phase B — Author the 3 tooling-touchup scripts (conditional on Phase A outcomes)

Author each script ONLY if its corresponding Lane B verification came back ✅ or ⚠️. If a verification came back ❌ Blocked, do NOT author that script — instead document the fallback (per the briefing's per-section "Fallback if blocked") in the brief §3 per-category playbook and report it.

### §3.b — `scripts/az_roc_verify.py` (brief §4.b; gated on §1 AZ ROC outcome)

Purpose: reads loaded `home-property-services` Provider rows from the DB, queries AZ ROC for each business name, and updates `Provider.verified = True` + `Provider.verified_field = 'az_roc_license'` on license matches. Unmatched rows stay `verified = False`.

Design per the §1 finding: if AZ ROC is plain HTML, a `requests`-based scraper; if it's Salesforce-XHR, a Playwright-based one (add `playwright` to `requirements.txt` if needed + note it in close-out). Conservative rate limiting (qps ≤ 0.5). Operator-runnable with `--dry-run` + `--limit` flags mirroring `scripts/places_discovery.py` conventions. Cache results by license number to avoid re-lookups. Add tests in a new `tests/test_phase5_az_roc_verify.py` (mock the AZ ROC response; do not hit the live endpoint in tests).

### §3.c — `scripts/npi_verify.py` (brief §4.c; gated on §5 NPI outcome)

Purpose: reads loaded `health-wellness-care` entity rows, cross-references each against the NPI registry via the existing `app/contrib/npi/` surface, and populates the `npi_number` field on matches. Mirror the `az_roc_verify.py` flag conventions (`--dry-run`, `--limit`). The NPI API is open + GET-based (no auth) per §5 — keep it a simple synchronous HTTP client; no headless browser. Add `tests/test_phase5_npi_verify.py` (mock the API response).

### §3.d — `scripts/osm_overpass_load.py` (brief §4.d; gated on §9 OSM outcome)

Purpose: the JSONL → DB load path for OSM data. Phase 4.3 shipped `scripts/osm_overpass_pull.py` (which produces JSONL) but no load script — Layer 1 has `places_load.py`, Layer 2 didn't have an equivalent. Mirror `scripts/places_load.py` shape exactly: read the OSM JSONL, map OSM tags to `entities.*` columns, run each hit through `reconcile_hit` from `app/contrib/ingest_reconciler.py`, emit `reconcile_skipped_ambiguous` / `reconcile_merged_geo` counts in the return. Per the §9 finding, handle missing optional tags gracefully (OSM tag sparsity is real — many LHC venues lack `phone`/`website`/`addr:*`); require only `name` + lat/lng. Add `tests/test_phase5_osm_overpass_load.py`.

After each script: run `python -m pytest -q` (must stay green) + `python -m ruff check scripts/ app/contrib/ tests/` (must stay clean).

**HALT BOUNDARY 2:** after all 3 scripts (or fewer, if some verifications blocked) are authored + pytest green + ruff clean, report the §13 close-out. The operator commits Phase B.

## §4 What NOT to do

1. **No schema migrations.** Phase 3 + 4 shipped every column. `verified` / `verified_field` / `npi_number` already exist.
2. **No edits outside `scripts/*` + `app/contrib/*` + `outputs/*`.** The parallel Phase 6 lane owns `app/templates/*`, `app/static/*`, `app/providers/*`, `app/api/routes/*`, `app/db/*`. Strict-disjoint.
3. **No live-endpoint calls in tests.** Mock every external response. Tests must run offline + deterministic.
4. **No §8 Google Places billing attempt.** Operator-only (Cloud Console auth).
5. **No running the actual category scrapes.** This dispatch builds the tooling; the operator runs the scrapes per the brief §3 per-category playbooks during the multi-week execution window.
6. **No `entities.sources` JSON-array migration.** Comma-separated string in `entity.source` per Phase 4.3 lock.
7. **Don't author a script whose verification came back ❌ Blocked.** Document the fallback instead.

## §5 Close-out (§13)

At each HALT boundary, report:
- §13.1 — what was done (Lane B outcomes table for HALT 1; scripts authored for HALT 2)
- §13.2 — files touched (exact list)
- §13.3 — pytest delta (collected count before → after) + ruff status
- §13.4 — any ❌ Blocked verifications + the fallback applied
- §13.5 — deviations from this dispatch + rationale
- §13.6 — what the operator does next (commit instructions; PowerShell-safe commit body — no embedded double-quotes per gotcha #16)

HALT at boundary 1, wait for operator commit, then proceed to Phase B. HALT at boundary 2.
```

---

## Operator instructions

1. **Confirm the working tree is clean Windows-side** (`git status`). The parallel Phase 6 Cowork chat has active uncommitted work — commit or stash it first so this Cursor dispatch starts clean and the file-scope lock holds.
2. **Commit this dispatch prompt:**
   ```powershell
   git add outputs/cursor_dispatch_prompt_phase5_leadup_tooling.md
   git commit -m 'chore(outputs): Phase 5 lead-up tooling Cursor dispatch prompt -- Lane B verifications + 3 tooling-touchup scripts' -m 'Paste-ready Cursor dispatch covering the Phase 5 lead-up work that needs live web access. Phase A executes Lane B 10 external-source verifications against outputs/phase5_lane_b_verification_briefing.md (the Cowork chat could not do this -- WebFetch provenance-locked + bash curl forbidden; Cursor has live web). Phase B conditionally authors scripts/az_roc_verify.py + scripts/npi_verify.py + scripts/osm_overpass_load.py against verified endpoint shapes, gated on Phase A outcomes -- a script whose verification came back blocked is not authored, the fallback is documented instead. Two HALT boundaries: after Lane B (operator commits findings), after the 3 scripts (operator commits tooling). Scope-locked to scripts + app/contrib + outputs per gotcha 18; strict-disjoint from the parallel Phase 6 lane. No migration. Section 8 Google Places billing stays operator-only. Does not run the actual category scrapes -- that is the multi-week operator field work per brief section-3.'
   git push
   ```
3. **Open a fresh Cursor chat**, paste the fenced block, let it run Phase A (Lane B verifications). It will HALT after Lane B with a findings summary.
4. **Review + commit the Lane B findings**, then tell Cursor to proceed to Phase B.
5. **Review + commit the 3 tooling-touchup scripts** after HALT boundary 2.

After this dispatch closes, the remaining Phase 5 lead-up is operator-only: §8 Google Places billing check, Lane D Railway redeploy, priority-30 list amendment. Then the multi-week per-category scrape + field-entry execution begins per brief §3.

---

*Authored by Cowork primary at the new-chat post-`0331102` session (2026-05-14). Lives at `outputs/cursor_dispatch_prompt_phase5_leadup_tooling.md` — brand-new outputs/ file, safe under the parallel-chat lock. Hands the live-web-dependent Phase 5 lead-up work to Cursor, which has the web access the Cowork chat structurally lacks.*
