# Lane M — V1.5 triage §8 #2 decision lock: re-tag 5.8 event aggregators V1.5 → Phase 9

> **What this is:** the paste-ready decision-lock artifact for V1.5 carry inventory triage §8 #2 — the recommendation to re-tag carry #8 (5.8 visitarizona.com + golakehavasu.com event aggregators) from "V1.5 — defer" to "Phase 9 — absorbed". Phase 9's event-source research confirms golakehavasu.com IS Source 2 of the 5 GREEN-locked Phase 9 sources, so the absorb is natural for GLH. **visitarizona.com is a sub-case the operator must decide** (it was not researched in the Phase 9 sub-agent sweep).
>
> **Author:** Cowork primary, post-`1e3f291` next-session pickup.
>
> **Effort:** ~5 min decision-lock + ~3 min patch-language apply + ~2 min commit = **~10 min total**.
>
> **Companion docs:** `outputs/v1_5_carry_inventory_triage.md` §2 (carry table) + §6 (subtotal) + §7 (cross-reference) + §8 #2 (recommendation); `outputs/phase_9_event_source_research.md` (the 5 GREEN-locked Phase 9 sources); `outputs/phase5_8_session_closeout.md` §3 (the 5.8 origin of the V1.5 defer).

---

## §1 Decision context

The triage doc currently inventories carry #8 as:

> | 8 | 5.8 | visitarizona.com + golakehavasu.com event aggregators (cat-2) | ~2–4h | **V1.5 — defer** | Phase 9 (Events) absorbs this naturally — RRULE-based event scraper subsystem is the right home, not a V1.5 retrofit. **Recommend: re-tag as Phase 9, not V1.5.** |

§8 #2 recommends:

> 2. **Re-tag carry #8 (5.8 event aggregators) from V1.5 to Phase 9.** Phase 9's RRULE-based event scraper subsystem is the right home for visitarizona.com + golakehavasu.com scrapes, not a V1.5 retrofit. Update `outputs/phase5_8_session_closeout.md` §6 to reflect this if the operator agrees. **Operator-decide.**

The Phase 9 sub-agent research (`outputs/phase_9_event_source_research.md`) locked **5 GREEN event sources** at canonical URLs:

| # | Source | Platform | Disposition |
|---|---|---|---|
| 1 | Lake Havasu Area Chamber of Commerce | GrowthZone microdata + JSON-LD | GREEN |
| 2 | **Go Lake Havasu (golakehavasu.com)** | **Simpleview JSON-LD** | **GREEN** |
| 3 | RiverScene Magazine | WordPress RSS | GREEN |
| 4 | LHC Library (= Mohave County) | Trumba iCal | GREEN |
| 5 | City of Lake Havasu City | CivicPlus RSS+iCal (meeting-focused; possible reframe) | GREEN |

**Gap surfaced by cross-check:** visitarizona.com is **NOT among the 5 researched sources**. The triage carry #8 lumped visitarizona.com + golakehavasu.com together, but the Phase 9 sub-agent sweep only researched + locked golakehavasu.com. visitarizona.com's scrape-feasibility is therefore unknown at this point.

This makes a flat "re-tag #8 to Phase 9" oversimple — splitting is more honest.

---

## §2 Three options for the operator

### Option A — Re-tag both to Phase 9 (with visitarizona.com as an unconfirmed 6th source)

