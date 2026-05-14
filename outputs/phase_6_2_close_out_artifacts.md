# Phase 6.2 Close-out Artifacts (pre-positioned)

> Pre-positioned during Phase 6.1 in-flight execution at session-23-extension-3 (2026-05-13). When Cursor returns with the Phase 6.2 §13 close-out report, fill the placeholder slots and paste each section into the indicated destination. Same template shape as `outputs/phase_6_1_close_out_artifacts.md`.
>
> **Why pre-position 6.2 close-out before 6.2 even dispatches:** the template shape is stable across all 5 sub-phases; only the per-sub-phase content slots differ. Filling slots after Cursor returns is ~10 min vs ~30-60 min authoring from scratch.
>
> **Sources:**
> - Brief §3.2 acceptance gates (`outputs/cursor_brief_phase_6_tier_1_ui.md`)
> - Phase 6.1 close-out template (`outputs/phase_6_1_close_out_artifacts.md`)
> - STATE.md / master plan pattern from prior phases

---

## §1 Master plan §4 Phase 6 ship-line (append under existing Shipped subsection)

**Paste destination:** `docs/maintainability/master_build_plan.md` §4 Phase 6, append after the Phase 6.1 entry under `**Shipped (incremental):**`:

```markdown
- **Phase 6.2 — First category landing page template + Eat & Drink proof (2026-05-XX, commit `<<<PHASE_6_2_SHA>>>`):** Second sub-phase of Phase 6 shipped. The first Tier 1 category landing template + the Eat & Drink page as the proof; 6.3 reuses the template for the remaining 5 categories. New `app/api/routes/category_pages.py` (~<<<ROUTE_LINES>>> lines) ships `GET /category/<slug>` for the 6 Tier 1 slugs (validation + 404 on unknown + dispatch to category-specific chip dispatcher); router mounted in `app/main.py` (anchored edit, +1 import + 1 include_router line). New `app/templates/category_landing.html` (~<<<TEMPLATE_LINES>>> lines) ships the page shell: compact sub-hero (search + title + description) + 3-row chip filter (cuisine / district / operational) + sort dropdown + sponsor slot (empty render in 6.2; no paying sponsors) + organic stream (`{% for vm in organic_stream %}{% include 'components/hava_card.html' with vm %}{% endfor %}` -- consumes 6.1's HavaCardViewModel) + map view toggle stub + editorial footer + empty-state copy when <15 entries ("more <category> coming soon"). New `app/static/styles/category_landing.css` (~<<<CSS_LINES>>> lines, mobile-first base + media query >=768px; chip styling matches existing home.css `.chip` pattern with active-state). New `app/static/js/category_filters.js` (~<<<JS_LINES>>> lines vanilla JS per prereq §4.5 lock; chip click toggles active state + updates URL query params + triggers <<<RELOAD_OR_XHR>>>). **<<<PYTEST_DELTA>>> net-new tests** in `tests/test_phase6_category_landing.py` covering: GET /category/eat-drink 200 OK with fixture; GET /category/<unknown> 404; all 6 Tier 1 slugs render 200 (smoke for 6.3 reuse); chip filter URL param parsing (cuisine + district + operational); sort dropdown URL param; empty-state copy; sponsor slot empty-render; editorial footer; mobile breakpoint smoke. Pytest **<<<PRE_PYTEST_COUNT>>> → <<<NEW_PYTEST_COUNT>>>** (+<<<PYTEST_DELTA>>> net-new). Alembic head unchanged at `0a1b2c3d4e5f`. Ruff clean. **<<<N_DEVIATIONS>>> brief §3.2-invited deviations:** <<<DEVIATIONS_NARRATIVE>>>. **No production runtime impact** until next deploy; once deployed, `/category/eat-drink` renders against current Phase 5 data (empty-state copy if data thin). HALT at brief §3.2 boundary per dispatch instructions; Phase 6.3 (remaining 5 category pages + district context + ranking + seasonal hours) dispatches in a fresh Cursor session against the pre-positioned dispatch prompt at `outputs/cursor_dispatch_prompt_phase_6_3.md` (TWO SHA-patch slots: 6.1 SHA + 6.2 SHA = `<<<PHASE_6_2_SHA>>>`; patched into 3 sites each before paste). Cursor session, single dispatch (or two if chip dispatcher splits).
```

**Placeholder slots to fill:**

