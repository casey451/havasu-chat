# WS6 — Classification & data linting (safe phase)

**Date:** 2026-07-06 · **Branch:** `fix/ws6-classification-lint` (off `main`) · **No data write.**

Verified the existing classification infra first (WS1–5 pattern), then built the missing piece.

## What already exists

- **Event classification with audience** — `app/events/activity_taxonomy.py` (`classify_activity`, `event_activity_tags`) already derives `activity:<slug>` + `facet:*` + `audience:youth` / `audience:senior`.
- **Provider misfile audit** — `scripts/misfile_audit_2026_07_06.py` (today): read-only name-pattern scan → suggested target leaf → feeds a gated reclassify.
- **Address quality** — `app/admin_portal/address_quality.py`.

## The gap → what this PR adds

The audit's **§14.3 lint rules (spec §6.3)** had no cohesive detector. Added `app/events/lint.py` — pure, read-only rules, each the machine-checkable form of a real defect:

| Rule | §14.3 defect it catches |
|---|---|
| `suspect_ampm_flip` | "Glow in the Dark Painting" at **5:30 AM** (PM typed as AM) — flags a 12 AM–7 AM start at a non-24h, non-overnight venue |
| `reads_as_venue_hours` | "Golf Course — Bridgewater Links · **Open daily**", "Open 24/7" — a venue's hours ingested as an event |
| `name_category_contradiction` | "Western States Restaurant **Consulting**" under Restaurants — a B2B/wholesale name in a consumer food/drink/retail category |

They are **detectors, not fixers** — a false positive costs a review, never a bad auto-edit. Precision negatives are pinned: "Open Swim"/"Open Mic"/"Open House"/"Pickleball Open Play" and a real overnight late show don't flag; consulting in a *professional* category is fine.

- `tests/test_events_lint_ws6.py` — §14.3 fixtures + precision negatives (21 cases).
- `scripts/event_lint_audit.py` + `.github/workflows/event-lint-audit.yml` — read-only: run the lint over live events, upload a CSV of flagged rows (runs in CI, where the internal DB host resolves; writes nothing).

## Deferred — gated / documented (not speculatively half-built)

- **Source-taxonomy audience (spec §6.1 / §14.3 items 1–3):** "Popsicles in the Park", "Big Fish Little Fish", "Mexican Train Dominoes" aren't caught by the *title* classifier — they need the P&R / Senior Center feed's **audience/program metadata**, which is currently discarded at ingest. Re-plumbing that + a **reclassify backfill** is an ingest change + gated prod write.
- **Provider recats (§14.3 items 4–6):** Massage under Colleges, Cigars under Bars, Traffic School under Colleges — surfaced by `misfile_audit`, resolved by the **gated reclassify** (dry-run → review → apply).
- **Venues ≠ events rail (M2 / spec §6.2):** moving the `venue_hours_as_event` rows to a "places_open_today" rail (excluded from event counts + calendar cells) is a render + data change tracked with the events-model work; this lint is the detector that feeds it.
- **Wiring the lint into the publish gate + nightly cron** (blocks publish / writes to the review queue) — a behavior change; the pure rules + read-only audit ship first.

## Gate
ruff clean · mypy `app/events/lint.py` clean · lint fixtures 21 passed.
