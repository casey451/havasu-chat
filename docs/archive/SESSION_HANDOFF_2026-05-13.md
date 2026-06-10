# Session Handoff — 2026-05-13 (fresh-session entry point)

**Audience:** the agent picking up where the 2026-05-13 session left off. This was the **first bounded engineering session under the directory-first pivot** (pivot itself landed 2026-05-12). Schema lane shipped end-to-end: §8 decisions 1–4 locked, `Category` model + FKs + `attributes`/`district` on Provider, Alembic migration `e7f8a9b0c1d2`, +7 tests (1422 → 1429), pivot-notice banners on `PROJECT.md` and `HAVA_CONCIERGE_HANDOFF.md`, BACKLOG/STATE ship-log entries, plus a follow-up ruff lint cleanup on three pre-existing test files surfaced by the `ruff==0.15.12` CI pin. Six commits across the session: `a6e9f6c` (decisions + banners), `6f6ef79` (schema), `aea87b8` (lint), `597d9cb` (BACKLOG/STATE), `11b248f` (cold-pitch script). Plus the in-flight pivot doc commit `b97942d` from 2026-05-12 evening that had already pushed.

**Read time:** ~3 minutes for this doc.

**Companion docs:**

- `docs/STRATEGY_PIVOT_2026-05-12.md` — strategic-direction-of-record. §8 status block updated 2026-05-13 to reflect decisions 1–4 LOCKED.
- `docs/SESSION_HANDOFF_2026-05-12.md` — yesterday's entry point (pivot lock + #64 ship). Pre-this-session.
- `docs/STATE.md` — project-state-of-record. Updated 2026-05-13 to reflect HEAD/pytest/alembic-head moves.
- `docs/BACKLOG.md` — ship logs + open tickets. Two new no-ticket entries added at end (schema lane + lint cleanup).
- `docs/maintainability/dispatch_protocol.md` — 12-rule reference card. Unchanged this session, but see §5 below for two new lessons worth folding in eventually.
- `docs/maintainability/dispatch_channels.md` — channel-pick playbook + 7 common gotchas. Same.
- `docs/sponsor_outreach/verified_presence_pitch.md` — new this session. ChatGPT-drafted Verified Presence ($79/mo) cold-pitch material with `[CASEY: confirm <X>]` markers.

---

## §0 — Boot sequence

