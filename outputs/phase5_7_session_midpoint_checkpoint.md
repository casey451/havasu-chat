# Phase 5.7 — Outdoors, Parks & Trails — Mid-session checkpoint (2026-05-17)

> **What this is:** a hand-off doc for the next Cowork primary agent
> to pick up Phase 5.7 at gates §2 → §4 → §5. The current session
> shipped §0 + §1 + the §1 sustainability layer + the §2 ambig audit
> dump SCRIPT (across 3 commits + 2 DB-only writes) but is being
> checkpoint'd here rather than pushed through — the remaining work
> is operator-curation-heavy (§2 audit doc + apply-script + §4
> heat_exposure + crowd_notes) and benefits from a fresh context
> window.
>
> **Mirrors** `outputs/phase5_4_session_midpoint_checkpoint.md` shape
> (which checkpointed 5.4 at gates 4+5 before the next session shipped
> it at `c13dfff`).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.7 boot
> session (2026-05-17) post-`0c011ae` + post-§1-load. Hand-off to the
> next session.

---

## §1 Commit chain this session (`b3acb03 → 0c011ae`)

| # | Commit | Subject | Source | Task |
|---|---|---|---|---|
| 1 | `f5d1062` | `chore(outputs)` — Phase 5.7 (Outdoors, Parks & Trails) kickoff | Cowork | kickoff doc |
| 2 | `1dfd28e` | `fix(scripts)` — _DISCOVERY_DOMAIN_FALLBACK + _PRIMARY_TYPE_MAP extend for Phase 5.7 sustainability layer | Cowork | sustainability (5 entertainment_attractions entries + golf_course direct mapping + medical_clinic widening that closes the 5.4 + 5.6 V1.5 carry-over) |
| 3 | `0c011ae` | `chore(outputs)` — Phase 5.7 narrow-label discovery wrapper | Cowork | §1 dispatch tool (Path A.2 — pre-filters the 21-label outdoors-parks-trails bundle down to 3 in-scope labels) |

**Plus 2 DB-only writes** (no commit; events.db is gitignored):