| Slot | Source |
|---|---|
| `<<<PHASE_6_2_SHA>>>` | Operator commit SHA after committing Cursor's §13 batch |
| `<<<ROUTE_LINES>>>` | Cursor's §4 — line count of new category_pages.py |
| `<<<TEMPLATE_LINES>>>` | Cursor's §4 — line count of new category_landing.html |
| `<<<CSS_LINES>>>` | Cursor's §4 — line count of new category_landing.css |
| `<<<JS_LINES>>>` | Cursor's §4 — line count of new category_filters.js |
| `<<<RELOAD_OR_XHR>>>` | Cursor's deviation choice in §11 — full-page reload OR XHR + DOM replace |
| `<<<PYTEST_DELTA>>>` | Cursor's §10 — net-new test count (expected 10-15) |
| `<<<PRE_PYTEST_COUNT>>>` | Post-6.1 baseline (1803 + 6.1 delta) |
| `<<<NEW_PYTEST_COUNT>>>` | Pre count + delta |
| `<<<N_DEVIATIONS>>>` | Count of §11 deviations (expected 1-3) |
| `<<<DEVIATIONS_NARRATIVE>>>` | One-sentence summary of each deviation Cursor flagged |

---

## §2 STATE.md Production block updates

**Paste destination:** `docs/STATE.md`, edit existing Production block bullets.

**Bullet 1 — Current main HEAD:**
- **Update SHA** to `<<<PHASE_6_2_SHA>>>`
- **Update description** to "(2026-05-XX, Phase 6.2 first category landing template + Eat & Drink proof on origin/main). Phase 6 lane in flight — 3 more sub-phases (6.3 remaining 5 categories + district + ranking + seasonal hours → 6.4 map + boat-mode + themed groups → 6.5 homepage + profile extension + mobile polish) to reach Phase 6 SHIPPED."

**Bullet 4 — Build phase:**
- **Append:** ` **Phase 6.2 SHIPPED on origin 2026-05-XX (commit `<<<PHASE_6_2_SHA>>>`); first Tier 1 category landing template + Eat & Drink as the proof. 6.3 dispatch prompt pre-positioned at `outputs/cursor_dispatch_prompt_phase_6_3.md` with two SHA-patch slots (6.1 + 6.2) — patch + dispatch when 6.2 §13 review closes.**`

**Bullet 5 — Pytest:**
- **Update count** to `<<<NEW_PYTEST_COUNT>>> collected (<<<NEW_PYTEST_PASSED>>> passed + 2 skipped + 30 subtests)`
- **Append narrative:** "(post-Phase-6.1 baseline `<<<POST_6_1_COUNT>>>`; post-Phase-6.2 baseline `<<<NEW_PYTEST_COUNT>>>`; **+<<<PYTEST_DELTA>>> net-new** in `tests/test_phase6_category_landing.py` covering /category/eat-drink rendering + chip filter URL params + sort dropdown + empty-state copy + mobile breakpoint smoke). The 2 skipped unchanged. Full-suite run 2026-05-XX on Windows venv ~<<<MINUTES>>>m; **ruff clean**."

**Bullet 6 — Alembic head:**
- No change. Head stays at `0a1b2c3d4e5f` (Phase 6 ships no migrations).

**Phase 6 lane status bullet (added in 6.1 close-out; UPDATE inline):**
- **Old (post-6.1):** "Phase 6.1 unified Hava card grammar SHIPPED 2026-05-XX at `<<<PHASE_6_1_SHA>>>`..."
- **New (post-6.2):** "Phase 6.1 + 6.2 SHIPPED 2026-05-XX at `<<<PHASE_6_1_SHA>>>` + `<<<PHASE_6_2_SHA>>>` — unified Hava card grammar + first category landing template + Eat & Drink proof. Remaining sub-phases: 6.3 dispatch prompt pre-positioned at `outputs/cursor_dispatch_prompt_phase_6_3.md`. Phase 6 runs in PARALLEL with Phase 5 (Tier 1 data gathering)..."

---

## §3 STATE.md "Recently shipped" prepend (new high-signal entry)

**Paste destination:** `docs/STATE.md`, immediately after the Phase 6.1 entry (which was prepended in 6.1 close-out). PREPEND this new entry above 6.1:

