# Schedule-hunt gather report — 2026-06-26

Recurring website crawl run. Browser (Claude-in-Chrome) **connected**. The
website tail of `schedule_hunt_entity_ids.csv` is fully exhausted from prior
runs, so this run re-read only the venues where a NEW recurring grid could
plausibly appear. None had refreshed → **0 POSTs**.

## Results

| Venue | entity_id | Classes posted | Response | Confidence | Source URL |
|---|---|---|---|---|---|
| Havasu Stingrays Swim Team | 98a4c54e-4969-4a81-a40b-0c562b150b1c | 0 | — (skipped, expired grid) | n/a | https://www.gomotionapp.com/team/azhsaz/page/practice/practice-schedule1 |
| Havasu Lions FC | c86f1829-db59-4f1b-815e-52d6908315c4 | 0 | — (skipped, no grid) | n/a | https://www.havasulions.com/ |
| Flips For Fun Gymnastics | d1497e49-e534-4a8b-bf89-3736c41db97c | 0 | — (skipped, site dead) | n/a | https://www.fffhavasu.com/ |
| Windy Hills Pottery & Art Studio | 1bee349f-d380-4425-b28c-e11993e7da8a | 0 | — (skipped, site dead) | n/a | http://windyhillsartstudio.com/ |

**Tally:** 0 POSTs → 0 published / 0 queued / 0 duplicate. 4 venues re-read.

## Detail

- **Havasu Stingrays** — practice grid reads cleanly off
  `/practice/practice-schedule1` but is still labeled "Starting Nov 10, 2025 –
  June 2, 2026", which **expired 6/2**. No summer grid published yet. Won't post
  an expired/invented schedule. This remains the highest-value re-check for a
  future run (summer practice times).
- **Havasu Lions FC** — homepage still "Recreational Fall 2026 OPENING SOON!!";
  no day/time grid, registration not yet open. Skip.
- **Flips For Fun Gymnastics** — `fffhavasu.com` still serves a browser error
  page (site/DNS dead across many runs). Skip.
- **Windy Hills Pottery & Art Studio** — `windyhillsartstudio.com` still serves
  an error page. Skip.

## Flags for Casey

- ⚠️ **Auto-publish is still ON.** Write-free dry-run of `/api/ingest/publish`
  returned `autopublish_enabled: true` (candidates 30, would_publish 1, id 610),
  unchanged from prior runs. The task premise ("Auto-publish is OFF") does not
  match production. Nothing was posted this run, so nothing auto-published, but
  please confirm `SCHEDULE_HUNT_AUTOPUBLISH` is intentionally enabled.
- The remaining un-posted CSV venues are all either FB-only/website-less
  (OpenClaw's job) or future seasonal re-posts (Stingrays summer, Lions FC fall).
  No new clean weekly grid was postable this run.

No git operations performed. No Approve clicks in the admin UI.