1. **Read `docs/STRATEGY_PIVOT_2026-05-12.md` end-to-end (~5 min)** if you haven't — still the authoritative strategic-priority signal. §8 decisions 1–4 LOCKED block at the top of §8 is new this session.
2. Read this doc end-to-end (~3 min) for ship details + state confirmation.
3. Skim `docs/SESSION_HANDOFF_2026-05-12.md` if you want the prior-session narrative (the session that locked the pivot itself).
4. Confirm repo state: `git log --oneline -8` should start with `11b248f` (cold-pitch) on `597d9cb` (BACKLOG/STATE) on `aea87b8` (lint) on `6f6ef79` (schema) on `a6e9f6c` (decisions + banners) on `b97942d` (pivot doc) on `eb6f2e1` (handoff) on `426f992` (#64 close-out) on `aa3abd4` (#64 ship) on `4f9a322` (2026-05-11 STATE close-out). All on origin/main.
5. Pytest verification (operator-side per Rule 7): `python -m pytest -q` should hit **1429 passed**.
6. **Alembic verification** (NEW step — added after this session's local-DB-drift false-alarm cycle):
   - `python -m alembic heads` should show **single head** `e7f8a9b0c1d2`. If multiple heads, halt and investigate.
   - `python -m alembic current` shows your local DB state — may be behind head depending on dev hygiene; that's fine for the session, only relevant if you're testing the new schema locally.
7. Check Railway: production deployed revision should now reflect Alembic head `e7f8a9b0c1d2` (Railway runs migrations on deploy). Chat-route runtime behavior is still unchanged since `54a56b1` — the new schema columns are dormant until application code reads them.
8. Ask Casey which thread he wants to start with — §7 below has multiple viable options.

## §1 — One-paragraph project summary

havasu-chat is **pivoting from chat-first concierge to a structured local directory + chat as one of three front doors** (browse + search + ask). V1 directory category locked: **Home Services** (plumbers, HVAC, pool, electrical, landscapers). Bootstrapped, founder-led sales (Casey-as-primary-salesperson), pivot-now (paused enrichment-as-scoped, redirecting operator effort to feed new directory shape). Pre-pivot infrastructure (`disclosure_renderer`, `placement_regime`, `confidence_tier` classifier, `confabulation_eval` harness, `verification_method` CHECK migration, smoke catalog infrastructure, `chat_logs` + disclosure telemetry) is reframed as backend trust infrastructure for the directory, not deprecated. Production at https://havasu-chat-production.up.railway.app, deployed via Railway from `main`. As of this session, the schema backbone for V1 directory pages is live (Category model + category_id FKs + Provider.attributes/district), with no application code yet reading the new columns — the next implementation lane is the Provider profile page.

## §2 — Final state at session close (2026-05-13)

- **Repo `main` HEAD:** **`11b248f`** — `docs(sponsor_outreach): Verified Presence ($79/mo) cold-pitch scripts (ChatGPT-drafted, primary-polished)`. (Note: PowerShell variable interpolation ate `$79` from the actual committed subject — reads as `(/mo)`. Cosmetic; not worth amending. See §5.) Pushed to origin/main.
- **Pytest:** **1429 passed** (1422 → 1429; +7 from `tests/test_directory_schema.py`).
- **Alembic head:** **`e7f8a9b0c1d2`** (directory pivot V1 schema, 2026-05-13; chains from `d6e7f8a9b0c1` Lane 4 disclosure-render telemetry).
- **Feature flags:** `FEATURE_FLAG_DISCLOSURE_RENDERER=false` (HOLD; less urgent post-pivot per pivot §6), `FEATURE_FLAG_CONFIDENCE_TIER=true`. Audience-signal persistence: AUTOMATIC.
- **Production runtime:** chat-route behavior unchanged since `54a56b1`. Schema migration `e7f8a9b0c1d2` will apply on next Railway deploy (single migration on top of currently-deployed `d6e7f8a9b0c1`); columns are dormant.
- **Working tree:** clean at session close.

## §3 — What shipped on 2026-05-13

1. **`a6e9f6c`** — `docs(pivot): lock §8 decisions 1-4 + add pivot-notice banners to PROJECT.md and HAVA_CONCIERGE_HANDOFF.md`. Four files (`docs/STRATEGY_PIVOT_2026-05-12.md` §8 status block, `docs/PROJECT.md` banner, `HAVA_CONCIERGE_HANDOFF.md` banner, `docs/SESSION_BOOT_PROMPT.md` overwritten with verbatim prose form). §8 decisions locked: taxonomy=12 as-proposed, Place model=defer to Phase 2, auth=Resend, map=Leaflet+OSM. §8 decisions 5–7 still open (pricing finalization, SKU naming, PROJECT/HANDOFF substantive rewrites — last is multi-week, deferred past Day 90).

2. **`6f6ef79`** — `feat(db): directory pivot V1 schema — Category model + category_id FKs + attributes/district on Provider`. Three files (`app/db/models.py` +60 lines, `alembic/versions/e7f8a9b0c1d2_directory_v1_schema.py` +115 lines new, `tests/test_directory_schema.py` +190 lines new). Implementation channel: Cursor on a heavily prescriptive multi-file brief (`outputs/cursor_brief_directory_v1_schema.md`). New `Category(Base)` class (12 seeded categories per pivot §8.1). Additive `category_id: Mapped[int | None]` FK on Provider and Program — parallel to legacy string `category` / `activity_category` columns; backfill is a future ticket. Additive `attributes: Mapped[dict | None]` JSON and `district: Mapped[str | None]` String(64) on Provider. `category_ref` relationship on both (named with `_ref` suffix to avoid name collision with existing `category` string attribute on Provider). Alembic migration uses `op.batch_alter_table` for SQLite-friendliness; seeds 12 categories via `op.bulk_insert(sa.table(...), ...)` (Cursor's pragmatic adaptation — `op.create_table` doesn't return a usable table object in this Alembic setup). Pytest 1422 → 1429.

3. **`aea87b8`** — `chore(lint): ruff --fix three pre-existing import issues (surfaced by ruff==0.15.12 pin in dev-requirements)`. Three test files (`tests/test_chat_route_integration.py`, `tests/test_entity_matcher_category_guard.py`, `tests/test_entity_matcher_trade_superlative.py`). Net diff: 2 insertions, 4 deletions. NOT caused by the schema commit — pre-existing issues that local older ruff didn't flag but CI's pinned `0.15.12` does. CI was likely failing silently on a few earlier doc-only commits as well.

4. **`597d9cb`** — `docs(BACKLOG+STATE): ship-log directory pivot V1 schema (6f6ef79) + ruff lint cleanup (aea87b8)`. Two files. BACKLOG.md gets two new no-ticket entries (schema + lint). STATE.md gets four surgical edits to the production paragraph (HEAD/pytest/alembic head/commit chain) plus a new "Recently shipped" entry at top.

5. **`11b248f`** — `docs(sponsor_outreach): Verified Presence (/mo) cold-pitch scripts (ChatGPT-drafted, primary-polished)`. New file `docs/sponsor_outreach/verified_presence_pitch.md` (~243 lines). 60-sec / 60-sec call / 3-min sit-down / voicemail / written follow-up + 8 anticipated objections + disqualifiers + pre-call checklist. Voice-anchored against `docs/sponsor_outreach/cold_email_templates.md`. `[CASEY: confirm <X>]` markers retained for demo URL, callback number, free-trial policy.

**Authored but not yet dispatched** (in `outputs/`, not in repo, not committed):
- `outputs/cc_prompt_rate_limiter_decisions_memo.md` — Claude Code prompt for #65 §8 decision memo. Read-only investigation lane; no git operations; output to `docs/maintainability/phase2_5_rate_limiter_decisions_memo.md`. Casey can paste to a fresh CC chat anytime.
- `outputs/chatgpt_prompt_provider_profile_ux.md` — ChatGPT prompt for the Provider profile page UX/copy spec. Will produce a markdown spec Casey reviews and Cowork primary polishes into the next Cursor implementation brief.
- `outputs/cursor_brief_directory_v1_schema.md` — already-shipped brief, kept for future reference.
- `outputs/backlog_ship_log_directory_v1_schema_DRAFT.md` — already-applied draft, kept for future reference.

## §4 — Dispatch channels used

- **Cursor** — schema lane (`6f6ef79`). Heavily prescriptive multi-file brief (3 files, +365 lines net). Ran cleanly, three minor pragmatic deviations Cursor reported transparently (the `sa.table()` bulk_insert workaround, comment line-offset adjustment, test-fixture adaptation for `init_db()` Alembic migrations).
- **ChatGPT** — Verified Presence cold-pitch scripts. Voice-anchored prompt; output landed `docs/sponsor_outreach/verified_presence_pitch.md` (~280 lines).
- **AskUserQuestion (Cowork primary → operator)** — locked §8 decisions 1–4 in a single round. All four answered with the recommended option.
- **Sub-agent** — not used this session.
- **Claude Code** — prompt for `#65 §8 decision memo` was authored but apparently not dispatched (or never paste-back-confirmed; Casey accidentally pasted Cursor's report into both "Cursor" and "CC" slots at one point).

## §5 — Working agreements + lessons absorbed

Canonical reference: `docs/maintainability/dispatch_protocol.md` (12 rules). All in force. **Three new lessons** worth folding into the dispatch playbook eventually:

1. **PowerShell variable interpolation hits commit messages too, not just `Invoke-RestMethod` bodies.** Rule 4 currently scopes to `Invoke-RestMethod`; should be broadened. Tonight's `git commit -m "...($79/mo)..."` lost the `$79` — committed subject reads `(/mo)`. Cure: single-quoted commit messages in PowerShell when subject contains `$`. Cosmetic incident this time; could be a real semantic problem if a future commit message needed to embed an actual variable-looking string.

2. **Local ruff installs on the Cowork primary's machine should match the version pinned in `dev-requirements.txt`.** Newer ruff has stricter I001 (isort) behavior; CI is pinned to `ruff==0.15.12` and started failing on three pre-existing test files when the schema-commit push triggered the first CI run after those issues took shape. Cure: `python -m pip install ruff==0.15.12` (or current pin) before any pre-commit lint check. Worth folding into `dispatch_channels.md` gotchas alongside Linux-bash-mount staleness and PowerShell encoding.

3. **`alembic current` showing a `(mergepoint)` label on an unexpected revision is a chain-walking diagnostic, not a multi-head alarm.** This session's false-alarm cycle: Casey's local SQLite dev DB was at `1a2b3c4d5e6f (mergepoint)`, primary initially read this as a multi-head conflict and held back the push. `Grep ^down_revision alembic/versions/` revealed the mergepoint is a long-resolved merge that lives 6 revisions earlier in the linear chain — Casey's local DB was just stale; production at `d6e7f8a9b0c1` was completely unaffected. Cure: when `alembic current` shows an unexpected revision, walk the down_revision chain forward via Grep before raising an alarm. Worth a one-line addition to the dispatch playbook.

**Two reinforced lessons from prior sessions (worth keeping front-of-mind):**

- **Schema-adjacent dispatch briefs should ground column names against `app/db/models.py` at line offset.** The schema brief I authored cited `Provider.category:36` and `Program.activity_category:248` directly. Cursor verified at step-0 and caught that `activity_category` had drifted to `:267` after edits to the file (originally `:248` per the brief). Self-correcting comment update — clean execution. (Lesson originally from #64 forensics, retained from `SESSION_HANDOFF_2026-05-12.md` §5.)
- **Don't trust a single Glob for "does this file exist."** Pre-dispatch alembic-versions Glob returned "No files found" because Glob's default cwd is the outputs sandbox not the workspace; switching to explicit `path` parameter or pairing with Grep resolves. (Lesson originally from #64 pre-dispatch hygiene, retained.)

## §6 — Open backlog at session close

### Truly open (could ship anytime)

- **#65 — Phase 2.5 third-party-source rate-limiter implementation** (DESIGN SHIPPED 2026-05-11; impl OPEN, MEDIUM; pivot bumped to MORE urgent). Gated on the 7 §8 open questions in `docs/maintainability/phase2_5_rate_limiter_design.md` + Casey decision on Phase 2.5 launch concurrency. **Decision-memo prompt is ready in `outputs/cc_prompt_rate_limiter_decisions_memo.md`** — paste to a fresh CC chat to unblock.
- **#39** — thread audience signal into placement-regime selection (DEFERRED to Phase 2; precondition: 4–6 weeks of `chat_logs.audience_signal` data — less urgent post-pivot).
- **#62** — trade-superlative scoring: alias-resolution vs disambiguation behavior (P3; chat-side concern, deprioritized post-pivot).
- Backlog #2 — `_time_bucket_first_hits` and broad `span` (Phase 2 candidate; unchanged).
- Backlog #18 — Repo hygiene & documentation hierarchy (PM phases A–D); ongoing under either vision.

### New top-of-queue work (post-pivot; per pivot §6 promoted bucket)

- **Provider profile page (`/provider/<slug>`)** — gates Verified Presence sponsor sales. **UX brief prompt is ready in `outputs/chatgpt_prompt_provider_profile_ux.md`** — paste to ChatGPT to get the spec, then I (next Cowork primary) polish into the Cursor implementation brief.
- **Home Services category landing page (`/category/home-services`)** — V1 directory proof.
- **Account-lite v0.1** — magic-link via Resend per §8.3 lock. Gates retention loops.
- **Sponsor claim flow + edit UI** — gates Verified Presence sales.
- **Per-merchant analytics dashboard** — gates Verified Presence value prop.
- **Backfill ticket: `Provider.category` (string) → `category_id` (FK)** — additive schema is in place; backfill maps existing legacy string values to the appropriate Category row. Not yet filed in BACKLOG. Worth filing as a P2 ticket when the next session starts.

### Deprioritized — chat-only concerns (per pivot §6 middle bucket; don't touch without Casey go-ahead)

- **HALT 3 close-out (#53)** — chat-surface gating; can defer 4–8 weeks past current expectation.
- **Smoke catalog ambiguity resolution** — chat-side validation; deprioritized.
- **#39 audience signal** — see above.
- **Phase 2.5 Premier inventory open (P2.PREM.1)** — original framing was a chat-surface placement concept; under the pivot, "Premier" reborn as a category-page sponsor slot (Category Visibility package per pivot §7).

### §8 decisions still open (per pivot doc §8 status block, updated 2026-05-13)

- **§8.5 Pricing finalization** — ground-truth via cold-pitch first. The cold-pitch script shipped this session is the instrument for this. Lock once Casey has 5+ pitch reps under his belt.
- **§8.6 Sponsor package SKU naming** — currently "Verified Presence" / "Category Visibility" / "Seasonal Takeover" from the report. Worth Casey-tone-checking once first sales conversations land.
- **§8.7 PROJECT.md / HAVA_CONCIERGE_HANDOFF.md substantive rewrites** — pivot-notice banners shipped this session; full rewrites deferred past Day 90.

## §7 — What to do first (next session)

Three viable starting threads, ranked by leverage:

1. **(Top) Dispatch the ChatGPT Provider profile page UX brief.** Paste `outputs/chatgpt_prompt_provider_profile_ux.md` to a fresh ChatGPT chat. When it returns, paste back; I (next Cowork primary) polish into a Cursor implementation brief. The Provider profile page is the gating piece for Verified Presence sponsor sales — schema is live, what's missing is the page that actually displays it.

2. **(Parallel-eligible) Dispatch the Claude Code rate-limiter §8 decision memo.** Paste `outputs/cc_prompt_rate_limiter_decisions_memo.md` to a fresh CC chat. Read-only investigation; output to `docs/maintainability/phase2_5_rate_limiter_decisions_memo.md`. When CC returns, frame the 7 decisions for Casey via a single AskUserQuestion round — that fully unblocks the rate-limiter implementation lane (now MORE urgent under the pivot per §6).

3. **(Alternative) File the `Provider.category` → `category_id` backfill ticket in `docs/BACKLOG.md`.** Small Cowork-primary task; specifies the mapping logic (free-text `category` strings observed in the current catalog → which Category slug they should map to), edge-case handling (NULL `category`, never-seen string, multi-tenant operator-collision), and the ingest-script changes needed so new rows land with `category_id` set going forward. P2 priority. Doesn't ship the backfill — just files it so it doesn't drift out of sight.

**Do not start without Casey explicit go-ahead** (deprioritized per pivot §6):
- ~~Smoke catalog ambiguity resolution~~ — chat-only, deprioritized.
- ~~HALT 3 close-out pre-investigation~~ — chat-surface gating, deprioritized.
- ~~Enrichment sprint kickoff as originally scoped~~ — needs re-scoping for new directory shape first.

## §8 — Reference docs and operational knowledge

- **Project state:** `docs/STATE.md`
- **Strategic direction (post-pivot):** `docs/STRATEGY_PIVOT_2026-05-12.md` (§8 status block updated 2026-05-13)
- **Backlog:** `docs/BACKLOG.md` (two new no-ticket entries at end as of this session)
- **Dispatch protocol (12 rules):** `docs/maintainability/dispatch_protocol.md`
- **Dispatch channel playbook + 7 gotchas:** `docs/maintainability/dispatch_channels.md`
- **Phase 2.5 rate-limiter design (7 open §8 Qs):** `docs/maintainability/phase2_5_rate_limiter_design.md`
- **HALT 3 definition + close-criteria:** `docs/maintainability/halt3_definition.md`
- **HALT 3 close-out template:** `docs/maintainability/halt3_closeout.md`
- **Post-enrichment smoke catalog (6 open spec Qs):** `docs/maintainability/post_enrichment_smoke_catalog.md`
- **LLM-mock pattern (project standard):** `docs/maintainability/llm_mock_pattern.md`
- **Sponsor outreach surface:** `docs/sponsor_outreach/cold_email_templates.md`, `cold_email_variants_2026-05-09.md`, `reply_handlers.md`, `post_launch_comms.md`, `enrichment_sprint_runbook.md`, `sponsor_quick_reference.md`, **`verified_presence_pitch.md` (NEW 2026-05-13)**
- **End-user FAQ:** `docs/user_facing/hava_user_faq.md`
- **Pivot-notice'd architectural docs (chat-surface architecture remains accurate as code-level reference; substantive narrative rewrite deferred past Day 90):** `docs/PROJECT.md`, `HAVA_CONCIERGE_HANDOFF.md`

---

*This handoff supersedes `SESSION_HANDOFF_2026-05-12.md` for purposes of "where is the project right now." The 2026-05-12 handoff remains valid for the prior-session narrative context (the pivot itself was decided then). Next agent: read THIS doc, optionally skim 2026-05-12 if you want yesterday's narrative, then dispatch.*
