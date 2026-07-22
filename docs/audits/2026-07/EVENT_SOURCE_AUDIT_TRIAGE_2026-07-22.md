# Nightly source-audit triage — 2026-07-22

Input: `discrepancies.csv` from prelaunch-verify run #13 (2026-07-22, artifact
`prelaunch-verify`, 209 findings). Companion op:
`scripts/remediate_event_source_audit_2026_07_22.py` (dry-run gated).

## Verdict in one paragraph

The 209-finding backlog is not 209 problems. ~180 findings are **systemic
repeats of ~12 root causes** — sources that can never pass Layer-1 the way it
verifies today (no per-event page, no JSON-LD, or a bot-blocking origin), each
re-flagged nightly per occurrence. ~29 findings are real per-event items, of
which 20 are high-confidence fixes staged in the gated op and the rest are
review/leave. Without the policy change below the gate stays red forever no
matter how many rows we fix, because farmers-market/Iron Wolf/Split Finger
occurrences inside the 14-day window regenerate the same findings every night.

## A. Systemic classes (repeat findings, need a policy change not row edits)

| Class | n | Dominant series | Root cause |
|---|---|---|---|
| SOURCE_IS_HOMEPAGE | 66 | Farmers Market ×17, Grace Arts ×9, Art Trail ×3, marquee one-offs ×~37 | provenance is a site root; the source has no per-event page (or we never captured it) |
| UNVERIFIABLE (200, no JSON-LD) | 52 | Split Finger "Strength/Conditioning/Agility" ×22+2, river_scene articles ×7, legistar ×5 | page exists but exposes no Event schema to compare |
| UNREACHABLE (403/5xx) | 36 | ironwolfgcc.com HTTP 502 ×16, farmers market ×6, lakehavasupickleball ×3, lhusd/mohave.gov | origin bot-blocks or 5xxes the CI fetcher; NOT proof of anything |
| generic_venue (lint) | 30 | Farmers Market ×20, Grace Arts ×8 | bare street address stored as the venue — **fixable, staged in the op** |

Proposed audit-policy change (small config lists in `scripts/prelaunch_verify.py`,
happy to implement on your go):

1. `VERIFY_VIA_CONNECTOR_DOMAINS` — domains whose events are maintained by our
   own scrapers and can't be page-verified: splitfinger (22+2), legistar (5),
   lakehavasupickleball (3), ironwolfgcc (16, also 502s). Layer-1 skips them
   with a `connector_verified` note; freshness of those feeds is already
   guarded by their own crons + data-freshness-check.
2. `KNOWN_HOMEPAGE_PROVENANCE` — recurring series we accept homepage
   provenance for (farmers market, Grace Arts, Art Trail, Hav-A-Sis): the
   SOURCE_IS_HOMEPAGE finding is suppressed for them; new events still flag.
3. Marquee one-offs with homepage provenance (~30 rows: Balloon Fest,
   Rockabilly, WinterBlast, Relics & Rods, …) stay flagged — that's the real
   repoint backlog, worked down over time.

With 1+2 the nightly finding count drops from ~209 to ~35 and the 14-day gate
goes green once the staged fixes land — while staying loud for real
regressions (dead per-event links, date/time mismatches, render anomalies).

## B. High-confidence fixes — staged in the gated op (dry-run first)

1. **3 time fixes the audit itself verified against source JSON-LD**:
   Crosscutt @ Flying X 08-01 20:00→20:30 · Cirque de Masquerade gala 09-11
   00:00→19:00 · Lizard Peak Scramble 10-17 06:30→06:45.
2. **3 ALL-CAPS titles**: HAVASIS ×2 → "Hav-A-Sis …" (matches their other
   listing's branding), Havasu Heroes festival → title case.
3. **Series venues**: Farmers Market '2144 McCulloch…' → **"The KAWS,
   Downtown Lake Havasu"** (their site: "at The KAWS, in Downtown Lake
   Havasu — every Saturday 8am–noon"); Grace Arts '2146 McCulloch Blvd' (their
   own theater's address) → "Grace Arts Live". Kills all 28 in-window
   generic_venue findings.
4. **11 same-date twin retirements** (the far-future month-view duplicates;
   Crosscutt-precedent: loser → `status='duplicate'`, survivor absorbs
   provenance): Cirque ×2 (a triple), Sleepless in Havasu, Pro Watercross,
   IJSBA (keep river_scene), Beard & Mustache, Witch Paddle, Parade of Lights
   (keep "Boat Parade of Lights"), Balloon Festival (keep "& Fair"),
   Winterfest (keep chamber "41st Annual"), All Abilities Fair (same-source
   twin). Every merge is guarded on both rows still being live **and dated the
   same day**; the dry-run prints each pair for your review.

Note these twins carry TBD/00:00 times, which is exactly why the render pass-2
never merged them (it requires two real timed rows — a deliberate guard we're
not loosening). Data retirement is the right tool here.

## C. Reviewed and deliberately left alone

- `season_out_of_season` ×2 — "End of Summer Lake Cleanup" (Oct) and "Home &
  Garden Expo Spring Show" (Jan) are plausibly the events' real names; flag is
  a lint false positive. Candidate: whitelist these two titles in the lint.
- `ampm_flip` ×16 — mostly 00:00 placeholders (render already treats those as
  TBD) plus pre-dawn starts that are *plausible for this town* (06:30 golf
  shotgun start, 06:00 Sleepless in Havasu art marathon, 07:00 lake cleanup).
  Only the Cirque 00:00 had a source-verified real time; it's fixed above.
  Blanket-fixing the rest without source times would create wrong data.
- Parade of Homes venue (`landmark_venue_mismatch`) — the description names
  the real venue; needs a human read, 1 row.

## D. How to run

    python -m scripts.remediate_event_source_audit_2026_07_22            # dry-run
    # review the printed plan (expect planned ≈ 45: 3 time + 3 title +
    # ~28 venue rows + 11 merges), then:
    python -m scripts.remediate_event_source_audit_2026_07_22 --apply    # gated

Undo: `--undo-from remediate_event_source_audit_undo_<stamp>.json --apply`.

After apply + the next nightly run, remaining findings should be ~30-35, all
in the systemic buckets — say the word on §A and I'll implement the two config
lists so the gate turns green and stays meaningful.
