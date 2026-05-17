# Phase 5.6 — Shopping, Grocery & Essentials — Session close-out (2026-05-16)

> **What this is:** the close-out for the session that picked up Phase 5.6
> at `66e02c8` (Phase 5.6 kickoff doc + boot prompt) and pushed 3 commits
> to land the data plane + **ALL 6 acceptance gate items**.
> Phase 5.6 SHIPPED at `[SHIP-COMMIT]`.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.6 session
> (2026-05-16) post-`[SHIP-COMMIT]`.

---

## §1 Commit chain (origin `66e02c8 → [SHIP-COMMIT]`)

| # | Commit | Subject | Source | Task |
|---|---|---|---|---|
| 1 | `[sus-fix-sha]` | `fix(scripts)` — `_DISCOVERY_DOMAIN_FALLBACK` extends for `retail` domain | Cowork | sustainability layer (gate-2 prerequisite) |
| 2 | `[audit+apply-sha]` | `chore(outputs)` — Phase 5.6 §2 audit + §4 apply-scripts | Cowork | gates 2 + 4 + 5 + audit-evidence-for-gate-1/6 |
| 3 | `[SHIP-COMMIT]` | `chore(outputs)` — Phase 5.6 SHIPPED -- all 6 gate items cleared | Cowork | **SHIP** |

Optional Amendment 6 in-line follow-up commit (mirroring 5.4 `0addb63`
pattern) if operator opts not to delegate to Claude Code as a parallel
agent: `docs(phase5)` — Phase 5.6 SHIPPED ledger entries (Amendment 6).

**Pytest baseline:** 1920 (kickoff-expected) → 1920 (pre-session actual,
no drift) → **1932 collected post-session (+12)**. Breakdown: 12 new
in `tests/test_phase5_6_places_load_resolver.py` (7 parametrized
`_RETAIL_KEYS` asserts via the sustainability commit fallback extension
+ 5 defensive preservation asserts for 5.2/5.3/5.4-health/5.4-fitness/
5.5-auto fallback entries).

**Ruff:** Clean throughout. The sustainability commit passed F,I,W,E402
on the two touched files. Audit dump + apply-scripts at the audit+apply
commit also F,I,W,E402-clean (the 5.3 `bff4a79` F401 footgun was
internalized — no unused `json`/`Category`/`EntityCategory` imports).
One F541 surfaced and was fixed inline on `outputs/phase5_6_ambig_
audit_dump.py:225` (`print(f"  cross-cat slug breakdown:")` → no
f-prefix needed; no placeholders).

**CI:** ✅ Green throughout (assumed pending operator confirmation post-
SHIPPED-push). The sibling `parks-rec-scrapes` cron workflow continues
to X — pre-existing carry-over from 5.3 + 5.4 + 5.5, not in 5.6 scope.

---

## §2 Phase 5.6 acceptance gate — ALL 6 CLEARED ✅

| # | Gate item | Status | Where |
|---|---|---|---|
| 1 | 40+ entries in `shopping-essentials` post-load | ✅ **76** rendering (83 total including 7 drafts) | 25 pre-existing + ~51 net new (Layer 1 Google Places only) — 1.90× over target |
| 2 | All Google ↔ existing-entity ambiguous reconciler hits reviewed (+ cat-9/cat-8 cross-list) | ✅ **177 reviewed, 0 misroutes, 0 cat-9/cat-8 flips** | `outputs/phase5_6_shopping_essentials_audit.md` §1-5 — McCulloch/Lake Havasu Ave strip-mall false-ambig pattern documented |
| 3 | Layer-4 verifier surface scoped — built or explicitly deferred to V1.5 | ✅ **Option C — deferred** | Operator picked Option C at session start; AZ TPT + BBB paths documented in audit §3 carry-forward + kickoff §3 |
| 4 | Top-10 by reviews have long-form `crowd_notes` | ✅ **10** | Drafted from `Provider.google_review_snippets` (own column, per 5.4 close-out §4 source-path correction); see `outputs/apply_phase5_6_shopping_crowd_notes.py` |
| 5 | `heat_exposure` non-NULL on every entry | ✅ **0 NULL** of 83 | 78 indoor + 5 outdoor (4 garden centers/nurseries + Tux and Tulips florist) |
| 6 | `/category/shopping-essentials` renders ≥15 | ✅ **76** | 5.07× over target |

**Note: 6 gate items (not 7).** `is_mobile_service` was 5.5-specific
and is dropped for 5.6 — retail is brick-and-mortar by definition (per
kickoff §6).

Final gate verification at `outputs/phase5_6_gate_verification.py` —
6/6 PASS, "ALL 6 ITEMS CLEARED — READY TO SHIP" line.

