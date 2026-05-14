# Phase 7 Handoff Note — the next major lane after Phase 5

> **Purpose:** make sure the Phase 5 → Phase 7 sequence isn't lost when Phase 5 (Tier 1 data gathering) wraps. Authored by Cowork primary at the new-chat post-`2f4676a` session (2026-05-14), at the coordination request of the parallel Phase 6 chat.
>
> **One-line:** when Phase 5 completes, **Phase 7 (Tier 2 UI + chat integration)** is the next major lane — and it carries forward both the Phase 6 card-grammar work *and* the Phase 5 operator-driven data-gathering muscle.

---

## §1 What Phase 7 is

Per `docs/maintainability/master_build_plan.md` §4 Phase 7 + §5 dependency graph:

**Phase 7 — Tier 2 UI + chat integration (3-4 weeks).** Two strands:

1. **Tier 2 UI** — category landing pages for the 3 Tier 2 categories (Outdoors/Parks/Trails, Lodging & Vacation Rentals, Pets), built on the *same template pattern as Phase 6* — i.e. it consumes the unified Hava card grammar that Phase 6.1 just shipped (`fd16e7a`). Plus chat integration wiring the ENTITY catalog into the chat surface.

2. **Tier 2 data gathering** — the operator-driven data work for those 3 categories. Per the master plan: *"same workflow as Phase 5 but smaller volume — 75-175 entries total across the 3 Tier 2 categories."* This is the natural continuation of the data-gathering muscle Phase 5 builds: the same layered-scrape pipeline, the same reconciler, the same per-category playbook shape, the same operator-curated field entry — just fewer entries and fewer categories.

## §2 Why Phase 7 follows Phase 5 specifically

- **Dependency-wise:** Phase 7 depends on Phase 1 (ENTITY schema — SHIPPED) + Phase 6 (unified card grammar — 6.1 SHIPPED `fd16e7a`, rest of Phase 6 in flight). It does **not** depend on Phase 5 *completing* — but it reuses Phase 5's tooling + playbook, so starting Phase 7's data strand before Phase 5's operator has built the data-gathering rhythm would mean climbing the same learning curve twice.
- **Operator-continuity-wise:** Phase 5 is where the operator builds the scrape → reconcile → triage → Layer-5 → field-entry workflow into muscle memory. Phase 7's Tier 2 data gathering is that exact workflow at ~1/4 the volume. Sequencing Phase 7 right after Phase 5 means the operator carries that muscle straight over while it's warm.
- **Restructure parallel:** just as Phase 5 was restructured (2026-05-14) into 5.0 + 5.1–5.6, Phase 7's data strand will naturally decompose the same way — a small shared lead-up + one sub-track per Tier 2 category (Outdoors/Parks/Trails, Lodging & VR, Pets). The Phase 5 artifacts (`cursor_brief_phase_5_tier_1_data.md`, `phase5_prereq_checklist.md`, `manual_recovery_checklist.md`, the 3 tooling-touchup scripts) are the templates Phase 7's data strand reuses — not re-authored from scratch.

## §3 What carries forward from Phase 5 into Phase 7

| Phase 5 artifact / capability | Phase 7 reuse |
|---|---|
| Layered-scrape framework + reconciler (Phase 4 SHIPPED) | Used as-is |
| `scripts/az_roc_verify.py` / `scripts/npi_verify.py` / `scripts/osm_overpass_load.py` (Phase 5.0 tooling) | OSM load script reused for Outdoors/Parks/Trails; AZ ROC + NPI likely not relevant to Tier 2 categories |
| `google_types_mapping.py` | Needs a Tier 2 `types[]` expansion (Outdoors/Parks/Trails, Lodging, Pets) — a small tooling-touchup, same shape as Phase 5.0's §4.a |
| Per-category playbook structure (`cursor_brief_phase_5_tier_1_data.md` §3.x) | Template for Phase 7's per-category playbooks |
| `manual_recovery_checklist.md` | Already has Tier-2 sub-categories sketched per its §6 — Phase 7 fills them in |
| Operator-curated field rubrics (heat_exposure, crowd_notes, boat_access, seasonal_hours) | Same fields apply to Tier 2 entities; rubrics carry forward unchanged |
| `heat_exposure_priority_30_list.md` | Outdoors/Parks/Trails will surface many `outdoor` / `shaded` venues — extend the priority list rather than re-author |

## §4 Where this pointer needs to land (propagation checklist)

This note is the canonical source; the Phase-7-is-next pointer should propagate to:

- [x] `master_build_plan.md` §4 Phase 5 success-criteria line — **DONE 2026-05-14** (added "Phase 7 is the next major lane after Phase 5 completes" pointer)
- [x] `outputs/new_chat_kickoff_phase_5_0.md` — **DONE 2026-05-14** (Phase 7 pointer added so the next Phase 5 agent knows the sequence)
- [ ] `STATE.md` "Queued / open work" section — **PENDING**: add "Phase 7 (Tier 2 UI + chat integration) is the next major lane after Phase 5" — fold this into the coordination-checkpoint STATE.md refresh (see `outputs/phase5_closeout_loose_ends.md` §2)
- [ ] Phase 5 close-out narrative (`outputs/phase5_close_out_narrative.md`, authored when Phase 5 SHIPS) — should end with the Phase 7 handoff pointer

## §5 What Phase 7 does NOT inherit

- Phase 7's UI strand depends on the *rest* of Phase 6 (6.2–6.5), not just 6.1. The Phase 6 lane is in flight (5 sub-phases, 6.1 done). Phase 7's UI strand can't fully dispatch until Phase 6's category-page template + map + profile surfaces are further along.
- Phase 7 is NOT a Phase 5 sub-phase — it's its own master-plan phase. The 5.0 + 5.1–5.6 restructure stays scoped to Tier 1; Phase 7's data strand gets its own (smaller) decomposition when it's dispatched.

---

*Authored by Cowork primary at the new-chat post-`2f4676a` session (2026-05-14), at the coordination request of the parallel Phase 6 chat. Lives at `outputs/phase7_handoff_note.md` — brand-new outputs/ file, safe under the parallel-chat lock.*
