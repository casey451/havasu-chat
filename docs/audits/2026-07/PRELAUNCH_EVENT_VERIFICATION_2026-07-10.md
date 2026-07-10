# Pre-launch deep event verification — 2026-07-10

**Scope:** every live event in the next 30 days, source-confirmed or quarantined
before launch, across three layers. **Method:** a new DB-free harness
(`scripts/prelaunch_verify.py`) that cold-fetches the LIVE site and re-fetches
each event's origin — no database, so it runs on a laptop now and as a nightly
CI cron unchanged.

- **Catalog:** 423 live events; **189 in [2026-07-10, 2026-08-09]** (non-recurring).
- **Running build:** `d5982c22312f` (= `origin/main`; prod == main, no pending deploy).
- **Launch gate (14 d):** **FAIL** pre-remediation — 9 blocking findings + 11
  render anomalies. Path to PASS is below; every fix is gated on your approval.

Raw artifacts (this run) live in `docs/audits/2026-07/prelaunch/`:
`discrepancies_2026-07-10.csv` (107 rows), `render_digest_2026-07-10.md`,
`launch_gate_2026-07-10.md`.

---

## How each layer works (and why no DB)

The repo `.env` points at Railway's **internal** host — no local prod DB. But the
public site exposes everything the three layers need, so the harness verifies the
site *against its sources* with zero DB dependency:

- **Catalog** = one cold GET of `/events.ics` (whole live calendar: id, title,
  precise DTSTART/DTEND, LOCATION, DESCRIPTION, source URL, CATEGORIES).
- **Layer 1 (source re-verify):** re-fetch each in-window event's source URL,
  extract JSON-LD `Event`, and field-compare date/time/venue. **Double-confirmed:**
  any quarantine verdict is re-fetched once and downgraded to a flaky-review unless
  both fetches agree (usabmx and some Cloudflare sites return intermittent 404s to
  a bot UA — a single dead reading is not proof).
- **Layer 2 (lint battery):** the full `app.events.lint` set over the window — the
  existing AM/PM-flip, venue-hours, P&R-facility, landmark rules **plus six new
  pre-launch rules** (weekday-in-title, season-out-of-season, generic/address
  venue, missing time, ALL-CAPS title, category↔keyword contradiction), all
  unit-tested (`tests/test_events_lint_ws6.py`, 104 cases green).
- **Layer 3 (render sweep):** cold-curl every day page for 21 days + `/family/camps`
  + `/night` + `/movies?date` for 7 days. Per page: build-sha == running build;
  every event row has a working link (no unlinked plain-text rows); a time label
  (or explicit all-day/hours); a non-generic venue; section header count == rows.
  Movies assert every film has showtimes and none is implausibly early (the Moana
  "4 AM" class).

Run it: `python scripts/prelaunch_verify.py --base-url https://askhava.com`.
Nightly: `.github/workflows/prelaunch-verify.yml` (workflow_dispatch now; the
cron activates only once merged to `main`).

---

## LAYER 1 — source re-verification

### Confirmed remove / quarantine (2 — stable across re-checks)

| date | event | source | reason |
|---|---|---|---|
| 2026-07-12 | Pilates with Purpose | momence | **404** — source URL is malformed: `momence.com/%7C/K1h08xKL` (a `\|` delimiter leaked into the URL at ingest) |
| 2026-07-21 | Monthly Council Meeting | allevents | **410 Gone** — the allevents page was deleted at source |

### Flaky source — verify via the connector, do NOT hard-quarantine

- **BMX Local Race** (×2–3, `usabmx.com/events/{id}`): returns 404 to a bot UA on
  *some* fetches and 200 on others — the set changes run-to-run. These are
  `lhc_bmx` connector events; re-confirm through the connector's own fetch (the CI
  `scrape_events`/connector re-run is authority), not this URL probe.

### Time mismatches (fix to source)

| date | event | site | source | note |
|---|---|---|---|---|
| 2026-07-12 | HAVASIS FREE SWIM DAY | **00:00** | 12:00 | shown at midnight (renders with no time) — should be 12:00 PM |
| 2026-07-31 | Crosscutt at The Flying X Saloon | 20:00 | 20:30 | minor |
| 2026-08-01 | Crosscutt at the Flying X Saloon | 20:00 | 20:30 | minor |

### Weak provenance — review (not defects, but not re-confirmable)

- **13 events** whose recorded source URL is only an **org homepage** (path `/`),
  e.g. Grace Arts, Farmers Market, Uncorked Bunco, Women With Willpower, Western
  Arizona Humane, mohavecomedy, telesis-academy, havasis.org. The homepage is
  alive (HTTP 200) — the event is likely real but can't be field-confirmed from a
  homepage. Consider capturing a per-event source URL going forward.
