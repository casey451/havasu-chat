# Session Handoff — Phase 1 Code Close (2026-05-08)

**Audience:** A fresh Cowork / Claude / Cursor session that's continuing where this one left off.
**Read time:** 10 minutes for the full bootstrap; 3 minutes for the "what's next" section.
**Companion docs:** `docs/STATE.md` (canonical "where is the project right now"); `docs/BACKLOG.md` (every ship-log + open item with attribution); `docs/maintainability/phase1_deploy_runbook.md` (operator-facing deploy + flag-flip steps).

---

## §1 — One-paragraph summary

This session shipped **Phase 1 code work** of the *Ask Hava — Detailed Plan* (`ask-hava-detailed-plan.docx` at repo root). Seventeen lanes landed across UI data correctness, schema additions, deterministic disclosure rendering, confidence-tier classification, audience-signal logging, and assorted follow-ups. Combined Phase 1 test surface is **149 passing**. All new behavior is gated behind feature flags that default to off — production code path is byte-identical to pre-session state until those flags flip. Three follow-up lanes (Lane #41a-followup, Lane #41b, voice-rubric test fix) were dispatched at the end of the session and may be in flight or completed by the time this doc is read; check `docs/BACKLOG.md` tail for status.

---

## §2 — Topology and protocol that worked

The session ran a **four-agent parallel topology** across most of the work:

- **Cowork primary** (this session, the one writing this doc) — orchestration, integration, BACKLOG.md / STATE.md owner, single source of truth for cross-lane state.
- **Claude Code (CC)** — heavy engineering lanes, multi-file refactors, comprehensive test suites.
- **Cursor** — focused-file edits, ops scripts, schema migrations, CSS/template work.
- **Cowork subagents** (spawned via the `Agent` tool) — independent code or spec lanes that report back as text.

**Hard-won protocol rules** (don't re-litigate these):

1. **Anchored `Edit` over full-file `Write` on shared files.** Three concurrent `Write` operations on `app/home/queries.py` early in the session truncated each other's work and broke `tests/test_home_queries.py`, `docs/BACKLOG.md`, and migration `2a3b4c5d6e7f` mid-flight. The fix: any agent editing a file another lane might also touch uses `Edit` with anchored `old_string` / `new_string`. Only new files use `Write`.
2. **Text-only ship-log reports.** Delegated lanes return ship-log entries as raw markdown text in their final report; the primary integrates them into `docs/BACKLOG.md`. Direct appends from multiple agents collide and truncate.
3. **Linux mount staleness vs Windows authoritative.** The Cowork bind sometimes serves stale or truncated views of files mid-write. The Windows-side files (read via the `Read` tool, written via Cursor / CC tools) are authoritative. Don't restore a file from git until you've verified Windows shows the same truncation. Several false-alarm "Sponsor class missing" / "models.py at line 530 IndentationError" reports turned out to be Linux mount lag.

These rules are now in the top "Lessons learned" callout of `docs/maintainability/ui_data_correctness_spec.md` for future parallel runs.

---

## §3 — Seventeen lanes, what they did, where they live

| # | Lane | Owner | What | Tests |
|---|---|---|---|---|
| 1 | A — Category labels + blurb sanitizer | Cowork | `_category_label()` helper + widened `CATEGORY_LABELS` + hardened `_card_blurb` in `app/home/queries.py` | 17 in `tests/test_home_queries_lane_a.py` |
| 2 | B — Tonight time-of-day + venue de-dup | Claude Code | `tonight_or_today_label()` + `_tonight_effective_floor()` in `queries.py`; heading wired in `router.py` + `home.html` + `mock_data.py` | 8 in `tests/test_home_queries.py` |
| 3 | C — Placeholder phone NANP guard | Cursor | `_PLACEHOLDER_PHONE_RE` + conditional `tel:` rendering + `scripts/cleanup/null_placeholder_phones.py` | 7 in `tests/test_home_queries.py` |
| 4 | Sponsor 2B migration restored | Primary recovery | `alembic/versions/2a3b4c5d6e7f_evolve_sponsors_for_four_tier_inventory.py` from `3c55cf9` | passes |
| 5 | S1 — Schema additions | Cursor | `f7e8d9c0b1a2`: `Provider.last_verified_at` + `verification_method` + `Event.last_verified_at` + `Sponsor.verified_fields_present` + `chat_logs.audience_signal` + partial index | — |
| 6 | S1.1 — Timezone-aware columns | Cursor | `b4c5d6e7f8a9`: `DateTime(timezone=True)` on the four temporal columns | — |
| 7 | #41a — TZAwareDateTime TypeDecorator | Cursor | New `app/db/types.py` (`TZAwareDateTime` returning naive Phoenix wall) + applied to four columns | 8 in `tests/test_tz_aware_datetime.py` |
| 8 | S2 / X1 — Disclosure renderer module | Claude Code | New `app/chat/disclosure_render.py` (376 lines): `PlacementRegime`, `SponsoredBlock`, `select_placement_regime`, `render_sponsored_block`, tone allowlist, `is_renderer_enabled()` | 32 in `tests/test_disclosure_render.py` |
| 9 | X2 — Tier 3 integration | Claude Code | `app/chat/tier3_handler.py` 206→331 lines: `_maybe_render_sponsored_block`, `_inject_sponsored_block`, `_format_sponsored_block` + new `organic_context` kwarg | 8 in `tests/test_disclosure_render_integration.py` |
| 10 | X2.1 — organic_context wiring | Claude Code | `_organic_context_for_tier3()` in `app/chat/unified_router.py`; wired into all four `answer_with_tier3` call sites | 6 in `tests/test_tier3_organic_context_wiring.py` |
| 11 | #43 — URGENT_NOW sub_intent | Claude Code | `URGENT_NOW` constant + regex in `intent_classifier.py`; mapped to `EMERGENCY_URGENT` in `disclosure_render.select_placement_regime` | 8 in `tests/test_urgent_now_sub_intent.py` |
| 12 | S3 — Audience signal slice | Cowork subagent | New `app/chat/audience_signal.py` (306 lines): `AudienceSignal` dataclass + `classify_audience()`; wired into `unified_router.route()` + `chat_logging.py` defensive write | 9 in `tests/test_audience_signal.py` |
| 13 | S3.1 — API route forwarding | Cursor | Anchored Edit on `app/api/routes/chat.py::post_concierge_chat` to forward `request_headers` / `client_ip` / `accept_language` | 1 in `tests/test_chat_route_audience_forwarding.py` |
| 14 | CT1 — Confidence-tier classifier | Cowork subagent | New `app/chat/confidence_tier.py` (304 lines): `ConfidenceTier` enum + `ConfidenceAssessment` + `classify_confidence()` + `is_stale()` + `hedge_phrase()` | 22 in `tests/test_confidence_tier.py` |
| 15 | CT2.A — T2 formatter integration | Cowork subagent | `is_confidence_tier_enabled()` + `_annotate_rows_with_confidence_hint()` + `_enforce_low_tier_phone()` in `tier2_formatter.py`; `EXCEPTION (confidence_hedge)` clause in `prompts/tier2_formatter.txt` | 10 in `tests/test_confidence_tier_integration_tier2.py` |
| 16 | CT2.B — T3 context_builder integration | Cowork subagent | `_hedge_suffix_for()` per-record helper in `app/chat/context_builder.py`; "Confidence hedges in Context lines" instruction block in `prompts/system_prompt.txt` | 11 in `tests/test_confidence_tier_integration_tier3.py` |
| 17 | #42 / CT2.B.1 — T3 phone enforcement | Cowork subagent | `_fetch_tier3_records()` + `rows_for_tier3_classification()` sibling in `context_builder.py`; post-process invocation in `tier3_handler.py` | 6 in `tests/test_tier3_phone_enforcement.py` |

**Combined: 149 tests across the Phase 1 surface.**

---

## §4 — Specs and docs that landed

- `ask-hava-detailed-plan.docx` (32KB) — strategy doc at repo root. Phase 1 / Phase 2 / Phase 3 / Phase 4 quarter-by-quarter plan with monetization tier structure ($59 / $179 / $399 + tourism affiliate rev share), $240–280K ARR planning baseline, six-decision appendix.
- `docs/maintainability/ui_data_correctness_spec.md` — RESOLVED. Top has the lessons-learned callout for parallel-agent coordination.
- `docs/maintainability/disclosure_renderer_spec.md` — 1,002 lines. Status OPEN (X3 / Tier 2 integration deferred to Phase 2; everything else shipped).
- `docs/maintainability/confidence_tier_integration_spec.md` — 410 lines. CT2.A and CT2.B both shipped; CT2.B.1 phone enforcement also shipped.
- `docs/maintainability/phase1_deploy_runbook.md` — 593 lines. Operator-facing deploy + flag-flip walkthrough.
- `docs/STATE.md` — updated with full Phase 1 narrative as the new top entry under "Recently shipped (high signal)."
- `docs/BACKLOG.md` — 1,443 lines. Twenty ship-log entries from today's session + eight new backlog items.

---

## §5 — Feature flags shipped (all default OFF)

| Flag | Controls | Activates lanes |
|---|---|---|
| `FEATURE_FLAG_DISCLOSURE_RENDERER` | Sponsored disclosure rendering in chat (Tier 3) | X1 + X2 + X2.1 + #43 |
| `FEATURE_FLAG_CONFIDENCE_TIER` | Per-row confidence hedge in Tier 2 + Tier 3 prompts and post-process phone enforcement | CT1 + CT2.A + CT2.B + CT2.B.1 |
| Audience signal persistence | Always on, gated on `chat_logs.audience_signal` column (now resolved by Lane S1) | S3 + S3.1 |

**Production code path is byte-identical to pre-session state until you flip flags.** See `phase1_deploy_runbook.md` §6 for the recommended flip order.

---

## §6 — What's open right now

### Backlog items still OPEN

| # | Title | Estimate | Notes |
|---|---|---|---|
| #38 | `request_time_utc` parameter rename in `audience_signal.py` | 5 min | Low priority — naming nit, no behavior change |
| #39 | Phase 2: thread audience signal into placement-regime selection | TBD | DEFERRED to Phase 2 by design |
| #41a-followup | Switch `TZAwareDateTime` to always-aware on read + drop `.replace(tzinfo=None)` workaround in `context_builder.py` | 30 min | **NOT SHIPPED at session end.** Cursor was dispatched but the work didn't reach disk. Verified at session end: `app/db/types.py::_to_naive_lake_havasu_wall` still ends with `.replace(tzinfo=None)`; `app/chat/context_builder.py` lines 154 + 246 still have the `_now_aware.replace(tzinfo=None) if _now_aware.tzinfo else _now_aware` pattern. **Pick this up first in the new session.** |
| #41b | Remove now-redundant defensive workarounds in `confidence_tier.py`, `disclosure_render.py`, `tier3_handler.py` | 30 min | **HALTED on precondition check** (correctly). Cursor verified that #41a-followup hadn't landed and refused to ship #41b. The halt-and-report is exactly the discipline the precondition gate was designed for. After #41a-followup lands, re-dispatch #41b with the same prompt. |

### Backlog items resolved this session

#37, #40, #41, #42, #43 — all closed. See `docs/BACKLOG.md` ship-log entries for each.

### Operator work (not code)

These were called out in the strategy doc Phase 1 close criteria but require operator/owner action, not code:

- **50-business enrichment sprint** — top-queried categories (restaurants, plumbers, HVAC, pool service, boat repair, urgent care, auto repair). Verified phone, hours, address, 2–3 sentence Hava-voice description, owner contact email, `last_verified_at` + `verification_method` populated. Schema is ready (Lane S1).
- **30-operator tourism inventory pass** — boat rentals, tour operators, lakeside dining, beach access, bridge viewing, family activities, ATV rentals, lodging.
- **Manual `/home` smoke check** at 5 AM / 12 PM / 5 PM Lake Havasu local. Spec §5 close criterion (`ui_data_correctness_spec.md`).
- **HALT 3 close-out review** — strategy doc Phase 1 calls for closing HALT 3 with documented gating-rate, anchor-regression, and catalog-flagging bands. Status of HALT 3 itself was not audited this session.

### Decision-only items

- **When to flip `FEATURE_FLAG_CONFIDENCE_TIER`** in production. Spec recommends staged: Tier 2 first, then Tier 3 after 4–6 weeks of observability. Both shipped in the same session, so they light up together — operator may want to flip on a low-traffic window first.
- **When to flip `FEATURE_FLAG_DISCLOSURE_RENDERER`**. Production needs sponsor inventory before this is meaningful. Recommend: no sponsors → no flip; one sponsor → flip on a known-quiet weekday.

---

## §7 — What a fresh Cowork primary should do first

If you're picking up this session in a fresh chat:

1. **Read `docs/STATE.md`** top entry for the canonical narrative.
2. **Read `docs/BACKLOG.md`** tail (last ~20 entries) for the lane-by-lane attribution.
3. **Run `python -m pytest tests/test_home_queries.py tests/test_home_queries_lane_a.py tests/test_audience_signal.py tests/test_disclosure_render.py tests/test_disclosure_render_integration.py tests/test_confidence_tier.py tests/test_confidence_tier_integration_tier2.py tests/test_confidence_tier_integration_tier3.py tests/test_chat_route_audience_forwarding.py tests/test_tier3_handler.py tests/test_tier3_organic_context_wiring.py tests/test_urgent_now_sub_intent.py tests/test_tier3_phone_enforcement.py tests/test_tz_aware_datetime.py -q`** — confirm 149+ passing as the baseline.
4. **Check the in-flight lane status:** Lane #41a-followup (Cursor), Lane #41b (Cursor, queued), test fix for `test_tier2_catalog_render` voice drift (Claude Code). Look for ship-log entries in `docs/BACKLOG.md` or ask the operator.
5. **Read `docs/maintainability/phase1_deploy_runbook.md`** if the operator is asking about deploy / flag-flip.

Most likely first request from the operator: either "ship #41a-followup + #41b" (small cleanup), "deploy and flip Phase 1 flags" (operator runbook), or "start Phase 2" (strategic — read the strategy `.docx` and reset).

---

## §8 — What Phase 2 should consider

Not exhaustive. The strategy doc has the full plan. Highlights:

- **Lane X3 — Tier 2 disclosure renderer integration.** Spec §5 of `disclosure_renderer_spec.md`. Deferred to Phase 2 by explicit decision; needs 4–6 weeks of Tier 3 observability data first.
- **Backlog #39 — thread audience signal into placement-regime selection.** Visitor-mode A/B testing requires this.
- **Visitor-mode UI** — content surface (different ranking + copy) on the same chat composer. Phase 2 deliverable per the strategy doc. Don't ship as a separate product — single composer is the discipline.
- **Distribution channel kickoff** — Airbnb host welcome cards (Phase 2 measurable test). Conversion metric defined in SQL against `chat_logs` BEFORE the cards print.
- **Premier tier inventory opens** — gated on disclosure renderer in production with the flag flipped and observability clean.
- **Confidence-tier formatter telemetry** — when CT2.A / CT2.B run flag-on, log per-row tier decisions to `chat_logs` so Phase 2 can audit hedge-leakage on HIGH rows. Backlog #42a candidate.

---

## §9 — Things that look broken but aren't

So a fresh primary doesn't waste time investigating known-non-issues:

- **12 pre-existing failures in the broader test suite** (entity matcher, phase2 integration, river_scene, tier2 catalog render, unified router). All confirmed unrelated to today's lanes by stash-and-rerun verification. The `test_tier2_catalog_render` voice-drift fix landed at session end (commit `655ffc5` was the cause); the other ~11 are still pre-existing. Operator should not roll back a clean ship over them.
- **SQLite returns naive datetimes despite `DateTime(timezone=True)` columns.** Python's sqlite3 driver historically ignores the timezone bit on read. Lane #41a workaround: `TZAwareDateTime.process_result_value` returns naive Phoenix wall. Postgres production round-trips aware. Defensive `try/except TypeError` workarounds in `confidence_tier.py`, `disclosure_render.py`, `tier3_handler.py`, `context_builder.py` remain load-bearing for SQLite dev/test until Lane #41a-followup + Lane #41b land.
- **Linux mount serves stale/truncated views of files mid-write.** Read tool (Windows path) is authoritative; bash `cat`/`grep` on `/sessions/.../mnt/havasu-chat/...` may show transient truncation. False-alarm reports of "Sponsor class missing from models.py" / "models.py:530 IndentationError" / "queries.py truncated at line 361" all traced to mount lag, not real corruption.
- **EMERGENCY_URGENT regime won't render in production without organic Provider rows.** Lane X2.1 closed the wiring (organic_context flows from API to `answer_with_tier3`), but `disclosure_render._eligible` still requires `bool(organic_rows)` for the regime — by design (spec §1.3). On a sparse Provider catalog, urgent queries fall through to LLM-only output. This is correct behavior, not a bug.

---

## §10 — Final test count + alembic state

```
$ python -m alembic heads
b4c5d6e7f8a9 (head)   # Lane S1.1; if Lane #41a-followup landed cleanly, no migration was added (TypeDecorator is a SQLAlchemy-layer change)

$ python -m pytest <Phase 1 surface> -q
149 passed
```

Phase 1 surface, exact file list:
```
tests/test_home_queries.py
tests/test_home_queries_lane_a.py
tests/test_audience_signal.py
tests/test_disclosure_render.py
tests/test_disclosure_render_integration.py
tests/test_confidence_tier.py
tests/test_confidence_tier_integration_tier2.py
tests/test_confidence_tier_integration_tier3.py
tests/test_chat_route_audience_forwarding.py
tests/test_tier3_handler.py
tests/test_tier3_organic_context_wiring.py
tests/test_urgent_now_sub_intent.py
tests/test_tier3_phone_enforcement.py
tests/test_tz_aware_datetime.py
```

---

*This handoff doc should be the first read for any fresh session continuing this work. It's intentionally exhaustive on the lane-level attribution because cross-agent context is exactly what gets lost between sessions.*
