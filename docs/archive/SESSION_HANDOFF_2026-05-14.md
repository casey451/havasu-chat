# Session-15 Handoff — 2026-05-14

> **Audience:** the next Cowork primary on havasu-chat. **Read time:** ~3 minutes. Then boot per `outputs/session_16_boot_prompt.md`. Most state is already durable on origin; this doc captures the deltas since master plan ship (`32ef46a`) + what's in flight.

---

## §1 — What session-15 accomplished

Ten commits on origin, all pushed. Origin/main HEAD = `92aa7e2`.

| Commit | Summary |
|---|---|
| `4211553` | Category backfill audit + Phase 3 amendment (sub-agent audit of `category_backfill_mapping_DRAFT.md` vs locked new taxonomy; master plan §4 Phase 3 + §6 + §10 amended) |
| `ff9832d` | **Phase 1A — unified ENTITY schema (additive)**. New `entities` core + 11 extension tables + Sponsor.entity_type. Migration `a1b2c3d4e5f6` chains off `f1a2b3c4d5e6`. Pytest 1476 → 1497 (+21). Four pragmatic deviations transparently flagged + accepted. |
| `287e503` | Phase 1A Shipped line on master plan §4 Phase 1 |
| `7e13c3a` | Landed session-13 cold-pitch sponsor outreach surface (5 files; referenced as shipped in master plan §2 but never committed) |
| `bf7383b` | Session-15 dispatch artifacts (Phase 1 brief + session-15 boot prompt) |
| `ec84eb4` | District paragraphs phased V1/V1.5/V2 (hybrid lock — operator V1, UGC V1.5, AI-summarized V2) |
| `d475b06` | **Phase 1B — data backfill (Provider/Event/Program → entities + extensions)**. Migration `b2c3d4e5f6a7` chains off `a1b2c3d4e5f6`. Pytest 1497 → 1503 (+6). Two pragmatic deviations: `entity_id` stays nullable through 1C (NOT NULL flip moved to 1D); SQLite time binds normalized. |
| `6513798` | Ruff cleanup on `app/providers/view_models.py` (I001 + F401; cleared multi-session CI failure) |
| `24fa935` | Phase 1B Shipped line + brief amendment for deferred NOT NULL flip |
| `92aa7e2` | STATE.md refresh + Phase 1C dispatch prompt artifact |

Three strategic decisions locked (master plan §10 has the entries):
1. Category taxonomy rewrite + audited backfill land in Phase 3 (effort bumped 3-5d/~1hr → 5-8d/~2-3hr)
2. Professional-services strings (insurance, financial, legal, real_estate, professional_services) deferred to V1.5+ — NULL operator-queue during Phase 3 backfill
3. District paragraphs phased: operator V1 / UGC V1.5 / AI-summarized V2

---

## §2 — What's in flight or queued

- **Phase 1C** — application read pivot (biggest sub-phase, 7-10 day brief estimate). Dispatch prompt queued at `outputs/cursor_dispatch_prompt_phase_1c.md`. Heavy-prescriptive operating doc at `outputs/cursor_brief_phase_1_entity_schema.md` (already amended for the deferred NOT NULL flip per session-15 §3 + §6.1 + §8 edits). Channel: Cursor (per session-15 operator decision).
- **Phase 1D** — write dual-target + close-out + entity_id NOT NULL flip. Same brief, §8 deliverables. Follows Phase 1C.
- **Phase 2A** account-lite — magic-link auth via Resend. Design memo at `docs/maintainability/account_lite_v01_design.md`. Brief not yet authored. Phase 2 starts after Phase 1D ships.

---

## §3 — Open operator-decision items

Most are queued for natural decision windows; none are blocking.

| Item | When | Notes |
|---|---|---|
| 3 trivial category audit lock-now items (`religion_community` → public-civic-resources; `childcare_education` / `education` → classes-sports-recreation) | At Phase 3 start | "Trivial confirmations" per audit memo §4 |
| 4 Phase-3 lock-during-Phase-3 questions (`beauty_personal_care`, `tourism`, K-12 schools, recreational-entertainment) | Phase 3 start | ~30 min total |
| Author 8-12 district paragraphs | Anytime, ideally pre-Phase-3 | ~1 hour; operator's unique contribution; hyperlocal moat |
| Drop+recreate local SQLite dev DB | Pre-Phase-1C dispatch | Path A baseline failure at `1a2b3c4d5e6f → 2a3b4c5d6e7f` (`duplicate column name: slot`) is local-DB drift only; production unaffected |
| AirNow API key registration | Pre-Phase-8 (months out) | ~20 min; signup + Railway env var drop |
| Resend API key registration | Pre-Phase-2A (after Phase 1) | ~30 min |
| Cloudflare R2 bucket + CDN domain | Pre-Phase-2B (after Phase 1) | ~2 hours per `image_storage_design.md` §8 |

---

## §4 — Pragmatic deviations to remember

Phase 1A:
- `passive_deletes=True` on Entity→extension relationships (SQLite ON DELETE CASCADE needs this)
- `engine.dispose()` in cascade test (PRAGMA foreign_keys pollution into pooled connections — caught test pollution that would have been silent flakiness)
- `SourceEvidence.verified_at` nullable (matches legacy `Provider.last_verified_at`)
- `SeasonalHours.hours_overlay` nullable (table ships empty)

Phase 1B:
- `providers.entity_id` / `events.entity_id` / `programs.entity_id` stay **nullable through 1C** — NOT NULL flip moved to Phase 1D after dual-write helpers populate at write time. Pinned in `test_entity_id_fk_columns_remain_nullable_for_dual_write_gap`.
- `_sql_time` helper normalizes SQLite time binds.

---

## §5 — Pointers for the next agent

Boot order:
1. `outputs/session_16_boot_prompt.md` (the boot prompt Casey pastes; see that file)
2. `docs/STATE.md` (refreshed 2026-05-14 — start with the Production block)
3. `docs/maintainability/master_build_plan.md` (the 13-phase operating doc; §4 Phase 1 has the "Shipped (incremental)" sub-phase ledger)
4. `outputs/cursor_brief_phase_1_entity_schema.md` (operating doc for Cursor across Phase 1 sub-phases; already includes 1A/1B post-ship amendments)
5. `outputs/cursor_dispatch_prompt_phase_1c.md` (paste-into-Cursor prompt for the next dispatch)
6. `docs/maintainability/dispatch_protocol.md` + `docs/maintainability/dispatch_channels.md` (12 working-agreement rules + channel-pick playbook)

The session-15 narrative in `docs/STATE.md` "Recently shipped (high signal)" §1 captures every commit + decision + deviation with enough detail that the next agent shouldn't need to read this handoff except for §3 + §4 above.

---

*Authored at session-15 close, 2026-05-14. Next agent picks up at Phase 1C dispatch.*
