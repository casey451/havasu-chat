# Phase 6.1 Close-out Artifacts (pre-positioned)

> **APPLIED 2026-05-14** — Phase 6.1 shipped at `fd16e7a` (1820 collected / 1818 passed + 2 skipped + 30 subtests; alembic `0a1b2c3d4e5f` unchanged; ruff clean). The §1 master-plan ship-line + §2/§3 STATE.md updates in this doc were applied to `docs/maintainability/master_build_plan.md` §4 Phase 6 + `docs/STATE.md`, and the §4 review rubric was walked against Cursor's §13 report (all gates passed; one invited deviation — place/program `profile_url` → `/home` stopgap). Placeholder slots below are left as the original template intentionally — this doc is now a historical record of the close-out plan, not a pending checklist.
>
> Pre-positioned during Phase 6.1 in-flight execution at session-23-extension-3 (2026-05-13). When Cursor returns with the §13 close-out report, fill the placeholder slots (`<<<SHA>>>`, `<<<PYTEST_DELTA>>>`, etc.) and paste each section into the indicated destination.
>
> **Why pre-position:** the operator-commit + STATE refresh + master plan ship-line authoring rhythm has been the bottleneck on prior sub-phase ships (~30-60 min per ship). Doing the templates now while Cursor runs saves that time on the back-end.
>
> **Sources:**
> - Brief §3.1 acceptance gates (`outputs/cursor_brief_phase_6_tier_1_ui.md`)
> - Phase 4.2 / 4.3 / 4.4 ship-line precedent (master plan `docs/maintainability/master_build_plan.md` §4 Phase 4 lines 233-244)
> - STATE.md Production-block + Recently-shipped pattern (docs/STATE.md lines 7-145)

---

## §1 Master plan §4 Phase 6 ship-line (paste under Phase 6 deliverables)

**Paste destination:** `docs/maintainability/master_build_plan.md`, immediately after line 297 (the existing `- Mobile-first responsive throughout (bottom-sheet patterns...)` bullet) — author a new `**Shipped (incremental):**` sub-section if it doesn't exist yet (it doesn't — Phase 6.1 is the first 6.X ship), then the per-sub-phase bullet:

```markdown
**Shipped (incremental):**

- **Phase 6.1 — Unified Hava card grammar (2026-05-XX, commit `<<<PHASE_6_1_SHA>>>`):** First sub-phase of Phase 6 shipped — the critical first deliverable per Opus design §6.1. Single Jinja partial `app/templates/components/hava_card.html` (~<<<HAVA_CARD_HTML_LINES>>> lines) that renders any ENTITY (commercial / place / event) in any context (category page / search results / group landing / profile reference). Place vs event vs commercial differentiation via status-line color (green / amber / red per freshness + lake-blue for events) + content ("Open until 10pm" vs "Tonight at 6:00pm"), NOT separate templates. New `app/providers/view_models.py::HavaCardViewModel` dataclass (~<<<VIEW_MODEL_LINES>>> lines; frozen, pure-data, consumed by template) + new `app/providers/queries.py::build_card_view_model(db, entity_id) -> HavaCardViewModel` helper (joins Entity + Location + Photo + Category + District + Source; reuses existing `derive_hero_photo` + `derive_freshness` + `is_open_now`). New `app/static/styles/components/hava_card.css` (~<<<CSS_LINES>>> lines, mobile-first: stacked layout <768px, horizontal >=768px; sponsor pill styling per prereq §3.b subtle-pill; freshness band as colored dot top-right; boat_access badge + heat_exposure pill only render when non-null). **<<<PYTEST_DELTA>>> net-new tests** in `tests/test_phase6_hava_card.py` covering: HavaCardViewModel construction; build_card_view_model from fixture Entity + Location + Photo; status_line_text + color per entity_type branches (commercial open/closed/freshness, place open/seasonal, event today/weekend/last-week); freshness_band thresholds; is_sponsored pill rendering; heat_exposure_pill render rules; boat_access_badge render rules; 4-context template render smoke (category page / search results / group landing / profile reference); mobile breakpoint CSS; empty hero photo placeholder; empty district graceful omit. Pytest **1803 → <<<NEW_PYTEST_COUNT>>>** (+<<<PYTEST_DELTA>>> net-new). Alembic head unchanged at `0a1b2c3d4e5f` (Phase 4.1 outbox; Phase 6 ships no migrations). Ruff clean. **<<<N_DEVIATIONS>>> brief §3.1-invited deviations:** <<<DEVIATIONS_NARRATIVE>>>. **No production runtime impact** until next deploy; once deployed, the card grammar renders against existing Phase 1+3 schema (no new columns, no new tables). HALT at brief §3.1 boundary per dispatch instructions; Phase 6.2 (first category landing page template + Eat & Drink proof) dispatches in a fresh Cursor session against the pre-positioned dispatch prompt at `outputs/cursor_dispatch_prompt_phase_6_2.md` (SHA-patch slot at `<<<PHASE_6_1_SHA>>>` patched into 3 sites in that prompt before paste). Cursor session, single dispatch.
```

