# Phase 2 Lane Decomposition Spec

**Status:** OPEN — drafted 2026-05-09 (morning, post Phase 1 close including Backlog #46).
**Audience:** operator (Casey) + any agent (Cursor / Claude Code / Cowork primary / general-purpose) dispatched against a Phase 2 lane.
**Source-of-truth references:** `ask-hava-detailed-plan.docx` Phase 2 + Appendix; `docs/STATE.md` 2026-05-09 morning entry; `docs/maintainability/disclosure_renderer_spec.md` §5, §7.2; `docs/maintainability/confidence_tier_integration_spec.md` §5; `docs/BACKLOG.md` #2, #18, #39, #45 (and #46 RESOLVED reference).

---

## 1. One-paragraph summary

Phase 2's strategic objective is **visitor-mode go-live + monetization activation** on top of the Phase 1 keystones that just shipped (deterministic disclosure renderer X1+X2+X2.1 behind a flag, audience-signal logging S1+S3+S3.1 persisting to `chat_logs.audience_signal`, confidence-tier formatter CT1+CT2.A+CT2.B with phone post-process #42, `/home` UI data-correctness pass). Phase 2 pulls the levers Phase 1 wired but left at default-off: flip the renderer flag and bake 4–6 weeks of audience-signal data; extend the renderer to the Tier 2 LLM-formatter path (Lane X3) and thread audience signal into placement-regime selection (Backlog #39); open Premier-tier inventory on a now-defensible sponsored surface; launch the Airbnb host welcome-card distribution test with a SQL conversion metric defined against `chat_logs` *before* cards print; close the operator-side preconditions (50-business + 30-tourism enrichment sprint, HALT 3 review, `verification_method` CHECK expansion #45). Per the strategy doc, Phase 2 explicitly does **not** scale paid customer counts (Phase 3) and does **not** ship a separate visitor mode product (Phase 4 conditional on Phase 2 data).

---

## 2. Lane inventory

| ID | Title | Effort | Dependencies | Agent type | Preconditions |
|---|---|---|---|---|---|
| **P2.OPS.1** | Phase 1 flag flip + post-deploy soak | S | none (Phase 1 already deployed) | operator + Cowork primary | runbook executed; both `FEATURE_FLAG_DISCLOSURE_RENDERER` and `FEATURE_FLAG_CONFIDENCE_TIER` flipped to `true` in Railway |
| **P2.OPS.2** | HALT 3 close-out review | M | P2.OPS.1 | operator + Claude Code (audit) | one week of flag-on production traffic; gating-rate / anchor-regression / catalog-flagging bands documented |
| **P2.OBS.1** | Disclosure-renderer observability instrumentation | S | P2.OPS.1 | Claude Code | `chat_logs` schema accepts a structured JSON column or new typed columns for `regime`, `sponsor_id`, `tone_pass`; per `disclosure_renderer_spec.md` §7.2 |
| **P2.OBS.2** | Confidence-tier formatter telemetry (Backlog #42a candidate) | S | P2.OPS.1, P2.OBS.1 (shares the `chat_logs` widening) | Claude Code | flag-on traffic exists; per `confidence_tier_integration_spec.md` §5 telemetry note |
| **P2.X3.A** | Lane X3 — Tier 2 formatter integration of disclosure renderer | M | P2.OPS.1 + 1 week of X2 observability clean (P2.OBS.1) | Cursor or Claude Code | spec §5.1 of `disclosure_renderer_spec.md`; Tier 2 currently bypasses the renderer entirely |
| **P2.X3.B** | Lane X3 regression test coverage | S | P2.X3.A | Claude Code (test-coverage lane) | mirrors `tests/test_disclosure_render_integration.py` shape for Tier 2 path |
| **P2.OPS.3** | Operator enrichment sprint — 50 businesses + 30 tourism operators | L (operator-driven) | P2.OPS.1 (so flag-on data informs prioritization); #45 *helpful but not blocking* | operator + ingest CLI (`scripts/ingest/ingest_enrichment_csv.py`) | template at `templates/enrichment/business_enrichment_template.csv`; 50-business outreach response rate is the rate-limiter |
| **P2.BL.45** | Backlog #45 — expand `verification_method` CHECK constraint | S | none | Cursor | `phone_call`/`in_person`/`web_form_submission`/`email_confirmation` admitted alongside legacy values; new alembic migration; ingest CLI drops the lossy DB map |
| **P2.HOME.1** | Homepage `DISCLOSURE_WORD` consistency pass | S | P2.OPS.1 | Cursor | replace literal `Spotlight` badge on `/home` spotlight cards with import of `DISCLOSURE_WORD = "Sponsored"` from `app/chat/disclosure_render` |
| **P2.AUD.1** | Audience-signal data bake (passive) | L (calendar time only — 4–6 weeks) | P2.OPS.1 | passive | per Backlog #39 precondition; no code lane, just calendar |
| **P2.BL.39** | Backlog #39 — audience-signal-driven placement-regime selection | M | P2.AUD.1 + P2.X3.A in production | Claude Code | renderer reads `audience_signal` from intent context; visitor-leaning queries get tourism-eligible sponsor pools, local-leaning get service pools; A/B telemetry via P2.OBS.1 |
| **P2.UI.1** | Visitor-mode UI surface (decision memo first, then ship) | M | P2.AUD.1 + P2.BL.39 in production with telemetry | operator (memo) → Cursor (ship) | strategy doc Phase 2 close criterion: *decision documented* on whether visitor mode UI is justified |
| **P2.DIST.1** | Airbnb host welcome card SQL conversion metric | S | P2.OPS.1 | Cowork primary or Claude Code | conversion query defined against `chat_logs` + UTM landing log **before** any card prints; per strategy doc §5.3 |
| **P2.DIST.2** | Airbnb host distribution test launch (50 hosts) | M (operator + design) | P2.DIST.1 + P2.OPS.3 (so catalog density survives the inbound traffic) | operator + design | unique URLs per host; outreach sequence drafted; printable card asset shipped |
| **P2.PREM.1** | Premier-tier inventory open (1–2 categories pilot) | M | P2.OPS.1 + P2.OPS.2 + P2.X3.A + P2.OBS.1 (i.e., renderer covers both T2 and T3, observability clean, HALT 3 closed) | operator + Cursor (admin UI) | per strategy doc §4.4 — *"Premier never opens at $399 without the deterministic renderer in production."* Pilot categories: HVAC, plumbing |
| **P2.BL.2** | Backlog #2 — `_time_bucket_first_hits` sampling decision | S | P2.OPS.3 (catalog density is what triggers the sampling path) | Cursor | telemetry already in place (Slice 30a); decide A/B/C/D per `relay/decision_2_time_bucket_sampling.md` once 7 days of post-enrichment chat data exist |
| **P2.BL.18** | Backlog #18 — repo hygiene + doc hierarchy continuation | S (rolling) | none | Cursor | rolling chore lane; ship as capacity allows |

**Total: 17 lanes.** Five are operator-driven or passive (P2.OPS.2, P2.OPS.3, P2.AUD.1, P2.UI.1 memo step, P2.DIST.2 launch). The rest are agent-dispatchable.

---

## 3. Recommended sequence

### Phase 2.0 — Flag flip + observability foundation (week 1)

**Ships:** P2.OPS.1, P2.OBS.1, P2.OBS.2, P2.HOME.1, P2.DIST.1, P2.BL.45.
**Closes when:** flags on in production with structured per-render telemetry on `chat_logs`; `/home` badge reads `Sponsored`; Airbnb conversion SQL shipped to the runbook **before** card design starts.
**Gate to 2.1:** 7 days flag-on with zero tone-allowlist trips on rendered rows; renderer-exception WARN `< 0.1%`; conversion-metric SQL validated against today's `chat_logs` shape.

### Phase 2.1 — Tier 2 renderer extension + HALT 3 close (weeks 2–3)

**Ships:** P2.X3.A, P2.X3.B, P2.OPS.2, P2.BL.2 (if catalog density permits).
**Closes when:** renderer fires on both Tier 2 and Tier 3; HALT 3 review artifact in `docs/`; full suite still 1314+ green.
**Gate to 2.2:** P2.OBS.1 telemetry shows zero disclosure-word drift on the new T2 path across 7 days; HALT 3 closed.

### Phase 2.2 — Operator enrichment + distribution kickoff (weeks 3–8, overlaps 2.1)

**Ships:** P2.OPS.3, P2.DIST.2.
**Closes when:** 50 businesses enriched (top-queried categories prioritized using flag-on chat-log data), 30 tourism operators added; Airbnb cards distributed to first 50 hosts with unique `utm_content=<host_id>` URLs.
**Gate to 2.3:** `Provider` rows with non-stale `last_verified_at` cross 80; first non-zero conversion data flowing through P2.DIST.1.
**Dependency:** 2.2 cannot start until 2.0 + 2.1 complete; P2.DIST.2 specifically requires P2.OPS.3 in flight or visitor-driven inbound hits a thin catalog.

### Phase 2.3 — Audience-signal data bake (weeks 4–10, concurrent)

**Ships:** P2.AUD.1 (passive; midpoint check-in only).
**Closes when:** 4–6 weeks of `chat_logs.audience_signal` with ≥500 rows per visitor/local/ambiguous bucket.
**Gate to 2.4:** cohort distribution stable across two consecutive weeks; `unknown` geo-bucket rate `< 5%`.

### Phase 2.4 — Audience-driven placement + visitor-mode decision (weeks 10–12)

**Ships:** P2.BL.39, P2.UI.1 (memo only).
**Closes when:** `select_placement_regime` reads audience signal; A/B telemetry compares audience-aware vs audience-blind variants; visitor-mode decision memo in `docs/` recommends ship / defer / kill.
**Gate to 2.5:** A/B shows non-zero lift on visitor-leaning queries, OR explicit decision-doc record that the lift threshold was missed and visitor-mode UI defers to Phase 4.

### Phase 2.5 — Premier inventory open + (conditional) visitor-mode UI ship (weeks 12–16)

**Ships:** P2.PREM.1, P2.UI.1 (ship step, conditional on 2.4 memo).
**Closes when:** Premier-tier admin UI live for HVAC + plumbing pilot; first 1–2 Premier sponsors onboarded; visitor-mode surface shipped *only if* 2.4 memo recommended it.
**Phase 2 close criteria (strategy doc):** audience-signal data reviewed + decision documented; at least one distribution channel demonstrates returning-user conversion above defined threshold; catalog density continues to improve with no regression on Phase 1 quality bands.

**Rolling lane:** P2.BL.18 (repo hygiene + doc hierarchy continuation) ships across all phases as capacity allows; not gated on any other lane.

---

## 4. Critical path

The longest dependency chain runs **P2.OPS.1 → P2.OBS.1 → P2.X3.A → P2.AUD.1 → P2.BL.39 → P2.UI.1 → P2.PREM.1** — roughly 10–14 weeks calendar.

Its rate-limiter is **P2.AUD.1 — the passive 4–6 week audience-signal bake**. No agent can shorten this; running #39 against synthetic or partial data produces a model that retunes the moment real data arrives.

The **second bottleneck is operator-driven**: P2.OPS.3 (50-business + 30-tourism enrichment) gates both P2.DIST.2 and P2.PREM.1. Outreach response rate is the constraint; assume 4–6 weeks even with full operator focus. If it slips, P2.DIST.2 launches against a thin catalog (polluted conversion signal) and P2.PREM.1 has nobody to sell to.

The **third bottleneck — invisible until it bites** — is HALT 3 (P2.OPS.2). Strategy doc Decision #37 makes HALT 3 close a precondition for Premier inventory open; Phase 1 close-out narrative does not name HALT 3 as completed. Audit before committing to the Phase 2.5 calendar.

Operator-driven and passive bottlenecks dominate. **Code lanes are not the rate-limiter for Phase 2.**

---

## 5. Risks and unknowns

1. **Backlog #46 voice-battery edge cases.** Cursor's RESOLVED fix has not been smoke-tested against the 30-query adversarial catalog in production. *Mitigation:* run the smoke catalog as P2.OPS.1's first check; file any new edge cases as #46 follow-ups before P2.X3.A opens.
2. **Operator enrichment sprint timing.** Outreach response rate to 50 businesses is unknown. *Mitigation:* P2.OPS.3 runs parallel to P2.0; if response rate stalls at week 3, drop target to 30 businesses and document the catalog-density gap in P2.PREM.1's launch memo.
3. **Tier 2 LLM-formatter divergence from Tier 3.** Lane X3 assumes Tier 2 mirrors X2's Tier 3 dispatch, but the two paths have different response shapes (row-oriented vs prose). *Mitigation:* P2.X3.A starts with a half-day spec review against `tier2_formatter.py::format()` line 144–153; update `disclosure_renderer_spec.md` §5.1 if the injection contract diverges.
4. **Audience-signal cohort skew.** If post-flag traffic is overwhelmingly local (chamber is a local-leaning channel), #39's A/B lacks visitor cohort data. *Mitigation:* P2.AUD.1 midpoint check at week 3; if either cohort has `< 100` rows, extend the bake 2 weeks.
5. **HALT 3 status ambiguity.** Strategy doc treats HALT 3 close as a Phase 1 deliverable; STATE.md's Phase 1 close-out does not name it. *Mitigation:* P2.OPS.2 audits and closes; P2.PREM.1 cannot open without that artifact.
6. **#45 ordering vs enrichment sprint.** If P2.OPS.3 starts before #45 lands, operators submit `phone_call`/`in_person` through the lossy DB map and audit fidelity is lost on those rows. *Mitigation:* ship #45 before week 1 of P2.OPS.3 outreach.
7. **Premier ARPU is a measured output.** Strategy doc §4.4: $399 is working v1, not validated. *Mitigation:* P2.PREM.1's success criterion is *measured ARPU after first 5 Premier sponsors*, not *count signed at $399*; pricing review defers to Phase 4.
8. **`chat_logs` schema coordination.** P2.OBS.1 may need a new migration; Backlog #41a-followup may also touch the schema. *Mitigation:* P2.OBS.1 brief decides JSON column vs typed columns vs the spec's misuse-of-`llm_tokens_used` example before any migration lands.
9. **Visitor-mode UI premature ship.** Strategy doc Phase 4 risk note: *"separate product framing is where 'operating two products' creeps in."* *Mitigation:* P2.UI.1's memo step is non-optional; no UI ship in 2.5 without explicit signoff.
10. **Backlog #2 (`_time_bucket_first_hits`) intersects enrichment.** Catalog density changes the sampling calculus. *Mitigation:* hold P2.BL.2 decision until 7 days of post-enrichment traffic exist (week 8+); decide on actual telemetry from Slice 30a.

---

## 6. Out of scope for Phase 2

Per the strategy doc:

- **Scaling paid customer counts** (Featured signup flow, business dashboard, sales playbook, tourism affiliate scaling) — **Phase 3**. Phase 2 only opens *Premier pilot* on 1–2 categories.
- **Visitor-mode product ship** (separate UX, single composer, ranking + copy variant) — **Phase 4**, conditional on Phase 2 data. Phase 2 ships only the decision memo and at most a minimal integration.
- **Hotel / resort partnership program** — **Phase 4**. Phase 2 distribution is Airbnb hosts only (one channel at a time per strategy doc §5).
- **Tourism affiliate tracking infrastructure + 3–5 operator pilot** — **Phase 3**. (Phase 2 only enriches the 30-operator tourism inventory.)
- **Chamber of Commerce + local SEO landing pages** — operator/marketing lanes, not engineering lanes; tracked separately by the operator.
- **Pricing review and tier rebalance** — **Phase 4**. Phase 2 holds $59 / $179 / $399 as working v1.
- **Confidence-tier age-aware hedge variance** — separate ship per `confidence_tier_integration_spec.md` §5.
- **LLM rephrasing of canonical hedge fragments or disclosure word** — disallowed by spec.

---

## 7. First-week dispatch table

If Casey wants to start Phase 2 this week, here are the lanes to dispatch in order. **Five lanes, dispatchable Monday morning, parallelism deliberately limited so the operator can review each ship before the next opens.**

| # | Lane | Agent | Prompt sketch |
|---|---|---|---|
| 1 | **P2.OPS.1 — flag flip + smoke** | operator (Railway) + Cowork primary | Execute `phase1_deploy_runbook.md` §5–7: flip `FEATURE_FLAG_DISCLOSURE_RENDERER=true` and `FEATURE_FLAG_CONFIDENCE_TIER=true`; run §6.2 + §6.3 smokes via `Invoke-RestMethod`; run the 30-query catalog from `backlog_46_smoke_check_queries.md`. Report any 422s, sponsored block on SPECIFIC_QUALITY, disclosure-word drift, wrong-entity Tier 1. Verification only — no code changes. |
| 2 | **P2.HOME.1 — `DISCLOSURE_WORD` consistency on `/home`** | Cursor | Anchored Edit on the spotlight builder: import `DISCLOSURE_WORD` from `app.chat.disclosure_render` and replace literal `'Spotlight'` on sponsored cards. Regression test asserts badge string equals `'Sponsored'`. Spec ref: `disclosure_renderer_spec.md` §5.3. |
| 3 | **P2.BL.45 — expand `verification_method` CHECK** | Cursor | New alembic migration: drop existing CHECK on `providers.verification_method`, replace with one allowing legacy values + `phone_call / in_person / web_form_submission / email_confirmation`. Drop `_VERIFICATION_METHOD_DB_MAP` in `scripts/ingest/ingest_enrichment_csv.py`. Test ingest of each operator vocab value. Round-trip `upgrade/downgrade/upgrade` before commit. |
| 4 | **P2.DIST.1 — Airbnb conversion SQL** | Cowork primary or Claude Code | Draft the SQL defining "host welcome card conversion" against `chat_logs` + UTM landing log; per-host (`utm_content=<host_id>`): inbound sessions, sessions with T2/T3 response, sessions with sponsored impression, returning sessions within 7 days. Land as `scripts/analytics/*.sql` + `docs/maintainability/phase2_distribution_metric.md`. No production-code changes. |
| 5 | **P2.OBS.1 — disclosure-renderer observability** | Claude Code | Per `disclosure_renderer_spec.md` §7.2: log every render decision (regime, sponsor picked, tone pass/fail, render_outcome) to `chat_logs` as structured JSON. Decide between new typed columns vs JSON column (recommend against the spec's `llm_tokens_used` example — misuse); document before migration. Wire in `tier3_handler._maybe_render_sponsored_block`; tests for flag-on row-per-render and flag-off byte-identical. Coordinate with Backlog #41a-followup. |

**Achievability:** lanes 1+2 finish Monday (operator + small Cursor edit). Lane 3 is half-day Cursor (migration + CLI + tests). Lane 4 is one day (SQL + doc). Lane 5 is the only meaningful engineering lane (~1.5 days Claude Code). One operator + two agents ship five lanes in week 1 without shared-file conflicts; lanes 2/3/5 touch distinct modules, 1/4 touch no production code.

---

**Spec complete.** Phase 2 dispatch can open with the week-1 table above as soon as P2.OPS.1's smoke verification clears.
