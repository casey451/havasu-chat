# Ask Hava — Master Execution Plan (2026-06-10)

Synthesizes five reports against the live repo (all key claims verified on
`feat/chat-routing-family-mode`):
1. Live site audit (WS-1–16, B1–B9, catch-all addendum)
2. Chat routing / family mode branch (committed, 1 ahead of main, awaiting PR)
3. Security/perf/ops audit (SEC/PERF/OPS)
4. Chat deep dive + monetization (incl. §4b retrieval root cause, §6 failure hunt)
5. Admin portal handoff (built, unwired, untracked)

**Operating model:** Cowork (this session) = specs, research, curation, data analysis,
PR review, plan upkeep. Claude Code = all code changes, feature branches, CLAUDE.md gates
(tests + ruff before commit, PR only, dry-run for prod data). Casey = merges, prod writes,
credentials, local-knowledge calls. Parallel Claude Code sessions use **separate git
worktrees** — never the same checkout (per CLAUDE.md).

---

## STATUS — end of day 2026-06-10 (Cowork upkeep pass)

**✅ INCIDENT RESOLVED + ALL MERGES COMPLETE (late 06-10, Cowork-executed with Casey's
authorization):** #243's build failure (unpinned Python floated to 3.13.14, no mise
binary) fixed by **#247** (`.python-version` = 3.13.13 + `requires-python`; CC authored,
Cowork merged). Then **#243 → #244 → #245 → #246 all merged and live-verified**:
`/health` 200 + `db_connected` · old café slug 301 → `cafes-and-coffee` 200 (migration
`c7e3a9d1f5b8` applied) · `/admin/portal` wired (auth-gated, was 404) · `/chat` +
`/events` 200. Both migrations applied via preDeploy. Toolchain-version skew
(ruff/mypy/CI still py311) queued as OPS-10 in the Track D prompt.

**Shipped today, awaiting Casey's merges** (review: `docs/PR_REVIEW_AND_MERGE_CHECKLIST_2026-06-10.md`
— all four APPROVED, merge order #243 → #244 → #245 → #246):
- **Track A ✅ → PR #243** (SEC-1/2/3, OPS-1/2/3, B6, B1/B3 café slug + migration)
- **Track E ✅ → PR #244** (portal wired, audit-log migration, pricing; stacked on #243)
- **§0.2 ✅ → PR #245** (family-mode branch has its PR; seed dry-run done: 2 inserts pending `--commit`)
- **OPS-6/OPS-9 ✅ → PR #246** (outputs/mockups untracked, ignore files; independent;
  gap fix `9266c52f` added the ignore-file edits the first commit missed — CI-green again)

**Cowork deliverables today:** B0 spec ✅ `HAVA_AUDIT_AND_TAXONOMY_REBUILD.md` (Casey
approved §8 decisions; count ranges + WS-3 paste still open) · WS-6 ✅
`docs/LAKE_CONDITIONS_SPEC.md` (endpoints live-verified; RISE prod-verify is the gate) ·
WS-7 ✅ `docs/RAMPS_DATA.md` (official fees verified; CVB table stale ×2) · WS-9/10 ✅
`docs/EDITORIAL_WS9_10_LAUNCH_PACK_2026-06-10.md` (3 drafts) · regression anchors ✅
`scripts/eval_anchors/` · kickoff prompts ✅ `docs/PROMPT_CLAUDE_CODE_TRACK_B_2026-06-10.md`
+ `docs/PROMPT_CLAUDE_CODE_TRACK_D_2026-06-10.md`.

**Casey's remaining manual list — FINAL (end of 06-10):** ① §0.1 password rotation —
**the only security item left** (step-by-step given in chat; CC's prod session is done,
safe to rotate now; includes revoking the .env.ghtoken* GitHub tokens) · ② UptimeRobot
monitor on `https://askhava.com/health` (his login; HTTP, 5-min, alert non-200) ·
③ Skates-vs-Sk8-Club call → approve the 2 seeded drafts (✅ seed applied by CC:
desert-hawks-rc-club + havasu-skates-sara-park-roller-rink, both draft+pending, draft
gate verified — 404 publicly) · ④ sponsors@askhava.com alias decision → CC's one-line
swap is parked ready. **Env checks ✅ closed by CC:** TIER3_MODEL unset → default
gpt-4.1-mini, pricing constants correct as shipped; AUTH_MAGIC_LINK_BASE_URL =
askhava.com. **Verified done tonight:** all merges ✅ · BASE_URL ✅ (legacy domain 301s) ·
Search Console ✅ (property live, sitemap submitted, Status: Success) · TIER3_MODEL +
AUTH_MAGIC_LINK_BASE_URL checks handed to CC (single-var protocol). Superseded list
below kept for history: ② merge the four PRs + post-#243 spot-checks
(slug pre-check ✅ done — prod has exactly one row, the old slug; migration safe) ·
③ §0.3 `seed_family_venues --commit` after #245 (+ Skates vs Sk8 Club call) · ④ §0.4 CSV
export → unblocks C1 hunt · ⑤ UptimeRobot on `/health` post-#243 · ⑥ TIER3_MODEL env
check · ⑦ sponsors@ alias decision · ⑧ #235 follow-ups (BASE_URL vars, Search Console).