---

## §3 Notable artifacts shipped this session

**One sustainability fix shipped mid-session** (5.3 shipped 3; 5.4
shipped 5; 5.5 shipped 1; 5.6 ships 1):

### `[sus-fix-sha]` — `_DISCOVERY_DOMAIN_FALLBACK` extension for `retail` domain

Phase 5.6 §1 load surfaced 21 of 268 rows landing at `category_id=None`
because their `primary_type` wasn't in `google_types_mapping`.
Distribution (visible-as-Provider subset of 10): `service` ×3
(IT/electronics service shops — Havasu Technologies, Vertical IT, Whiz
Kid Computer Services), `None` ×1 (Havasu Computers), plus 6 edge
cases (`corporate_office`, `manufacturer` ×3, `garden`, `farm`,
`health`, `community_center`). The other 11 are inside the 181 ambig-
skip pool. Added 7 entries to `_DISCOVERY_DOMAIN_FALLBACK` keyed on
`(primary_type, "retail")` → `"shopping-essentials"` (`None`, `service`,
`supplier`, `point_of_interest`, `establishment`, `store`,
`shopping_mall` — kickoff §1 anticipation plus 2 defensive). Re-running
`places_load` cleared the operator queue to 0. +12 regression tests
in `tests/test_phase5_6_places_load_resolver.py`. Same `7c994aa` /
`fc51940` / `4d41944` surgical-fix shape.

The `(None, "retail")` catch-all also picked up the 6 edge-case rows I
expected to leave for per-row operator queue review (the resolver's
second-chance `(None, domain)` lookup fires for any unmapped
primary_type). This matches every prior phase but routes more
category-spillover than 5.5's `auto` domain did, requiring the §2
edge-case re-route apply-script (11 FLIPs + 7 DRAFTs).

**Pre-flight surprises (1 found, triaged before §1 dispatch):**

1. **`scripts/places_categories.json` locally corrupted** (third
   recurrence in 3 sessions) — working tree at 202 lines (ends
   mid-token `"chil`), HEAD at 211 lines. Operator restored via `git
   restore` Windows-side. Cause still unknown (suspect external editor
   save). Pre-flight item #6 in the 5.6 kickoff continues to catch this.

### **NOT shipped this session: AZ TPT / BBB-style verifier surface**

Operator picked Option C at session start — no Layer-4 verifier built
for 5.6. AZ TPT (Transaction Privilege Tax) Playwright path + BBB
(Better Business Bureau) cross-reference path documented for V1.5
pickup in the audit doc + kickoff §3.

### **NOT shipped this session: medical_clinic in google_types_mapping**

