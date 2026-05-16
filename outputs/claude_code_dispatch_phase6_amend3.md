# Claude Code dispatch — Phase 6 Amendment 3: Phase 5.3 SHIPPED ledger lines

> Drop-in artifact for the operator to paste into Claude Code terminal.
> Lands the Phase 6 lane Amendment 3 that was deferred at the close of the
> Phase 5.3 session per `outputs/phase6_coordination_message.md` (Amendments
> 1 + 2 shipped at `b7bf91d` by Claude Code; Amendment 3 deferred for next
> Phase 6 dispatch).
>
> **What this amendment does:** adds Phase 5.3 SHIPPED ledger entries to
> `docs/maintainability/master_build_plan.md` (§4 Phase 5.3 sub-section)
> and `docs/STATE.md` ("Recently shipped (high signal)" section). The
> Phase 5.3 lane shipped at `805a38c` with all 6 acceptance gate items
> cleared; the lane's commit chain runs `f0a46f8 → bff4a79` (12 commits)
> per `outputs/phase5_3_session_closeout.md` §1.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.4 session
> (2026-05-16) pre-§1 scrape. Operator dispatches at convenience —
> runs in parallel with Phase 5.4 §1 work.

---

## §1 Context for Claude Code

The Phase 5.3 (Home & Property Services) lane SHIPPED at commit `805a38c`
on 2026-05-15/16, plus a follow-on lint cleanup at `bff4a79`. All 6
acceptance gate items cleared per `outputs/phase5_3_gate_verification.py`
("ALL 6 ITEMS CLEARED — READY TO SHIP").

Amendments 1 + 2 from `outputs/phase6_coordination_message.md` landed at
`b7bf91d` in the Phase 5.3 session (Claude Code, parallel agent). Amendment
3 — the Phase 5.3 SHIPPED ledger line itself — was deferred because the
Phase 5.3 lane was still mid-flight at the time of `b7bf91d`. It is now
ready to land, and the Phase 5.4 session is starting against the same
HEAD (`ef23456`), so this is the cleanest moment to amend the ledger
before Phase 5.4 closes.

The source of truth for the gate scorecard, commit chain, and surgical
fixes is `outputs/phase5_3_session_closeout.md` — particularly §1
(commit chain), §2 (gate scorecard with all 6 cleared), §3 (3 surgical
fixes: `cdf3d0c`, `7c994aa`, `f35d5e4`, plus `420f893`), and §4
(sustainability layer update).

---

## §2 What to change

### File 1 — `docs/STATE.md`

Add a new bullet under the heading `## Recently shipped (high signal)`
**immediately above the existing Phase 5.2 entry** (currently the first
bullet under that heading, beginning "Phase 5.2 — On the Water (Tier 1
data gathering) SHIPPED on origin (2026-05-15...").

The new bullet should follow the shape of the Phase 5.2 entry exactly —
single-line dense ledger entry with bold lead, gate scorecard, commit
chain, pytest baseline + alembic head, state-index pointer, CI note,
next-lane pointer. Concretely the entry should:

- Open `**Phase 5.3 — Home & Property Services (Tier 1 data gathering)
  SHIPPED on origin (2026-05-15/16, post-Phase-5.2)** — Third
  per-category sub-phase of the Phase 5 restructure. Dispatched at
  `f0a46f8` (Phase 5.3 kickoff) and closed at `bff4a79` (lint follow-up
  after `805a38c` SHIPPED) after 12 commits including three surgical
  fixes shipped mid-session (`cdf3d0c` places_discovery dry-run
  intersection bug, `7c994aa` sustainability layer extension for
  `home_services` domain, `f35d5e4` crowd_notes JSON-column
  double-encoding fix).`
- State **All 6 acceptance-gate items cleared:** with each item's final
  count + colour from `outputs/phase5_3_session_closeout.md` §2:
  - (1) 60+ entries → **230** post-load (Layer 1 Google Places only;
    home-property-services scope is single-layer per kickoff §1)
  - (2) Google ↔ existing-entity ambiguous reconciler hits reviewed →
    **75 reviewed** (9 cross-category + 66 same-category; 1 misroute
    flipped — Stanley Steemer)
  - (3) AZ ROC verification run completed for licensed sub-trades →
    **60 verified** (Cowork primary at `420f893` productionized the
    sub-trade allowlist filter + 15s no-results timeout for
    `az_roc_verify.py`)
  - (4) Top-10 by review count have long-form `crowd_notes` → **10**
    under the locked `{"short": str, "long"?: str}` JSON shape
  - (5) `heat_exposure` non-NULL on every entry → **0 NULL** (230 of
    230 set to `indoor` — mechanical sweep per kickoff §4)
  - (6) `/category/home-property-services` renders ≥15 per default
    filter → **230** (trivially met at gate-1 count)
- Include the **Phase 5.3 lane commit chain (12 commits):**
  `cdf3d0c → 7c994aa → d644739 → 420f893 → 6ef5ea8 (Cursor) → 30bff52
  (Cursor) → b7bf91d (Claude Code) → 98bc9aa (Claude Code) → e373714 →
  f35d5e4 → 805a38c (SHIPPED) → bff4a79 (lint follow-up)`
- Note **Pytest local baseline 1855 → 1882 collected** (+27 via Cursor
  dispatches at `6ef5ea8` + `30bff52` — 19 Phase 5.3 regression guards
  + 8 Phase 5.2 OSM regression guards carry-forward). Alembic head
  unchanged at `0a1b2c3d4e5f`.
- Add **State index for fresh-chat handoff:**
  `outputs/phase5_3_session_closeout.md`. Companion artifacts in
  `outputs/`: `apply_phase5_3_home_property_audit.py`,
  `apply_phase5_3_home_property_heat_exposure.py`,
  `apply_phase5_3_home_property_crowd_notes.py`,
  `phase5_3_home_property_pre_load_audit.md`,
  `phase5_3_gate_verification.py`.
- Add a brief **CI note** parallel to the Phase 5.2 entry's CI note:
  GitHub Actions was red across `805a38c`/`bff4a79`/`ef23456` due to a
  single failing test (`tests/test_phase5_az_roc_verify.py::test_az_roc_verify_marks_provider_and_name_cache`)
  whose fixture Providers lacked `google_primary_category` and were
  therefore excluded by the `420f893` sub-trade allowlist filter; fixed
  on the Phase 5.4 session's first commit (single-line `google_primary_category="plumber"`
  set on the test fixtures — pytest local baseline now consistently
  passes). Lint side cleared at `98bc9aa` (Claude Code, F401
  `EntityCategory`) and `bff4a79` (Cowork, F401 `json` + `Category` in
  crowd_notes apply-script).