- golakehavasu.com → Phase 9 Source 2 (already in scope; natural absorb)
- visitarizona.com → Phase 9 Source 6 candidate (Phase 9 dispatch needs an amendment to the wrapper at `outputs/cursor_dispatch_prompt_phase_9.md` to either research+add it or explicitly drop it during Cursor's §0 audit)

**Trade-off:** Slight scope creep on Phase 9 (5 → 6 sources). Effort estimate for Phase 9 ticks up ~3-4h if visitarizona.com's scrape is GREEN-equivalent; ~0h if it's RED and dropped during §0 audit.

### Option B — Split: GLH → Phase 9; visitarizona.com → retain V1.5 (recommended)

- golakehavasu.com → Phase 9 Source 2 (natural absorb)
- visitarizona.com → V1.5 — defer (with explicit note "may upgrade to Phase 9 source #6 if future research confirms scrape-feasibility")

**Trade-off:** Cleanest. Honors the Phase 9 sub-agent research's actual scope (5 sources GREEN-locked; not 6). visitarizona.com stays inventoried as a V1.5 carry until someone does the scrape-feasibility research. Carry #8 splits into 8a (GLH-Phase-9) + 8b (visitarizona-V1.5).

**Recommendation:** This is the most evidence-grounded path. Phase 9 absorbs what the research confirmed; visitarizona.com remains explicit V1.5 with an upgrade hook.

### Option C — Re-tag both to Phase 9 + drop visitarizona.com explicitly

- golakehavasu.com → Phase 9 Source 2 (natural absorb)
- visitarizona.com → dropped (state-level tourism aggregator; coverage of LHC-local events likely low; effort/yield ratio unfavorable for V1)

**Trade-off:** Most aggressive narrowing. Defensible if the operator believes visitarizona.com would have ~10-20% LHC-local event yield (state-level DMOs typically don't deep-cover small cities). Removes a carry entirely rather than deferring it.

---

## §3 Paste-ready patch language (per option)

> Apply the patches for the option you pick. All 3 options touch the same 4 files; the differences are in the carry-table row + cross-reference language.

### §3.1 Common patches (all three options)

**File:** `outputs/v1_5_carry_inventory_triage.md`

**Patch 1 — line ~56 subtotal:**

Find:

> **Subtotal:** 15 carries; 14 V1.5 — defer (including #8 with a re-tag-to-Phase-9 recommendation per §8 #2); 1 Drop/closed (#14). Total V1.5 effort ~35–60h.

Replace with the appropriate option's subtotal language below.

**Patch 2 — line ~149 cross-reference paragraph (after the inventory tables):**

Find:

> **Re-tag recommendation:** #8 (5.8 visitarizona.com + golakehavasu.com event aggregators) is currently labeled V1.5 — defer in §2 but §8 #2 recommends re-tagging to Phase 9 (event scraper subsystem absorbs it naturally). Pending operator decision.

Replace with the appropriate option's cross-reference language below.

**Patch 3 — line ~157 §8 #2:**

Find:

> 2. **Re-tag carry #8 (5.8 event aggregators) from V1.5 to Phase 9.** Phase 9's RRULE-based event scraper subsystem is the right home for visitarizona.com + golakehavasu.com scrapes, not a V1.5 retrofit. Update `outputs/phase5_8_session_closeout.md` §6 to reflect this if the operator agrees. **Operator-decide.**

Replace with the appropriate option's §8 #2 language below (it becomes a "locked" entry, not a "recommend" entry).

**Patch 4 — line ~47 carry-table row:**

Find:

> | 8 | 5.8 | visitarizona.com + golakehavasu.com event aggregators (cat-2) | ~2–4h | **V1.5 — defer** | Phase 9 (Events) absorbs this naturally — RRULE-based event scraper subsystem is the right home, not a V1.5 retrofit. **Recommend: re-tag as Phase 9, not V1.5.** |

Replace with the appropriate option's row language below.

### §3.2 Option B specifics (recommended)

**Patch 4 (row) — replace with:**

> | 8a | 5.8 | **golakehavasu.com event aggregator (cat-2)** | n/a | **Phase 9 — absorbed (Source 2)** | Confirmed as Phase 9 Source 2 (Simpleview JSON-LD) per `outputs/phase_9_event_source_research.md` §Source 2 GREEN. Phase 9 dispatch consumes this; no separate V1.5 work. |
> | 8b | 5.8 | **visitarizona.com event aggregator (cat-2)** | ~1–2h | **V1.5 — defer** | NOT among the 5 Phase 9 GREEN-locked sources; scrape-feasibility unresearched. **May upgrade to Phase 9 Source 6 if scrape research confirms ≥10% LHC-local yield;** else retain V1.5 — defer or drop during V1.5 sweep. |

**Patch 1 (subtotal) — replace with:**

> **Subtotal:** 15 carries (16 after #8 splits into #8a + #8b); 13 V1.5 — defer (including #8b with a possible Phase 9 upgrade hook); 1 Phase 9 — absorbed (#8a, GLH = Phase 9 Source 2); 1 Drop/closed (#14). Total V1.5 effort ~33–58h.

**Patch 2 (cross-reference) — replace with:**

> **Re-tag locked [YYYY-MM-DD]:** #8 split into #8a (golakehavasu.com → Phase 9 Source 2, naturally absorbed) + #8b (visitarizona.com → V1.5 — defer with possible Phase 9 Source 6 upgrade hook). Phase 9 sub-agent research at `outputs/phase_9_event_source_research.md` confirmed GLH as Source 2 GREEN; visitarizona.com was not in that research scope. **§8 #2 closed.**

**Patch 3 (§8 #2) — replace with:**

> 2. **#8 split locked [YYYY-MM-DD]:** carry #8a (golakehavasu.com) re-tagged Phase 9 — absorbed (Source 2 per `outputs/phase_9_event_source_research.md`). Carry #8b (visitarizona.com) retained V1.5 — defer with Phase 9 Source 6 upgrade hook. Triage table §2 + subtotal §6 + cross-reference §7 all patched. **CLOSED.**

**Additional file:** `outputs/phase5_8_session_closeout.md`

**Patch 5 — line ~148-151 (the V1.5 pickup note):**

Find:

> Operator picked Option C at kickoff — no Layer-4 verifier built for
> 5.8. visitarizona.com + golakehavasu.com paths documented for V1.5
> pickup in the audit doc + kickoff §3.

Replace with:

> Operator picked Option C at kickoff — no Layer-4 verifier built for
> 5.8. **Re-tag locked [YYYY-MM-DD] per V1.5 triage §8 #2 lock:** golakehavasu.com → Phase 9 Source 2 (absorbed); visitarizona.com → V1.5 — defer with Phase 9 Source 6 upgrade hook. See `outputs/lane_m_retag_5_8_aggregators_decision_lock.md` for the full decision-lock memo.

### §3.3 Option A specifics

**Patch 4 (row):**

> | 8 | 5.8 | visitarizona.com + golakehavasu.com event aggregators (cat-2) | n/a | **Phase 9 — absorbed** | GLH confirmed as Phase 9 Source 2 (Simpleview JSON-LD) per research doc. visitarizona.com added as Phase 9 Source 6 candidate; Cursor §0 audit during Phase 9 dispatch confirms scrape-feasibility or drops it. |

**Patch 1 (subtotal):**

> **Subtotal:** 15 carries; 13 V1.5 — defer; 1 Phase 9 — absorbed (#8); 1 Drop/closed (#14). Total V1.5 effort ~33–58h.

**Patch 2 (cross-reference):**

> **Re-tag locked [YYYY-MM-DD]:** #8 re-tagged Phase 9 — absorbed in full. GLH = Phase 9 Source 2 (confirmed GREEN); visitarizona.com = Phase 9 Source 6 candidate (unresearched; Cursor §0 audit resolves). **§8 #2 closed; Phase 9 wrapper needs Source 6 amendment.**

**Patch 3 (§8 #2):**

> 2. **#8 lock [YYYY-MM-DD]:** re-tagged Phase 9 — absorbed. GLH = Source 2 (research-confirmed GREEN); visitarizona.com = Source 6 candidate. Phase 9 wrapper at `outputs/cursor_dispatch_prompt_phase_9.md` needs amendment to either research visitarizona.com or drop during Cursor §0. **CLOSED.**

**Phase 9 wrapper amendment (required for Option A):** add a §0 audit step for visitarizona.com — "Confirm scrape-feasibility via `nimble:nimble-web-expert` or equivalent; if GREEN, add as Source 6; if RED, document drop reason and continue with 5 sources."

### §3.4 Option C specifics

**Patch 4 (row):**

> | 8 | 5.8 | golakehavasu.com event aggregator (cat-2) | n/a | **Phase 9 — absorbed (Source 2)** | Confirmed as Phase 9 Source 2 (Simpleview JSON-LD) per research doc. visitarizona.com originally bundled with #8 but dropped at lock per Option C — state-level DMO; LHC-local yield expected <10%. |

**Patch 1 (subtotal):**

> **Subtotal:** 14 carries (#8 narrowed; visitarizona.com dropped at re-tag lock); 13 V1.5 — defer; 1 Phase 9 — absorbed (#8); 1 Drop/closed (#14). Total V1.5 effort ~33–58h.

**Patch 2 (cross-reference):**

> **Re-tag locked [YYYY-MM-DD]:** #8 narrowed to GLH only → Phase 9 Source 2 (absorbed). visitarizona.com dropped at lock — state-level tourism DMO; LHC-local event yield expected <10%; not worth V1 or V1.5 effort. **§8 #2 closed.**

**Patch 3 (§8 #2):**

> 2. **#8 lock [YYYY-MM-DD]:** narrowed to GLH-only and re-tagged Phase 9 — absorbed (Source 2 per research doc). visitarizona.com explicitly dropped (state-level DMO; LHC-local yield <10%). **CLOSED.**

---

## §4 Phase 9 wrapper cross-reference (Option A only)

If Option A is picked, the Phase 9 wrapper at `outputs/cursor_dispatch_prompt_phase_9.md` needs a §0-audit amendment to research visitarizona.com's scrape-feasibility before §1 Source-2-through-N scrape implementation begins. Suggested amendment (insert in §0 prereq audit):

> **§0.X visitarizona.com source-6 feasibility audit (if §8 #2 locked Option A):**
> Use `nimble:nimble-web-expert` or `mcp__Claude_in_Chrome__navigate` to fetch `https://www.visitarizona.com/events/` (or the LHC-filtered subset URL). Confirm: (a) list page renders server-side with event detail links; (b) detail pages include schema.org JSON-LD `@type: Event` with `startDate`/`endDate`/`location`; (c) LHC-filtered yield ≥10% of total events on page-1. If all 3 confirm GREEN, add as Source 6 in §1.6; cadence Daily 05:00 LHC local (offset from Sources 1-5). If any fail RED, document the drop reason in §13 deviations and continue with 5 sources.

Options B and C require no Phase 9 wrapper amendment.

---

## §5 Commit suggestion

For Option B (recommended):

```
git add outputs/v1_5_carry_inventory_triage.md outputs/phase5_8_session_closeout.md
git commit -m "docs(triage): §8 #2 lock -- split carry #8 (GLH→Phase 9 Source 2 absorbed; visitarizona→V1.5 retained with upgrade hook)"
git push
```

For Option A (adds Phase 9 wrapper amendment):

```
git add outputs/v1_5_carry_inventory_triage.md outputs/phase5_8_session_closeout.md outputs/cursor_dispatch_prompt_phase_9.md
git commit -m "docs(triage+phase9): §8 #2 lock -- re-tag #8 to Phase 9 absorbed; wrapper §0 adds visitarizona Source 6 feasibility audit"
git push
```

For Option C:

```
git add outputs/v1_5_carry_inventory_triage.md outputs/phase5_8_session_closeout.md
git commit -m "docs(triage): §8 #2 lock -- #8 narrowed to GLH→Phase 9 Source 2 absorbed; visitarizona dropped (state-level DMO; <10% LHC yield)"
git push
```

All three options: docs-only commit; no code changes; alembic head unchanged at `c9d0e1f2a3b4`; pytest count unchanged.

---

## §6 Carries forward (post-lock)

Once Lane M closes regardless of option, the V1.5 triage §8 #2 carry is **CLOSED**. The remaining §8 items are:

- §8 #1 (sustainability extensions) — **CLOSED via CC `a4260ce`** 2026-05-20
- §8 #2 (5.8 aggregators re-tag) — **closes via this Lane M lock**
- §8 #3 (7 V1-operator-action items) — Lane L, partial closure via sub-agent research (`outputs/operator_action_items_research_findings.md`)
- §8 #4 (Phase 13 V1.5 carry-forward) — **CLOSED via CC `f168c52`** 2026-05-20
- §8 #5 (Layer-4 verifier bundle priority) — V1.5 ranking documented; no action gate

Post-Lane-M, §8 closure scorecard: **4 of 5 §8 items closed; only §8 #3 remains** (Lane L work).

---

*Authored by Cowork primary at the post-`1e3f291` Lane M pre-staging step. Lives at `outputs/lane_m_retag_5_8_aggregators_decision_lock.md`. Self-contained paste-ready package; operator picks A/B/C + applies the corresponding §3 patches + commits per §5. Closes V1.5 triage §8 #2.*
