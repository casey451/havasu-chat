# Post-Phase-5.11 Next-Session Boot Prompt

> Drop-in artifact for the operator to paste into a fresh Cowork session
> after Phase 5.11 SHIPPED and Phase 5 is COMPLETE. This is a
> **branch-point** boot prompt -- no single "next sub-phase" pre-staged
> kickoff like 5.1-through-5.11 had, because Phase 5 (Tier 1 data
> gathering) is now done. The next Cowork lane picks ONE of three
> available work tracks per operator decision.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.11 session 1
> (2026-05-17) post-SHIP + SHA-cleanup + ruff-fix + framing-correction.
> Pastable as-is below the `---` line.

---

You're picking up the project after **Phase 5 (Tier 1 data gathering)
COMPLETED on 2026-05-17 at Phase 5.11 SHIP**. All 13 Tier-1 categories
are now populated. The Phase 5 multi-phase data-population lane is done;
the next major lane choice is yours per the 3 dispatchable tracks
below.

Working directory: `C:\Users\casey\projects\havasu-chat`.

---

## 1 Current state (as of 5.11 SHIP)

**Top of `origin/main`:** `54f17e6` (framing correction commit; Phase
6/7 hand-off corrected from earlier mis-framing as "V1 acceptance
gate (Phase 6)").

**5.11 lane chain on `origin/main`** (newest to oldest):

| Commit | What | CI |
|---|---|---|
| `54f17e6` | `docs(outputs)` framing correction (Phase 6/7) | green |
| `6adfc05` | `fix(outputs)` ruff I001 in crowd_notes (extra blank line) | green |
| `6b8ba50` | `docs(outputs)` SHA-cleanup (`<SHIP-COMMIT>` -> `dcf3dd4`) | red (forward-fixed by 6adfc05) |
| `dcf3dd4` | `chore(outputs)` Phase 5.11 SHIPPED -- all 6 gate items cleared | red (forward-fixed) |
| `1dd443a` | `fix(scripts)` Phase 5.11 sustainability layer (pet_care + (None,"pets") catch-all) | green |
| `3ecd8ed` | `docs(outputs)` Phase 5.11 boot prompt SHA-cleanup | green |
| `7472b4a` | `chore(outputs)` Phase 5.11 (pets) kickoff | red (transient) |
| `fa3b943` | `chore(outputs)` Phase 5.11 (pets) kickoff (initial) | red (transient) |
| `accc06d` | `docs(outputs)` Phase 5.10 SHA-cleanup | green |
| `592ee74` | `chore(outputs)` Phase 5.10 SHIPPED | green |
| ... | ... | ... |

Final tree-state CI green on `54f17e6` is the ship-readiness signal per
kickoff `0` step 8 ("Final tree-state CI green is the ship-readiness
signal"). 2 intermediate red CI runs on docs-only commits were
forward-fixed by `6adfc05` (a 1-line ruff I001 cleanup) and `54f17e6`
(the Phase 6/7 framing correction).

**Phase 5 final outcome -- all 13 Tier-1 categories populated:**

| cat | slug | entries | source |
|---|---|---|---|
| 1 | eat-drink | 255 | 5.1 |
| 2 | events | 20 | 5.8 |
| 3 (db id=6) | on-the-water | 119 | 5.2 |
| 4 | home-property-services | 237 | 5.3 |
| 5 | health-wellness-care | 272 | 5.4 |
| 7 | outdoors-parks-trails | 27 | 5.7 |
| 8 | shopping-essentials | 87 | 5.6 |
| 9 | auto-rv-fuel | 153 | 5.5 |
| 10 | lodging-vacation-rentals | 73 | 5.10 |
| **11** | **pets** | **38** | **5.11** |
| 12 | classes-sports-recreation | 31 | 5.9 |
| 13 | public-civic-resources | 4 | (pre-Phase-5) |

(Cat-3 on-the-water lives at DB id=6 due to early-phase renumbering;
"cat-3" shorthand in docs refers to the slug.)

Total active entities: **1,314** across 12 active Tier-1 slugs.

**Pytest baseline:** **2018 collected** post-`1dd443a` sustainability
(2002 5.10 baseline + 16 new `tests/test_phase5_11_places_load_resolver.py`
regression guards). Alembic head unchanged at `0a1b2c3d4e5f` (Phase 5
lane shipped no migrations).

---

## 2 Three dispatchable lanes (operator picks ONE)

### Lane A -- Phase 6 amend5-to-11 dispatch (LOW-FRICTION, recommended first)

**What:** Update `docs/maintainability/master_build_plan.md` 4 + `docs/STATE.md` "Recently shipped" to land the Phase 5.5-5.11 SHIPPED ledger entries. STATE.md currently tops at Phase 5.4 SHIPPED; master plan has 5.5 + 5.6 sub-section headers but no SHIPPED lines.

**Authored dispatch docs (paste-ready):**
- `outputs/claude_code_dispatch_phase6_amend5_to_8.md` -- covers 5.5 + 5.6 + 5.7 + 5.8 SHIPPED ledger
- `outputs/claude_code_dispatch_phase6_amend9_to_11.md` -- covers 5.9 + 5.10 + 5.11 SHIPPED ledger (authored at 5.11 SHIP)

**Operator may consolidate into a single 5.5-to-5.11 dispatch** per the amend9-to-11 doc's 4 sequencing note (the cleanest option since both docs touch the same 2 files; no anchor races).

**Channel:** Claude Code parallel agent (or land in-line at the next Cowork commit per Amendment 4/5 precedent).

**Effort:** ~10-15 minutes Claude Code time.

**Why first:** ledger debt is the only thing currently mis-pointing the state-of-record. Until it lands, STATE.md "Recently shipped" doesn't reflect 5.5-5.11 SHIPs.

### Lane B -- Phase 6.3+ continuation (Cursor lane)

**What:** Phase 6 (Tier 1 UI build) is in flight -- 6.1 (unified Hava card grammar, `fd16e7a` 2026-05-14) + 6.2 (category landing page template + Eat & Drink proof, `3948add` 2026-05-15) shipped. **6.3 and beyond pending** -- dispatch prompt staged at `outputs/cursor_dispatch_prompt_phase_6_3.md`.

Phase 6.3 deliverables per master plan 4 + brief 3.3:
- Apply 6.2's `category_landing.html` template to remaining 5 Tier 1 categories (the 5.2-through-5.11 categories beyond Eat & Drink)
- District-context chip rendering on profile pages
- Time-aware + heat-aware default ranking logic
- Seasonal hours rendering on profile pages

**Channel:** Cursor session via the pre-staged dispatch prompt.

**Effort:** dispatch + operator review; UI work shipped via Cursor.

**Pre-flight:** the dispatch prompt has 1 unfilled SHA slot (`<<<PATCH_PHASE_6_2_SHA_HERE>>>` -- replace with `3948add` before paste).

### Lane C -- Phase 7 (Tier 2 UI + chat integration) -- needs scope reconciliation FIRST

**What:** Per `outputs/phase7_handoff_note.md` (authored 2026-05-14 pre-Phase-5-restructure), Phase 7 is "Tier 2 UI + chat integration (3-4 weeks)" covering 3 "Tier 2" categories (Outdoors/Parks/Trails, Lodging & Vacation Rentals, Pets) plus chat ENTITY wiring + HALT 3 close-out + cross-entity queries.

**SCOPE STALENESS CAVEAT:** The Phase 7 hand-off note's "Tier 2 categories" list (Outdoors/Parks/Trails, Lodging & VR, Pets) **are the categories Phase 5 just SHIPPED in 5.7, 5.10, and 5.11**. The hand-off doc was written before the Phase 5 restructure expanded Tier 1 to all 13 categories. The next session must reconcile this against the current `docs/maintainability/master_build_plan.md` 4 Phase 7 section before dispatching:
- Are those 3 categories still "Tier 2" for Phase 7 purposes (UI-only, since data shipped in Phase 5)?
- Or has Phase 5's coverage absorbed Phase 7's Tier 2 data strand entirely, leaving Phase 7 = just chat integration + HALT 3 close-out?
- Or has the master plan been updated post-restructure to redefine Tier 2?

**Reconciliation action:** read `docs/maintainability/master_build_plan.md` 4 Phase 7 section (around line 345) carefully, cross-reference with `outputs/phase7_handoff_note.md` 1 + 5, decide scope, possibly update the hand-off doc.

**Channel:** Cowork primary (or Cursor if a tight scope can be locked) after scope reconciliation.

**Effort:** scope reconciliation = small Cowork session (1-2h); Phase 7 itself = M-L (10-14 days per master plan).

---

## 3 Read order for the next session

1. **This document** -- the branch-point boot prompt.
2. **`outputs/phase5_11_session_closeout.md`** -- 5.11 SHIPPED state + V1.5 carry inventory (~20 items consolidated from 5.0-5.11).
3. **`docs/maintainability/master_build_plan.md`** -- 4 Phase 6 + 4 Phase 7 + 5 dependency graph. Authoritative on phase sequencing.
4. **`docs/STATE.md`** -- "Recently shipped" (tops at 5.4 until amend5-to-11 lands) + "Now / Next / Later".
5. **Lane-specific reads** depending on which lane you pick:
   - Lane A: `outputs/claude_code_dispatch_phase6_amend5_to_8.md` + `outputs/claude_code_dispatch_phase6_amend9_to_11.md` (both paste-ready for Claude Code).
   - Lane B: `outputs/cursor_dispatch_prompt_phase_6_3.md` (1 SHA patch needed -- `3948add`) + `outputs/cursor_brief_phase_6_tier_1_ui.md` (operating doc).
   - Lane C: `outputs/phase7_handoff_note.md` -- read with scope-staleness caveat above; consult master plan 4 Phase 7 first.

---

## 4 V1.5 carry inventory (consolidated 5.0-5.11)

Full inventory in `outputs/phase5_11_session_closeout.md` 6 + 7. Highlights:

- **Layer-4 verifier surfaces deferred to V1.5** (per kickoff 3 Option C across 5.5-5.11):
  - 5.10: AZDOR transient-lodging tax + AZRE vacation-rental license + LHC Tourism Board lodging directory
  - 5.11: AZ State Veterinary Medical Examining Board + national pet franchise locators (PetSmart/Petco/Banfield)
  - 5.9: AZDHS childcare-license + franchise gym chain APIs + LHC Parks & Rec
- **Multi-place_id consolidations:**
  - 5.10: HEAT Bar <-> Heat Hotel; Havasu Dunes Resort <-> GetAways
  - 5.11: 3 Beautiful Beards franchise (Pet Spaw x2 + Boutique); 3 PetSmart franchise (cat-8 + Grooming cat-11 + Dog Training cat-11)
- **Cat-8 pet-retail DUAL candidates** (5.11): PetSmart, Doggie Shades, Rok Dog Leashes for cat-8 + cat-11 DUAL ADD review
- **5 zero-review Slice E entries** (5.11): Obedience Please, PetSmart Grooming, PetSmart Dog Training, Penney's Pampered Pawz, TagWorks -- may be defunct or placeholder Google listings; DRAFT review carry
- **5.10 waterfront RV/campground candidates** (5): Sam's Beachcomber, Anchor Lake House, Campbell Cove, Islander, Havasu Falls -- water_adjacent override review
- **5.10 lake_recreation-domain ambig** (29 records): Sunset Charter, At The Bridge Rentals, HAVASU RENTALS, etc. -- cat-3 NEW creates if 5.2 lane re-opened
- **86 of 265 HWC providers remain `verified=False`** (5.4 carry): operator-driven DBA->NPI follow-up surface
- **Sustainability layer extensions**:
  - 5.10: `camping_cabin` / `cottage` / `mobile_home_park` / `guest_house` direct mappings
  - 5.11: `pet_supply_store` / `animal_shelter` / `aquarium_store` direct mappings
- **Manual recovery surfaces** (5.11): mobile groomers (2 known), independent dog walkers, cat boarding, pet sitting services (Care.com / Rover not Google-indexed)

---

## 5 Sandbox-specific gotchas (NEW carry from 5.11 session)

The 5.11 session discovered + documented the Cowork sandbox FUSE-mount
unlink-block. Carry forward for any future sandbox-driven repo work:

- **FUSE mount blocks `unlink()` system-wide** at `/sessions/<id>/mnt/havasu-chat/`. `rm` fails with EPERM. Git operations (which use `unlink()` for index-lock release, ref updates, temp-file cleanup) cannot complete from this sandbox path.
- **Workaround:** clone the repo to `/sessions/<id>/havasu-chat-work/` (non-FUSE filesystem where unlinks work). Make commits there. Push via the bundle workflow:
  1. `git bundle create /tmp/<phase>_<step>.bundle origin/main..HEAD` (or similar)
  2. `cp -a /tmp/<bundle> /sessions/<id>/mnt/havasu-chat/outputs/<phase>_<step>.bundle` (FUSE writes work; unlinks don't)
  3. Operator runs Windows-side: `git fetch outputs/<bundle>` + `git merge --ff-only FETCH_HEAD` + `git push origin main`
- **Edit / Write tools UNSAFE on FUSE-mount paths.** One Edit attempt during the 5.11 sustainability commit truncated 2 source files mid-string (`google_types_mapping.py` to 133 lines, `places_load.py` to 199 lines). Recovery: Windows-side `git restore <files>`. Re-author via bash heredoc + Python in `/sessions/<id>/havasu-chat-work/`.
- **Pre-commit ruff check pattern:** `pip install --target=/tmp/ruff_install ruff && PYTHONPATH=/tmp/ruff_install python3 -m ruff check <files>` catches I001-type issues before commit (caught the 5.11 `6adfc05` blank-line bug too late).
- **The full diagnostic + workaround narrative is in `outputs/phase5_11_session_closeout.md` 3 + 6.** May warrant graduation to `docs/maintainability/dispatch_channels.md` after operator review.

---

## 6 Cleanup carry-over (operator at convenience)

**Working-tree untracked files** (no longer relevant):
- 3 probe leak files (`.preflight`, `probe1.txt`, `probe3-renamed.txt`) -- sandbox diagnostic leaks from 5.11 session; safe to `Remove-Item`.
- 4-5 bundle files (`outputs/phase5_11_*.bundle`) -- served their purpose during 5.11 ship; safe to `Remove-Item`.
- 2 audit-trail JSON emissions (`outputs/phase5_11_ambig_audit_data.json` + `outputs/phase5_11_top10_data.json`) -- regenerable from `phase5_11_ambig_audit_dump.py` + `phase5_11_top10_discovery.py`; commit-as-artifact or leave untracked per operator preference.
- `hava_api_catalog.docx` -- long-standing carry; unrelated to 5.x scope.

**Recommended PowerShell sweep:**

```powershell
cd C:\Users\casey\projects\havasu-chat
Remove-Item .preflight, probe1.txt, probe3-renamed.txt -ErrorAction SilentlyContinue
Remove-Item outputs/phase5_11_sustainability.bundle, outputs/phase5_11_ship.bundle, outputs/phase5_11_sha_cleanup.bundle, outputs/phase5_11_ruff_fix.bundle, outputs/phase5_11_framing_fix.bundle -ErrorAction SilentlyContinue
git status
```

`hava_api_catalog.docx` + 2 audit JSON files left untouched per operator discretion.

**Older carry-over (5.0-5.10):**
- `data/events.db.bak-*` files (accumulating since 5.3) -- operator prunes when comfortable.
- `outputs/_deltest` + 2 historical `outputs/ci_*_log_failed.txt` files -- unrelated to active lanes.
- Google Places API key rotation deferred per operator ("all keys will be changed at the conclusion of this project").

---

## 7 Pre-flight checks (do once at next-session dispatch)

1. **`git log --oneline -10`** -- top should be `54f17e6` (framing correction) or later if Lane A landed between sessions.
2. **`git status`** -- clean. Carry-over untracked: 1-3 files per cleanup section above.
3. **`python -m alembic current`** -- `0a1b2c3d4e5f` (Phase 4.1 outbox; unchanged across all 5.x phases).
4. **`python -m pytest -q --collect-only 2>&1 | Select-Object -Last 3`** -- expect **2018 collected** (5.11 baseline) unless Lane B / C added tests.
5. **`gh run list --branch main --workflow CI --limit 5`** -- top run should be green on `54f17e6` (or later).
6. **`python outputs/phase5_11_db_spot_check.py`** -- expect cat-11 = 38, all prior baselines unchanged (5.8 events 20, 5.9 classes 31, 5.10 lodging 73). Cumulative DB: 1314 entities.
7. **Decide which lane to dispatch.** Recommended order: A (low-friction ledger) -> B (Phase 6.3 UI) -> C (Phase 7 with scope reconciliation).

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.11 session 1
(2026-05-17) post-Phase-5-COMPLETE. Phase 5 multi-phase data-population
lane closed; this boot prompt hands off to the next session's lane
choice across Phase 6 ledger amend / Phase 6.3 UI / Phase 7 scope
reconciliation.*
