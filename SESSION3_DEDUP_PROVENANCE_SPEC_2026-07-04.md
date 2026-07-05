# Session 3 — Event Dedup, Source Provenance & Dropped Times (spec + sequencing)
**Date:** 2026-07-04 · Companion to `ASK_HAVA_FULL_SITE_AUDIT_REMEDIATION_PLAN_2026-07-04.md` (§6 Session 3).
**Status:** spec only — no code/data changed. Built from a read-only code investigation.

> **Mount caveat:** `app/contrib/approval_service.py` is served **truncated (~line 340, mid-`should_auto_approve_event`)** through the Cowork mount — the documented "mount reads lie." Every line number below is from the mount view and must be re-confirmed Windows-side before editing; the body of `should_auto_approve_event` in particular must be read on the real disk.

---

## The five root findings (why the symptoms exist)

1. **No field-merge on dedup.** Render-time dedup (`app/events/dedup.py::dedup_cross_source_occurrences`, entry ~L503) picks ONE survivor via `_survivor_rank` (~L309) and **drops the loser entirely** — no merge. `_survivor_rank` doesn't even consider `image_url`. So the twin holding the flyer / richer description / correct time can lose wholesale. Ingest-time merge (`event_reconciler.py::_compute_merge_fields` ~L113) merges title/description/url/time **but never `image_url`**, and the approval schema (`schemas/contribution.py::EventApprovalFields` ~L139) has no `image_url` field. → **This is why the Calvary twins both show and neither carries a flyer.**
2. **Calvary slips both dedup layers.** Ingest `find_duplicate`: `token_sort_ratio("Calvary Baptist Church … Family Water Night","Family Water Night") = 61 < 85` threshold (`DEDUP_TITLE_FUZZY_THRESHOLD`, dedup.py:30) → inserted as new. Render pass-2 (`_cross_source_session_drops` ~L463): titles share the "water" token and times match, but the merge is blocked by the **venue guards** (`_is_specific_venue`/`_venue_match` ≥92, dedup.py:414/420) because one twin has a named venue and the other the bare-city fallback.
3. **Billiards "×2 every day" is a same-source split.** The title-keyed pass keeps **one survivor per 120-min cluster** (`_SEPARATE_SESSION_GAP_MINUTES=120`, dedup.py:255); two same-title rows whose start times are >120 min apart land in separate clusters and both survive, and same-source rows never reach the cross-source pass (`_different_source` guard, dedup.py:449).
4. **Source label is domain-based and already prefers the primary — but doesn't drop the aggregator.** The ONLY public event source byline is `app/events/permalink.py::_event_link_html` (L151–179): it links `event_url or source_url` as the primary, then emits a small `Source: <aggregator domain>` byline whenever `source_url`'s domain differs (L170–178). It never *drops* the aggregator when a genuine organizer `event_url` exists. Event **rows** don't render source at all (only admin does). → **This is the Farmers Market "source: River Scene" byline.**
5. **Times drop to null, and the Farmers Market primary URL isn't durably captured.** `river_scene.py::_parse_time_cell` (L177–184) returns `None` on any parse miss, and `_table_label_map` (L262) matches the "Time" label by exact string, so a page with no "Time" row or an odd label/format yields a timeless event by design (never fabricates noon). `lakehavasufarmersmarket.com` appears **only** in a one-off gated seed (`scripts/events_hygiene_2026_07_01.py:63`), not in any live scraper — so the primary URL is only in prod if that script was applied, and isn't re-captured on ingest.

Plus: **stale events.** `scripts/expire_past_events.py` exists (cutoff = today−7d, sets `status="expired"`), but **no cron in this repo runs it** (Procfile has only `web`; no in-app scheduler). The ~50% past-dated finding is most likely "the job isn't running," not a logic bug.

---

## Sequencing — four sub-PRs (do 3A first; 3D is the gated data op)

### 3A — Provenance: surface primary, drop the aggregator label *(CODE, small, safe)*
- Edit `permalink.py::_event_link_html` (L170–178): when `event_url` is a real organizer URL distinct from `source_url`, **suppress** the `Source: <aggregator>` byline (keep the primary "Event Link"). Keep the byline when the only link we have *is* the aggregator (i.e. `event_url` empty or itself the aggregator).
- Acceptance: an event whose `event_url` is the organizer's own domain shows only the primary link, no "Source: River Scene Magazine". An aggregator-only event still shows its source. Unit-test both shapes.
- Not enough on its own for Farmers Market — see 3C/3D (its `event_url` must actually be the primary).

