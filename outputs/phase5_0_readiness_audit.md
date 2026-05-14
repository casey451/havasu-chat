# Phase 5.0 Readiness Audit — locked-decision verification against disk

> **Purpose:** before Phase 5.1 (Eat & Drink) dispatches, verify that the Phase 5.0
> lead-up work the brief + prereq checklist claim is "LOCKED / SHIPPED" is actually
> present and correct on disk — not just asserted in a doc. Phase 5 has a history of
> failed sub-agent doc writes (see `phase5_prereq_checklist.md` preamble) and the
> codebase runs in a mixed-OS session where the sandbox bash mount serves stale views
> (gotcha #15), so "the commit says it landed" is not the same as "it's on disk."
>
> **Method:** every finding below was verified with the Windows-authoritative Read /
> Grep tools, not sandbox bash. Where bash and Read disagreed, Read wins (and the
> disagreement is noted — it happened once here).
>
> **Authored by:** Cowork primary, Phase 5 lane, new-chat post-`dc11430` session
> (2026-05-14), while the Lane B Cursor dispatch (B1) runs in parallel. Brand-new
> `outputs/` file — safe under the parallel-chat scope lock (gotcha #18).

---

## §1 Summary

| Area | Status |
|---|---|
| `google_types_mapping.py` Tier 1 expansion + beauty skip + RV-park boundary | ✅ Confirmed on disk — exact match to brief §2 |
| `places_discovery.py` docstring repoint (§3.4.k) | ✅ Confirmed on disk |
| `docs/operations/boat_access_rubric.md` (§3.3.i) | ✅ Confirmed on disk — complete, 264 lines, §1–§7 |
| `docs/maintainability/manual_recovery_checklist.md` back-fill (§3.4.j) | ✅ Confirmed on disk — complete, 414 lines, §1–§9 |
| Phase 4 scrape scripts (`places_discovery` / `places_enrichment` / `places_load` / `osm_overpass_pull`) | ✅ All present |
| `scripts/osm_overpass_load.py` | ✅ Correctly absent — it is the §3.d script Cursor authors in Phase B |
| `parks-rec-scrapes.yml` workflow | ✅ Present, cron `15 */6 * * *` + `workflow_dispatch` |
| Reconciler `SOURCE_PRIORITY` slots for `az_roc` / `npi_registry` | ✅ Present |
| **`app/contrib/npi/` client surface** | ⚠️ **Does NOT exist** — brief / prereq / Cursor dispatch all claim it does. See §3. |

**Bottom line:** the §3 lock-batch landed cleanly on disk — one real drift, the
NPI client surface, plus three minor doc-accuracy notes. None of this blocks the
Lane B Cursor dispatch's **Phase A** (the 10 verifications). The NPI drift affects
the Cursor dispatch's **Phase B** (the `npi_verify.py` script) and is worth
surfacing to Cursor before HALT-2.

---

## §2 Confirmed on disk ✅

### §2.1 `app/contrib/google_types_mapping.py` — exact match

Brief §2 claims the Tier 1 `types[]` expansion landed in commit `62ab3b7` with
"~54 new entries total." Verified by reading the file and counting:

| Category | Existing | New | Brief §2 claim | Match |
|---|---|---|---|---|
| Eat & Drink | 4 | +13 | +13 | ✅ |
| On the Water | 2 | +3 (`harbor`, `boat_dealer`, `boat_rental`) | +3 | ✅ |
| Home & Property | 4 | +10 | +10 | ✅ |
| Health, Wellness & Care | 5 | +9 | +9 | ✅ |
| Auto, RV & Fuel | 3 | +6 | +6 | ✅ |
| Shopping & Essentials | 3 | +10 | +10 | ✅ |
| Beauty skip (`hair_salon` / `beauty_salon` / `nail_salon` → `(None, None)`) | — | +3 | +3 | ✅ |
| **Total new** | | **+54** | **~54** | ✅ |

Also confirmed: `rv_park` → `("lodging-vacation-rentals", "commercial")` (§3.1.b
lock — where-you-stay framing); `rv_repair` → `("auto-rv-fuel", "commercial")`;
`veterinary_care` / `pet_store` → `("pets", ...)` kept separate from health. The
beauty types carry an inline comment documenting the intentional Phase 5 skip.

### §2.2 `scripts/places_discovery.py` docstring (§3.4.k)

Confirmed: the docstring now points Phase 5 execution at
`outputs/cursor_brief_phase_5_tier_1_data.md` §3 + `outputs/phase5_prereq_checklist.md`
§4, and explicitly notes the old `relay/HAVA_BUSINESSES_EXECUTION_PLAN_2026-05-06.md`
reference (which never existed in the tree) was removed 2026-05-13. No stale
reference remains.

### §2.3 `docs/operations/boat_access_rubric.md` (§3.3.i)

Confirmed complete — 264 lines, §1–§7: the 4 canonical shapes (marina / public
ramp / beach / shoreline commercial), key tables, `null`-vs-`0`-vs-`{}` semantics,
operator entry tips, a deferred-validator note (§5), an operator-amendable
surface-gaps section (§6), and a Phase 6 / Phase 8 consumer reference (§7).

### §2.4 `docs/maintainability/manual_recovery_checklist.md` (§3.4.j)

Confirmed complete — **414 lines**, §1–§9 fully back-filled with field-work prompts
(where to look / expected count / per-entry pattern / operator notes) across
community recreation, public infrastructure, hobbyist venues, ephemeral/seasonal,
non-business places, Tier-2 weak-online-presence businesses, plus a §7 field-trip
route planner with 6 geographic clusters and a sequencing recommendation. Only
intentional placeholders are the §8 status-summary counters (TBD-pending-fieldwork
by design).

> **Note on method:** sandbox bash `wc -l` reported this file at **121 lines** —
> the Read tool showed the true **414**. This is gotcha #15 in the wild (the bash
> mount served a truncated/stale view). It is the reason this audit was done with
> Read/Grep, not bash, and the reason future readiness checks should be too. The
> brief §2's "~250 lines" figure was an undercount, not an overclaim — the file is
> *more* complete than advertised.

### §2.5 Phase 4 runtime scripts present

`scripts/places_discovery.py`, `scripts/places_enrichment.py`, `scripts/places_load.py`,
`scripts/osm_overpass_pull.py` — all present. `scripts/osm_overpass_load.py` is
**correctly absent**: it is the §3.d tooling-touchup the Lane B Cursor dispatch
authors in Phase B. The reconciler (`app/contrib/ingest_reconciler.py`) carries
`SOURCE_PRIORITY` slots for `az_roc` (3) and `npi_registry` (4), so the load path
is ready to *accept* Layer-3/Layer-4 data once the verify scripts produce it.

### §2.6 `parks-rec-scrapes.yml` workflow

Present and configured: cron `15 */6 * * *` + `workflow_dispatch`, three steps
(`run_scrapes.py` → `parks_rec_load.py` → `parks_rec_prune.py`), uploads snapshots
as a run artifact. Lane B §10 (workflow run-health check) is a live-GitHub-Actions
check Cursor does — the YAML itself is sound.

---

## §3 Drift — `app/contrib/npi/` does not exist ⚠️

**Claim (in three places):**
- Brief §2, layered-scrape row: *"Layer 4 (specialized) NPI for health"* — implies built.
- Prereq checklist §4 row 5: *"NPI registry — Already integrated per master plan §4 Phase 4 (Layer 4); verify ... against the existing `app/contrib/npi/` surface."*
- Prereq checklist §7 (nice-to-haves) + Cursor dispatch §0 + §3.c: *"reads loaded `health-wellness-care` entity rows, cross-references each against the NPI registry via the existing `app/contrib/npi/` surface."* The dispatch §0 reading list literally instructs Cursor to *"Read `app/contrib/npi/`."*

**Reality (verified by Grep over `app/`):** there is no `app/contrib/npi/`
directory and no NPI client module anywhere. The only `npi` references in `app/`
are:
- `app/contrib/ingest_reconciler.py` — `"npi_registry": 4` in `SOURCE_PRIORITY`
- `app/db/models.py` — `npi_registry` as an allowed value in the `providers.verification_method` CHECK constraint
- `app/providers/view_models.py` + `app/chat/confidence_tier.py` — consume the `verification_method` value

So the **schema, reconciler, and confidence pipeline have NPI slots reserved**, but
the **Layer-4 client that actually queries the NPI registry API was never built.**
No Phase 4 commit (`86eeaf8` Phase 4.2, `2f87211` Phase 4.3) added it — the
"already integrated" framing appears to be aspirational, carried forward unchecked
through the prereq checklist and into the Cursor dispatch.

**Impact:** **Phase A is unaffected** — Lane B §5 just verifies the *public NPI
registry API* endpoint shape (`https://npiregistry.cms.hhs.gov/api/...`), which is
a live-web check that doesn't depend on any local client. **Phase B §3.c is
affected** — the dispatch tells Cursor `npi_verify.py` "wraps the existing
`app/contrib/npi/` surface," and that surface isn't there. Cursor will either (a)
build the NPI HTTP client from scratch inside `npi_verify.py` (or a new
`app/contrib/npi_client.py`), or (b) HALT confused.

**Recoverability: high.** The dispatch §3.c already says the right thing
operationally — *"The NPI API is open + GET-based (no auth) ... keep it a simple
synchronous HTTP client; no headless browser."* That is a from-scratch build spec.
The only problem is the "wraps the existing surface" framing.

**Recommended action (operator, low effort):** when Cursor reaches HALT-1 and you
send it on to Phase B, add one line: *"Note: there is no `app/contrib/npi/` surface
— it was never built. `npi_verify.py` builds the NPI client fresh as a simple
synchronous GET-based HTTP client per §3.c; put shared client logic in a new
`app/contrib/npi_client.py` if it's cleaner than inlining."* That keeps Phase B
moving without a confused HALT. (`app/contrib/` is in this Phase 5 lane's scope, so
a new `npi_client.py` there is fine; it does not collide with the Phase 6 lane.)

---

## §4 Minor / FYI — no action required, just don't be surprised

1. **Pytest baseline floors are stale in the briefs.** Brief §0 says "1795
   collected"; Cursor dispatch §0 says "~1803." Actual per STATE.md is **1820**
   (post-Phase-6.1 — the Phase 6 agent added `tests/test_phase6_hava_card.py`).
   Both docs say "verify," so this self-corrects; Cursor should just record 1820
   as its true baseline.

2. **Lane B §2 test procedure points at the wrong file for scrape URLs.** The
   briefing tells the operator/Cursor to *"open `parks-rec-scrapes.yml` + identify
   the URL(s) being scraped."* The YAML doesn't contain URLs — it invokes
   `python scripts/run_scrapes.py`. The actual target URLs live in the
   `app/contrib/` scraper modules (`webtrac.py`, `lhcaz_aquatic.py`,
   `scrape_runner.py`). Cursor should look there for the §2 verification.

3. **Brief playbook prose lists a couple of `types[]` that weren't mapped.** Brief
   §3.1 prose says add `fast_food`; the locked + landed type is
   `fast_food_restaurant` (§2 lock and the code agree — the §3.1 prose is just
   loose). Brief §3.2 prose mentions `aquarium` / `swimming_pool` as possible
   on-the-water adds; neither was mapped, and §2's "+3 on-the-water" count
   confirms they were intentionally not. The code is correct per §2 — the §3.x
   playbook prose is the looser of the two; trust §2 + the code.

4. **The §3.4.k stale-reference cleanup was incomplete.** Prereq §3.4.k patched the
   dead `relay/HAVA_BUSINESSES_EXECUTION_PLAN_2026-05-06.md` reference out of
   `scripts/places_discovery.py` — but `scripts/places_enrichment.py:14` still
   carries the identical dead reference (*"Companion to relay/HAVA_BUSINESSES_..."*).
   Cosmetic only (it's a docstring, not runtime), and `places_enrichment.py` is in
   this Phase 5 lane's scope — fold a one-line docstring fix into the first Phase 5
   commit that touches `scripts/` (e.g. alongside the Lane B Phase B tooling
   commit). Not worth a standalone commit.

---

## §5 What this audit does NOT cover

- **Live-web verifications.** All 10 Lane B items (AZ ROC reachability, NPI API
  shape, OSM Overpass posture, GitHub Actions run health, Google billing, etc.)
  are Cursor's Phase A job — this Cowork chat structurally can't do live web.
- **Pytest / ruff status.** The Cowork sandbox has no pytest module; canonical
  test runs are Cursor's or the operator's Windows venv.
- **The Phase 6 lane's files.** Out of this chat's declared scope (gotcha #18).
- **Prod deploy state.** Railway redeploy is operator action B2-b — unverifiable
  from here.

---

## §6 Net effect on the Phase 5.0 punch list

| Punch-list item | Audit effect |
|---|---|
| B1 — Lane B Cursor dispatch | **Phase A unaffected** — proceed as written. **Phase B:** feed Cursor the §3 NPI note before/at HALT-1→B handoff. |
| B2-a — Google Places billing | Unaffected — operator-only. |
| B2-b — Railway redeploy | Unaffected — operator-only. |
| B2-c — heat_exposure priority-30 amendment | Unaffected — `boat_access_rubric.md` (which anchors several priority-30 rows) is confirmed complete, so the operator has the reference it needs. |

The §3 lock-batch is sound on disk. Phase 5.0 can close on schedule once B1 + the
three operator actions land — the only thing this audit adds to the critical path
is a one-line note to hand Cursor at the Phase A→B boundary.

---

*Authored by Cowork primary, Phase 5 lane, new-chat post-`dc11430` session
(2026-05-14). Lives at `outputs/phase5_0_readiness_audit.md` — brand-new `outputs/`
file, safe under the parallel-chat scope lock. Verified with Windows-authoritative
Read/Grep per gotcha #15; sandbox bash was observed serving a stale view of
`manual_recovery_checklist.md` during this very audit.*
