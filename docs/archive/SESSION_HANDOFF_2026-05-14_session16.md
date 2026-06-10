# Session-16 Handoff — 2026-05-14

> **Audience:** the next Cowork primary on havasu-chat. **Read time:** ~3 minutes. Then boot per `outputs/session_17_boot_prompt.md`. Most state is already durable on origin; this doc captures the deltas since the session-15 close-out hotfix (`5132162`) + what's in flight.

---

## §1 — What session-16 accomplished

Eight commits on origin, all pushed. Origin/main HEAD = `1c98365`. **Phase 1 of the master build plan is COMPLETE on origin.**

| Commit | Summary |
|---|---|
| `2817951` | STATE.md Production block refresh + session-16 entry capturing the `5132162` hotfix narrative (Postgres rejecting `sa.text("1")` / `sa.text("0")` as Boolean `server_default`; swapped to `sa.true()` / `sa.false()`; production alembic head moved through `b2c3d4e5f6a7` on that deploy) |
| `a7984c6` | Folded the Postgres boolean-default lesson into `outputs/cursor_brief_phase_1_entity_schema.md` §10 (use `sa.true()`/`sa.false()` not `sa.text("1")`/`sa.text("0")`; use `sa.func.now()` not `sa.text("CURRENT_TIMESTAMP")`; verify raw SQL portability) |
| `e0417c8` | **Phase 1C — application read pivot.** 8 files (+827/-38). Cursor session, single dispatch. Pattern A (ENTITY-aware joins on legacy drivers) for `app/chat/tier2_db_query.py` (+176); Pattern B (legacy + alias via `Provider.entity` relationship) for `app/providers/queries.py` (+135) + `app/providers/view_models.py` (+12); light touches elsewhere. Pytest 1503 → 1512 (+9). One substantive deviation: hybrid read pattern (legacy-driver outerjoin Entity + `entity_id IS NULL` orphan fallback) instead of strict Pattern A — correct call given Phase 1B's deferred NOT NULL flip. |
| `e2e66ad` | Phase 1C shipped line on master plan §4 Phase 1 |
| `a27058d` | Phase 1D dispatch prompt artifact (`outputs/cursor_dispatch_prompt_phase_1d.md`, 125 lines) — pre-positioned during standby; explicit 5-step order-matters sequence + Postgres compatibility reminder + Option X vs Y decision point on the orphan-fallback hybrid |
| `3f3628e` | **Phase 1D — dual-write + entity_id NOT NULL flip + close-out.** 14 files (+814/-14). Cursor session, single dispatch. New `app/db/entity_dual_write.py` + `app/db/sponsor_resolve.py`; alembic migration `f8e9d0c1b2a3` chains off `b2c3d4e5f6a7` (`op.batch_alter_table` × 3 with portable `nullable=False`). Pytest 1512 → 1518 (+6). Three pragmatic deviations: `before_flush` safety net, `derive_provider_slug` Entity.slug reservation, Sponsor.business_id stays Integer with `str(...)` lookup. Cursor chose Option X (left orphan-fallback hybrid unchanged). |
| `cd079fc` | Phase 1D shipped line on master plan §4 Phase 1 + Phase 1 SHIPPED close-out header |
| `1c98365` | STATE.md session-16 close-out + Phase 1 complete narrative |

**Phase 1 final summary:** 4 sub-phases, 15 commits since master plan ship (`32ef46a`), pytest 1476 → 1518 (+42 net-new), alembic chain `f1a2b3c4d5e6` → `a1b2c3d4e5f6` → `b2c3d4e5f6a7` → `f8e9d0c1b2a3`. Phase 2 (account-lite + image storage + search index) is the next dispatchable lane.

---

## §2 — What's in flight or queued

- **Production deploy of `1c98365`** — Phase 1C application read pivot + Phase 1D dual-write + NOT NULL flip migration are NOT yet deployed. Operator-cadence call. Chat-route response shape pinned unchanged across the entire Phase 1 lane via regression coverage, so safe whenever Casey is ready. When deploy ships, alembic will advance production from `b2c3d4e5f6a7` to `f8e9d0c1b2a3` (single migration: legacy entity_id NOT NULL flip).
- **Phase 2 — two parallel lanes per master plan §4 Phase 2.** Lane 2A (account-lite v0.1, magic-link auth via Resend, 5 new tables) is the smaller of the two. Lane 2B (image storage R2 + Postgres FTS + pg_trgm) is the bigger. **Neither lane has a dispatch brief authored yet** — both need fresh briefs in the heavy-prescriptive Cursor-operating-doc shape (mirror `outputs/cursor_brief_phase_1_entity_schema.md` pattern: §0 baseline, §1 why, §2 locked decisions, §3 sub-phase boundaries, §4+ deliverables in detail, §10 what NOT to do, §11 acceptable deviations, §12 risks, §13 final report format). Lanes are file-disjoint per dispatch_protocol Rule 3 — can dispatch concurrently if desired.
- **Phase 2 operator prereqs are gating brief authoring usefully:** Lane 2A needs Resend API key registration (~30 min); Lane 2B needs Cloudflare R2 bucket + CDN domain (~2 hours per `image_storage_design.md` §8). Authoring briefs before these prereqs lock in risks baking-in assumptions that need rework.

---

## §3 — Open operator-decision items