- **Cache-reload load** (1st run of `places_load --category outdoors-parks-trails`) — 102 in-LHC rows → 28 inserts + 32 updates + 42 ambig-skips + 0 operator-queue. Brought outdoors-parks-trails from 6 → 29 entries.
- **Fresh-sweep load** (2nd run, after running the wrapper for actual narrow discovery) — 103 in-LHC rows → 1 insert + 60 updates + 42 ambig-skips + 0 operator-queue. Net: +1 entry to 30. The 1 fresh insert is **Bill Williams River National Wildlife Refuge** (`wildlife_refuge` primary type — federal land directly adjacent to LHC; caught by the new `(None, "entertainment_attractions")` catch-all because `wildlife_refuge` isn't in `_PRIMARY_TYPE_MAP`).

**Pytest baseline:** 1932 collected (5.6 SHIPPED) → **1946 collected post-`1dfd28e`** (+14). Breakdown: 5 parametrized `_ENTERTAINMENT_KEYS` asserts + 2 type-map asserts (`golf_course` + `medical_clinic`) + 6 defensive preservation asserts (5.2 / 5.3 / 5.4-health / 5.4-fitness / 5.5-auto / 5.6-retail fallback) + 1 park/dog_park preservation = 14 named tests. (Forecast was +15 — off-by-one on my recount; actual is +14.)

**Ruff:** green throughout. The wrapper's `# noqa: E402` markers (added after the sys.path insertion fix) silence the imports-not-at-top warnings cleanly; no F401 / F541 surfaces.

**CI:** ✅ Green on `1dfd28e` (run `2597846…`, 1m47s) and on `0c011ae` (run `2597670…`, 1m39s). One sibling workflow `parks-rec-scrapes` continues ❌ on its scheduled cron triggers — pre-existing carry-over from 5.3 + 5.4 + 5.5 + 5.6; **5.7 §4.5 sidebar still TODO** (Decision 3 — post-gate-2, not blocking).

---

## §2 Phase 5.7 acceptance gate — 3 of 6 CLEARED ✅, 3 pending ⏭

| # | Gate item | Status | Where |
|---|---|---|---|
| 1 | 20+ entries in `outdoors-parks-trails` post-load | ✅ **30** rendering (1.50× target) | 6 pre-existing + 29 new from cache-reload + fresh-sweep loads (1 fresh insert: Bill Williams River NWR via the new `(None, "entertainment_attractions")` catch-all) |
| 2 | All Google ↔ existing-entity ambiguous reconciler hits reviewed | ⏭ **pending §2** | 42 ambig-skipped (same set both loads). Dump script authored at `outputs/phase5_7_ambig_audit_dump.py` — **next agent runs the dump script + authors the audit doc + apply-script** |
| 3 | Layer-4 verifier surface scoped — built or explicitly deferred to V1.5 | ✅ **Option C deferred** | Resolved in `outputs/phase5_7_outdoors_parks_trails_kickoff.md` §3 — AZ State Parks + NPS + LHC Parks & Rec paths documented for V1.5 |
| 4 | Top-10 by reviews have long-form `crowd_notes` | ⏭ **pending §4** | 0 long-form notes today. Mirror `outputs/apply_phase5_6_shopping_crowd_notes.py` — pass dict directly to `Entity.crowd_notes` JSON column (no `json.dumps`); source drafts from `Provider.google_review_snippets` (its own column, not in attributes) |
| 5 | `heat_exposure` non-NULL on every entry | ⏭ **pending §4** | **30 NULL today.** §4 apply-script needed. **5.7 flips the default to `outdoor`** (opposite of 5.6's `indoor`) with `INDOOR_OVERRIDES` for: `Altitude Trampoline Park` (only obvious indoor candidate). Mirror `outputs/apply_phase5_6_shopping_heat_exposure.py` but flip the default + populate INDOOR_OVERRIDES instead of OUTDOOR_OVERRIDES |
| 6 | `/category/outdoors-parks-trails` renders ≥15 | ✅ **30** | 2.00× target; trivially met at gate-1 count |

**Final gate verification script `outputs/phase5_7_gate_verification.py` NOT yet authored** — mirror `outputs/phase5_6_gate_verification.py` shape but: 6 gates (no `is_mobile_service`); threshold ≥20 not ≥40; `outdoors-parks-trails` slug everywhere; the gate-1 query MUST use the `(e.entity_type != 'commercial' OR provider-visible)` shape from `outputs/phase5_2_gate_verification.py` since outdoors-parks-trails will have a mix of `place` + `commercial` entries in the long run (though all 30 today are commercial — see §3 below).

---

## §3 Notable artifacts shipped this session

### `1dfd28e` — sustainability layer for 5.7 (mirrors `44e8097` / `4d41944` / `fc51940` / `7c994aa` shape)

- 5 new `_DISCOVERY_DOMAIN_FALLBACK` entries (`(None / tourist_attraction / amusement_park / point_of_interest / establishment, "entertainment_attractions")` → `"outdoors-parks-trails"`)
- 1-line `_PRIMARY_TYPE_MAP` widening for `golf_course` → `("outdoors-parks-trails", "commercial")`
- 1-line `_PRIMARY_TYPE_MAP` widening for `medical_clinic` → `("health-wellness-care", "commercial")` — **closes V1.5 carry-over from 5.4 + 5.6 close-outs §3**
- 14 regression tests in `tests/test_phase5_7_places_load_resolver.py`

The sustainability commit was effective: **0 operator-queue rows across both loads** (cache-reload + fresh-sweep). Every row routed correctly. The fresh discovery surfaced `wildlife_refuge` primary type (Bill Williams River NWR) which fell through to the new `(None, "entertainment_attractions")` catch-all — perfect catch.

### `0c011ae` — narrow-label discovery wrapper

`outputs/phase5_7_narrow_label_filter.py` (~190 lines). Path A.2 pattern (standalone outputs/ wrapper, no production code touched) — pre-filters the 21-label outdoors-parks-trails bundle down to the 3 in-scope labels (`parks`, `golf courses`, `mini golf`) per kickoff §1 Narrow scope decision. Mirrors `scripts/places_discovery.py` arg shape; dispatches `GooglePlacesClient.sweep_discovery` directly. **Bug surfaced + fixed mid-session:** running via `python outputs/phase5_7_narrow_label_filter.py` hit `ModuleNotFoundError: No module named 'app'` because Python's `-m` invocation adds repo root to sys.path but direct script invocation doesn't. Fixed inline with a 4-line sys.path.insert + `# noqa: E402` markers on the `app.*` imports. Script runs cleanly both ways now.

### `outputs/phase5_7_ambig_audit_dump.py` — authored, NOT yet committed, NOT yet run

The §2 audit dump script for the next agent to run. Mirrors `outputs/phase5_6_ambig_audit_dump.py` shape with three 5.7-specific adjustments:

1. **Narrow scope filter** — input set reconstruction uses `is_entertainment(row)` (10 entertainment_attractions labels) plus a `is_fitness(row)` anomaly surface (any fitness_sports row in the load pool would be a §2 anomaly per kickoff §1 defer decision).
2. **Three special-audit axes** (vs 5.6's single gas-station axis):
   - (a) cat-6 on-the-water cross-list (Thompson Bay Beach + lake-adjacent state parks)
   - (b) cat-12 classes-sports-recreation cross-list (gun club, motocross park, Ofd Racing all surfaced in §1)
   - (c) SARA Park same-cat de-dup pile (6 §1-surfaced SARA entries: parent + dog park + disc golf + 2 hiking trails + mountain park loop)
3. **Edge-case rubric** keyed to entertainment_attractions primary types (`event_venue`, `amusement_park`, `garden`, `sports_complex`, `race_course`, `sports_activity_location`, `wildlife_refuge`, `hiking_area`, `athletic_field`, `tourist_attraction`).

### Pre-flight surprises (3 found, triaged before §1 dispatch):

1. **WIDER working-tree drift than documented** — not just `places_categories.json` corruption (fourth recurrence) but also `scripts/places_load.py` (639 → 199 lines), `app/db/models.py` (1539 → 1475 lines), `app/contrib/google_types_mapping.py` (153 → 135 lines) plus ~55 other tracked files. Operator restored via `git restore .` Windows-side after sandbox `rm .git/index.lock` failed with `Operation not permitted`. **Cause likely**: stale checkout / external-editor crash. The 5.7 kickoff §0 item 6 is widened accordingly.
2. **Sandbox `.git/index.lock` mount-staleness gotcha (NEW)** — sandbox bash reported a stale `.git/index.lock` (empty, dated May 13) that did NOT exist Windows-side. Operator's `Remove-Item .git\index.lock` Windows-side returned "Cannot find path." `git restore .` Windows-side worked despite the sandbox-side lock view.
3. **Sandbox `git diff` mount-staleness (NEW DEPTH)** — even after the operator's Windows-side `git restore .` left the working tree clean per Windows `git diff` (empty output), sandbox-side `git diff --stat` continued to report the original drift (places_load.py -440, etc.). This is a STRONGER form of the documented mount-staleness gotcha — it's not just file-shape `wc -l` that's unreliable; `git diff` itself reads stale data. **The Read tool was authoritative throughout** (confirmed restored shapes on every Read; bypassed the bash mount cache). Internalized: when in doubt, use Read tool + `git show HEAD:` for sandbox file inspection; trust Windows-side `git status` / `git diff` for working-tree state.

---

## §4 §1 load result analysis (operator-decision surface for §2)

### 30 entries by primary_type distribution

13 `park` + 2 `state_park` + 2 `sports_activity_location` + 2 `race_course` + 2 `hiking_area` + 2 `event_venue` + 1 each of `sports_complex` / `golf_course` / `garden` / `dog_park` / `athletic_field` / `amusement_park` / `wildlife_refuge`.

**All 30 are `entity_type='commercial'`.** None are `place`-typed despite `park` / `dog_park` mapping to `('outdoors-parks-trails', 'place')` in `_PRIMARY_TYPE_MAP`. Why: the existing Provider rows had `entity_type='commercial'` set on initial dual-write (from prior-phase pulls); the cache-reload + fresh-sweep UPDATE path doesn't re-set entity_type. **Per kickoff §2 recommendation: leave as commercial for V1** — the gate-1 OR-clause query handles both correctly; flipping to `place` is cosmetic + risks dual-write re-promotion edge cases.

### §2 audit pre-classification (operator-decision surface)

Based on §1 surface (DB query results, not the dump script output):

**Clear FLIPs / DRAFTs:**
- `Altitude Trampoline Park` (amusement_park, INDOOR) → DRAFT (kickoff §1 explicitly deferred indoor entertainment)
- `Buses By The Bridge` (event_venue, annual bus festival) → FLIP to `events` (cat-2)
- `Desert Storm Headquarters` (event_venue, annual boat poker run) → FLIP to `events` (cat-2)
- `Parks & Recreation Department` (sports_activity_location, municipal dept) → DRAFT or FLIP to `public-civic-resources` (cat-13)

**Review-needed (operator picks):**
- `Lake Havasu City Sportsman's Club` (sports_complex, gun club) — arguably `classes-sports-recreation` (cat-12)
- `Lake Havasu Motocross Park` (race_course, outdoor track) — arguably cat-12
- `Ofd Racing` (race_course) — what is this? May need investigation
- `Thompson Bay Beach` (sports_activity_location) — likely already in `on-the-water` from 5.2; cross-cat check needed
- `Butterfly Garden` (garden) — community garden? Private? Public?
- `ASU SWANSON FIELDS` (park, all-caps name) — capitalization suggests stale name from a different source; investigate

**Clear KEEPs:**
- `Avalon Park`, `Cattail Cove State Park`, `Dick Samp Memorial`, `Lake Havasu State Park`, `Rotary Community Park & Playgrounds`, `SARA Park`, `Spezzano Cactus Park`, `Grand Island Park`, `Jack Hardie Park`, `Mesquite Park`, `Realtor Park`, `Wheeler Park`, `Yonder Park` — all `park` or `state_park`
- `Bridgewater Links Golf Course` (golf_course)
- `Bill Williams River National Wildlife Refuge` (wildlife_refuge, federal land)
- `SARA Park Dog Park` (dog_park) — though see SARA de-dup decision

**SARA Park same-cat de-dup (special-audit (c)):**

6 SARA-related entries — likely 1 physical complex with 5 sub-features (the dog park, disc golf course, mountain park loop trail, hiking trail head, sara park hiking trail). V1 recommendation: **KEEP all 6** — they're real distinct surfaces a user would want to discover separately. Compress only if any pair is clearly a navigation alias for the same physical surface.

### 42 ambig-skips

Same 42 across both loads (cache-reload + fresh-sweep produced identical place_id sets in the ambig pool). The dump script's aggregates section will surface the cross-cat vs same-cat vs no-match breakdown. Per kickoff §2 expectation: most should be benign geo-proximity false-positives against existing on-the-water / eat-drink / lodging entities (waterfront restaurants near parks, hotels near parks, etc.).

---

## §5 Remaining work for next session (Phase 5.7 ship)

### Gate-blocking (3) — must clear before SHIP

1. **§2 audit cycle** (gate-2):
   - Run `python outputs/phase5_7_ambig_audit_dump.py` (operator dispatches; produces `outputs/phase5_7_ambig_audit_data.json` + stdout aggregates)
   - **Commit the dump script** — `git add outputs/phase5_7_ambig_audit_dump.py` + commit (mirrors 5.6's `phase5_6_ambig_audit_dump.py` precedent of landing the dump script as audit-trail before the audit doc)
   - Cowork agent reads the JSON + authors `outputs/phase5_7_parks_audit.md` (audit doc mirroring `outputs/phase5_6_shopping_essentials_audit.md` shape)
   - Cowork agent authors `outputs/apply_phase5_7_parks_audit.py` (FLIPs + DRAFTs per §4 pre-classification + dump-script edge-case rubric output)
   - Operator reviews + dispatches apply-script (stop FastAPI dev server first per the documented gotcha)
2. **§4 `heat_exposure` apply-script** (gate-5):
   - Author `outputs/apply_phase5_7_parks_heat_exposure.py` mirroring `apply_phase5_6_shopping_heat_exposure.py` BUT **flip default to `outdoor`** + populate `INDOOR_OVERRIDES` for `Altitude Trampoline Park` (only obvious indoor candidate; possibly also any indoor mini golf venues that surface)
   - Run apply-script
3. **§4 `crowd_notes` top-10** (gate-4):
   - Author `outputs/apply_phase5_7_parks_crowd_notes.py` mirroring `apply_phase5_6_shopping_crowd_notes.py`
   - Source drafts from `Provider.google_review_snippets` (its own column, NOT inside `attributes` — per 5.4 close-out §4 source-path correction)
   - Pass dict directly to `Entity.crowd_notes` JSON column (no `json.dumps()` per 5.3 `f35d5e4` gotcha)
   - Run apply-script
4. **Gate verification script** (`outputs/phase5_7_gate_verification.py`) — mirror `outputs/phase5_6_gate_verification.py` shape with 5.7 overrides per §2 above
5. **SHIP commit** (`chore(outputs)` — Phase 5.7 SHIPPED — all 6 gate items cleared)

### 🚨 Carry-over for operator-side action

- **Phase 6 lane dispatch: Phase 5.7 SHIPPED ledger amendment** — author `outputs/claude_code_dispatch_phase6_amend7.md` (mirrors Amendment 6 pattern) for operator to paste into Claude Code OR land in-line per the 5.4 `0addb63` precedent
- **V1.5 Layer-4 verifier surface for 5.7** — AZ State Parks + NPS + LHC Parks & Rec paths documented in kickoff §3 for V1.5 pickup
- **V1.5: `wildlife_refuge` direct mapping** — soft-edge surfaced this session (`wildlife_refuge` isn't in `_PRIMARY_TYPE_MAP`; caught by `(None, "entertainment_attractions")` catch-all). 1-line addition `"wildlife_refuge": ("outdoors-parks-trails", "place")` would catch federal-land entries regardless of discovery domain. Same shape as the 5.7 §1 `medical_clinic` / `golf_course` widenings. Defer to V1.5.
- **86 of 265 HWC providers remain `verified=False`** — carry-over from 5.4. Operator-driven DBA→NPI follow-up surface (optional V1.5).
- **Operator: prune `data/events.db.bak-*` files** when comfortable (carry-over from 5.3 + 5.4 + 5.5 + 5.6)
- **`parks-rec-scrapes` scheduled CI** — Decision 3 sidebar deferred to post-gate-2. Hypotheses in kickoff §4.5: (a) workflow was authored against pre-Phase-3.2 `outdoors-and-parks` slug and slug-rename broke it; (b) workflow scrapes the slug and fell into the `(None, "entertainment_attractions")` gap that the 5.7 §1 sustainability commit just patched (so it may go green retroactively on next cron). Investigate after §2 audit.
- **Google Places API key rotation** — deferred per operator ("all keys will be changed at conclusion of this project")

### Soft-edges (3 deferred per §4 pre-classification)

- 6 SARA Park entries (parent + 5 sub-features) — V1 recommendation KEEP all; revisit if any pair is a navigation alias
- All 30 entries `entity_type='commercial'` (none `place`-typed) — cosmetic; gate-1 OR-clause handles both
- ASU SWANSON FIELDS uppercase name — investigate source, decide whether to normalize

None are gate-blocking.

### Sandbox bash MOUNT-STALENESS — pattern continues to deepen

5.5 documented this as a new gotcha (file-shape queries); 5.6 hit it twice (json.load + importlib); **5.7 hit it three times: (a) `.git/index.lock` view existed in sandbox but not Windows-side, (b) `git diff` output didn't update post-restore, (c) post-Edit `wc -l` continued to show pre-restore line counts.** The Read tool is the source of truth for file state in sandbox; sandbox bash is unreliable for ANY file-shape or git-state query. Future agents should default to Read tool + `git show HEAD:` for sandbox-side inspection; trust Windows-side `git status` / `git diff` for working-tree state.

---

## §6 Coordination summary (one-line)

| Lane | Coordination need |
|---|---|
| Phase 6 (parallel agent OR in-line) | Amend `master_build_plan.md` + `STATE.md` with Phase 5.7 SHIPPED at `[SHIP-COMMIT]` via `outputs/claude_code_dispatch_phase6_amend7.md` (not yet authored — next session's job, after SHIP commit lands) |
| Cursor | No dispatches pending (Phase 5.7 produced its own regression tests in-lane: +14 at 1946) |
| Operator | §2 audit dispatch + apply-script reviews, §4 heat_exposure + crowd_notes reviews, final gate verification + SHIP commit, V1.5 carry-overs (wildlife_refuge widening, AZ State Parks / NPS / LHC Parks & Rec verifier paths), `parks-rec-scrapes` cron investigation per §4.5 sidebar |

---

## §7 Read order for the next session

1. **This document** — the state of play (mid-session checkpoint + commit chain + §1 load result + §2 pre-classification)
2. `outputs/phase5_7_outdoors_parks_trails_kickoff.md` — Phase 5.7 runbook (authoritative for §6 acceptance gate definitions + §3 Option C verifier resolution + §4.5 CI sidebar)
3. `outputs/phase5_7_next_agent_boot_prompt.md` — the original boot prompt that primed THIS session (for historical framing; some of its anticipated-label-set claims turned out to be wrong — see kickoff §0 + the "BOOT-PROMPT FRAMING NOTE" callout in the kickoff header)
4. `outputs/phase5_6_session_closeout.md` — the just-shipped 5.6 close-out (carries the apply-script + audit + sustainability layer playbooks 5.7 reuses verbatim)
5. `outputs/phase5_7_ambig_audit_dump.py` — the §2 dump script authored this session, awaiting operator dispatch
6. `outputs/phase5_6_shopping_essentials_audit.md` — template for the equivalent 5.7 audit doc the next agent will author
7. `outputs/apply_phase5_6_shopping_audit.py` / `_heat_exposure.py` / `_crowd_notes.py` — template apply-scripts the 5.7 equivalents will mirror
8. `outputs/phase5_6_gate_verification.py` — template for the equivalent `outputs/phase5_7_gate_verification.py`

---

## §8 Pre-flight for the next session

1. **`git log --oneline -15`** — origin should top at `0c011ae` (Phase 5.7 wrapper) or later. Lane chain since 5.6 SHIPPED: `7609a01 → b3acb03 → f5d1062 → 1dfd28e → 0c011ae`.
2. **`git status`** — clean. Carry-over untracked from 5.6: `hava_api_catalog.docx` + `~$va_api_catalog.docx` Word lock + 2 historical `outputs/ci_*_log_failed.txt` files + `outputs/_deltest`. Plus the new `outputs/phase5_7_ambig_audit_dump.py` if not yet committed by the next session.
3. **`python -m alembic current`** — `0a1b2c3d4e5f` (unchanged across all 5.x phases).
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — expect **1946 collected** (5.7 baseline; +14 from `1dfd28e`). Verify no drift.
5. **`gh run list --branch main --limit 5`** — top runs should be ✓ on `0c011ae` + `1dfd28e` + `f5d1062`. `parks-rec-scrapes` scheduled cron continues ❌ (carry-over; §4.5 sidebar).
6. **🚨 WIDENED four-file shape check** per kickoff §0 item 6:
   ```powershell
   git diff --stat scripts/places_categories.json scripts/places_load.py app/db/models.py app/contrib/google_types_mapping.py
   ```
   MUST be empty. If ANY shows drift, restore via `git restore .` Windows-side first.
7. **DB state spot-check** — `outdoors-parks-trails` should show **30 entries / 0 verified / 30 heat_exposure=NULL / 0 long-form crowd_notes / 0 draft / 30 commercial / 0 place** (the post-§1-load state this session left).
8. **§2 cycle dispatch**:
   - Operator runs `python outputs/phase5_7_ambig_audit_dump.py` (produces JSON + stdout aggregates) — first action
   - Operator commits the dump script (precedent from 5.6's `phase5_6_ambig_audit_dump.py` landing alongside the audit)
   - Cowork agent reads the JSON + authors audit doc + apply-script per §5 above

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.7 boot session
(2026-05-17) post-`0c011ae` + post-§1-load. Phase 5.7 mid-session
checkpoint — 3 of 6 gate items cleared; 3 commits on origin/main from
`b3acb03 → 0c011ae` plus 2 DB-only writes. Hand-off to next session
for §2 audit cycle + §4 apply-scripts + SHIP.*