**Next sessions:** Track B worktree (prompt ready, **now seeded with prod data prep** —
`scratch/TRACK_B_DATA_PREP_2026-06-10.md`: 199 dedupe candidate groups mined, B2's
C=25/m≈4.47 decided, WS-4 queue sized 377+976, spec §4 ranges validated against live
counts) · Track C worktree (prompt ready) · Track D worktree (prompt ready). All
unblocked — merges are done.

**B1+B2 ✅ SHIPPED + LIVE (late 06-10 → early 06-11, Cowork-executed, Casey-gated):
#248 #249 #250 all merged, deployed, live-verified.** B1: dedupe resolutions table
+ multi-location/parent-child paths + queue persistence + merge-301/place_id-move
fixes + provider-level ingest gate + batch place_id script (prod dry-run: 0 pairs,
as predicted). B2: WS-2 Bayesian C=25 live-m at all sort sites (hard review tier
retired) · WS-4 shipped AND prod data passes applied (run 1: 110 addresses + 373
zips; precision patch #249 killed the 268 street-name false positives; run 2: 106
pipe-seam fixes, 0 holds — snapshots at repo root). **Copy audit 2026-06-10 also
shipped in #249/#250** (hero B template default, /sponsor teaser, jargon sweep,
voice fixes, Featured row gated on sold inventory, `docs/COPY_VOICE.md`).
**Uncommitted on disk (next commit):** review-excerpt recency ordering (audit §5b)
+ `scripts/check_taxonomy_anchors.py` (§6.1 phase gate, tested) + this status
block. **Casey-only leftovers:** unset `HOME_HERO_HEADLINE` (+eyebrow) on Railway
so hero B renders · portal queues (17 T3 dedupe confirms → T2 phone → Address
flags) · sponsors@ alias → one-line mailto swap. Hooks: `GIT_OPTIONAL_LOCKS=0`
added to both graphify hooks after three stale-lock collisions. Remaining Track B:
WS-5 zones (needs spec session) · B3 taxonomy phases (anchors checker ready) ·
B4 bug batch.

**SESSION CLOSE 2026-06-11 ~03:30 — full-night ledger.** Merged + deployed +
live-verified: **#248** (B1 dedupe engine + B2 Bayesian/WS-4) · **#249** (WS-4
precision + copy audit) · **#250** (leaf intro) · **#252** (§5b excerpts + §6.1
anchors checker) · **#254** (B3 phase-1 prep: anchors reconciled to prod, 12-row
QSR remap CSV, --department filter, `docs/ZONES_WS5_SPEC.md` with D1–D4) ·
**#255** (OPS-10 toolchain pin — pulled forward from Track D; CI now reads
`.python-version`). Prod data passes applied with snapshots: 216 addresses +
373 zips; place_id tier 0 as predicted. **Parallel sessions:** Track D ✅
COMPLETE — 5 bundles awaiting Casey's fetch+push (**skip its ops10 bundle,
superseded by #255**; answer its playwright/pytesseract question). Track C 🔄
RUNNING — PRs #251 + #253 pushed, CI-green; review after it goes idle. QA
second pass ✅ — `COWORK_SECOND_PASS_FIXLIST_2026-06-10.md` now carries a
do-not-execute-§0.1 annotation (mount mirage) + overtaken-by-events list; its
real new finds (reserve-form category taxonomy = funnel blocker · double-escaped
/categories names · "event has passed" timing · /search raw tokens · /group
pages · ICS junk titles) are the next bug batch. E&D phase runbook:
`docs/ED_PHASE1_PREP_2026-06-11.md`.

