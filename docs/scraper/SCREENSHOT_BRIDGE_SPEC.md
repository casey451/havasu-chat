# Spec: Screenshot capture bridge (image inbox) — for Claude Code

**Goal:** Let OpenClaw upload Facebook-post screenshots to havasu-chat so a Cowork
skill can later read them, judge them, and (later phase) publish. OpenClaw stays
dumb (upload only); all judgment happens in Cowork. This phase = capture + store +
let Cowork read. **No publishing logic in this PR.**

Build on a feature branch off latest `main`, tests + ruff green, open a PR, do NOT
merge (Casey merges).

## Reuse (do not reinvent)
- R2 upload: `app.photos.r2_client.upload_bytes(key, content, content_type) -> public_url` and `build_public_url`.
- Auth: the existing bearer-token dep from the ingest route — `require_ingest_token` (env `INGEST_API_TOKEN`). Import/reuse it; do not duplicate the token logic.
- DB session: `app.db.database.get_db`. Router registration in `app/main.py`.

## 1. New model + migration — `scrape_captures`
New table (additive migration; nullable-friendly). Suggested columns:
- `id` str PK (uuid)
- `business_name` str (nullable)
- `source_url` str(2048) — the FB page/post the shot came from
- `captured_at` datetime nullable — when the post was made/seen
- `image_url` str(2048) — R2 public URL
- `image_key` str(512) — R2 object key (for later cleanup)
- `status` str default "new"  — check in ('new','reviewed','discarded','flagged')
- `notes` text nullable — OpenClaw flags (e.g. "page blocked", "no FB page found")
- `created_at` datetime default now, indexed
- index on `status`

Write the Alembic migration following the repo's existing migration style.

## 2. Endpoints (token-authed; put in a new `app/api/routes/captures.py`, prefix `/api/ingest`)
- **POST `/api/ingest/capture`** — accepts `multipart/form-data`:
  - file field `image` (PNG/JPEG) — optional (allow a metadata-only "flag" row when OpenClaw couldn't capture)
  - form fields: `business_name`, `source_url` (required), `captured_at` (optional ISO), `notes` (optional)
  - If `image` present: read bytes → `upload_bytes(f"scrape-captures/{uuid4()}.png", content, content_type)` → store returned url + key.
  - Insert a `scrape_captures` row (status `"new"`, or `"flagged"` if no image). Return 201 `{id, status, image_url}`.
- **GET `/api/ingest/captures?status=new&limit=50`** — returns list of captures (id, business_name, source_url, captured_at, image_url, notes, status). For the Cowork skill to pull the queue.
- **PATCH `/api/ingest/captures/{id}`** — body `{status: "reviewed"|"discarded"}`. Lets Cowork mark items done. 404 if missing; validate status.

## 3. Tests (`tests/test_captures_api.py`, mirror tests/test_ingest_api.py)
- Auth required (no/!bad token → 401) on all three.
- POST with image (use a tiny fake PNG bytes; **monkeypatch `upload_bytes`** so no real R2 call) → 201, row exists, status "new", image_url set.
- POST without image + notes → 201, status "flagged".
- GET ?status=new returns the row(s).
- PATCH → status updates; invalid status → 422; missing id → 404.

## Notes
- Don't touch publishing or the live event/entity tables — this is just the inbox.
- Keep it small and idiomatic to the repo.
- After green tests + ruff, open the PR and stop.
