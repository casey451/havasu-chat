# Phase 5.0 Close-Out — lead-up & shared tooling

> **Purpose:** the capstone for Phase 5.0 (the shared lead-up + tooling sub-phase of the
> restructured Phase 5). Ties off the four-item punch list, records the drift findings the
> sub-phase surfaced, lists every carry-forward item, and hands off to Phase 5.1. A fresh
> chat picking up Phase 5.1 should read this first — it's the index to everything Phase 5.0
> produced.
>
> **Authored by:** Cowork primary, Phase 5 lane, new-chat post-`5d429aa` session
> (2026-05-14). Brand-new `outputs/` file — safe under the parallel-chat scope lock.

---

## §1 The Phase 5.0 punch list — all four closed

| Item | What it was | Status |
|---|---|---|
| **B1** | Cursor dispatch: Lane B's 10 external-source verifications + 3 tooling-touchup scripts | ✅ **DONE** — both Cursor HALTs committed (`1ea31b7` Lane B findings, `5d429aa` the scripts) |
| **B2-a** | Google Places API billing check + spend cap | ✅ **DONE** — key active, Places API (New) enabled, $250/mo budget already set |
| **B2-b** | Phase 4 Railway redeploy → walk prod alembic to `0a1b2c3d4e5f` | ✅ **DONE** — `dc11430` auto-deployed; prod `alembic_version` confirmed `0a1b2c3d4e5f` |
| **B2-c** | `heat_exposure_priority_30_list.md` — fill placeholders + resolve open calls | ✅ **DONE** — Cowork web-research first pass + ChatGPT deep-research pass reconciled, open calls decided on operator delegation; list is commit-ready |

(B3 — the master-plan restructure — was already applied at `dc11430` before this chat started.)

**Phase 5.0 is COMPLETE once the final outputs batch is committed** (see §6). Phase 5.1
Eat & Drink dispatches next.

---

## §2 What shipped on origin during Phase 5.0

| Commit | Contents |
|---|---|
| `1ea31b7` | Lane B verification findings recorded in the briefing + prereq checklist §4 |
| `af31eca` | Phase 5.0 readiness audit + Phase 5.1 Eat & Drink kickoff runbook + STATE.md refresh supplement |
| `5d429aa` | `npi_client.py`, `az_roc_client.py`, `scripts/npi_verify.py`, `scripts/az_roc_verify.py`, `scripts/osm_overpass_load.py` + 3 `tests/test_phase5_*` (pytest 1820 → 1825) |
| *(pending)* | Final outputs batch — see §6 |

Origin tip at close-out authoring: `5d429aa`. Alembic head unchanged (`0a1b2c3d4e5f`); no
migrations in Phase 5.0. Pytest 1825 collected (1823 passed + 2 skipped).

---

## §3 Drift findings surfaced during Phase 5.0

Phase 5.0 was supposed to be mostly mechanical; it surfaced four pieces of drift between
what the briefs *claimed* existed and what's actually on disk. All are captured with
detail + recommended action in `outputs/phase5_0_readiness_audit.md`.

1. **No `app/contrib/npi/` client surface ever existed.** The brief, prereq checklist, and
   Cursor dispatch all claimed "NPI already integrated (Layer 4)." Only `npi_registry`
   *schema slots* existed (a `SOURCE_PRIORITY` entry + a `verification_method` CHECK value).
   Resolved in Phase B — Cursor built `app/contrib/npi_client.py` fresh.
2. **`verified_field` / `npi_number` columns don't exist.** The dispatch assumed them.
   Real schema: `Provider.verified` (bool) + `Provider.verification_method` (String(32),
   CHECK-constrained) + `Provider.attributes` (JSON). Resolved — the verify scripts write
   `verification_method='npi_registry'` / `'scraper'` + stash details in `attributes` JSON,
   no migration.
3. **`places_enrichment.py:14` still carries the dead `relay/HAVA_BUSINESSES_...` reference**
   that §3.4.k only patched out of `places_discovery.py`. Cosmetic — fold a one-line
   docstring fix into the next `scripts/` commit.
4. **`osm_overpass_load.py` update branch clobbers higher-priority data** — see task #5
   below.

---

## §4 Carry-forward — open items beyond Phase 5.0

