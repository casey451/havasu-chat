# Broken-link fix runbook

The VPS link sentinel emails a **work order** of confirmed-broken links (and shows
them at `/admin/link-health`). This runbook is for a Claude Code session handed
that report: how to investigate and fix each link **safely**.

> The report groups links by site, most-affected first. Systematic rot (a site
> that restructured its URLs) shows up as one site with many entries — fix those
> as a batch pattern, not one by one.

## Golden rules
- **Never auto-edit prod blindly.** Every fix is a prod DB write → follow the
  `CLAUDE.md` gate: **dry-run → show counts → Casey approves → apply.**
- **Fixes self-clear.** Once a URL is corrected (or the listing deactivated), the
  next 6-hour sweep marks it OK and it drops off `/admin/link-health` — no manual
  "resolve" step.
- The report **excludes** `blocked_by_site` (403/429) links — those are anti-bot
  walls, not dead links. Don't chase them.

## Decision tree (per link)
1. **404/410 but the site's root domain works** → the page *moved*. The local-AI
   verdict will usually say "business present on site." Find the correct URL
   (check the AI `suggested:` value if present, else browse/search the site), and
   update `Provider.website` (or `Event.event_url`). *This is the common,
   high-value case — e.g. `lhcaz.gov` restructured all its park URLs.*
2. **Root domain itself unreachable** across sweeps (DNS fail, connection refused,
   "domain for sale") → the business is likely **gone**. Confirm with a quick
   search of the business name; if defunct, **deactivate the provider**
   (`is_active=False`) rather than editing the URL. If it just moved hosts, update
   the URL.
3. **SSL certificate errors** (expired / self-signed / hostname mismatch) → the
   site usually still exists; a browser would load it past a warning. **Low
   priority** — note it, don't deactivate. Optionally fix `http→https` or a `www`
   variant if that resolves it.
4. **Event URL 404** (e.g. `golakehavasu.com/events/...`) → partner sites delete
   past-event pages. If the event date is **past**, no action (it'll age out); if
   **upcoming**, find the new URL or clear `event_url`.

## How the data + tooling work
- Table: `link_health` (one row per URL: `category`, `consecutive_failures`,
  `confirmed_broken`, `llm_assessment`, `llm_suggested_url`).
- Re-scan on demand (read-only): `python scripts/link_health_scan.py --workers 8`
  (add `--apply` to persist, `--email-summary` to send the work order).
- AI assess unassessed confirmed-broken links:
  `python scripts/link_assess.py --apply` (uses the local model on the VPS).
- On the VPS these run on timers (`havasu-linkcheck.timer` every 6h,
  `havasu-linkassess.timer` daily).

## Suggested fix flow for a session
1. Group the report by site; identify systematic patterns (one site, many links).
2. For each group, apply the decision tree; collect the intended changes
   (provider_id → new website, or deactivate) into a CSV/script.
3. Run the change script **`--dry-run`**, print the counts and a sample, and
   **stop for Casey's approval**.
4. On approval, apply, then trigger a sweep (`systemctl start
   havasu-linkcheck.service`) to confirm the fixed links drop off the list.