**FINAL STATE ~04:30 (supersedes the two blocks above): ALL TRACKS LANDED.**
Track C merged everything: C-PR-1…6 (#251 #253 #256 #257 #259 #260) + **C3
conversation restore (#265)** + **audit fix batches 1+2 (#266** — event
classifier/dedup, privacy renderer, favicon, **reserve-form taxonomy** ✅,
proxy headers). Track D's four bundles landed as #261–#264 (ops10 correctly
skipped). One dropped Railway webhook was re-triggered (CI #1056). Post-stack
live sweep ✅: /health db_connected · home · events-ui · restaurants leaf
(160 — QSR phase still pending its gated run) · gas · chat. **~20 PRs merged
and deployed in one night, all verified.** Still open: the Casey-only list
above (Railway hero env, E&D phase run, portal queues, sponsors@, ranges,
WS-5 D1–D4, live-site-audit paste for B4/WS-3) + QA leftovers not covered by
#266 (double-escaped /categories names · "event has passed" timing · /search
raw tokens · /group pages · ICS junk titles · page-cache vintage skew).

**C1 ✅ RUN (late 2026-06-10, on CC's CSV export):** 8.2% real miss rate (118/1,432
turns, 31 HIGH). Top families: standalone events ~48 turns (pull into first C batch),
plumber/trades ~14 (the §4b hay gap), Tier-1 fuzzy + spell-correct shapes. Results +
`_QUERY_TO_LEAF`/synonym spec + ad-outreach order:
`scratch/FAILURE_HUNT_RESULTS_2026-06-10.md`. **Late addendum (CC verification +
gap re-mine):** gap leakage measured via `tier_used='gap_template'` — of ~62 real-user
gap turns, ~92% are false positives (catalog has the answer; Mudshark misspellings,
events, discovery intents) → total real-miss surface ≈ 12.3% of turns; `feedback_signal`
pipeline verified fine, zero real users have clicked thumbs since 06-05 (→ new C-PR-6:
visible thumbs). Track C prompt updated accordingly.

---

## 0. Today — Casey, manual (~45 min)

1. **Rotate the prod Postgres password.** `.env` and `.env.produrl` at repo root contain
   the full prod `DATABASE_URL` with password (flagged independently by the monitoring plan
   and the portal handoff; verified present). Untracked, but multiple agent sessions read
   this directory. Also audit/rotate `.env.ghtoken` / `.env.ghtoken2`; delete or rename all
   four; add explicit gitignore entries for `pull_prod_env.ps1` / `check_prod_env.ps1`.
2. **Review + merge the family-mode PR** (`feat/chat-routing-family-mode`, tests green).
   Unblocks: chat→page hand-off, calendar family mode, chat P0 fixes going live.
3. **Seed script:** run `scripts/seed_family_venues.py` dry-run → approve `--commit`.
   Local-knowledge call: Havasu Skates vs Havasu Sk8 Club (same rink?).
4. **Export prod CSVs** into `scratch/` per chat deep dive §6 (providers + chat_logs
   minimum). Unblocks the failure hunt (Track C).

## Track A — Hotfix batch (Claude Code, one branch, ~1 day)

Small, verified, high-value diffs in a single PR:
SEC-1 admin cookie `secure=` + v1 `samesite="strict"` · SEC-2 per-IP limit on both admin
logins · OPS-1 `/health` 503 on DB failure + `healthcheckPath` in railway.json · OPS-2
fail-closed on empty `DATABASE_URL` in prod (kill SQLite fallback) · OPS-3 try/except +
Sentry around `_hourly_cleanup_loop` · SEC-3 Jinja2→3.1.6 · B6 hello@askhava.com ·
B1/B3 slug fixes with 301s. Plus external: UptimeRobot pinger (no code).

## Track B — Data integrity (keystone; blocks ad sales)

Every flaw here is on pages where businesses are asked to pay. Order:

- **B0. ✅ DONE 2026-06-10 — `HAVA_AUDIT_AND_TAXONOMY_REBUILD.md` written** (Cowork; from
  COVERAGE_GAP_AUDIT + A-migration CSV + codebase; WS-3/Part 7 sections marked provisional
  pending Casey's paste). Casey approved the §8 structural decisions same day. Still his:
  expected-count ranges (HVAC 20+, etc.) and the WS-3 reconcile. Kickoff prompt:
  `docs/PROMPT_CLAUDE_CODE_TRACK_B_2026-06-10.md`.
- **B1. Dedupe engine (WS-1).** place_id exact merge → phone / name-similarity+street-number
  candidate queue → enriched-record-wins merge with 301 slugs → ingest gate. Extend existing
  `merge_duplicate_provider_slugs.py` / `cross_source_dedup_audit.py`. Add resolution paths:
  *same business, multiple locations* and *parent org / departments* (Specialty Associates).
  DB-wide, not per-category. **All merges: dry-run → counts → Casey approves.**
- **B2. WS-4 addresses** (structured components, never concatenate; pattern-check flag
  queue) · **WS-2 Bayesian ranking** (C≈25–50, FAQ text updated to match — small,
  independent, ship early) · **WS-5 zones** (In town / Nearby / Out of scope; gas headline
  scoped).
- **B3. Taxonomy migration:** Eat & Drink first, **Health & Medical second** (largest, most
  broken, highest consequence). Regression cases 1–10 from the audit go into the
  confabulation harness (`scripts/confabulation_eval.py` exists).
- **B4. Bug batch B2/B4/B5/B7/B8/B9** rides along.

## Track C — Chat retrieval, memory, correctness (parallel with B via worktree)

- **C1. Failure hunt (Cowork, gated on §0.4 export).** Run
  `scratch/audit_retrieval.py mine` + `sweep`, produce ranked miss list → immediate
  leaf-dict + synonym-group additions, sizing data for C2, and the ad-outreach lead list.
- **C2. Retrieval fixes (§4b):** category-aware Tier-3 retrieval (Google categories + FTS,
  push filtering into SQL — this *is* PERF-2), service-intent → leaf routing, gap-template
  false-positive fix (boat rentals!), Tier-1 fuzzy matching. Embedding retrieval is step 2
  *after* resolving the 32-dim vs 1536-dim mismatch noted in repo docs.
- **C3. Conversation restore:** frontend calls `/api/chat/history`; last ~6 turns into
  Tier-3 context; persist session hints to DB.
- **C4. Correctness backlog:** standalone events in Tier-3 context, cache key + intent,
  day-specific hours gaps, LLM retry/backoff, per-session rate limit.
- **Conflict to manage:** SEARCH_DEMAND_INTEGRATION_PLAN WS1–4 also touches the intent
  classifier. One owner, sequenced — recommend C2 lands first, search-demand rebases on it.

## Track D — Perf/ops hardening (after A, alongside C)

PERF-1 pool sizing + release connection before LLM calls · PERF-3/4 sync work off the event
loop (contribute route, session middleware) · PERF-5/6 parallelize hint/embedding calls ·
OPS-4 stale-job reaper · OPS-5 preDeploy as sole migration owner · OPS-6
`git rm --cached outputs/ mockups/` + `.railwayignore` · OPS-7 deps (drop passlib/bcrypt,
pytest→dev, decide playwright) · OPS-8 logging config. PERF-7 streaming lands with C3.

## Track E — Admin portal wiring (small PR, do early)

Wire `portal_router` in main.py, promote audit-log migration (dry-run gate), nav link, move
smoke tests into `tests/`, set real pricing constants in `chat_insights.py`. Cheap, and the
queue cards + chat insights directly support oversight of Tracks B and C (dedupe queue,
unmatched-query mining). Follow-up: per-admin accounts to retire shared `ADMIN_PASSWORD`.

## Track F — New surfaces (starts once B stabilizes; the traffic plays)

Order by value/effort: **WS-6 `/lake`** (✅ spec done — `docs/LAKE_CONDITIONS_SPEC.md`;
endpoints live-verified, RISE Railway-IP check is the implementation gate) → **WS-7
`/ramps`** (✅ data done — `docs/RAMPS_DATA.md`; 4 private-operator fees need phone
verify) →
**WS-11** calendar unique-events fix + "Visiting this weekend" view → **WS-8** rental tags +
kayak ingest pass → **WS-14 `/urgent`** (gated on Urgent Care subcat from B3) → **WS-9/10**
collections + landmark pages (✅ editorial drafted —
`docs/EDITORIAL_WS9_10_LAUNCH_PACK_2026-06-10.md`: London Bridge + Parker Dam landmark
pages, kids collection; ⚠ Parker Dam road-crossing fact must be verified pre-publish) →
**WS-12/13/15/16**.
SEO items (JSON-LD, OG images, canonical 301s, internal linking) ride with each.

## Monetization sequence

Sell nothing until B1–B3 + WS-4/5 are live ("fix before selling"). Then, in order:
1. Chat ad readiness: gap-leak fix, sponsor ranking by `weight`, double-mention guard,
   `chat.sponsored.impression/click` events, frequency caps → **sponsored card** unit →
   flip the flag.
2. Stripe Phase 1 Checkout ($39 listings, $19 event boosts).
3. Advertiser stats page (retention).
4. Sales motion: `query_log` demand data + Hunt-A miss list = cold-email list.
5. Enforce category exclusivity + founding-partner terms in the approval flow.

## Rough sequence

- **Week 1:** §0 today-items, Track A, Track E, B0–B1 start, C1 hunt run.
- **Weeks 2–3:** B1–B4 merges (Casey-gated), C2–C4, Track D.
- **Week 3+:** Track F begins, monetization checklist, flip chat ads when B+C2 verified.

**Leading metric:** repeat/direct visits to utility pages (gas → lake, ramps, urgent) —
the habit-formers that make ad inventory worth buying.