### 3B — Dedup + merge into one authoritative entry *(CODE, behaviorally subtle — most care)*
- **Field-merge, not drop.** Make the render survivor **absorb** the best fields from its dropped twin(s): non-null `image_url` (flyer), longest description, a real start time over a TBD one. Loci: add `image_url` presence to `_survivor_rank` (dedup.py:309–323) so a flyer-bearing twin wins, **and** add a field-copy step in `dedup_cross_source_occurrences` (L503–530) so the survivor inherits the loser's flyer/richer-desc/real-time before the loser is dropped. Mirror the same `image_url`/richest-desc gap-fill at ingest in `_compute_merge_fields` (event_reconciler.py:145–161).
- **Calvary:** relax the venue guard for the "titles subset-match + same date + same time, one venue is the bare-city fallback" shape (dedup.py:414–432 / 483–490). Mind the over-merge risk the guard was added to prevent (comment at dedup.py:365–372) — gate the relaxation on the title+time agreement.
- **Billiards:** collapse same-source, same-normalized-title, same-day rows even when >120 min apart (dedup.py:326–349), or add a same-source dedup edge; also check whether two recurring rows are being ingested that `find_duplicate` should have reconciled.
- Acceptance: on 2026-07-04, Calvary appears **once** (with the richest description; flyer if either twin has one) and Billiards appears **once**. Add regression tests for both shapes. Run the full parity + dedup suites.
- **Note:** render-dedup is read-only, so this fixes the *display* immediately on deploy, but the duplicate **rows remain in the DB** — physical collapse for admin/API surfaces is the 3D data op.

### 3C — Times + Farmers Market primary URL *(CODE)*
- Harden `river_scene.py`: make `_table_label_map`/`_parse_time_cell` tolerant of `Time:`/`Times`/ranges (L177–184, L262–286) so published times aren't dropped; keep the "never fabricate noon" rule.
- Confirm the all-day auto-approve gate (`_ALLDAY_OK_SOURCES`, approval_service.py:334–336 **+ verify the truncated body Windows-side**) so structured feeds still auto-approve time-less events rather than queueing them.
- Capture the market's primary URL going forward: ensure the River Scene submission URL picker (`_submission_public_url`) or the market's source yields `lakehavasufarmersmarket.com` as `event_url` so 3A drops the aggregator label for it.
- Acceptance: a River Scene event with a parseable time keeps it; Farmers Market resolves to its own URL on new ingests.

### 3D — Data ops *(PROD DATA OP — dry-run → show counts → Casey approves → apply, per CLAUDE.md)*
- Physically collapse existing duplicate rows (`scripts/collapse_event_dups_*` / `dedupe_events_cross_source.py`) so admin/API match the deduped display.
- Backfill dropped times where recoverable; set the Farmers Market `event_url` on already-ingested rows.
- Retire the past-dated backlog: run `scripts/expire_past_events.py --dry-run`, review counts, then apply; **and decide how the daily run is scheduled** (GitHub Actions cron off main, or the VPS box) so it doesn't re-accumulate — this is the likely real fix for the ~50% past-dated symptom.

---

## Code vs data-op summary
- **CODE (deploys via normal PR, changes display next deploy):** 3A, 3B, 3C.
- **PROD DATA OP (gated):** 3D — collapsing existing dup rows, backfilling times/URLs, retiring past events, and scheduling `expire_past_events`.
- **Order:** 3A → 3B → 3C as PRs, then 3D once the new logic is live (so the backfill applies the new rules).

## Decisions for Casey
1. **Billiards:** confirm the two daily rows are true duplicates to collapse (vs. two legitimately different sessions). A quick prod look at the two rows' start times / source_urls settles it before 3B relaxes the split.
2. **Calvary venue-guard relaxation** carries a small over-merge risk. OK to proceed gated on title+time agreement, with regression tests?
3. **Stale-event scheduling (3D):** GitHub Actions cron off `main`, or the existing VPS crawler box? (Determines where `expire_past_events` gets wired.)
4. Confirm the standard dry-run → counts → approval flow for all of 3D.