```markdown
### Phase 6.2 — First category landing page template + Eat & Drink proof (2026-05-XX, commit `<<<PHASE_6_2_SHA>>>`)

**Why this matters:** First Tier 1 category landing page goes live. Eat & Drink is the proof case (highest data density per Phase 5 §3.1 — warm-up category). The template shipped here is reused in 6.3 for the remaining 5 Tier 1 categories — getting it right at 6.2 means 6.3 is template-fill rather than re-engineering.

**Ship surface (Cursor §4 file list):**
- New `app/api/routes/category_pages.py` (~<<<ROUTE_LINES>>> lines): `GET /category/<slug>` route + 6-Tier-1-slug validation + per-category chip dispatcher (6.2 ships Eat & Drink dispatcher; 6.3 adds remaining 5). Wired into `app/main.py` via anchored edit (+1 import + 1 include_router).
- New `app/templates/category_landing.html` (~<<<TEMPLATE_LINES>>> lines): page shell consumed by all 6 Tier 1 slugs. Sub-hero + 3-row chip filter + sort dropdown + sponsor slot + organic stream (consumes 6.1's `components/hava_card.html` partial) + map toggle stub + editorial footer + empty-state copy.
- New `app/static/styles/category_landing.css` (~<<<CSS_LINES>>> lines): mobile-first chip styling + sub-hero compact variant + responsive layout.
- New `app/static/js/category_filters.js` (~<<<JS_LINES>>> lines vanilla JS): chip click → URL param update → <<<RELOAD_OR_XHR>>>. Matches Phase 2B.3 `app/static/js/search.js` pattern.
- New `tests/test_phase6_category_landing.py` (~<<<TEST_FILE_LINES>>> lines): <<<PYTEST_DELTA>>> net-new tests across route rendering + chip filter URL param parsing + sort dropdown + 6-slug smoke + empty-state copy + mobile breakpoint.

**Deviations from brief §3.2 (Cursor §11):** <<<DEVIATIONS_NARRATIVE>>>. <<<DEVIATION_NOTES_IF_ANY>>>

**Pytest:** <<<PRE_PYTEST_COUNT>>> → <<<NEW_PYTEST_COUNT>>> (+<<<PYTEST_DELTA>>> net-new). Alembic head unchanged at `0a1b2c3d4e5f`. Ruff clean.

**No production runtime impact** until next deploy; once deployed, `/category/eat-drink` renders against current Phase 5 data. Empty-state copy fires when fewer than 15 entries match. The other 5 Tier 1 slugs would 404 until 6.3 ships their dispatchers.

**HALT at brief §3.2 boundary** per dispatch instructions. Phase 6.3 (remaining 5 category pages + district context + ranking + seasonal hours) dispatches in a fresh Cursor session against the pre-positioned dispatch prompt at `outputs/cursor_dispatch_prompt_phase_6_3.md` — TWO SHA-patch slots (6.1 SHA + 6.2 SHA = `<<<PHASE_6_2_SHA>>>`) patched into 3 sites each before paste.

**Parallel-execution status:** Phase 5 chat continues in its own Cowork lane. File-scope disjoint per gotcha #18 (Phase 6 owns templates + category routes + static; Phase 5 owns contrib + scripts + db).

Cursor session, single dispatch.
```

---

## §4 §13 Review Rubric — Phase 6.2 acceptance gate checklist

**When Cursor returns with §13 close-out report, walk through this checklist BEFORE recommending the commit batch.**

### Cursor §0 baseline values reported

- [ ] HEAD SHA matches `<<<PHASE_6_1_SHA>>>` (post-6.1 origin tip)
- [ ] Pytest collection floor: post-6.1 baseline (1803 + 6.1 delta)
- [ ] Alembic head: `0a1b2c3d4e5f` (unchanged through 6.1)
- [ ] No Phase 5 chat scope overlap reported

### Brief §3.2 deliverable surface (Cursor §4 file list)

- [ ] `app/api/routes/category_pages.py` exists (new file)
- [ ] `app/templates/category_landing.html` exists (new file)
- [ ] `app/static/styles/category_landing.css` exists (new file)
- [ ] `app/static/js/category_filters.js` exists (new file)
- [ ] `tests/test_phase6_category_landing.py` exists (new file)
- [ ] `app/main.py` modified (anchored edit — `category_pages_router` import + `include_router` line; check line delta is ~2-3 lines)
- [ ] No other files modified outside 6.2 scope. If `app/providers/queries.py` modified (e.g., for chip aggregation helper) — verify deviation flagged in §11.
- [ ] **6.1 deliverables UNCHANGED**: `app/templates/components/hava_card.html` + `HavaCardViewModel` + `build_card_view_model` + `app/static/styles/components/hava_card.css` should NOT appear in 6.2's file-change list. If any of them are touched, surface and discuss (probably wrong).

### Brief §3.2 acceptance gates (Cursor §5 + §10)

- [ ] `/category/eat-drink` renders 200 OK with mock fixtures
- [ ] `/category/<unknown-slug>` returns 404
- [ ] All 6 Tier 1 slugs render 200 OK (template smoke for 6.3 reuse)
- [ ] Chip filtering works (URL param parsing + filtered stream)
- [ ] Sort dropdown works (URL param flips sort order)
- [ ] Mobile responsive smoke at 320px / 768px / 1024px+ (CSS rule introspection OR responsive HTML output)
- [ ] 10-15 net-new tests
- [ ] Ruff clean (Cursor confirms; operator runs `ruff check .` independently post-commit)
- [ ] Pytest stays green: pre-6.2 count + 10-15 net-new