| Item | Where it's tracked | When it's needed |
|---|---|---|
| **Task #5 — `osm_overpass_load.py` priority-aware update** | Cursor dispatch staged at `outputs/cursor_dispatch_osm_overpass_load_priority_fix.md` | Before the Phase 5.2 On the Water OSM load step (GATE 2 in the 5.2 runbook) |
| **Task #6 — real `az_roc_client.lookup_contractor`** | Currently a stub; `az_roc_verify.py` is inert until it's built | **Decision needed before Phase 5.3:** build the Playwright/XHR scrape of the AZ ROC Salesforce portal, OR take the Lane B §1 fallback (operator manually verifies the top-30 contractors, soften the §3.3 acceptance gate) |
| **`boat_access_rubric.md` §3.4 Pier 19 example is defunct** | Flagged in `heat_exposure_priority_30_list.md` §7 + §9 | Whoever owns `docs/operations/` patches it — outside this Phase 5 chat's scope |
| **heat list — 2 PROVISIONAL rows** (El Paraiso, College Street Brewhouse) | `heat_exposure_priority_30_list.md` §2 | Operator confirms patio shade during the §3.1 Eat & Drink scrape |
| **heat list — deferred off-island venues** (Cattail Cove, Take-Off Point) | `heat_exposure_priority_30_list.md` §9 item 6 | Off-island sweep / V1.5 per `manual_recovery_checklist.md` §7 |
| **STATE.md refresh** | Ready-to-paste content in `outputs/state_md_refresh_supplement.md` | Shared-doc — coordinate with the Phase 6 agent, or apply at a checkpoint |
| **API enrichment catalog** (`hava_api_catalog.docx`) | Assessed this session — recommended as its own future master-plan track, not interleaved into Phase 5/6; weather/water/AQI APIs link tightly to Phase 8 | Not on the master plan yet — operator decides whether to formalize it |

---

## §5 What's next — Phase 5.1 Eat & Drink

Phase 5.1 dispatches off **`outputs/phase5_1_eat_drink_kickoff.md`** — a paste-and-go
operator runbook (the brief §3.1 playbook + §0 baseline + §5 rhythm consolidated). It's
gated only on Phase 5.0 closing, which the final commit does.

Phase 5.1 in brief: single-layer (Google Places only, no OSM/AZ ROC/NPI), warm-up category,
~90–140 entries targeted, ~10–25 operator hours over 1–2 weeks. The runbook has the scrape
sequence, ambiguous-queue review, Layer-5 prompts, the field-entry rubric, and the
acceptance gate. The locked `heat_exposure_priority_30_list.md` is the tag-or-default
decision tree for field entry.

After 5.1: Phase 5.2 On the Water (`outputs/phase5_2_on_the_water_kickoff.md`, already
pre-staged) — which is where task #5's dispatch fires.

---

## §6 Phase 5.0 artifact inventory

Everything Phase 5.0 produced in `outputs/`, so nothing's lost:

**Committed (`af31eca`):**
- `phase5_0_readiness_audit.md` — disk-state verification of the §3 lock-batch + the drift findings
- `phase5_1_eat_drink_kickoff.md` — the Phase 5.1 operator runbook
- `state_md_refresh_supplement.md` — ready-to-paste STATE.md refresh

**Committed (`1ea31b7`):**
- `phase5_lane_b_verification_briefing.md` + `phase5_prereq_checklist.md` §4 — Lane B findings

**Committed (`5d429aa`):**
- `npi_client.py`, `az_roc_client.py`, `scripts/npi_verify.py`, `scripts/az_roc_verify.py`, `scripts/osm_overpass_load.py` + 3 `tests/test_phase5_*`

**Pending commit (final Phase 5.0 batch):**
- `heat_exposure_priority_30_list.md` — reconciled + decided + commit-ready (closes B2-c)
- `heat_exposure_chatgpt_deep_research_prompt.md` — the ChatGPT deep-research prompt
- `deep-research-report-b947a1f2.md` — ChatGPT's deep-research output (provenance for the heat list)
- `phase5_2_on_the_water_kickoff.md` — the Phase 5.2 operator runbook
- `cursor_dispatch_osm_overpass_load_priority_fix.md` — staged Cursor dispatch for task #5
- `phase5_0_close_out.md` — this file

Suggested commit body (PowerShell-safe, no embedded double-quotes per gotcha #16):
`chore(outputs): Phase 5.0 close-out -- heat_exposure list reconciled+locked, 5.2 runbook, osm priority-fix dispatch, close-out doc`

---

*Authored by Cowork primary, Phase 5 lane, new-chat post-`5d429aa` session (2026-05-14).
Lives at `outputs/phase5_0_close_out.md` — brand-new `outputs/` file, safe under the
parallel-chat scope lock. Committing the §6 pending batch completes Phase 5.0; Phase 5.1
Eat & Drink dispatches off `outputs/phase5_1_eat_drink_kickoff.md`.*
