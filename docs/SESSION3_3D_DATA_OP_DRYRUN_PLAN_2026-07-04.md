# Session 3 — 3D data-op plan (GATED: dry-run → counts → Casey approves → apply)

**Date:** 2026-07-04 · Companion to `SESSION3_DEDUP_PROVENANCE_SPEC_2026-07-04.md` §3D.
**Status:** PLAN ONLY. No prod writes were made. The code PRs (3A/3B/3C) are up and
must be **merged + deployed first** so the backfill applies the new logic. Every
step below is `--dry-run` first; the real run waits for Casey's explicit approval
in chat, per CLAUDE.md.

> Diagnostic counts below came from **read-only** SELECTs against prod during the
> Session 3 investigation. They are a snapshot; re-run each dry-run to get live
> counts at apply time.

---

## Why 3D is separate from the code PRs
- **3A** (PR #708) drops the aggregator "Source:" byline when a distinct organizer
  `event_url` exists — display-only, live on deploy.
- **3B** (PR #709) makes the render survivor absorb the twin's flyer/richest-desc/
  real-time and collapses the Calvary twins — **display-only** (render-time dedup
  is read-only; the duplicate **rows remain in the DB**).
- **3C** (this session's PR) hardens River Scene time parsing for **new** ingests.

3D is where the **physical DB** is brought in line with the new display: collapse
the duplicate rows, backfill recoverable times/URLs, retire the past-dated backlog,
and schedule the expiry job so the backlog can't re-accumulate.

---

## Op 1 — Physically collapse existing duplicate rows
**Goal:** admin/API/JSON surfaces match the deduped display (3B fixed the display
only). Uses the render-dedup logic as the oracle.

- **Script:** `scripts/dedupe_events_cross_source.py` (dry-run by default; writes a
  review CSV; `--apply` to write — prod-data gate).
- **Also available:** `scripts/collapse_event_dups_2026_06_23.py` (`--apply
  --confirm`) for the older same-title/date clusters.
- **Known targets (from prod):**
  - **Calvary Baptist "Family Water Night" (2026-07-04):** 2 live rows
    (`0764acb3` river_scene_import @ `3100 Sweetwater Ave LHC`, and `c2145cd4`
    go_lake_havasu @ `Calvary`). 3B now collapses these at render to the go_lake
    survivor carrying the 482-char river_scene description. 3D should deactivate
    the river_scene twin (keep for provenance) and merge its richer description +
    `image_url` (neither has a flyer here) onto the survivor.
  - The 100%-crawl audit found **~35 exact same-title/same-date clusters** plus
    listing shadow-mirrors — the CSV will enumerate the current set.
- **Dry-run:**
  ```
  .venv\Scripts\python.exe scripts\dedupe_events_cross_source.py        # dry-run + CSV
  ```
  Review the CSV → confirm counts with Casey → `--apply`.
- **Reversibility:** collapse deactivates (`status`) rather than hard-deletes;
  keep the CSV as the undo manifest.

## Op 2 — Backfill recoverable dropped times
**Goal:** rows that lost a time to the old parser (or carry a bare 00:00/TBD) get
the real time where it is knowable.

- **Farmers Market:** 36 live rows, **all already carry**
  `event_url = https://www.lakehavasufarmersmarket.com/` (so 3A already drops the
  aggregator label for them). But their **times are mixed**: some `08:00`, many
  `00:00`/TBD. The real market time is **8:00 AM – 12:00 PM** (the go_lake twins
  carry `08:00–12:00`). Backfill the TBD/`00:00` river_scene_import FM rows to
  `start_time=08:00, end_time=12:00`.
- **General:** where a River Scene detail page has a parseable time that 3C now
  reads (ranges + `Times`/`Start Time` labels), a **re-pull** of River Scene after
  3C deploys will fix new/updated rows automatically; a one-off backfill script can
  re-parse stored source pages for the rest. Keep the "never fabricate noon" rule —
  only set a time that is actually recoverable.
- **Gate:** write a small dry-run script that prints `(id, old_time → new_time)`
  per affected row; Casey reviews counts before apply.

## Op 3 — Set the Farmers Market `event_url` on any stragglers
- Current prod: **36/36** FM rows already have the organizer URL, so this is likely
  a **no-op** — confirm with a dry-run count of FM rows where
  `event_url` is null/aggregator, and only apply if > 0.

## Op 4 — Retire the past-dated backlog
**Goal:** the ~50% past-dated finding is most likely "the expiry job never runs"
(no cron wired), not a logic bug.

- **Script:** `scripts/expire_past_events.py` (cutoff = today − 7d; sets
  `status="expired"`; recurring series with a live future occurrence are spared).
- **Dry-run (read-only):**
  ```
  .venv\Scripts\python.exe -m scripts.expire_past_events --dry-run
  ```
  Review the count → approve → run without `--dry-run`.

## Op 5 — Schedule `expire_past_events` so the backlog can't re-accumulate
**Decision needed (Casey):** where does the daily run live?
- **Option A — GitHub Actions cron off `main`** (matches every other scrape job;
  needs `DATABASE_URL` secret; no new infra). **Recommended** for consistency.
- **Option B — the existing VPS crawler box.**

There is **no in-app scheduler** (Procfile has only `web`), so without one of these
the job never runs. Wire the chosen option in a follow-up PR (workflow file or VPS
cron), then Op 4 becomes self-maintaining.

---

## Approval checklist (per CLAUDE.md)
For **each** write op: `--dry-run` → paste counts here → Casey approves in chat →
apply → re-verify counts. Do the ops **after** 3A/3B/3C are merged + deployed so
the backfill runs against the new logic.

1. [ ] 3A/3B/3C merged + deployed to prod
2. [ ] Op 1 dedupe dry-run CSV reviewed → apply
3. [ ] Op 2 time backfill dry-run counts reviewed → apply
4. [ ] Op 3 FM event_url straggler count (likely 0) → apply if > 0
5. [ ] Op 4 expire_past_events --dry-run count reviewed → apply
6. [ ] Op 5 scheduling decision (A or B) → follow-up PR
