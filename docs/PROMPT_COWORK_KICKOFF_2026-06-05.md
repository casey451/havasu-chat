# Cowork Kickoff — Browser, Research & Verification Workstream

**Created:** 2026-06-04 (Cowork review session) · **For:** future Cowork sessions, supervised by Casey
**Scope:** everything that needs a real browser, live-web research, or human-in-the-loop review.
Code PRs belong to the Claude Code workstream (`docs/PROMPT_CLAUDE_CODE_KICKOFF_2026-06-05.md`) — do not duplicate them here.

## Guardrails

- All CLAUDE.md rules apply: no prod DB writes, no railway/secrets, no merges to
  `main`. Ingest token comes from repo-root `.env` — never echo it.
- Do not do git work in `C:\Users\casey\projects\havasu-chat` if another session
  may be active there. Read-only access is fine.
- Contribution review: never use admin **Approve** on scraper findings targeting
  an existing entity (it creates a new venue) — they wait for auto-publish or the
  manual-attach flow from PR #127.
- Posting to `/api/ingest/contribution`: real schedules only, confidence per the
  Schedule Hunt conventions (single-week observation ≤0.70; 0.85+ reserved for
  multi-observation or authoritative sources), auto-publish stays OFF unless
  Casey enables it.

## Workstream A — Schedule Hunt continuation

Read `docs/scraper/SCHEDULE_HUNT_PLAN.md`, `docs/scraper/COWORK_REVIEW_RUNBOOK.md`,
and `INGEST_PUBLISH_CONTRACT.md` first. State from the 2026-06-04 run:

1. **Backfill `docs/scraper/schedule_hunt_candidates.csv`** with the 2026-06-04
   discoveries: websites/schedule URLs found, and statuses — dead sites (Trinity
   MMA, Flips For Fun), FB-only (Kaizen Golf & Fitness, Havasu Shaolin Kempo,
   Next Generation MMA), schedule-down (Havasu Pilates/Crazy Ed's), not-launched
   (Soul Lifting), stale-source-only (Marsh Dance Studios), blank-embed (LHC
   Pickleball). Most entity-id-map venues are missing rows entirely.
2. **Stingrays (contribution 567):** re-crawl gomotionapp.com/team/azhsaz when the
   summer schedule posts (reportedly 7–9a at the Aquatic Center); supersede 567.
3. **Eight Lotus:** observe a second week at 8lotuswellness.com/book-class (JS-only
   Mindbody widget — needs the Chrome extension). Two consistent weeks justify
   raising confidence toward the 0.85 auto-publish bar.
4. **Next venue batch:** continue down the entity-id map. Lessons: Mindbody/Wix/
   GoDaddy calendars need the browser; schedule-as-image needs vision+zoom; check
   season validity dates before posting; flag dead sites for an entity liveness flag.
5. FB-only venues queue for the OpenClaw sweep (`docs/scraper/openclaw_facebook_avenues.md`).

## Workstream B — SEO verification & measurement (paired with Claude Code SEO PRs)

After each SEO deploy, verify live (fetch + browser):

- Canonical/og:url are absolute `https` on provider/category/home/event pages.
- Post-D1: dead route family 301s correctly (spot-check legacy slugs:
  things-to-do, attractions, services, beauty-care); sitemap emits only the survivor.
- `/category/home-property-services` serves its ~237 providers; `?page=2` returns
  page 2 with crawlable links.
- JSON-LD validates (Google Rich Results test) — and confirm no Google-sourced
  `AggregateRating` remains if Casey picked option (a)/(b) on that decision.
- **Benchmark rank tracking:** the 13 queries in
  `docs/SEO_ASSESSMENT_PLAN_2026-06-04.md` §1 — monthly SERP checks, expanding to
  trade pages as they ship. First indexation check ~2 weeks after Phase 0
  (domain + Search Console) completes. Offer Casey a scheduled task for this.

## Workstream C — Research & off-page support (Casey-driven, Cowork assists)

- Domain shortlist: check availability/pricing for askhava.com, havasu.chat,
  havasuchat.com (footer already uses hello@havasuchat.com — confirm whether
  Casey owns it). Walk through Railway domain attach + Search Console + Bing
  verification when Casey is ready.
- Citations groundwork: Lake Havasu Chamber membership/directory requirements;
  press contacts at Havasu News-Herald and RiverScene Magazine with 2–3 data-angle
  pitches ("we mapped every plumber/restaurant in Havasu"); golakehavasu
  partnership angle (we already ingested their 543 partners).
- Phase 3 data depth, when Casey green-lights: hours backfill candidates
  (Shugrue's flagged), photo gaps, top-200 editorial descriptions — gather via
  browser; any DB write goes through the Claude Code workstream as a dry-run
  gated data op.

## Standing reminders

- Casey still has queued contributions **563–566** to review in admin (567
  supersedes later).
- Sandbox `/tmp` leftovers from old sessions (~900 MB: pr104, havasu-dupe-report,
  hava-fix) can be cleared; the hava-fix hint-extractor work is preserved at
  `patches/0001-hint-extractor-signal-gate.patch` and handled by Claude Code PR 1.
