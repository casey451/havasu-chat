# Spec: Admin "Jobs" portal — one-click scraper pipeline (v0.1)

Goal (Casey): in the EXISTING admin (session-cookie auth — already live, used for
admin_contributions), add a **Jobs** page with buttons. Clicking a button queues a
job; worker agents (Cowork = brain, OpenClaw = hands) pick it up, do the work, and
the results land on the site (events calendar / offerings) after the review step.
Casey's only involvement: click the button (and, for now, approve the review report).

## New table: `jobs`
id (uuid) · job_type (enum: schedule_hunt | fb_capture_sweep | capture_review |
publish_approved) · status (queued | claimed | running | done | failed) ·
requested_by · claimed_by (worker name) · params (json) · result_summary (text) ·
created_at · claimed_at · finished_at

## API
- POST /api/admin/jobs {job_type, params} — admin session auth → creates queued job
- GET  /api/admin/jobs?limit=50 — admin session: job history for the UI
- GET  /api/ingest/jobs/pending?worker=cowork|openclaw — bearer INGEST_API_TOKEN;
  returns oldest queued job matching the worker's type map and marks it claimed
  (worker type map: openclaw → fb_capture_sweep; cowork → the other three)
- PATCH /api/ingest/jobs/{id} {status, result_summary} — bearer token

## Admin UI (Jobs page)
Buttons: "Hunt schedules (websites)" · "Capture Facebook (OpenClaw)" ·
"Review captures" · "Publish approved". Below: job table (type, status, when,
result summary). Status auto-refresh. Disable button while same type queued/running.

## Casey's directives (2026-06-03, override anything below that conflicts)
- Polling cadence: ~3x/day is fine for BOTH workers (e.g. 7am/1pm/7pm). Jobs are
  "run eventually", never urgent. Polls must be dumb/zero-AI: plain curl check;
  only wake the model when a job actually exists.
- The END GOAL is automatic upload to the website. Build the publish path so the
  full loop (hunt → capture → review → publish to live events/offerings) can run
  WITHOUT Casey once quality is proven. Keep the manual-approve mode as the
  initial setting, but auto-publish is the destination, not an afterthought.

## Workers (no app code — wiring notes)
- OpenClaw: a permanent cron (every ~10 min, isolated, exec-only) polls
  GET /api/ingest/jobs/pending?worker=openclaw with the .token file; if it gets a
  fb_capture_sweep job → runs the proven chromium-exec capture procedure over
  docs/scraper/schedule_hunt_fb_queue.csv (mirrored to /data/.openclaw/workspace/lhc/),
  PATCHes result. OpenClaw VPS is 24/7 → these jobs run within ~10 min of the click.
- Cowork: scheduled task polls the same endpoint for cowork jobs (runs when the
  Claude desktop app is open; "Run now" = immediate). schedule_hunt → website
  crawl pipeline; capture_review → COWORK_REVIEW_RUNBOOK; publish_approved → step 4.

## Publish path (the new, gated piece)
capture_review/schedule_hunt output proposed records (Offering+Schedule / Event
JSON per the data contract) stored as pending contributions (existing queue).
"Publish approved" job promotes ONLY records Casey approved in admin_contributions
to live tables. Phase 2 (after Casey trusts quality): auto-approve high-confidence
records — flip via a setting, not a code change.

## Build route
Casey pastes this spec into HIS Claude Code session → feature branch → PR → Casey
merges (auto-deploys). Backstop rules in CLAUDE.md apply (no direct main pushes).