- **31 "unreachable" (HTTP 403/429/5xx)** — bot-blocks / transient outages
  (ironwolf golf was 502 during the run; lhusd calendar 403). Not evidence of a
  bad event; the nightly recheck clears these.
- **7 "unverifiable"** — 200 but no `Event` schema to compare (booking/landing
  pages). Deep field-diff for those connectors is the CI connector re-run's job.

---

## LAYER 2 — lint battery

| rule | n | notes |
|---|---|---|
| `venue_not_facility` | 35 | **systemic** — see below |
| `weekday_mismatch` | 6 | Creative Mondays on Sun/Tue (×5), Fishing Fridays on a Saturday — all `parks_rec` vision rows; likely mis-dated OCR or a brand-name series. **Needs your eyes.** |
| `allcaps_title` | 2 | HAVASIS FREE SWIM DAY, HAVASIS CHAT & CRAFT |
| `ampm_flip` | 1 | HAVASIS FREE SWIM DAY (00:00 — same row as the time mismatch) |
| `generic_venue` | 1 | Telesis First Day of School → venue is a bare address `2598 Starlite Lane…` |
| `season_out_of_season` | 0 | *(the one hit — "Christmas in July Camp" — is correctly suppressed: the title names the actual month)* |

**Systemic — P&R venue = "Lake Havasu":** all 35 `venue_not_facility` hits are the
same shape — every `parks_rec` vision event renders its venue as the generic
**"Lake Havasu"** rather than a named facility (Community Center, Aquatic Center…).
This is one pipeline gap (the vision OCR isn't capturing the facility, or defaults
to the city), not 35 independent errors. Worth a dedicated P&R venue backfill.

---

## LAYER 3 — render sweep (21 days + camps/night/movies)

- **build-sha:** current (`d5982c22312f`) on every page — no stale edge renders.
- **`/family/camps`, `/night`:** clean.
- **`/movies?date` (7 days):** every film has showtimes; **no implausibly-early
  showtimes** (Moana-class clean). *(2026-07-16 has only 1 film / 1 showtime — thin,
  worth a glance, but not an assertion failure.)*
- **Day-page anomalies (11 in the window; 8 within the 14-day gate):**
  - **Unlinked plain-text rows (the "Art Guild" class):** recurring civic/club rows
    with no link — "General Member Meeting", "Executive Board Meeting", "Community
    Outreach Sewing" (Havasu Stitchers). Decide: link them, or accept as info rows.
  - **Missing time label:** "Tiny Tots – Open Gym Play", "HAVASIS FREE SWIM DAY",
    "Summer Free Movies (TMNT)".
  - **Generic venue:** Telesis First Day of School (bare street address).

---

## Launch gate — definition and current status

> **PASS** = zero *un-quarantined* events in the next 14 days failing Layer 1 or 2;
> zero render-sweep assertion failures; review queue back to 0 after the approval pass.

**Current: FAIL.** Path to PASS (all gated on your approval — nothing applied yet):

1. **Quarantine 2** confirmed dead-source rows (momence 404, allevents 410).
2. **Fix time** on HAVASIS FREE SWIM DAY (→ 12:00) and normalize its ALL-CAPS title;
   optionally the two Crosscutt 20:00→20:30.
3. **Adjudicate the 6 weekday-mismatch** P&R rows (real mis-dates vs. series brand).
4. **Resolve the 8 in-gate render anomalies** (link or accept the 3 unlinked civic
   series; add times to the 3 missing-time rows; fix the Telesis venue).
5. **BMX:** re-confirm via the connector, not a hard quarantine.
6. Systemic P&R "Lake Havasu" venue backfill (not strictly gate-blocking, but the
   biggest single quality lift).

---

## Remediation (prepared, **not run** — awaits your approval pass)

All DB writes follow the repo rule: **dry-run → show counts → you approve → apply**,
reversible via undo CSV. Quarantine = flip `Event.status` → `pending_review` (out of
the public calendar/ICS, into `/admin`, reversible). Nothing in this pass has
touched the database or `main`.

**Your move:** review `discrepancies_2026-07-10.csv`, confirm which rows to
quarantine vs. fix vs. accept, and I'll build the gated apply (mirroring
`parks-rec-quarantine.yml` / `approve-events-apply.yml`).

## Cadence

`prelaunch-verify.yml` runs Layers 2+3 (and 1) nightly at 16:30 UTC once merged to
`main`, uploading the same three artifacts and turning the run red on any gate
regression — so drift surfaces daily, not at the next manual sweep.