### Brief §3.2 invited deviations (Cursor §11)

- [ ] **Server-side rendering vs hydration**: brief assumed server-side Jinja + vanilla JS for chips; alternative XHR + DOM replace acceptable. Confirm choice + rationale.
- [ ] **Editorial footer source**: brief assumed hardcoded constant; alternative `category_editorial.json` operator-maintainable file acceptable. Confirm choice.
- [ ] **Route module placement**: brief suggested new `app/api/routes/category_pages.py`; alternative extension of `app/home/routes.py` acceptable. Confirm choice.
- [ ] **Topbar reuse pattern**: brief assumed copy-paste from home.html; alternative shared partial (`_topbar.html` + `_directory_search.html` includes) cleaner. Confirm.
- [ ] **Chip data source**: brief assumed hardcoded sub-trade lists per category; alternative DB aggregation (Provider.attributes.sub_trades) acceptable. Confirm.
- [ ] **Ranking math placement**: brief locked Phase 6.3; if Cursor shipped ranking math in 6.2 as a bonus, that's a deviation worth flagging — verify it doesn't bleed into 6.3 scope.

### Brief §4 + §5 "do not do" rails

- [ ] No other category pages built (just Eat & Drink for proof)
- [ ] No map view (6.4 territory; map view toggle is STUB in 6.2)
- [ ] No boat-mode toggle (6.4)
- [ ] No homepage rebuild (6.5)
- [ ] No profile extension (6.5)
- [ ] No district context paragraph (V1.5)
- [ ] No seasonal hours rendering (6.3)
- [ ] No new schema migrations (alembic head unchanged)
- [ ] No `/api/search` shape change
- [ ] No frontend framework (Jinja2 + vanilla JS per prereq §4.5)
- [ ] No new Python dependencies
- [ ] HALT'd at §3.2 boundary

### Phase 5 parallel-chat coordination (gotcha #18)

- [ ] Phase 6.2 files in declared Phase 6 scope: `app/templates/* + app/static/* + app/api/routes/category_pages.py + app/main.py (router mount) + tests/test_phase6_*.py`
- [ ] Zero overlap with Phase 5: `app/contrib/* + scripts/* + app/db/*`

### Commit-batch recommendation (Rule 8)

Expected single commit with body shape:

```
feat(phase6.2): first category landing template + Eat & Drink proof

New app/api/routes/category_pages.py (GET /category/<slug>) + new app/templates/category_landing.html (page shell consumed by all 6 Tier 1 slugs in 6.3) + new app/static/styles/category_landing.css + new app/static/js/category_filters.js (vanilla JS chip-filter per prereq §4.5) + Eat & Drink dispatcher + 10-15 net-new tests in tests/test_phase6_category_landing.py. Phase 6.1 unified Hava card grammar consumed via {% include %} in organic_stream. <<<PYTEST_DELTA>>> tests added: pre-count -> <<<NEW_PYTEST_COUNT>>>. Alembic head unchanged at 0a1b2c3d4e5f. Ruff clean.

Deviations flagged in Cursor §11: <<<DEVIATIONS_NARRATIVE>>>. All within brief §3.2 invited-deviation list.

HALT at brief §3.2 boundary; Phase 6.3 (remaining 5 categories + district + ranking + seasonal hours) dispatches in fresh Cursor session against outputs/cursor_dispatch_prompt_phase_6_3.md (two SHA-patch slots: 6.1 + 6.2).
```

Gotcha #16 — PowerShell-safe single-quoted `-m '...'` outer + no embedded double-quotes inner.

After commit + push:
1. Patch `<<<PHASE_6_2_SHA>>>` into `outputs/cursor_dispatch_prompt_phase_6_3.md` (3 sites for the 6.2 SHA + verify the 6.1 SHA is already patched from the post-6.1 docs commit)
2. Update master plan §4 Phase 6 with the §1 ship-line above
3. Update STATE.md per §2 + prepend Recently-shipped per §3
4. Commit docs update (`docs: Phase 6.2 ship-line on master plan + STATE.md session-23-extension-X refresh + Phase 6.3 dispatch prompt SHA-patch`)
5. Push
6. Dispatch Phase 6.3 in fresh Cursor session

---

*Authored at session-23-extension-3 (2026-05-13) pre-positioned during Phase 6.1 in-flight execution. Lives at `outputs/phase_6_2_close_out_artifacts.md`. Placeholder slots fill when Cursor returns with §13 close-out report for 6.2.*
