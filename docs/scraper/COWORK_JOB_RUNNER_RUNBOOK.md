# Cowork job-runner runbook — the scraper's autonomous brain

Run this in a Cowork session (scheduled task: "run docs/scraper/COWORK_JOB_RUNNER_RUNBOOK.md").
It is the dispatcher that makes the one-click Jobs portal autonomous: poll the
jobs queue, claim one, do the work for its type, and report back. It ties
together the pieces that already exist:

- Jobs API + portal — `docs/scraper/ADMIN_JOBS_SPEC.md`
- Website crawl pipeline — `docs/scraper/SCHEDULE_HUNT_PLAN.md`
- Capture review — `docs/scraper/COWORK_REVIEW_RUNBOOK.md`
- Ingest + auto-publish contract — `docs/scraper/INGEST_PUBLISH_CONTRACT.md`
- Data contract — `docs/scraper/havasu_scraper_data_contract.md`

> OpenClaw (the "hands") is a SEPARATE permanent cron that polls
> `worker=openclaw` for `fb_capture_sweep` and runs the chromium-exec capture.
> This runbook is Cowork (the "brain") only: `worker=cowork`.

## Auth (never paste the token)
Token = `INGEST_API_TOKEN` from the repo-root `.env` (`grep ^INGEST_API_TOKEN .env`),
or the `.token` file in the Cowork workspace. Base URL:
`https://havasu-chat-production.up.railway.app`. If absent, ask Casey — never put
the token in chat, reports, or committed files.

## The poll must stay dumb (zero-AI when idle)
The scheduled task's FIRST step is a plain `curl` — only wake the model when a
job actually exists:

```bash
JOB=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/ingest/jobs/pending?worker=cowork")
# HTTP 204 / empty body  -> nothing queued, STOP (no model work).
# HTTP 200 + JSON job     -> the job is now CLAIMED; proceed to dispatch.
```

`GET /api/ingest/jobs/pending` atomically claims the oldest matching job, so two
runs never grab the same one. Capture the returned `id` and `job_type`.

## Always bracket the work with status PATCHes
```bash
# at start:
curl -s -X PATCH "$BASE/api/ingest/jobs/$JOB_ID" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"status":"running"}'
# at end (done or failed) with a one-line human summary:
curl -s -X PATCH "$BASE/api/ingest/jobs/$JOB_ID" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"status":"done","result_summary":"hunted 12 venues, posted 9 schedules (3 auto-published, 6 queued)"}'
```
On any unrecoverable error, PATCH `{"status":"failed","result_summary":"<what broke>"}`.

## Dispatch by job_type

### `schedule_hunt` → website crawl → POST findings
1. Pick the next chunk of candidates from `docs/scraper/schedule_hunt_candidates.csv`
   (work ~10–15 per run; SCHEDULE_HUNT_PLAN Phase 2/2b).
2. For each, fetch the site + likely schedule pages (or directory fallback) and
   extract the real class schedule per the data contract.
3. **Resolve `target_entity_id`** for the venue (see "Resolving the venue" below).
4. POST each finding to `/api/ingest/contribution` in the shape from
   `INGEST_PUBLISH_CONTRACT.md`: `entity_type:"program"`, `confidence` (your
   honest 0–1 read), `target_entity_id`, and a `proposed_record`
   (ProgramApprovalFields: title, description ≥20 chars, schedule_days,
   schedule_start_time/end_time `HH:MM`, location_name, provider_name, cost?).
5. Response tells you what happened: `published` (auto-published onto the venue),
   `queued` (kept for manual review), or `duplicate`. Tally for the summary.
6. Update the CSV (`schedule_found`, `schedule_url`) and compile a short report
   under `docs/scraper/reports/schedule_hunt_<date>.md`.

### `capture_review` → run the review runbook
Follow `docs/scraper/COWORK_REVIEW_RUNBOOK.md` to vision-read the capture inbox.
Where it says "do NOT create contributions" — that guard is now lifted for the
autonomous loop ONLY to the extent of POSTing findings to
`/api/ingest/contribution` with a `confidence` and (when you can resolve it) a
`target_entity_id`. Low confidence → low number → it queues for Casey. Still
flip capture statuses (`reviewed`/`discarded`) and leave "needs Casey" as `new`.

### `publish_approved` → batch publish
Call the batch endpoint (it is gated by `SCHEDULE_HUNT_AUTOPUBLISH`):
```bash
# preview first (writes nothing, ignores the gate):
curl -s -X POST "$BASE/api/ingest/publish" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"dry_run":true}'
# then the real run:
curl -s -X POST "$BASE/api/ingest/publish" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{}'
```
Put the returned `{published,skipped,errors}` into the job `result_summary`. If
the switch is off the endpoint publishes nothing and says so — that's expected
until Casey enables it.

### `discovery_audit` → find venues the DB is missing
Run SCHEDULE_HUNT_PLAN Phase 1b: web-discovery sweep per category, diff against
`schedule_hunt_candidates.csv`, add misses; audit `source LIKE '%test%'` /
hash-suffixed names for real-business shadows. Output a report; do NOT create
entities here (that's the gated `scripts/import_schedule_hunt_entities.py` →
Casey approves `--apply`).

## Resolving the venue (`target_entity_id`) — the important bit
Auto-publish attaches a schedule to an EXISTING entity. Give it the right id:
- Best: keep an entity-id column in `schedule_hunt_candidates.csv`. Populate it
  once from the entities table (the import created them with
  `source='schedule_hunt:2026-06-03'`); reuse it on every run.
- If you don't have the id, you MAY omit `target_entity_id` — the server will try
  a STRONG-signal reconcile (google_place_id / geo+name / contact), but a
  name-only guess is deliberately treated as ambiguous and the finding QUEUES for
  manual review rather than risk attaching to the wrong venue. So: prefer the
  explicit id; never fabricate one.

## Confidence guidance (drives auto-publish)
`confidence` is your honest read of "is this schedule correct and unambiguous?"
- ≥ 0.85 (the default threshold) + `target_entity_id` resolved → auto-publishes
  when the switch is on.
- Live grid you read cleanly, current site, exact times → high.
- Stale directory, inferred times, JS-only page you couldn't fully read,
  ambiguous venue → low (let it queue). When in doubt, go lower.

## Scheduling
Casey runs both polls ~3×/day (e.g. 7am/1pm/7pm). Auto-publish stays OFF
(`SCHEDULE_HUNT_AUTOPUBLISH` unset) until Casey trusts the queued output and
flips it; until then every finding lands in `/admin/contributions` for review.

## Hard-won watch-outs (carried from SCHEDULE_HUNT_PLAN)
- One Cowork session per task; isolated crons don't inherit chat context or env —
  read the token from the file.
- Directory hours lag (mohavelocal); unclaimed WellnessLiving stubs are useless;
  sports schedules carry end dates — check them.
- Never auto-create a new venue from here; new-venue discovery is the gated
  import script + Casey's approval.
