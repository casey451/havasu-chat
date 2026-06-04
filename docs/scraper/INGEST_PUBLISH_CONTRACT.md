# Ingest + auto-publish contract (schedule-hunt loop)

What the worker agents POST to havasu-chat to get a scraped **class schedule**
onto an existing venue. All endpoints use the machine-ingest bearer token
(`Authorization: Bearer $INGEST_API_TOKEN`). Base URL:
`https://havasu-chat-production.up.railway.app`.

## Auto-publish kill-switch (env, default OFF)
- `SCHEDULE_HUNT_AUTOPUBLISH` — unset/`0`/`false` → nothing publishes without a
  manual approve (everything queues). Set to `1`/`true` to enable no-human
  publishing of high-confidence findings.
- `SCHEDULE_HUNT_AUTOPUBLISH_THRESHOLD` — confidence floor (default `0.85`).

Both are read at request time; flipping the Railway env var takes effect on the
next request (no code change). Leave OFF until quality is trusted.

## 1. Submit a finding — `POST /api/ingest/contribution`
Send a contribution. For a class schedule the worker should send:

```jsonc
{
  "entity_type": "program",            // auto-publish only acts on "program" findings
  "submission_name": "Iron Age Gym",   // venue name (for audit / reconcile fallback)
  "source_url": "https://facebook.com/ironagehavasu/",
  "confidence": 0.95,                   // 0–1; must be >= threshold to auto-publish
  "target_entity_id": "<existing entity id>",  // the venue this schedule belongs to
  "proposed_record": {                  // ProgramApprovalFields shape — the schedule itself
    "title": "Morning Bootcamp",
    "description": "High-intensity outdoor bootcamp (>=20 chars).",
    "schedule_days": ["tuesday", "thursday"],
    "schedule_start_time": "06:00",     // exactly HH:MM
    "schedule_end_time": "07:00",       // exactly HH:MM
    "location_name": "Iron Age Gym",    // >=3 chars (use the venue name)
    "provider_name": "Iron Age Gym",    // >=2 chars (use the venue name)
    "cost": "$10",                       // optional
    "contact_phone": "928-555-0101",    // optional
    "contact_url": "https://...",       // optional
    "tags": ["fitness"]                 // optional
  }
}
```

Response:
- `{"status":"published","id":...,"entity_id":...}` — auto-published (gate on,
  confidence ≥ threshold, target resolved, payload valid). A recurring
  `Schedule` + `Offering` were attached to that existing entity. **No new venue
  is ever created** by auto-publish.
- `{"status":"queued","id":...}` — kept as a pending contribution for manual
  review in `/admin/contributions` (gate off, low confidence, no entity match,
  or invalid `proposed_record`).
- `{"status":"duplicate",...}` — a pending/approved contribution already has this
  `submission_url`.

### How the venue is resolved
1. `target_entity_id` if it names a real Entity (the precise, preferred path —
   the worker imported the venues and knows their ids).
2. Else a **strong-signal** reconcile (google_place_id / geo+name / contact
   tier). A name-only guess is treated as ambiguous and is **not** auto-linked —
   the finding queues for review instead.

## 2. Batch publish — `POST /api/ingest/publish`
For the `publish_approved` job: promote eligible pending findings in bulk.

```jsonc
{ "contribution_ids": [12, 13], "dry_run": false, "limit": 200 }
```
- Omit `contribution_ids` to act on all pending `facebook_scrape` contributions
  (capped by `limit`, max 500).
- `dry_run: true` → previews `{would_publish, would_publish_ids}` and writes
  nothing (works regardless of the gate — use it before flipping the switch).
- Live run respects `SCHEDULE_HUNT_AUTOPUBLISH`: if off, publishes nothing;
  if on, publishes each eligible row. Idempotent — safe to re-run.
- Returns `{published, skipped, errors, published_ids}` — write this into the
  job's `result_summary` via `PATCH /api/ingest/jobs/{id}`.

## 3. Jobs — `GET /api/ingest/jobs/pending?worker=...`, `PATCH /api/ingest/jobs/{id}`
Unchanged (see ADMIN_JOBS_SPEC.md). A `publish_approved` job → call
`POST /api/ingest/publish`; a `schedule_hunt` job → crawl + POST findings to
`/api/ingest/contribution`.

## Safety summary
Auto-publish only ever **attaches a class schedule to an already-existing
venue**. New venues, dated events, providers, low-confidence findings, and
anything that doesn't cleanly resolve all queue for manual review. The whole
behavior is off until `SCHEDULE_HUNT_AUTOPUBLISH` is set.