**Placeholder slots to fill:**

| Slot | Source |
|---|---|
| `<<<PHASE_6_1_SHA>>>` | Operator commit SHA after committing Cursor's §13 batch |
| `<<<HAVA_CARD_HTML_LINES>>>` | Cursor's §4 file list — line count of new hava_card.html |
| `<<<VIEW_MODEL_LINES>>>` | Cursor's §4 — net additions to view_models.py |
| `<<<CSS_LINES>>>` | Cursor's §4 — line count of new hava_card.css |
| `<<<PYTEST_DELTA>>>` | Cursor's §10 — net-new test count (expected 10-15) |
| `<<<NEW_PYTEST_COUNT>>>` | 1803 + delta |
| `<<<N_DEVIATIONS>>>` | Count of §11 deviations in Cursor report (expected 1-3) |
| `<<<DEVIATIONS_NARRATIVE>>>` | One-sentence summary of each deviation Cursor flagged |

---

## §2 STATE.md Production block updates

**Paste destination:** `docs/STATE.md`, edit existing Production block bullets.

**Bullet 1 — Current main HEAD (line 8):**
- **Old:** `**Current main HEAD (origin):** `2f87211` (2026-05-13, Phase 4.3 OSM + reconciler on origin/main)...`
- **New:** `**Current main HEAD (origin):** `<<<PHASE_6_1_SHA>>>` (2026-05-XX, Phase 6.1 unified Hava card grammar on origin/main). Phase 6 lane is now in flight — 4 more sub-phases (6.2 first category landing + Eat & Drink proof → 6.3 remaining 5 category pages + district + ranking + seasonal hours → 6.4 map + boat-mode + themed groups → 6.5 homepage + profile extension + mobile polish) to reach Phase 6 SHIPPED.`

**Bullet 4 — Build phase (line ~11):**
- **Old:** ends with `**Next dispatchable major lane:** Phase 5 (Tier 1 data gathering — master plan §5; do not start Phase 5 work in this Phase 4.4 close-out thread).`
- **Append:** ` **Phase 6.1 (unified Hava card grammar) SHIPPED on origin 2026-05-XX (commit `<<<PHASE_6_1_SHA>>>`); Phase 6 lane in flight in parallel with Phase 5 data gathering per master plan §4 Phase 5/6 parallel design. Phase 6.2 dispatch prompt pre-positioned at `outputs/cursor_dispatch_prompt_phase_6_2.md` — SHA-patch + dispatch when 6.1 §13 review closes.**`

**Bullet 5 — Pytest (line ~12):**
- **Old:** `**Pytest:** **1795 collected (1793 passed + 2 skipped + 30 subtests)** ...`
- **New:** `**Pytest:** **<<<NEW_PYTEST_COUNT>>> collected (<<<NEW_PYTEST_PASSED>>> passed + 2 skipped + 30 subtests)** (post-Phase-4.4 baseline 1795; post-Phase-6.1 baseline <<<NEW_PYTEST_COUNT>>>; **+<<<PYTEST_DELTA>>> net-new** in `tests/test_phase6_hava_card.py` covering HavaCardViewModel + build_card_view_model + status_line text/color branches + freshness_band thresholds + sponsor pill + heat_exposure pill + boat_access badge + 4-context template render smoke + mobile breakpoint CSS + empty-slot graceful degradation). The 2 skipped are unchanged: (a) Postgres-only FTS path in `tests/test_search_fts.py`; (b) Phase 4.2 places_discovery dry-run parity deferred to operator. Full-suite run 2026-05-XX on Windows venv ~<<<MINUTES>>>m; **ruff clean**.`

