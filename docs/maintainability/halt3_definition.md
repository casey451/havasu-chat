# HALT 3 — Definition + Close Criteria

**Source:** `ask-hava-detailed-plan.docx` (off-tree strategy doc at repo root, May 2026, "Prepared for Casey · Lake Havasu City"). Recovered into on-tree on 2026-05-09 evening per BACKLOG #53.

**Scope of this doc:** captures HALT 3's *definition* and *close-criteria framework*, NOT specific numeric thresholds. The strategy doc explicitly defers thresholds to the close-out itself — they are computed from baseline measurements during HALT 3 close, not pre-stated.

---

## §1 — What HALT 3 is

HALT 3 is the **closure milestone for the confabulation harness** at `app/eval/confabulation_*.py`. The strategy doc treats it as the keystone of the Trust Pipeline ("the moat"): hallucination prevention is what makes Hava's 1–3-sentence answer format defensible, since "every wrong answer is loud" in that format.

From the strategy doc §1.1 "Hallucination prevention — extending HALT 3":

> "HALT 3 / Tier 2 formatter / confabulation harness work continues to closure. Two extensions to scope now:
>
> - **Negative-set evaluation.** A curated set of queries whose correct answer is 'I don't know' or 'no current match' — closed businesses, cancelled events, services Havasu does not have. Confabulation rate on negative sets is a sharper signal than gating rate alone.
>
> - **Per-category anchor regression with calibrated thresholds.** A wrong restaurant recommendation is recoverable. A wrong emergency plumber recommendation at 11pm is not. Higher-stakes categories warrant tighter gating; this is a per-category band, not a global one."

## §2 — The three close-criteria bands

The Phase 1 close criteria require:

> "Close HALT 3 with documented gating-rate, anchor-regression, catalog-flagging bands."

The three bands are:

1. **Gating rate** — the headline metric. Per `docs/confabulation-eval-runbook.md`, denominator is `Tier 2 always` + `Tier 3 only when Layer 2 fires`. Tier 1 is excluded (`tier_1_no_formatter`); Tier 3-no-L2 is excluded (`tier_3_no_layer2_hits`).
2. **Anchor / regression** — surfaced via the harness `summary.md` "regression anchors (gating only)" mechanism. **Per-category**, with tighter thresholds for emergency / high-stakes categories.
3. **Catalog-flagging** — per `per_row.csv` (`gating_runs_with_hit`, `top_3_gating_tokens`) — flags rows in the catalog that the harness identifies as confabulation-prone.

**CRITICAL — thresholds are set during close, not pre-stated.** The strategy doc explicitly says:

> "Confabulation rate on negative-set evals below threshold (set during HALT 3 close)."

> "Catalog data-quality flag rate below acceptable band on top-50 enriched businesses."

Neither sentence names a specific percentage. There is no "<5% confabulation rate" or similar in the strategy doc. **HALT 3 close is itself a calibration exercise** — the first step is to run the harness on baseline conditions, then use the results to set bands at acceptable levels for ongoing monitoring.

## §3 — Sequencing constraints

From the strategy doc:

> "**Sequencing constraint:** anchor regression on an empty providers table grades the routing layer on a fictional load. Per-category bands cannot be calibrated until the enrichment sprint (§2.2) populates the table. Phase 1 close gates these together, not in parallel."

Practical consequences:

1. **Enrichment sprint must complete before anchor regression can be calibrated.** The 50-business operator enrichment sprint (top-queried categories: restaurants, plumbers, HVAC, pool service, boat repair, urgent care, auto repair) populates `Provider.last_verified_at` and gives the harness real rows to grade.
2. **Disclosure renderer must be in production for the sponsored-disclosure portion of the eval (per Decision #37).** Renderer is shipped behind `FEATURE_FLAG_DISCLOSURE_RENDERER` (OFF as of 2026-05-09; flag flips after enrichment populates Sponsor + matching Provider rows).
3. **CT flag must be on for ≥1 week of production traffic** before harness baselines reflect production reality. CT was re-enabled on 2026-05-09 evening per BACKLOG #47/#48/#49 close. Earliest meaningful baseline run: **2026-05-16**.

## §4 — Phase 1 close criteria (HALT-style) — full list from strategy doc

These are *all* the Phase 1 close criteria. Items adjacent to HALT 3 are bundled into the same gate:

| Criterion | Source threshold | Status as of 2026-05-09 evening |
|---|---|---|
| Confabulation rate on negative-set evals | "below threshold (set during HALT 3 close)" | ⏳ requires enrichment + ≥1 week traffic + harness baseline run |
| Disclosure compliance on sponsored-eligible eval queries | **100%** | ⏳ disclosure renderer shipped (Lane S2); eval harness pending Lane 4 / P2.OBS.1 |
| Tone-rule violations on sponsored-eligible eval queries | **Zero** | ⏳ same as above |
| Catalog data-quality flag rate on top-50 enriched businesses | "below acceptable band (set during HALT 3 close)" | ⏳ depends on enrichment sprint |
| Event catalog active sources contributing weekly | **At least 5** | ⏳ verify via `data/events.db` query |
| Tier 1 hit rate on representative chat traffic, 7-day window post-enrichment | **>25%** | ⏳ requires enrichment + measurement |
| UI-data-correctness audit | **Zero** raw enum slugs / placeholder phone numbers / pre-dawn events under `Tonight` | ✓ shipped 2026-05-08 (Lanes A/B/C + Sponsor Phase 2B migration) |

**Per-criterion footnote on Tier 1 hit rate (>25%):** the strategy doc adds a critical policy clause —

> "If it doesn't, the gap is routing/classifier, not catalog — open a new investigation rather than treating Phase 1 as closed."

## §5 — Phase 1 deliverables already shipped (related to HALT 3)

From the strategy doc "Phase 1 deliverables" section:

- ✓ Stale-data detection rules document — `docs/maintainability/disclosure_renderer_spec.md` + Lane S1 schema + Lane CT1/CT2.A/CT2.B confidence-tier classifier (2026-05-08).
- ✓ `disclosure_render.py` module + test suite — Lane S2 (2026-05-08).
- ✓ Audience signal column on `chat_logs` + dashboard — Lane S3 + S1 column (2026-05-08); dashboard pending.
- ✓ Confidence-tier formatter spec + production rollout — Lane CT1/CT2.A/CT2.B (2026-05-08); flag re-enabled 2026-05-09 evening after Lane 1 #47/#48/#49 close.
- ⏳ HALT 3 review artifact — strategy doc says "already in flight" as of May 2026; the only on-disk artifact is `relay/halt3-step1-runs-excerpts.txt` (raw probe captures, no §Outcome).
- ⏳ Disclosure-policy eval harness extension and v1 results — corresponds to Lane 4 / P2.OBS.1 in the dispatch playbook.
- ⏳ Event aggregation pipeline build — partially shipped (parks-rec WebTrac + Aquatic Center on 2026-05-07); rest pending.
- ⏳ Catalog enrichment SOP for ongoing additions — toolchain shipped 2026-05-08 (`templates/enrichment/` + `scripts/ingest/`); operator workflow ongoing.

## §6 — Sequenced work-to-close

1. **Operator enrichment sprint completion** (Casey-driven; ~weeks). Top-queried categories. Toolchain ready: `templates/enrichment/business_enrichment_template.csv` → `scripts/ingest/validate_enrichment_csv.py` → `scripts/ingest/ingest_enrichment_csv.py --apply`.
2. **`FEATURE_FLAG_DISCLOSURE_RENDERER` flag flip** to true once enrichment populates ≥1 Sponsor + matching Provider rows. (CT flag is already on as of 2026-05-09 evening.)
3. **≥1 week of production traffic with both flags on** for harness baselines to reflect reality. Earliest meaningful baseline run: 1 week after the disclosure-renderer flag flip.
4. **Run the confabulation harness end-to-end** with the enriched catalog and live traffic patterns: `python scripts/confabulation_eval.py --mode=inprocess --runs=3 --flags=both --rows=both`. Generates `summary.md` + `per_row.csv` + `runs.jsonl`.
5. **Set the three bands** from the baseline output — these become the Phase 1 close thresholds:
   - Gating rate threshold (global default + per-category for emergency / high-stakes categories).
   - Anchor regression threshold per category (tighter for emergency, looser for restaurants).
   - Catalog-flagging band on top-50 enriched businesses.
6. **Run the negative-set evaluation extension** — curate ~30–50 "I don't know / no current match" queries and grade confabulation rate on the negative set.
7. **Author the close-out artifact** at `docs/maintainability/halt3_closeout.md` with §Outcome filled — pass/fail per band against the calibrated thresholds plus negative-set rate.
8. **Append RESOLVED** to `docs/BACKLOG.md` #53 + `docs/STATE.md` close-out entry.
9. **Then dispatch P2.PREM.1** (Premier inventory open) — gated on HALT 3 close + Decision #37 (renderer in production with §4 harness green).

## §7 — Decision #37 clarification

The morning HALT 3 audit referenced "Decision #37" from the strategy doc as the source of the HALT 3 definition. Reading the docx Appendix:

> **Decision #37 (New):** Confirm the deterministic disclosure renderer is a Phase 1 close gate for Premier inventory — i.e., Premier does not open until §4 harness is green and the renderer is in production.

Decision #37 is about the **disclosure renderer's Premier-gating role**, NOT specifically the HALT 3 bands. The audit was correct to point at this decision (it's the canonical "Premier blocked on Phase 1 close" gate), but the definition recovery for HALT 3 itself comes from §1.1 ("Hallucination prevention — extending HALT 3") and the Phase 1 close-criteria section in the docx, not Decision #37.

## §8 — Related missing artifacts (orthogonal but worth tracking)

- **`relay/halt1-closure-final-lexicons.md`** — (closed via #54 — references stripped from `app/eval/confabulation_detector.py` and `confabulation_query_gen.py`; lexicons documented inline as Python constants)
- **Phase 8.8.6 spec markdown** — pruned per `docs/STATE.md`:215; possibly recoverable via `git log --all --diff-filter=D -- 'docs/**phase*8*'`.
- **HALT 1 and HALT 2 closure docs** — neither exists on disk. The "HALT 1 governance: owner-reviewed, append-only style updates, no silent drift" pattern is referenced in `docs/confabulation-eval-runbook.md` but no closure artifact remains.

## §9 — Sources

- `ask-hava-detailed-plan.docx` (off-tree, repo root, May 2026):
  - Executive Summary "Sequencing in Five Moves" §1
  - §1.1 "Hallucination prevention — extending HALT 3"
  - §1.2 "Stale-data detection at the record level"
  - "Phase 1 close criteria (HALT-style)" section
  - "Phase 1 deliverables" section
  - Appendix "Decisions Required" — Decision #37 + Decision #38
- `docs/confabulation-eval-runbook.md` — gating rate methodology + harness invocation.
- `docs/components/confabulation_detector.md` and `confabulation_query_gen.md` — code-level harness component docs.
- `relay/halt3-step1-runs-excerpts.txt` — only on-disk HALT 3 artifact (raw run captures, no §Outcome).
- `docs/SESSION_HANDOFF_2026-05-09_evening.md` §5 — HALT 3 audit findings.
- `docs/BACKLOG.md` #53 — original audit ticket; references this file for the recovered definition.

---

*This document recovers the HALT 3 definition and close-criteria framework from the off-tree strategy doc into on-tree authoritative form. Specific numeric thresholds are intentionally not stated — they are calibrated during HALT 3 close from baseline measurements per the strategy doc's explicit guidance. The next agent who needs to close HALT 3 should read this doc + run the sequenced work-to-close in §6.*
