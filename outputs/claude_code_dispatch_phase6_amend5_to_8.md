# Claude Code dispatch — Phase 6 consolidated Amendments 5+6+7+8: Phase 5.5–5.8 SHIPPED ledger lines

> Drop-in artifact for the operator to paste into Claude Code terminal.
> Consolidates four deferred Phase 6 amendments (5, 6, 7, 8) into a
> single dispatch. Mirrors `outputs/claude_code_dispatch_phase6_amend6.md`
> shape but bundles four SHIPPED milestones in one commit per operator
> decision at Phase 5.9 §0 (defer all 4 to Phase 6 sidecar; Cowork
> primary stays focused on the Phase 5.9 data plane).
>
> **What this amendment does:** adds Phase 5.5 + 5.6 + 5.7 + 5.8 SHIPPED
> ledger entries to `docs/maintainability/master_build_plan.md` (§4
> Phase 5.5 / 5.6 sub-sections and NEW 5.7 / 5.8 sub-sections) and
> `docs/STATE.md` ("Recently shipped (high signal)" section, 4 new
> bullets above the existing Phase 5.4 bullet). Each phase landed all
> 6 (or 7 for 5.5) acceptance gate items cleared.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.9 session
> (2026-05-17) post-`4856020` (5.9 kickoff pre-stage). Operator
> dispatches at convenience — can run in parallel with Phase 5.9 lane
> (file-scope disjoint).

---

## §1 Context for Claude Code

Four consecutive Phase 5 sub-phase lanes shipped without their
corresponding Phase 6 amendments landing:

| Lane | SHIP commit | Date | Gates | Close-out doc |
|---|---|---|---|---|
| **Phase 5.5 — Auto, RV & Fuel** | `08d5ff3` | 2026-05-16 | 7/7 | `outputs/phase5_5_session_closeout.md` |
| **Phase 5.6 — Shopping, Grocery & Essentials** | `7609a01` | 2026-05-16 | 6/6 | `outputs/phase5_6_session_closeout.md` |
| **Phase 5.7 — Outdoors, Parks & Trails** | `e60b051` | 2026-05-17 | 6/6 | `outputs/phase5_7_session_closeout.md` |
| **Phase 5.8 — Events** | `2808146` | 2026-05-17 | 6/6 | `outputs/phase5_8_session_closeout.md` |

The pre-authored `claude_code_dispatch_phase6_amend5.md` and
`claude_code_dispatch_phase6_amend6.md` carry the same shape framing
but never landed (operator dispatch backlog). Amendments 7 and 8 were
never authored as standalone dispatch docs — this consolidated doc
replaces both.

Each lane's gate verification script outputs "ALL N ITEMS CLEARED —
READY TO SHIP" — proof-of-cleared at:

- `outputs/phase5_5_gate_verification.py` (7/7)
- `outputs/phase5_6_gate_verification.py` (6/6)
- `outputs/phase5_7_gate_verification.py` (6/6)
- `outputs/phase5_8_gate_verification.py` (6/6)

The source of truth for each phase's gate scorecard, commit chain, and
surgical sustainability fixes is the corresponding
`outputs/phase5_<N>_session_closeout.md`. **Claude Code agent should
Read each close-out's §1 + §2 sections to draft the STATE.md +
master_build_plan.md ledger lines.**

---

## §2 What to change

### File 1 — `docs/STATE.md`

Add **four new bullets** under the heading `## Recently shipped (high signal)`,
**inserted above the existing Phase 5.4 entry** (which is the current
top-of-section). Order chronologically: Phase 5.8 newest (top), then
5.7, then 5.6, then 5.5 (immediately above 5.4).

Each bullet follows the shape of the Phase 5.4 entry exactly — single-line
dense ledger entry with bold lead, gate scorecard, commit chain, pytest
baseline + alembic head, state-index pointer, CI note, next-lane
pointer.