| Item | When | Notes |
|---|---|---|
| Deploy `1c98365` to production | Anytime | Carries Phase 1C + 1D code + the `f8e9d0c1b2a3` NOT NULL flip migration. Chat-route shape pinned via regression. Watch for any migration surprise on first deploy (the `5132162` hotfix lesson — Postgres can surprise even when SQLite is happy; the 1D migration uses only portable `op.batch_alter_table` with `nullable=False` so should land cleanly, but verify). |
| Resend API key registration | Pre-Phase-2A dispatch | ~30 min; signup + Railway env var drop. Gates Lane 2A brief authoring usefully. |
| Cloudflare R2 bucket + CDN domain | Pre-Phase-2B dispatch | ~2 hours per `image_storage_design.md` §8. Gates Lane 2B brief authoring usefully. |
| 3 trivial category audit lock-now items + 4 Phase-3 review questions | At Phase 3 start | Carry-over from session-15 §3; not relevant before Phase 2 ships. |
| Author 8-12 district paragraphs | Anytime, ideally pre-Phase-3 | ~1 hour; operator's unique contribution; hyperlocal moat. |
| AirNow API key registration | Pre-Phase-8 (months out) | ~20 min; signup + Railway env var drop. |

---

## §4 — Pragmatic deviations to remember

Phase 1C:
- **Hybrid read pattern** (legacy-driver outerjoin Entity + `entity_id IS NULL` orphan fallback) in `app/chat/tier2_db_query.py` + `app/providers/queries.py` + `scripts/places_load.py`, instead of brief §7.1's strict Pattern A `select(Entity)`. Correct call at the time given Phase 1B's deferred NOT NULL flip; after Phase 1D's NOT NULL flip lands the orphan branches become dead code paths in production. Cursor explicitly chose Option X (leave as-is, defer cleanup to Phase 13) at the Phase 1D decision point. Could be Option Y'd (re-tightened toward strict ENTITY-first) at any future polish pass.

Phase 1D:
- **`before_flush` Session listener safety net** via `register_catalog_dual_write_hooks` in `app/db/database.py::_register_orm_listeners` — catches raw `db.add(Provider|Event|Program)` paths that bypass the explicit `entity_dual_write` helpers. Same precedent as session-13's slug-listener pattern (`d967568` / `register_provider_slug_hooks`). Idempotency guards make double-call harmless. Worth folding into future write-path briefs as a "consider safety-net listener for fixture coverage" prompt.
- **`derive_provider_slug` Entity.slug collision reservation** in `app/db/seed_helpers.py` — reserves slugs used by commercial Entity rows to avoid `UNIQUE entities.slug` failures when dual-writing. Direct consequence of dual-write + global Entity.slug uniqueness.
- **`Sponsor.business_id` stays Integer**; resolution uses `str(business_id) → Provider.id` lookup (test fixtures use numeric-string IDs like `900042`). Phase 11 monetization will unify Sponsor.business_id → Entity.id String UUID; for now this is the discriminator-branching pragma.
- **Brief §8.1 listed `app/api/routes/events.py`** that doesn't actually exist; Cursor correctly identified Event creates flow through `approve_contribution_as_event` (River Scene + Parks & Rec). `app/contrib/river_scene.py` is parse-only.

---

## §5 — Pointers for the next agent

Boot order:
1. `outputs/session_17_boot_prompt.md` (the boot prompt Casey pastes; see that file)
2. `docs/STATE.md` (refreshed 2026-05-14 at session-16 close — start with the Production block, especially the origin-vs-deployed divergence note)
3. `docs/maintainability/master_build_plan.md` §4 Phase 1 ("Shipped (incremental)" list now has all four sub-phases plus the Phase 1 SHIPPED header) and §4 Phase 2 (next dispatchable lane)
4. `docs/maintainability/account_lite_v01_design.md` if dispatching Lane 2A; `docs/maintainability/image_storage_design.md` + `docs/maintainability/search_index_decision.md` if dispatching Lane 2B
5. `outputs/cursor_brief_phase_1_entity_schema.md` (preserved as reference for the brief-authoring pattern; sections 0/3/10/11/12/13 are the canonical shape to mirror for Phase 2)
6. `docs/maintainability/dispatch_protocol.md` + `docs/maintainability/dispatch_channels.md` (12 working-agreement rules + channel-pick playbook + 12 gotchas; nothing changed in session-16 but folding the PowerShell `;` vs `&&` quirk would be a reasonable micro-edit at next natural touch)

Session-16 absorbed two new lessons worth carrying forward into future briefs:
- **Postgres-vs-SQLite portability is a real and recurring risk.** Already folded into the Phase 1 brief §10; Phase 2 briefs should carry the same checklist (use `sa.true()`/`sa.false()`, `sa.func.now()`, verify raw SQL portability). The bash sandbox runs SQLite; production runs Postgres; constructs that work in one don't necessarily work in the other.
- **The `before_flush` safety-net listener pattern generalizes well.** Cursor reached for it independently in 1D after the slug-listener precedent in session-13. When future write-path briefs land, consider explicitly inviting the safety-net pattern in §11 acceptable deviations so Cursor doesn't have to rediscover it case-by-case.

The session-16 narrative in `docs/STATE.md` "Recently shipped (high signal)" §1 captures every commit + decision + deviation with enough detail that the next agent shouldn't need to read this handoff except for §3 + §4 above.

---

*Authored at session-16 close, 2026-05-14. Next agent picks up at Phase 2 dispatch — but operator prereqs (Resend / R2) usefully gate the brief authoring, so the natural first move is checking whether Casey has done either prereq before authoring either brief.*
