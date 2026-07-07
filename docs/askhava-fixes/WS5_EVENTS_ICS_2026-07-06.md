# WS5 — Event series/instance model + ICS (safe phase)

**Date:** 2026-07-06 · **Branch:** `fix/ws5-events` (off `main`) · **No data migration.**

Verified against live prod first (the WS1–4 pattern), then fixed the pure-code half.

## Verified live (B5)

Fetched the real Rainforest Rush `.ics` from prod:

```
DTSTART:20260706T180000
DTEND:20260710T180000        <- one 96-hour block, floating local time, no TZID
```

Confirmed **both** halves of B5:
1. **No timezone.** Floating local `DTSTART`/`DTEND` are interpreted in the *viewer's* zone, so an out-of-state subscriber sees the wrong hour. (Pure code bug.)
2. **96-hour block.** The camp is *stored* as a 4-day span (`date`=Jul6, `end_date`=Jul10) with **no RRULE**, so it exports as a single block instead of 5 nightly events. (Data/ingest bug.)

## Fixed in this PR (code only, tested)

`app/api/routes/calendar_feed.py` (both the per-event `.ics` and the `/events.ics` feed):
- Timed `DTSTART`/`DTEND` now carry **`;TZID=America/Phoenix`**, and the calendar embeds a **`VTIMEZONE`** (Arizona = MST year-round, no DST — single STANDARD component). All-day events keep `VALUE=DATE` (no TZID), unchanged.
- A **recurring** event's per-occurrence `DTEND` is now **same-day** (`end_date` is the series end — the RRULE's `UNTIL` covers it), so a nightly RRULE camp is 5 two-hour evenings, never one block repeated daily.

Tests (`tests/test_ics_timezone_ws5.py`, §14.2 item 3): TZID + VTIMEZONE present; a properly-stored nightly RRULE event emits same-day `DTEND` + `RRULE` and **expands via `dateutil` to exactly Jul 6–10** (the Google-Calendar-import acceptance); all-day stays `VALUE=DATE`; structural BEGIN/END balance. Updated `test_wp3_events_surfaces.py` for the new TZID output. `icalendar` was deliberately **not** added — the module hand-rolls RFC 5545 to avoid a runtime dep, so validation uses `dateutil` (already present) + structural assertions.

## Deferred — gated / next session (documented, not speculatively half-built)

- **B5 data half (§14.2 item 3, data):** re-store the Rainforest-Rush-style multi-evening spans as nightly RRULEs (ingest parse of "every evening 6–8 PM Jul 6–10" → `FREQ=DAILY` + same-day `end_time`) + a **backfill** for existing span rows. This is a prod write → gated. Captured as a `strict` xfail (`test_span_stored_camp_should_become_nightly_rrule`) that flips to pass once the data is nightly.
- **§14.2 item 1 — Afternoon Enrichment series/session double.** There is already event-dedup machinery (`app/events/dedup.py` `recurring_series_key` + time-overlap dedup, `app/contrib/event_ingest.py` same-day `(normalized_title, start_date, venue)` uniqueness guard, `app/contrib/event_reconciler.py`). Whether the "series row + daily session row" pair collapses needs a focused verification against that machinery; any gap fix + feed-level "series never renders beside its own instance" belongs in the ingest-model PR (with a backfill), not this safe phase.
- **§14.2 item 2 — pickleball UUID-per-day.** `Event.id` is `uuid4` (non-deterministic). Making instance IDs deterministic (`hash(series_id + date)`) so a day's URL is stable across rescrapes is an ingest-model change + slug/URL backfill — gated.
- **M7 internal links** (feed items → internal `/events/<instance>`, external URL as a "Register" button) — a rendering change tracked with the series-model work.

## Gate
ruff clean · mypy `app/api/routes/calendar_feed.py` clean · WS5 ICS tests 4 passed / 1 xfailed; touched suites green.
