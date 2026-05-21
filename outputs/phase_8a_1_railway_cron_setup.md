# Phase 8a.1 — Railway cron for scheduled conditions fetch

> **Status:** Setup walkthrough — operator action in Railway dashboard. No repo code change.
> **Authored:** 2026-05-21, post-handoff resume.
> **Why now:** Phase 8a is healthy on prod but all conditions cache fields are `is_stale=true` (>1h old). No auto-fetch was wired in the original Phase 8a ship (deliverable §3 mentioned "Railway scheduled jobs" but the cron was deferred). Manual `railway run python -m scripts.fetch_external_conditions --all` works but doesn't scale.

## What we're adding

A Railway cron service that runs `python -m scripts.fetch_external_conditions --all` every 15 minutes against the production database. No code changes; uses the existing script.

## The command + schedule

| Field | Value |
|---|---|
| Start command | `python -m scripts.fetch_external_conditions --all` |
| Cron schedule | `*/15 * * * *` (every 15 min — aligns with USGS native cadence; ~96 runs/day; well under AirNow 500/hr rate limit) |
| Env vars needed | Same as the web service: `DATABASE_URL`, `AIRNOW_API_KEY`, plus the public-source defaults already in `app/conditions/fetcher.py` |

## Railway dashboard steps

1. Open the `havasu-chat-production` project at https://railway.com (or whatever Railway domain you use).
2. In the project view, click **+ New** → **Empty Service** (or **GitHub Repo** → same repo).
3. Name it something like `conditions-cron` or `fetch-conditions`.
4. In the new service's **Settings**:
   - **Source:** point at the same `havasu-chat` GitHub repo, same branch (`main`).
   - **Build:** use the same Nixpacks config (Railway will detect `nixpacks.toml` automatically).
   - **Deploy → Start Command:** override to `python -m scripts.fetch_external_conditions --all`
   - **Deploy → Cron Schedule:** set to `*/15 * * * *`
   - **Deploy → Restart Policy:** **Never** (so a successful run doesn't restart the container).
   - **Networking:** do NOT expose a port — this is a job, not a web service.
5. In **Variables**, reference all the env vars from the web service. Easiest: click **Add Variable Reference** and pick `DATABASE_URL` + `AIRNOW_API_KEY` (any others your web service has that the fetchers touch).
6. Deploy.

## Verification

After the first cron run (within 15 min of deploy):

```powershell
$base = "https://havasu-chat-production.up.railway.app"
Invoke-RestMethod -Uri "$base/api/conditions" | ConvertTo-Json -Depth 5
```

Expected: every `*_updated_at_iso` field should be within the last 15 min; `*_is_stale` should be `false`; `*_staleness_label` should be `"Just now"` or `"Updated <hour ago"` (per the staleness label logic in `app/conditions/__init__.py` or similar).

If still stale after 20 min: check the Railway cron service logs for fetch errors. Watch items:
- **USGS HTTP 404** (per handoff §3) — `usgs.fetch_usgs_lake_havasu()` returns 404; partial-failure behavior expected.
- **AIRNOW_API_KEY missing** (per Phase 8a close-out) — must be set on the cron service's env, not just the web service.

## After this lands

1. Add ship-line to `docs/STATE.md` `## Recently shipped (high signal)` block:
   > **Phase 8a.1 — Railway cron for scheduled conditions fetch SHIPPED (2026-05-21).** Dashboard-only setup; no commit. New `conditions-cron` Railway service runs `python -m scripts.fetch_external_conditions --all` on `*/15 * * * *`. Verifies via fresh `*_updated_at_iso` + `is_stale=false` on `/api/conditions`. Closes the Phase 8a §3 "scheduled jobs" deferred carry.
2. Append a §11 entry to `outputs/phase_8a_close_out.md` noting Phase 8a.1 landed and the residual operator-action queue (AIRNOW_API_KEY set in cron-service env vars) is closed.

## Roll-back

If the cron service misbehaves, **Settings → Danger Zone → Delete Service** removes it cleanly with no data impact (the conditions cache is in the shared DB and just falls back to staleness). The web service is unaffected.