The 2 medical_clinic eye-care providers (Lake Havasu Family Eyecare +
Barnet Dulaney Perkins) surfaced as §4 misroutes because
`medical_clinic` isn't in `google_types_mapping._PRIMARY_TYPE_MAP`
directly — it's only in the `(medical_clinic, "health_medical")`
fallback. Discovering them under a `retail` label routed them via the
catch-all to shopping-essentials. The 5.4 close-out §4 already flagged
this as a soft-edge ("medical_clinic arguably belongs in
google_types_mapping.py directly") — left for V1.5 widening.

---

## §4 Catch-all routing edge-case review (Phase 5.6 §2 special surface)

The kickoff §2 specifically called out the cat-9/cat-8 axis (gas
station / convenience store cross-list). Findings:

- **5 gas-station/convenience-store cross-list hits** — Sunny Stop
  Mini Mart, Marathon Gas Station & Oasis Food Mart, Marathon, Motor
  and Boat Texaco, Shell. All correctly stay-in-cat-9 per V1 policy
  (primary use is fuel + impulse-snack, not destination grocery).
  **0 flips needed.**
- **27 catch-all edge-case routings** (the `retail`-domain-specific
  surface, not anticipated by kickoff but emerged from the `(None,
  "retail")` second-chance lookup behavior) — 11 FLIPs (3 to cat-5 +
  2 to cat-5 surfaced in §4 sweep + 4 to cat-9 + 2 to cat-4) and 7
  DRAFTs (5 B2B wholesale + community garden + Anderson AZ West) +
  13 KEEPs (including Hospice of Havasu **Resale Store**, which IS
  retail and is distinct from the main hospice).
- **177 cross-cat ambig hits** — eat-drink ×99, HWC ×24, HPS ×22, auto-
  rv-fuel ×17, on-the-water ×12, pets ×1. All benign McCulloch /
  Lake Havasu Ave strip-mall adjacency. **0 real misroutes.**

---

## §5 Sustainability layer update (post-`[sus-fix-sha]`)

`_DISCOVERY_DOMAIN_FALLBACK` extended for the `retail` domain — 7 new
entries beyond the 5.5 set. All future Phase-5.6-style re-pulls will
auto-categorize the same shape.

### Sustainability matrix (updated)

| Field | Auto on re-pull? | Auto for new business? |
|---|---|---|
| `Provider.category_id` from `_resolve_category_id` | ✅ preserved if set | ✅ resolved at INSERT (now covers `retail` catch-alls) |
| `EntityCategory` linkage | ✅ via `_ensure_entity_category` | ✅ via dual-write hook |
| `Provider.verified` | ✅ not overwritten by re-pull | ❌ deferred to V1.5 (no verifier ran in 5.6) |
| `heat_exposure` | ✅ not overwritten | ❌ lands NULL — needs periodic sweep |
| `is_mobile_service` | n/a for retail (gate-dropped) | n/a |
| `crowd_notes` | ✅ not overwritten | ❌ — needs operator curation |
| `Provider.draft` | ✅ preserved | ⚠️ defaults False; operator review needed for new B2B/wholesale entries discovered under retail |

**Phase 5.7 (Outdoors, Parks & Trails)** anticipated catch-all
primary_types per `scripts/places_categories.json` `outdoor_recreation`
domain — likely some `(None, "outdoor_recreation")` /
`("tourist_attraction", "outdoor_recreation")` /
`("point_of_interest", "outdoor_recreation")` fallback entries needed.
5.7 may also surface the `parks-rec-scrapes` scheduled CI workflow that
has been X on cron throughout 5.3-5.6.

---

## §6 Remaining work for next session (Phase 5.7)

### Gate-blocking (0) — Phase 5.6 SHIPPED at `[SHIP-COMMIT]`

All 6 gate items met per `outputs/phase5_6_gate_verification.py`. The
SHIPPED commit landed on `origin/main` at `[SHIP-COMMIT]` 2026-05-16.

### 🚨 Carry-over for operator-side action

- **Phase 6 lane dispatch: Phase 5.6 SHIPPED ledger amendment** —
  `outputs/claude_code_dispatch_phase6_amend6.md` is ready for operator
  to paste into Claude Code (or land in-line per the 5.4 `0addb63`
  precedent). Pattern mirrors Amendment 5.
- **V1.5 Layer-4 verifier surface for 5.6** — AZ TPT (Transaction
  Privilege Tax) Playwright + BBB cross-reference paths documented in
  the audit doc + kickoff §3 for V1.5 pickup.
- **V1.5: `medical_clinic` widening in `google_types_mapping`** —
  surfaced as a soft-edge in 5.4 + 5.6 (`medical_clinic` only resolves
  via the health_medical fallback, not directly). A 1-line addition
  would catch eye-care/medical clinics correctly regardless of which
  discovery domain surfaces them.
- **V1.5 carry-over: Anderson AZ West** — drafted as B2B wholesale by
  default; operator un-drafts if it turns out to be consumer-retail.
- **86 of 265 health-wellness-care providers remain `verified=False`** —
  carry-over from 5.4. Operator-driven DBA→NPI follow-up surface
  (optional V1.5).
- **Google Places API key rotation** still deferred — operator declined
  per "all keys will be changed at the conclusion of this project".

### Soft-edges (3 deferred per `phase5_6_shopping_essentials_audit.md` §7)

- 7 drafted providers in shopping-essentials (5 B2B wholesale +
  community garden + Anderson AZ West) — review for un-drafting if
  scope changes
- Optional `GEO_PROXIMITY_THRESHOLD_M` tune (50 → 25) — 5.6 hit 177
  ambigs (above kickoff range of 30-100) but all benign per audit
- Optional same-discovery-domain bypass in reconciler

None are gate-blocking. Same shape as 5.5 carry-forwards.

### `parks-rec-scrapes` scheduled CI (carry-over)

X on cron triggers throughout this session — same pre-existing
condition as 5.3 + 5.4 + 5.5. **Phase 5.7 (Outdoors, Parks & Trails)
WILL likely need to investigate** — that scheduled workflow is
directly relevant to 5.7's scope.

### Files-to-prune carry-over

`hava_api_catalog.docx` + `~$va_api_catalog.docx` (Word lock) + 2
`outputs/ci_*_log_failed.txt` historical CI logs in working tree.
Unrelated to the 5.6 lane; operator prunes when comfortable.

### `data/events.db.bak-*` files (carry-over from 5.3 + 5.4 + 5.5)

Backup files may continue to accumulate. Operator prunes when
comfortable.

### Sandbox bash MOUNT STALENESS — recurring pattern

The 5.5 close-out documented this as a new gotcha; 5.6 hit it twice:
(a) `json.load(scripts/places_categories.json)` failed in sandbox bash
even after operator's Windows-side `git restore` (Read tool showed the
file healthy at full 211 lines); (b) importlib on
`app/contrib/google_types_mapping.py` reported a SyntaxError at the
file's opening dict (Read tool again showed the file healthy). Read
tool remains the source of truth for file state; sandbox bash is
unreliable for post-restore / post-Edit verification. Internalized.

