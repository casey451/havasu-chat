# Paste everything below this line into Claude Code (havasu-chat repo)

Read docs/scraper/ADMIN_JOBS_SPEC.md and build it exactly as specced, plus the
small additions below. Follow CLAUDE.md rules: feature branch off main, pytest
green + ruff clean before every commit, open a PR and STOP — I merge.

BUILD (one PR):
1. The `jobs` table + Alembic migration, the four API routes, and the admin
   Jobs page from ADMIN_JOBS_SPEC.md, with these additions:
   a. Add a 5th job_type: `discovery_audit` (worker map: cowork). Button label
      "Discovery audit (find new venues)".
   b. PATCH /api/ingest/captures/{id} should also accept an optional
      `business_name` field (bearer token auth, same as status) — we have two
      mislabeled captures in the inbox (Flying X Saloon and The Office were
      uploaded under wrong names) and review passes need to fix labels without
      DB surgery.
   c. GET /api/ingest/jobs/pending must be safe under concurrent polling
      (claim atomically — single UPDATE ... RETURNING or equivalent).
2. Tests for: job create/claim/finish lifecycle, worker type map routing,
   double-claim race, captures rename, and admin-session auth on the admin
   routes.

DATA TASK (separate PR, dry-run first — do NOT apply without my approval):
3. Write scripts/import_schedule_hunt_entities.py that reads
   docs/scraper/schedule_hunt_candidates.csv and proposes:
   - new Entity rows (+ Location/ContactPoint/Category satellites) for venues
     not already in the DB by fuzzy name match — expect roughly 39 new ones,
   - a quarantine list of test fixtures: entities with source LIKE '%test%'
     or hash-suffixed names (e.g. the two "Bridge City Combat <hash>" rows),
     EXCEPT ones that shadow a real business in the CSV (report those
     explicitly so we keep the name and fix the row instead).
   It must support --dry-run (default ON) printing counts + a full proposed-
   changes table, and only write with --apply. Show me the dry-run output in
   the PR description. Schedules/Offerings do NOT get imported yet — that goes
   through the capture-review → contributions → publish path once the Jobs
   page exists.

Context you may want: docs/scraper/SCHEDULE_HUNT_PLAN.md (the pipeline),
docs/scraper/reports/schedule_hunt_discovery_2026-06-03.md (why the discovery
job type exists), docs/scraper/COWORK_REVIEW_RUNBOOK.md (what the
capture_review job runs), docs/scraper/havasu_scraper_data_contract.md (where
data lands). The ingest auth pattern is in app/api/routes/ingest.py.
