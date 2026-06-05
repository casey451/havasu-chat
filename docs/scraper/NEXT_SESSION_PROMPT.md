# Paste this to start the next Cowork session

Continue my Lake Havasu scraper project in the havasu-chat folder. Read
docs/scraper/SCHEDULE_HUNT_PLAN.md, docs/scraper/PROJECT_HANDOFF.md, and
docs/scraper/ADMIN_JOBS_SPEC.md first — follow their rules (OpenClaw = dumb
screenshot hands, Cowork = brain, nothing auto-publishes yet).

Then, in order:
1. Using dynamic workflows / parallel agents, re-crawl ALL websites in
   docs/scraper/schedule_hunt_candidates.csv to verify and deepen the 2026-06-03
   first pass: extract complete schedule data (days, times, prices) including the
   PDF schedules (Beyond Dance, Aquatic Center) and js-only sites via rendered
   fetch where possible. Update the CSV and write a dated report in
   docs/scraper/reports/.
2. Set up the Facebook capture sweep for docs/scraper/schedule_hunt_fb_queue.csv
   (15 venues) on OpenClaw: open https://openclaw-y4qf.srv1729030.hstgr.cloud in
   Chrome, START A NEW OPENCLAW SESSION (main session is ~40% context — use New
   session), and build a cron named lhc-schedule-sweep using the EXACT proven
   procedure in PROJECT_HANDOFF.md (exec-only chromium headless screenshots,
   .token file auth, state files under lhc/schedule-*, paced 2 venues/45min,
   self-disabling). Supervise its first run, verify 201s.
3. Run the capture review per docs/scraper/COWORK_REVIEW_RUNBOOK.md on everything
   in the inbox (includes 2 bar captures from 2026-06-03) and produce my review
   report.
4. Remind me to paste docs/scraper/ADMIN_JOBS_SPEC.md into my Claude Code session
   to build the admin Jobs page + publish path — that's what makes this all
   one-click from the website admin afterward.

I trust your judgment — only ask me about things you can't figure out.
