# HANDOFF — Lake Havasu autonomous Facebook scraper (continue here)

## DIRECTION CHANGE 2026-06-03 (late evening) — READ SCHEDULE_HUNT_PLAN.md
Casey shelved the bars sweep (cron lhc-fb-sweep DISABLED after 2/5 venues;
Barley Brothers + College Street captures are in the inbox awaiting review).
New priority: the schedule-hunt pipeline — see docs/scraper/SCHEDULE_HUNT_PLAN.md.
A daily Cowork scheduled task "havasu-schedule-hunt" (7am) drives it.
Everything below remains valid as infrastructure reference.

## SESSION UPDATE 2026-06-03 (evening) — PIPELINE IS LIVE ✅
The 401 is RESOLVED (OpenClaw container had a wrong INGEST_API_TOKEN; Casey
re-synced it from Railway). Current state:
- Barley Brothers (898KB PNG) and College Street (951KB PNG) uploaded →
  **HTTP 201** → sitting in scrape_captures as status=new.
- Cron `lhc-fb-sweep` is **ENABLED** (45-min cadence, 2 venues/run, exec-only
  chromium-headless procedure, self-disables when all 5 batch-1 venues done).
  Remaining: The Office, Flying X, Javelina (~2 more runs / ~1.5h).
- NEXT SESSION: (1) verify the sweeps completed (OpenClaw chat or sweep-state),
  (2) run `docs/scraper/COWORK_REVIEW_RUNBOOK.md` — NOTE the repo `.env`
  may still hold the OLD token; if GET /api/ingest/captures 401s, ask Casey to
  update `.env`'s INGEST_API_TOKEN to the new Railway value. (3) Compile the
  review report for Casey. Also: Casey should reject junk contributions
  #550/#551 in admin, and answer the 2 UNRESOLVED venues in the seed CSV.

## Earlier session detail (same day)

- **Step 1 DONE**: all 37 venues resolved → `havasu_bars_restaurants_seed.csv`
  updated. 33 verified FB pages; 4 closed venues marked EXCLUDE (Pennington's,
  Taco Hacienda, likely BBQ Bills + Octane); Bad Dogs → renamed Legendz; Turtle
  Beach Bar + Turtle Grille SHARE one FB page (scrape once); 2 UNRESOLVED for
  Casey (Black Rock Cafe — likely not in LHC; Sirens Cafe — that name is in
  Kingman, LHC match is "Siren's Bistro & Sweets").
- **Step 2 ~90% DONE** (OpenClaw chat, main session): lhc/ state files exist
  (master-list.json = first batch of 5: Barley Brothers, College Street, The
  Office, Flying X, Javelina; sweep-state.json; sent-hashes.json; .token file =
  copy of $INGEST_API_TOKEN, mode 600). Cron `lhc-fb-sweep`
  (id 46055f04-5340-4ddf-a7b6-79a98ea042a5) exists, **kept PAUSED**, payload is
  a full self-contained "screenshot courier" procedure.
- **KEY FIX — gateway browser control is broken container-wide; do NOT use the
  browser tool.** Screenshots work via exec headless chromium:
  `timeout 120 chromium --headless=new --no-sandbox --disable-gpu
  --disable-dev-shm-usage --hide-scrollbars --window-size=1366,4000
  --screenshot=/tmp/lhc/<slug>.png '<fb_url>'` → ~900KB 1366x4000 PNGs, proven
  on Barley Brothers + College Street (files in /tmp/lhc/).
- **BLOCKER**: uploads return **401** from /api/ingest/capture AND
  /api/ingest/contribution — same token that got 201 at 12:09 PM today.
  Token file == env var (verified MATCH, 43 bytes). So the SERVER side token
  changed after ~12:09 PM (Railway redeploy? token rotated?). ASK CASEY.
  Auth code: app/api/routes/ingest.py `require_ingest_token` (simple bearer
  compare vs env INGEST_API_TOKEN; 401 = mismatch, 503 = unset).
- DeepSeek lessons: it hallucinates tool names (oxylabs_web_fetch is a
  registered agent TOOL but errors when invoked; NOT a shell command), leaks
  malformed tool calls as text (then the action never ran — verify in the cron
  store), stalls mid-run (subagent died after hashing, before upload). Always
  demand raw outputs, give exact exec commands, verify stored state not claims.
- Local repo checkout git HEAD is BROKEN (parallel-session tangle) — repo work
  must go through Casey's Claude Code session, not here.
- Step 3 runbook written: `docs/scraper/COWORK_REVIEW_RUNBOOK.md` (review pass
  reads token from repo .env; verify that token still works after 401 fix).

**NEXT ACTIONS**: (1) Casey: check/rotate INGEST_API_TOKEN on Railway vs
OpenClaw container env — they no longer match; update OpenClaw container env
var AND regenerate /data/.openclaw/workspace/lhc/.token after fixing. (2) Rerun
the two uploads (exact curls are in the OpenClaw main-session chat, last
messages) or just re-trigger the cron manual run. (3) On 201s: enable the cron
(45-min cadence, self-disables when all 5 venues done). (4) Run the review
runbook on the captures. (5) Casey eyeballs report → then discuss next batch.