- Close with **Next major data-gathering lane: Phase 5.4 (Health,
  Wellness & Care)** — in flight under Cowork primary (kickoff at
  `ef23456`; not gating Phase 5.3's SHIPPED status).

### File 2 — `docs/maintainability/master_build_plan.md`

Add the SHIPPED ledger line between **line 274** (the `#### Phase 5.3 —
Home & Property Services (~2-3 weeks)` header) and **line 278** (the
`#### Phase 5.4 — Health, Wellness & Care (~1-2 weeks)` header). Match
the shape of the Phase 5.2 entry at line 272 — single SHIPPED line with
gate scorecard + commit chain + close-out index, no extended retro
narrative (the retro narrative for Phase 5.3 lives in STATE.md and the
session close-out).

Concretely:

```
**SHIPPED `805a38c` 2026-05-15/16 (lint follow-up `bff4a79`)** — All 6
gate items cleared. Gate scorecard at close: (1) 60+ entries → **230**
post-load (Layer 1 Google Places only; single-layer scope per kickoff
§1); (2) Google ↔ existing-entity ambiguous reconciler hits reviewed →
**75 reviewed** (9 cross-category + 66 same-category, 1 Stanley Steemer
misroute flipped via apply-script); (3) AZ ROC verification completed
for licensed sub-trades → **60 verified** (Cowork primary
productionized the AZ ROC verifier at `420f893` — sub-trade allowlist
filter + 15s no-results timeout); (4) top-10 by review count have
long-form `crowd_notes` → **10** under the locked `{"short": str,
"long"?: str}` shape; (5) `heat_exposure` non-NULL on every entry →
**0 NULL** (230 indoor); (6) `/category/home-property-services` ≥15 →
**230**. Phase 5.3 dispatched at `f0a46f8` and closed at `bff4a79`
after 12 commits including three surgical fixes (`cdf3d0c`
places_discovery dry-run intersection, `7c994aa` sustainability layer
extension for `home_services` domain, `f35d5e4` crowd_notes JSON-column
double-encoding fix) and the `420f893` AZ ROC verifier
productionization. Phase-5.3-lane commit chain: `cdf3d0c → 7c994aa →
d644739 → 420f893 → 6ef5ea8 → 30bff52 → b7bf91d → 98bc9aa → e373714 →
f35d5e4 → 805a38c → bff4a79`. Close-out index:
`outputs/phase5_3_session_closeout.md`.
```

(Adjust the prose to match the project's house style — the goal is
parity with the line-272 Phase 5.2 entry, not character-for-character
mimicry. The numeric gate scorecard MUST match the source of truth in
`outputs/phase5_3_session_closeout.md` §2.)

---

## §3 Commit shape

Single commit, single author (Claude Code via Phase 6 lane).

```
docs(phase5): Phase 5.3 SHIPPED ledger entries -- master plan + STATE.md (Amendment 3)

Lands Amendment 3 of outputs/phase6_coordination_message.md (Amendments
1 + 2 shipped at b7bf91d 2026-05-15; Amendment 3 deferred because Phase
5.3 was still mid-flight). Adds Phase 5.3 SHIPPED ledger lines per
outputs/phase5_3_session_closeout.md §1+§2.

- docs/STATE.md: new "Phase 5.3 SHIPPED" bullet above Phase 5.2 bullet
- docs/maintainability/master_build_plan.md: SHIPPED line under §4
  Phase 5.3 header (line 274) -- parallel to the Phase 5.2 line at
  line 272

All 6 acceptance gate items cleared:
  60+ entries -> 230 / ambiguous reviewed -> 75 / AZ ROC verified -> 60
  / top-10 crowd_notes -> 10 / heat_exposure -> 0 NULL / category page -> 230

Phase 5.3 lane commit chain (12 commits): f0a46f8 -> bff4a79
Pytest local baseline: 1855 -> 1882 collected (Cursor +27 regression
guards at 6ef5ea8 + 30bff52). Alembic head unchanged at 0a1b2c3d4e5f.

State index for fresh-chat handoff: outputs/phase5_3_session_closeout.md
```

---

## §4 Out of scope

- **Do not modify** `outputs/phase5_3_session_closeout.md` or any other
  Phase 5 session artifact. They are session-archive — read-only after
  the session that authored them closes.
- **Do not modify** Phase 5.4 docs (`outputs/phase5_4_health_wellness_care_kickoff.md`
  or any 5.4 SHIPPED ledger lines) — Phase 5.4 is still in flight under
  Cowork primary in a parallel session. Adding Phase 5.4 SHIPPED to the
  ledger is the next Phase 6 amendment, after Phase 5.4 closes its gate.
- **Do not rewrite** the existing Phase 5.2 SHIPPED entry to mention
  Phase 5.3 — the line-272 master_build_plan entry and STATE.md
  Phase 5.2 entry already mention "Phase 5.3 — Home & Property Services"
  as the next dispatchable lane; that phrasing is fine to keep.
- **Do not invent** retroactive corrections. If the gate scorecard
  numbers in §2 above don't match `outputs/phase5_3_session_closeout.md`
  §2, surface the discrepancy to operator — don't pick a side.

---

## §5 Reference

- `outputs/phase5_3_session_closeout.md` — source of truth for the
  Phase 5.3 commit chain + gate scorecard + sustainability matrix.
- `outputs/phase6_coordination_message.md` — original Phase 6
  coordination message (Amendments 1 + 2 shipped, Amendment 3 deferred).
- `docs/STATE.md` — current ledger; line 148 has the Phase 5.2
  SHIPPED entry to model the shape after.
- `docs/maintainability/master_build_plan.md` — Phase 5.2 SHIPPED line
  at 272 is the immediate shape reference; Phase 5.3 sub-section header
  is at line 274.
- `outputs/phase5_3_gate_verification.py` — runnable proof that all 6
  gate items cleared (outputs "ALL 6 ITEMS CLEARED — READY TO SHIP").

---

## §6 Sequencing note

This dispatch is **parallel-eligible** with the Phase 5.4 lane currently
in flight under Cowork primary. The Phase 5.4 lane is touching
`scripts/`, `tests/`, `outputs/phase5_4_*.md`, `outputs/apply_phase5_4_*.py`,
`docs/scrape_logs/health-wellness-care_*.md`. This dispatch only touches
`docs/STATE.md` + `docs/maintainability/master_build_plan.md` +
(possibly) a new commit-history note in `outputs/phase6_coordination_message.md`
marking Amendment 3 as landed. **File-scope disjointness holds** per the
gotcha-#18 lock (Phase 6.1 ship-line).

The Phase 5.4 lane will land at least one commit before this dispatch
runs (the `tests/test_phase5_az_roc_verify.py` CI fix is the very first
Phase 5.4 commit). Claude Code should rebase against latest `origin/main`
before pushing.

---

*Drop-in dispatch artifact authored by Cowork primary, Phase 5 lane,
Phase 5.4 session (2026-05-16) pre-§1 scrape. Operator dispatches to
Claude Code at convenience. Lands Amendment 3 of
`outputs/phase6_coordination_message.md` — the final deferred amendment
from the Phase 5.3 session.*