**Gate scorecard sources** (pull authoritative numbers from each
close-out's §2):

- **Phase 5.5** — see `outputs/phase5_5_session_closeout.md` §2:
  1. 30+ entries in `auto-rv-fuel` → **140** (41 pre-existing + 99 net new; 4.7× target)
  2. Ambig reconciler hits reviewed (+ RV cross-list) → **76 reviewed, 0 misroutes, 0 RV flips**
  3. Layer-4 verifier surface → **Option C deferred to V1.5** (AZ MVD + AZCC documented)
  4. Top-10 long-form `crowd_notes` → **10**
  5. `is_mobile_service` non-NULL → **0 NULL** (126 False + 14 True)
  6. `heat_exposure` non-NULL → **0 NULL** (131 indoor + 9 outdoor)
  7. `/category/auto-rv-fuel` ≥15 → **140**
  Lane chain: `4d41944` (sustainability) → `[apply+audit]` → `08d5ff3` (SHIP).
  Pytest 1911 → 1920 (+9 in-lane via `_AUTO_KEYS` regression suite). Alembic head `0a1b2c3d4e5f`.

- **Phase 5.6** — see `outputs/phase5_6_session_closeout.md` §2:
  1. 40+ entries in `shopping-essentials` → **76 rendering** (83 total incl. 7 drafts; 1.90× target)
  2. Ambig reconciler hits reviewed (+ cat-9/cat-8 cross-list) → **177 reviewed, 0 misroutes, 0 cat-9/cat-8 flips**; catch-all edge-case review → **11 FLIPs + 7 DRAFTs + 13 KEEPs**
  3. Layer-4 verifier surface → **Option C deferred to V1.5** (AZ TPT + BBB documented)
  4. Top-10 long-form `crowd_notes` → **10**
  5. `heat_exposure` non-NULL → **0 NULL** of 83 (78 indoor + 5 outdoor)
  6. `/category/shopping-essentials` ≥15 → **76** (5.07× target)
  Note: 6 gate items (not 7) — `is_mobile_service` dropped per kickoff §6.
  Lane chain: `66e02c8` (kickoff) → `[sus-fix]` → `[apply+audit]` → `7609a01` (SHIP).
  Pytest 1920 → 1932 (+12 in-lane via `_RETAIL_KEYS` regression suite). Alembic head `0a1b2c3d4e5f`.

- **Phase 5.7** — see `outputs/phase5_7_session_closeout.md` §2:
  1. 20+ entries in `outdoors-parks-trails` → **26 rendering** (1.30× target; 6 pre-existing + 24 net new − 3 §2-FLIPped − 1 §2-DRAFTed)
  2. Ambig reconciler hits reviewed (+ 3 special audits) → **32 reviewed, 0 misroutes**; 3 FLIPs + 1 DRAFT
  3. Layer-4 verifier surface → **Option C deferred to V1.5** (AZ State Parks + NPS + LHC Parks & Rec documented)
  4. Top-10 long-form `crowd_notes` → **10** (100% snippet coverage in top-10)
  5. `heat_exposure` non-NULL → **0 NULL** of 27 (26 outdoor + 1 indoor — Altitude Trampoline Park)
  6. `/category/outdoors-parks-trails` ≥15 → **26** (1.73× target)
  Note: 6 gate items (not 7) — `is_mobile_service` dropped per kickoff §6.
  Lane chain (session 1 + 2): `f5d1062 → 1dfd28e (sustainability) → 0c011ae (narrow-label wrapper) → c2bdb6d (s1 hand-off) → 5f8fe08 (F541 fix) → e60b051 (SHIP) → 4b20e37 (SHA-cleanup)`.
  Pytest 1932 → 1946 (+14 in-lane via `1dfd28e` `_DISCOVERY_DOMAIN_FALLBACK` + `_PRIMARY_TYPE_MAP` extensions for `entertainment_attractions`). Alembic head `0a1b2c3d4e5f`.

- **Phase 5.8** — see `outputs/phase5_8_session_closeout.md` §2:
  1. 20+ entries in `events` → **20 rendering** (1.00× target; 2 pre-existing + 0 §1 net insert routed to cat-7 + 16 §2 Slice A NEW creates + 1 §2 Slice B-2 cross-cat move + 1 §2 Slice C DRAFT)
  2. Ambig reconciler hits reviewed (+ 3 special audits) → **33 reviewed, 0 misroutes**; 17 FLIPs + 1 DRAFT + 15 KEEPs; 3 special-axis sweeps (a) cat-7 (b) cat-13 (c) seasonal-activation all cleared
  3. Layer-4 verifier surface → **Option C deferred to V1.5** (AZ event aggregators + LHC Tourism Board documented)
  4. Top-10 long-form `crowd_notes` → **10** (100% snippet coverage in top-10)
  5. `heat_exposure` non-NULL → **0 NULL** of 20 (17 indoor + 3 outdoor — Buses By The Bridge, Desert Storm HQ, WORCS Racing)
  6. `/category/events` ≥15 → **20** (1.33× target)
  Note: 6 gate items (not 7) — `is_mobile_service` dropped per kickoff §6 (events are venue-based).
  Lane chain: `8dfa2a2 → 0b426e1 (sustainability) → f139be7 (narrow-label wrapper) → 2808146 (SHIP) → ffa9808 → 209e99f (SHA-cleanup)`.
  Pytest 1946 → 1964 (+18 in-lane via `0b426e1` `_PRIMARY_TYPE_MAP` 7 events primary_types). Alembic head `0a1b2c3d4e5f`.
  Notable §2 lesson: mid-apply Slice B-1 reclassification (Lake Havasu Museum of History initially miscoded as cat-6→cat-2 move; DB-verify confirmed no pre-existing cat-6 entity; reframed as Slice A NEW create — see close-out §4 for the audit-trail lesson).

Companion artifacts in `outputs/` for each phase (one block per
bullet): `phase5_<N>_*_audit.md`, `apply_phase5_<N>_*_audit.py`,
`apply_phase5_<N>_*_heat_exposure.py`, `apply_phase5_<N>_*_crowd_notes.py`,
`phase5_<N>_ambig_audit_dump.py`, `phase5_<N>_gate_verification.py`,
plus scrape logs at `docs/scrape_logs/<slug>_<YYYY-MM-DD>.md`.

**CI notes per phase** — all four phases shipped ✅ green at the SHIP
commit (occasional CI-flake X on duplicate runs per the 5.5/5.7/5.8
known pattern; the green run is authoritative). The sibling
`parks-rec-scrapes` cron continues ❌ on scheduled triggers — root
cause identified in Phase 5.7 §4.5 sidebar (Postgres FK constraint
violation in `scripts/parks_rec_prune.py`), handed off to Phase 6 /
sidecar lane. **NOT in scope** for this amendment.

**Next-lane pointers** (one per bullet):

- 5.5 → 5.6 dispatchable
- 5.6 → 5.7 dispatchable
- 5.7 → 5.8 dispatchable
- 5.8 → 5.9 (`classes-sports-recreation`) — in flight under Cowork primary at `4856020` kickoff pre-stage

### File 2 — `docs/maintainability/master_build_plan.md`

Add the SHIPPED ledger lines for each phase under their respective
sub-section header. **Two of the four sub-section headers don't exist
yet** — Phase 5.7 and 5.8 need new sub-section headers inserted.

**For Phase 5.5** (line ~286, header already exists): add a `**SHIPPED
\`08d5ff3\` 2026-05-16**` line directly under the header, before the
Phase 5.6 header. Mirror the Phase 5.4 line at line 284 for shape.
Pull gate scorecard from `outputs/phase5_5_session_closeout.md` §2.

**For Phase 5.6** (line ~290, header already exists): add a `**SHIPPED
\`7609a01\` 2026-05-16**` line directly under the header, before the
existing "Estimated totals at end of Phase 5" paragraph. Mirror shape.
Pull scorecard from `outputs/phase5_6_session_closeout.md` §2.

**For Phase 5.7** (NO header exists yet): insert a new `#### Phase 5.7
— Outdoors, Parks & Trails (~1-2 weeks)` sub-section header BEFORE the
"Estimated totals at end of Phase 5" paragraph. Header content should
include kickoff context: "Target 20+ entries. Google Places only.
Narrow scope: parks + golf courses + mini golf labels from
entertainment_attractions domain (3 of 10 labels; fitness_sports
deferred to V1.5 per HWC overlap)." Then add `**SHIPPED \`e60b051\`
2026-05-17**` line with scorecard from
`outputs/phase5_7_session_closeout.md` §2.

**For Phase 5.8** (NO header exists yet): insert a new `#### Phase 5.8
— Events (~1-2 weeks)` sub-section header AFTER the new Phase 5.7
header. Header content: "Target 20+ entries. Google Places only.
Narrow scope: 7 entertainment_attractions labels (event venues + live
music venues + art galleries + museums + movie theaters + bowling
alleys + arcades); parks/golf/mini-golf deferred since Phase 5.7
absorbed them." Then add `**SHIPPED \`2808146\` 2026-05-17**` line
with scorecard from `outputs/phase5_8_session_closeout.md` §2.

**Tone reference:** the Phase 5.4 SHIPPED line at line 284 is the
closest immediate shape mirror — single dense paragraph with bold lead,
each gate scorecard line embedded inline, lane commit chain, close-out
index pointer.

(Adjust prose to match the project's house style — the goal is parity
with the existing Phase 5.1 / 5.2 / 5.3 / 5.4 SHIPPED entries. The
numeric gate scorecards MUST match the source of truth in each phase's
close-out doc.)

---

## §3 Commit shape

**Single consolidated commit** — one author (Claude Code via Phase 6
lane). Lands all 4 amendments in one transaction since they're
file-scope disjoint and chronologically ordered.

```
docs(phase5): Phase 5.5-5.8 SHIPPED ledger entries -- master plan + STATE.md (Amendments 5-8 consolidated)

Lands Amendments 5+6+7+8 of the Phase 6 coordination message series
in one consolidated commit per Phase 5.9 §0 operator decision (defer
all 4 to Phase 6 sidecar; Cowork stays focused on 5.9 data plane).

Adds 4 SHIPPED ledger lines per the corresponding close-out docs:
  Phase 5.5 (Auto, RV & Fuel) at 08d5ff3 (2026-05-16) -- 7/7 gates
  Phase 5.6 (Shopping, Grocery & Essentials) at 7609a01 (2026-05-16) -- 6/6 gates
  Phase 5.7 (Outdoors, Parks & Trails) at e60b051 (2026-05-17) -- 6/6 gates
  Phase 5.8 (Events) at 2808146 (2026-05-17) -- 6/6 gates

- docs/STATE.md: 4 new bullets above the existing Phase 5.4 entry
  (newest at top: 5.8, 5.7, 5.6, 5.5)
- docs/maintainability/master_build_plan.md: SHIPPED lines under
  existing Phase 5.5 + 5.6 sub-section headers; NEW Phase 5.7 + 5.8
  sub-section headers + SHIPPED lines inserted before "Estimated
  totals at end of Phase 5"

All gate scorecards pulled authoritatively from each phase's
session_closeout.md §2 -- runtime evidence via the per-phase
gate_verification.py outputting "ALL N ITEMS CLEARED -- READY TO SHIP".

Pytest baseline progression: 1911 -> 1920 (5.5) -> 1932 (5.6) -> 1946
(5.7) -> 1964 (5.8). Alembic head unchanged at 0a1b2c3d4e5f across
all 4 lanes.

Coordinates with Phase 5.9 lane (in flight under Cowork primary at
4856020 kickoff pre-stage). File-scope disjoint per the gotcha-#18
lock (Phase 6.1 ship-line).
```

---

## §4 Out of scope

- **Do not modify** any `outputs/phase5_<N>_session_closeout.md`, audit
  doc, apply-script, or other Phase 5 session artifact. They are
  session-archive — read-only after the session that authored them
  closes.
- **Do not modify** Phase 5.9 docs or any in-flight 5.9 artifact. The
  5.9 lane is concurrently shipping under Cowork primary; coordinate
  by file-scope disjointness.
- **Do not** SHA-cleanup the `[SHIP-COMMIT]` placeholders in the
  pre-existing `claude_code_dispatch_phase6_amend5.md` /
  `_amend6.md` files. They're superseded by this consolidated
  dispatch; leaving them as-is preserves the audit trail.
- **Do not investigate** the `parks-rec-scrapes` cron failure. Root
  cause identified in Phase 5.7 §4.5 sidebar; handed off to separate
  Phase 6 / sidecar lane (3 fix options surfaced in
  `outputs/phase5_7_session_closeout.md` §3). Out of this dispatch's
  scope.
- **Do not invent** retroactive corrections. If the gate scorecard
  numbers above don't match the corresponding close-out doc, surface
  the discrepancy to operator — don't pick a side.

---

## §5 Reference

- `outputs/phase5_5_session_closeout.md` — Phase 5.5 final SHIPPED
  close-out.
- `outputs/phase5_6_session_closeout.md` — Phase 5.6 final SHIPPED
  close-out.
- `outputs/phase5_7_session_closeout.md` — Phase 5.7 final SHIPPED
  close-out.
- `outputs/phase5_8_session_closeout.md` — Phase 5.8 final SHIPPED
  close-out.
- `outputs/phase5_5_gate_verification.py` / `phase5_6_gate_verification.py` /
  `phase5_7_gate_verification.py` / `phase5_8_gate_verification.py` —
  runnable proof that each lane cleared its gates.
- `docs/STATE.md` — current ledger; the Phase 5.4 SHIPPED entry is the
  immediate shape reference.
- `docs/maintainability/master_build_plan.md` — existing Phase 5.5 +
  5.6 sub-section headers present; Phase 5.7 + 5.8 headers need
  creating per §2 above.
- `outputs/claude_code_dispatch_phase6_amend5.md` /
  `outputs/claude_code_dispatch_phase6_amend6.md` — pre-existing
  pre-SHA-cleanup dispatch docs; superseded by this consolidated
  dispatch. Leave as-is (audit trail).
- `docs/scrape_logs/auto-rv-fuel_2026-05-16.md` /
  `shopping-essentials_2026-05-16.md` /
  `outdoors-parks-trails_2026-05-17.md` / `events_2026-05-17.md` —
  per-lane scrape logs.

---

## §6 Sequencing note

This dispatch is **parallel-eligible** with the in-flight Phase 5.9
lane (Cowork primary). The Phase 5.9 lane touches `scripts/`, `tests/`,
`app/contrib/`, `outputs/phase5_9_*`, `docs/scrape_logs/
classes-sports-recreation_*.md`. This dispatch only touches
`docs/STATE.md` + `docs/maintainability/master_build_plan.md`.
**File-scope disjointness holds** per the gotcha-#18 lock (Phase 6.1
ship-line).

Like Amendments 4 and 5, the operator may choose to land this
consolidated amendment **in-line** at a future Phase 5.x SHIPPED
commit rather than via Claude Code parallel dispatch — particularly
if the 5.9 lane is the natural place to consolidate. Either path is
valid; the artifact above describes the dispatch shape for either
operator. **Coordinate with the in-flight 5.9 lane before landing**
to avoid ledger-line race conditions on `STATE.md` /
`master_build_plan.md`.

---

*Drop-in dispatch artifact authored by Cowork primary, Phase 5 lane,
Phase 5.9 session (2026-05-17) post-`4856020` (5.9 kickoff pre-stage).
Operator dispatches to Claude Code at convenience (or lands in-line
per Amendment 4/5 precedent). Consolidates four deferred amendments
(5+6+7+8) per operator decision at Phase 5.9 §0.*