Read this first. Casey is non-technical: give him only paste-this/click-this steps;
never ask him to write code or hunt URLs. Casey's standing directive: build it,
use your judgment, only ask what you can't figure out.

## Architecture principles (Casey's explicit decisions — do not violate)
- **OpenClaw = dumb cheap hands**: navigate → screenshot → upload → flag problems.
  It must NEVER reason through problems or extract content (token waste + hallucination).
- **Cowork (Claude) = the brain**: resolves FB pages, vision-reads screenshots,
  categorizes, compiles reviews, solves everything OpenClaw flags.
- **Public Facebook Pages only.** NO login — protects Casey's personal account.
  (Private groups like Orchids & Onions deferred; would need his login = ban risk.)
- **Stop at review**: compile findings for Casey's sign-off. NOTHING auto-publishes
  yet. Auto-publish is a later phase after he validates quality.
- Onions (complaints) = internal-only, never published. Orchids (praise) = new
  community-mentions model (later phase).

## What is LIVE and verified
- **OpenClaw** on Hostinger VPS (srv1729030, Docker project `openclaw-y4qf`):
  https://openclaw-y4qf.srv1729030.hstgr.cloud — Casey logs in w/ gateway token.
  - Model: `openrouter/deepseek/deepseek-chat` (added to openclaw.json providers
    AND agent defaults.models allow-list; backup at openclaw.json.bak). Live-tested.
  - Env vars on container: OPENROUTER_API_KEY, INGEST_API_TOKEN (+ stock ones).
  - OpenRouter: funded ~$24.81, key capped $25/month. Oxylabs: 1,000 credits.
  - The Settings web UI is VERY laggy — config via chat/exec works far better.
    Chat tips: tell it "no GET re-verify loops"; model picker works via form_input.
- **App** havasu-chat (Railway, auto-deploys on merge to main):
  Base URL: https://havasu-chat-production.up.railway.app
  - PR #98 (merged): `POST /api/ingest/contribution` — bearer INGEST_API_TOKEN →
    pending Contribution (source forced to facebook_scrape). Test rows #550/#551
    are junk — Casey should reject them in admin.
  - PR #99 (merged): screenshot inbox — `scrape_captures` table +
    `POST /api/ingest/capture` (multipart `image` + business_name, source_url,
    captured_at, notes → R2, status `new`; metadata-only → `flagged`),
    `GET /api/ingest/captures?status=new&limit=50`,
    `PATCH /api/ingest/captures/{id}` ({status: reviewed|discarded}).
  - App repo flow: write a spec file → Casey pastes a prompt into HIS Claude Code
    session → it builds on a feature branch + opens PR → Casey merges (branch
    protection: PR required, approvals NOT required anymore). Works smoothly.

## Reference files (same outputs folder as this handoff)
- `havasu_scraper_data_contract.md` — where each info type lands in the schema.
- `openclaw_facebook_avenues.md` — all planned FB feeds, tiered.
- `havasu_bars_restaurants_seed.csv` — ~37 seed venues (fb_url column EMPTY).
- `SCREENSHOT_BRIDGE_SPEC.md` — spec PR #99 implemented.

## NEXT STEPS (in order — start at 1)
1. **Resolve Facebook Page URLs** for the seed CSV (Cowork's job): per venue try
   business website → Google Maps profile → `site:facebook.com` search. Update the
   CSV; flag unresolved for Casey (should be few). Do NOT guess URLs.
2. **Configure OpenClaw's sweep** (via its chat): a paced cron (~every 45 min,
   2 venues/run) spawning an isolated lightContext subagent that, per venue:
   open the public Page → screenshot posts from last 7 days → POST each image to
   /api/ingest/capture with curl + $INGEST_API_TOKEN → on ANY problem, POST a
   metadata-only flagged row and move on. State files on disk under lhc/
   (master-list.json, sweep-state.json, sent-hashes.json — OpenClaw drafted these
   earlier and knows the design). Idempotent, resumable, self-disabling when done.
3. **Build the scheduled Cowork review skill**: GET captures?status=new → fetch
   image URLs → vision-read → judge/categorize per the data contract → compile a
   review report for Casey → PATCH each to reviewed. Schedule it (or run manually).
4. **First batch = 3–5 venues only.** Casey eyeballs the review report. Only after
   his sign-off do we discuss auto-publish (which needs a publish auth path —
   not built yet, deliberately).

## Watch-outs
- DeepSeek may hallucinate — that's why it never extracts content.
- Facebook may block some fetches → OpenClaw flags, Cowork resolves later.
- FB CDN image URLs expire — always store the screenshot file itself (R2).
- One Claude Code session at a time in the repo (git tangles otherwise); my
  sandbox cannot do git worktrees on the mount — use Claude Code for repo work.