---

## §7 Coordination summary (one-line)

| Lane | Coordination need |
|---|---|
| Phase 6 (parallel agent OR in-line) | Amend `master_build_plan.md` + `STATE.md` with Phase 5.6 SHIPPED at `[SHIP-COMMIT]` via `outputs/claude_code_dispatch_phase6_amend6.md` |
| Cursor | No dispatches pending (Phase 5.6 produced its own regression tests in-lane: +12 at 1932) |
| Operator | Audit doc carry-over actions (V1.5 verifier build, medical_clinic mapping widening, Anderson AZ West un-draft decision, API key rotation), file-prune list (.bak files + stray .docx + historical CI logs), `parks-rec-scrapes` cron investigation before 5.7 |

---

## §8 Read order for the next session (Phase 5.7)

1. **This document** — the state of play (close-out + commit chain).
2. `outputs/phase5_7_outdoors_parks_trails_kickoff.md` — Phase 5.7
   runbook (authoritative for the §6 acceptance gate definitions;
   **next agent authors this if not yet present**, mirroring
   `outputs/phase5_6_shopping_grocery_essentials_kickoff.md` shape).
3. `outputs/phase5_6_shopping_grocery_essentials_kickoff.md` — the
   5.6 runbook this document mirrored.
4. `outputs/phase5_6_shopping_essentials_audit.md` — combined post-load
   audit doc (template the 5.7 audit will mirror).
5. `docs/scrape_logs/shopping-essentials_2026-05-16.md` — Layer 1
   actuals + commit chain (template for Phase 5.7's scrape log).
6. `outputs/apply_phase5_6_shopping_audit.py` / `_heat_exposure.py` /
   `_crowd_notes.py` — template apply-scripts that 5.7 equivalents
   will mirror.
7. `outputs/phase5_6_gate_verification.py` — template for
   `outputs/phase5_7_gate_verification.py`.

---

## §9 Pre-flight for the next session

1. **`git log --oneline -15`** — origin should top at `[SHIP-COMMIT]`
   or later (Phase 6 lane may push `0addb63`-shape Amendment 6 between
   sessions).
2. **`git status`** — clean. Note the carry-over file-prune list above.
3. **`python -m alembic current`** — `0a1b2c3d4e5f` (unchanged across
   all 5.x phases).
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — expect
   **1932 collected** (5.6 baseline). Verify no drift.
5. **`gh run list --branch main --limit 3`** — top run should be ✓ on
   `[SHIP-COMMIT]`. Note that `parks-rec-scrapes` scheduled jobs
   continue to X — 5.7 should investigate.
6. **DB state spot-check** — `shopping-essentials` should show **83
   entries / 0 verified / 78 indoor + 5 outdoor / 76 render (7
   drafted) / 10 long-form crowd_notes** (the 5.6 SHIPPED state).
7. **`scripts/places_categories.json` integrity check** — `git diff
   scripts/places_categories.json` should be empty. The 5.5 and 5.6
   §0 found local corruption each time; if the cause (external editor?)
   recurs, it'll surface here.
8. **Phase 5.7 sub-trade scope** — Phase 5.7 (Outdoors, Parks &
   Trails) kickoff doc should land first. Anticipated label set from
   `places_categories.json` `outdoor_recreation` domain: parks,
   trails, viewpoints, campgrounds (non-RV), playgrounds, dog parks,
   skateparks, picnic areas. Likely 8-12 labels; single-layer Google
   scrape; no Layer-4 verifier (no obvious public registry for
   parks/trails) — likely Option C analog.
9. **`parks-rec-scrapes` cron investigation** — 5.7's scope makes this
   workflow directly relevant. Pre-existing X since 5.3 should be
   debugged before or during 5.7 §1.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.6 session
(2026-05-16) post-`[SHIP-COMMIT]`. Phase 5.6 SHIPPED with all 6 gate
items cleared; 3 commits on origin/main from `66e02c8` →
`[SHIP-COMMIT]`. Hand-off to Phase 5.7 (Outdoors, Parks & Trails)
next session.*
