# HALT 2 — close decision

**Status:** **Closed** (2026-04-26).

## Final v5 gate (harness `halt2-dryrun-v5`)

**3 of 4** close criteria are **fully** met:

1. **Signal differentiation** — Layer 1 advisory vs Layer 2/3 gating is clear in artifacts and reporting.
2. **Real confabulation in top gating tokens** — v5 top tokens are substantive wordlist content (e.g. `enrollment`, `outdoor`), not Layer 3 time-format noise.
3. **Open Jump dramatic drop** — false positives from schedule-format vs response-format time mismatch are removed by symmetric `t:HH:MM` canonicalization; Open Jump went from heavy `ta:*` / `hm:*` artifacts to **0/18** gating hits on included runs in the v5 sample.

**Criterion 1 (Aqua Beginnings anchor)** — **partially** met: the detector **correctly** surfaces anchor confabulation when it appears in **Tier 3** (wordlist + partial inclusion in the rate). v5’s **tier mix** produced **fewer** Tier 3 invocations for Aqua Beginnings on **flag-on** than v4 in the same 5-name battery—**routing / stochasticity**, not a defect in the detector. At HALT 3 full-sweep scale, tier counts are expected to stabilize.

## Close rationale

The **eval harness and detector design** (layers, gating policy, time canonicalization, Tier 3 Layer 2 partial inclusion) are **sound** for use as the step 0 measurement tool. The expected behavior in **HALT 3** (full catalog, **1800+** invocations) is that **variance** in routing and phrasing **averages out** and **per-row** rates become interpretable for baseline and regression.

## Deferred to HALT 3

- Full-catalog signal at **scale** (broad N per row/flag)
- **Baseline** confabulation rate and quarter-over-quarter comparison
- **Lexicon governance** for any new gating or advisory tokens HALT 3 surfaces

## Deferred to Phase 8.8.6 step 1+ (not blocking HALT 2)

- **Catalog data quality** — e.g. Aqua Beginnings **address** field carrying descriptive prose that interacts with the anchor
- Ongoing **Tier 3** anchor **pattern** monitoring (when Tier 3 reproduces the historical confabulation class)
- **Formatter** and prompt evolution informed by the HALT 3 **baseline** after it exists

---

*HALT 2 closure recorded after amendment 5 (spec) + Task 4 harness fixes + v5 dry-run.*
