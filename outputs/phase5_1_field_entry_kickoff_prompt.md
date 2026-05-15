# New-chat kickoff prompt — Phase 5.1 field-entry phase

> Paste the block below into a fresh Cowork chat to start the Phase 5.1
> field-entry phase. Everything the new agent needs is reachable from the
> handoff doc it points at.

---

You are Cowork primary for the havasu-chat project, Phase 5 lane, picking up at **PHASE 5.1 field entry** — the back half of the Eat & Drink sub-phase. The Phase 5.1 **scrape phase** (discovery → enrichment → load) SHIPPED 2026-05-14 at origin commit `038192d`; 287 eat-drink providers are loaded into a freshly-rebuilt local `data/events.db`.

A separate Cowork agent runs Phase 6 (Tier 1 UI) in parallel — coordinate via origin commits. This chat's file scope: `app/contrib/`, `scripts/`, `app/db/`, `outputs/` only. Shared docs (`docs/STATE.md`, `docs/maintainability/*`) are NOT in scope — coordinate before touching.

Read in order:
1. **`outputs/phase5_1_field_entry_handoff.md`** — the scrape-phase close-out + field-entry handoff. START HERE. It is the index to DB state, the 5 drift findings, every carry-forward item, and the read order.
2. `outputs/phase5_1_eat_drink_kickoff.md` §3/§4/§5 — the live field-entry runbook (§0/§1 are done; §3 Layer-5 recovery, §4 curated field-entry rubric, §5 daily/weekly rhythm are the live sections).
3. `outputs/heat_exposure_priority_30_list.md` — the LOCKED `heat_exposure` decision tree for field entry.
4. `docs/STATE.md` — production state + gotchas (esp. #4/#15 bash-mount unreliability — Windows-side reads are authoritative; #16 PowerShell `-m` quoting).
5. `docs/scrape_logs/eat-drink_2026-05-14.md` — the scrape run record.

First action: `git log --oneline -8` to confirm origin (should top at `038192d` or later if the Phase 6 agent pushed). Then surface, from the handoff doc §5, the open carry-forward items — and ask the operator whether they want to start with field-entry work (§4 rubric) or clear a carry-forward first (drift #5 `places_load` summary fix is the quickest, and it should land before Phase 5.2).

Framing: Phase 5.1 field entry is operator-driven, multi-week, self-paced (~2h/day cap, ~7–22h over 1–2 weeks). Cowork is the reactive companion — field-entry judgment calls, the 2 PROVISIONAL heat-list confirms (El Paraiso, College Street Brewhouse), the §5 day-7 QA spot-check, ambiguous-call triage, tooling touch-ups as they surface. Not driving a sub-phase chain. Operator commits all git per the working agreement.

Open carry-forward (detail in `phase5_1_field_entry_handoff.md` §5): drift #5 — `places_load` load summary omits reconciler counts, ~2-line `scripts/` fix, wanted before Phase 5.2; `filter_by_category` unit test — needs a Cursor dispatch (`tests/` out of scope); task #5 — `osm_overpass_load.py` priority fix, dispatch staged, fires before Phase 5.2; task #6 — real `az_roc_client.lookup_contractor`, operator decision before Phase 5.3; `master_build_plan.md` §4 + `STATE.md` refresh — shared docs, coordinate.

---

*Staged by Cowork primary, Phase 5 lane, Phase 5.1 scrape-phase chat (2026-05-14).
Lives at `outputs/phase5_1_field_entry_kickoff_prompt.md`.*