**Bullet 6 — Alembic head (line ~13):**
- No change needed — Phase 6.1 ships no migrations. Head stays at `0a1b2c3d4e5f`. The "Alembic head (deployed prod)" remains `e1f2a3b4c5d6` (last production deploy was session-22).

**Add new bullet under Production block after the Phase 4 references but before Prior production state:**
```markdown
- **Phase 6 lane status:** Phase 6.1 unified Hava card grammar SHIPPED 2026-05-XX at `<<<PHASE_6_1_SHA>>>` — the critical first deliverable per Opus design §6.1. Remaining sub-phases pre-positioned via brief at `outputs/cursor_brief_phase_6_tier_1_ui.md` (§3.2 → §3.5). Phase 6.2 dispatch prompt at `outputs/cursor_dispatch_prompt_phase_6_2.md` — paste-ready post-6.1 SHA patch. Phase 6 runs in PARALLEL with Phase 5 (Tier 1 data gathering) per master plan §4 Phase 5/6 parallel design; gotcha #18 file-scope disjointness holds (Phase 6 owns `app/templates/* + app/static/* + app/providers/view_models.py + app/providers/queries.py + app/api/routes/category_pages.py + tests/test_phase6_*.py`; Phase 5 owns `app/contrib/* + scripts/* + app/db/*`). Phase 6 builds against the schema (Phase 1+3 SHIPPED), Phase 5 fills against the schema — Phase 6.2+ category landing pages render empty-state copy until Phase 5 data lands.
```

---

## §3 STATE.md "Recently shipped" prepend (new high-signal entry)

**Paste destination:** `docs/STATE.md`, immediately after line 146 `## Recently shipped (high signal)` heading (PREPEND as the first entry):

```markdown
### Phase 6.1 — Unified Hava card grammar (2026-05-XX, commit `<<<PHASE_6_1_SHA>>>`)

**Why this matters:** The unified Hava card grammar is the **critical first deliverable** of Phase 6 per Opus design §6.1 + master plan §4 Phase 6 — a single Jinja partial that renders ANY entity (commercial / place / event) in ANY context (category page / search results / group landing / profile reference) with the same shell. Place vs event vs commercial differentiation via status-line color + content, NOT via separate templates. This grammar is the foundation Phase 6.2-6.5 compose into category pages, map markers, themed group landings, and profile reference cards. Getting it right at 6.1 means each subsequent sub-phase reuses without re-engineering the rendering surface.

**Ship surface (Cursor §4 file list):**
- New `app/templates/components/hava_card.html` (~<<<HAVA_CARD_HTML_LINES>>> lines): hero image + sponsor pill overlay + title + color-coded status line + category chip + district chip + heat_exposure pill + boat_access badge + freshness band dot. Empty-slot graceful degradation throughout (missing hero → category-themed placeholder; missing district → omit chip cleanly).
- Append to `app/providers/view_models.py`: new `@dataclass(frozen=True) class HavaCardViewModel` (~<<<VIEW_MODEL_LINES>>> lines) mirroring `ProviderProfileVM` pattern. Fields: entity_id, entity_type, name, profile_url, hero_photo_url, category_slug, category_label, district_slug, district_name, status_line_text, status_line_color, freshness_band, freshness_copy, is_sponsored, boat_access_badge, heat_exposure_pill.
- Append to `app/providers/queries.py`: new `build_card_view_model(db, entity_id) -> HavaCardViewModel` helper (~<<<BUILD_HELPER_LINES>>> lines). Joins Entity + Location + Photo (latest is_hero=True status='live') + Category + District + Source. Reuses existing `derive_hero_photo` + `derive_freshness` + `category_label_for` + `is_open_now` + `effective_hours_structured` helpers — no parallel logic, no new helpers.
- New `app/static/styles/components/hava_card.css` (~<<<CSS_LINES>>> lines): mobile-first base styles + media query >=768px; color variables for status_line_color states + freshness_band dot colors; sponsor pill styling per prereq §3.b (subtle pill + same shell).
- New `tests/test_phase6_hava_card.py` (~<<<TEST_FILE_LINES>>> lines): <<<PYTEST_DELTA>>> net-new tests across HavaCardViewModel dataclass construction + build_card_view_model from fixture data + status_line_text computation (commercial open/closed/freshness, place open/seasonal, event today/weekend/last-week) + status_line_color branches per entity_type + freshness_band threshold logic + is_sponsored render + heat_exposure_pill render rules + boat_access_badge render rules + 4-context template render smoke + mobile breakpoint CSS + empty-slot graceful degradation.

**Deviations from brief §3.1 (Cursor §11):** <<<DEVIATIONS_NARRATIVE>>>. All within brief §3.1 invited-deviation list; operator-confirmed at commit time. <<<DEVIATION_NOTES_IF_ANY>>>

**Pytest:** 1803 → <<<NEW_PYTEST_COUNT>>> (+<<<PYTEST_DELTA>>> net-new). Alembic head unchanged at `0a1b2c3d4e5f`. Ruff clean.

**No production runtime impact** until next deploy; once deployed, the card grammar renders against existing Phase 1+3 schema (no new columns, no new tables, no migration).

**HALT at brief §3.1 boundary** per dispatch instructions. Phase 6.2 (first category landing page template + Eat & Drink proof) dispatches in a fresh Cursor session against the pre-positioned dispatch prompt at `outputs/cursor_dispatch_prompt_phase_6_2.md` — single SHA-patch slot at `<<<PHASE_6_1_SHA>>>` patched in 3 sites before paste.

**Parallel-execution status:** Phase 5 chat is running in its own Cowork lane (`outputs/cursor_brief_phase_5_tier_1_data.md`) — Phase 5 operator-driven data gathering can ship Tier 1 categories into the schema at its own pace; Phase 6.2+ category landing pages render empty-state copy ("more coming soon") until Phase 5 data lands. File-scope disjoint per gotcha #18 (Phase 6 owns templates + view models + queries + category routes; Phase 5 owns contrib + scripts + db).

Cursor session, single dispatch.
```

---

## §4 §13 Review Rubric — Phase 6.1 acceptance gate checklist

**When Cursor returns with §13 close-out report, walk through this checklist BEFORE recommending the commit batch.** Each line tied to brief §3.1 acceptance gates + brief §4-5 design rails. Mark ✓ / ⚠ / ✗ per item.

### Cursor §0 baseline values reported

- [ ] HEAD SHA reported matches origin/main pre-dispatch (`0331102` or whatever the operator's local HEAD was at paste time)
- [ ] Pytest collection floor: 1803 collected (the baseline floor)
- [ ] Alembic head: `0a1b2c3d4e5f` (unchanged from Phase 4.1)
- [ ] No Phase 5 chat scope overlap reported (gotcha #18 holds)

### Brief §3.1 deliverable surface (Cursor §4 file list)

- [ ] `app/templates/components/hava_card.html` exists (new file)
- [ ] `app/providers/view_models.py` has new `HavaCardViewModel` dataclass appended (anchored edit, not full rewrite)
- [ ] `app/providers/queries.py` has new `build_card_view_model` helper appended (anchored edit)
- [ ] `app/static/styles/components/hava_card.css` exists (or alternative location per deviation #2 — flag if flat-file path chosen)
- [ ] `tests/test_phase6_hava_card.py` exists (or test_provider_profile.py augmented per deviation #3 — flag which)
- [ ] **No other files modified** outside Phase 6.1 scope. If anything else changed (e.g., `app/templates/home.html`, `app/db/models.py`, `app/api/routes/*` that isn't category_pages.py) — surface and discuss.

### Brief §3.1 acceptance gates (Cursor §5 + §10 confirmation)

- [ ] Template renders cleanly in isolation (Jinja `{% include %}` from a test template works without errors)
- [ ] 10-15 net-new tests in tests/test_phase6_hava_card.py
- [ ] Ruff clean (Cursor confirms; operator independently runs `ruff check .` post-commit per session-23 lesson — feat commit must not falsely claim ruff clean)
- [ ] Pytest stays green: 1803 collection floor + 10-15 net-new = 1813-1818 collected; passed count consistent
- [ ] Mobile rendering deferred-to-operator (manual smoke after ship: render at 320px / 375px / 768px via browser DevTools)

### Brief §3.1 invited deviations (Cursor §11 — expected categories)

- [ ] **ViewModel placement**: brief recommended `app/providers/view_models.py`; alternative `app/components/view_models.py` acceptable. Confirm placement.
- [ ] **CSS file location**: brief recommended `app/static/styles/components/hava_card.css`; alternative flat-file acceptable. Confirm choice.
- [ ] **Test file**: brief recommended `tests/test_phase6_hava_card.py`; alternative augment of `tests/test_provider_profile.py` acceptable. Confirm choice.
- [ ] **Freshness anchor**: brief locked `entities.updated_at`; alternative `entities.last_verified_at` acceptable (and is what the existing `derive_freshness()` helper uses — **strongly expect Cursor to flag this and propose reusing derive_freshness directly**). If switched: confirm rationale + that the band labels match (existing helper uses `fresh / acceptable / aging / stale / none`; prereq §3.i said `green / amber / red`; **acceptable map: fresh→green, acceptable→amber, aging+stale→red, none→neutral/no-dot**).
- [ ] **Sponsor pill rendering**: brief locked "subtle pill" per prereq §3.b; flag in §13 if visual hierarchy or color-contrast accessibility forced rework.

### Brief §4 + §5 "do not do" rails (Cursor must NOT have done)

- [ ] No category landing pages built (6.2 territory)
- [ ] No map view (6.4 territory)
- [ ] No boat-mode toggle (6.4 territory)
- [ ] No homepage rebuild (6.5 territory)
- [ ] No profile extension (6.5 territory)
- [ ] No new schema migrations (alembic head unchanged at `0a1b2c3d4e5f`)
- [ ] No changes to `/api/search` response shape
- [ ] No frontend framework added (stays on Jinja2 + vanilla JS per prereq §4.5)
- [ ] No new Python dependencies in `pyproject.toml` / `requirements.txt`
- [ ] No bypass of Phase 1D dual-write (card reads via `queries.py` helpers)
- [ ] HALT'd at §3.1 boundary — did NOT proceed to §3.2

### Phase 5 parallel-chat coordination (gotcha #18)

- [ ] Phase 6.1 files all in declared Phase 6 scope: `app/templates/* + app/static/* + app/providers/view_models.py + app/providers/queries.py + tests/test_phase6_*.py`
- [ ] Zero overlap with Phase 5 scope: `app/contrib/* + scripts/* + app/db/*`
- [ ] If Phase 5 chat shipped a sub-phase during 6.1 in-flight, verify clean rebase

### Commit-batch recommendation (Rule 8)

Based on §13 review, expect a **single commit** with body shape:

```
feat(phase6.1): unified Hava card grammar -- single Jinja partial renders any ENTITY in any context

New app/templates/components/hava_card.html (~XXX lines) + new HavaCardViewModel dataclass appended to app/providers/view_models.py + new build_card_view_model helper appended to app/providers/queries.py + new app/static/styles/components/hava_card.css (~XXX lines) + new tests/test_phase6_hava_card.py with XX net-new tests. <<<PYTEST_DELTA>>> tests added: 1803 -> <<<NEW_PYTEST_COUNT>>>. Alembic head unchanged at 0a1b2c3d4e5f (Phase 6 ships no migrations). Ruff clean.

Deviations flagged in Cursor §11: <<<DEVIATIONS_NARRATIVE>>>. All within brief §3.1 invited-deviation list.

HALT at brief §3.1 boundary; Phase 6.2 (first category landing + Eat & Drink proof) dispatches in fresh Cursor session against outputs/cursor_dispatch_prompt_phase_6_2.md (SHA-patch slot fills with this commit's SHA before paste).
```

**Commit message PowerShell-safe pattern** (gotcha #16 — no embedded double-quotes inside `-m '...'` bodies). Use single-quoted outer + plain text inner. If brief details require nested quotes, use Unicode curly quotes (`'` `'`) or just rephrase.

After commit + push:
1. Patch `<<<PHASE_6_1_SHA>>>` into `outputs/cursor_dispatch_prompt_phase_6_2.md` (3 sites — preamble, dispatch body, pre-dispatch checklist)
2. Update `docs/maintainability/master_build_plan.md` §4 Phase 6 with the §1 ship-line above
3. Update `docs/STATE.md` Production block per §2 and prepend Recently-shipped entry per §3
4. Commit docs update separately (`docs: Phase 6.1 ship-line on master plan + STATE.md session-23-extension-3 refresh + Phase 6.2 dispatch prompt SHA-patch`)
5. Push
6. Dispatch Phase 6.2 in fresh Cursor session

---

*Authored at session-23-extension-3 (2026-05-13) pre-positioned during Phase 6.1 in-flight execution. Lives at `outputs/phase_6_1_close_out_artifacts.md`. Placeholder slots fill when Cursor returns with §13 close-out report.*
