# Production-Ready Plan — consolidated 2026-06-03

Synthesizes: `SITE_AUDIT_LIVE_2026-06-03.md` (8 P0 / 32 P1 / 35 P2-P3, Waves 0-3),
`AUDIT_TRIAGE_2026-06-03.md` (code-verified verdicts), `LIVENESS_RANKING_HANDOFF_2026-06-03.md`,
`CROSS_SOURCE_DEDUP_SESSION.md` + `CURSOR_DEDUP_TASKS.md`, `GOLAKEHAVASU_PROJECT_CLOSEOUT.md`,
`DEPLOY_MIGRATION_GAP.md` (resolved — preDeploy migrate is live in `railway.json`).

Repo rules apply to every step: feature branch off `main`, pytest + ruff green, PR and STOP
(merge is Casey's gate); every prod data op is dry-run -> counts -> Casey approves -> apply.

## Definition of "production ready" (launch gate)
1. All 8 P0 ship-blockers closed (B-01..B-08).
2. Serving is deterministic — no stale/split cache; counts and Open/Closed pills stable across requests.
3. No legal contradiction live (/terms placeholders gone; accounts disclosed or gated — D-1).
4. Wave-1 data triage applied (miscategorization hot list, event venue corruption, provider dupes).
5. Verification checklist in SITE_AUDIT §7 passes for Waves 0-2.

Everything else (Wave 3 polish, redesign spec, feature opportunities) is post-launch.

---

## Phase 0 — Foundation: trust the deploy and the serving path (do FIRST, ~1 session)
Nothing else can be verified until these land, because B-04 means two different snapshots answer requests.

| # | Item | Why first |
|---|------|-----------|
| 0.1 | **Resolve stale/split cache serving (B-04).** Check Railway replica count, any edge/response caching, and whether one instance serves an hours-old snapshot. Make serving deterministic; one staleness policy shared by strip//today//gas (G-2 thresholds -> ~24-30h for daily feeds). | Every Open/Closed pill, count, and "verify live" item is untrustworthy until this is fixed. Several audit findings may evaporate. |
| 0.2 | **Resolve the G-1/G-4 contradiction:** code humanizes the gas timestamp and uses %.2f, but prod renders raw ISO + 3 decimals. Find which template/path actually serves /gas (a dead/second render path or deploy lag). | If prod isn't serving latest main code paths, "already fixed" triage items aren't actually fixed. |
| 0.3 | **Confirm prod == origin/main:** alembic current vs heads, deployed SHA, and PR #63 (river_scene Task B) status. | DEPLOY_MIGRATION_GAP fixed the mechanism; confirm state. |
| 0.4 | **Rotate prod Postgres password + Bright Data key** (exposed in chat — GOLAKEHAVASU closeout open item). | Security debt; cheap; do before more prod ops. |
| 0.5 | Check why the June 3 gas refresh didn't land (M-11 ingest-job half). | Data freshness underpins /gas + strip. |

## Phase 1 — P0 ship-blockers (code; parallelizable into 2-3 lanes, ~2-3 sessions)
Wave 0 of the site audit, minus items moved to Phase 2 (data ops).

Lane A — presentation (no data ops):
- **B-01** chat transcript CSS: constrain inline SVG/img in response cards; fix whitespace runs; style chips + Photo button (N-01). "One CSS file likely fixes the whole transcript."
- **B-02** month-calendar grid: 7-col template + leading-empty-cell logic; stop clipping.
- **B-06** /terms: strip placeholders/lawyer notes to an honest minimal stub (no invented legal language). Pair with D-1 decision.
- Copy/label batch (audit W0-5/W0-6): "Tap a type to narrow" removal on chip-less pages, "Tonight" guard, gauge-height relabel, "Time TBD" render, Event Link -> labeled button + strip fbclid, remove SPONSORED overlay markup, AI disclaimer, brand-name sweep to one name in titles.

Lane B — events window math:
- **B-03** weekend bucket: add "This Weekend" (Sat-Sun), fix E-1 boundary math (`(6-weekday)%7` Sunday collapse), anchor to `now_lake_havasu().date()`, reconcile SSR vs JS bucketing, "Tonight" excludes passed events + caps recurring classes (H-1/M-19). Test matrix: Wed/Sat/Sun anchors. **Confirmed: the routed template is `events_sandstone.html` (Lake Light is dead — don't fix it).**
- **ED-1** event scraper fix (`go_lake_havasu.py:80-86`): parse JSON-LD address object into structured fields; venue/address split; shape validation (reject description-shaped venue input). Ship parser first; backfill is Phase 2.
- **ED-5** https og:url; **E-5** count relabel.

Lane C — chips + dedupe code:
- **B-07** dead `?sub=` chips: chips must derive from stored subtypes (zero-member chips don't render). Subtype backfill itself is Phase 2.
- **B-08** event cross-source dedupe: dedupe on canonical URL (Facebook event ID / organizer URL) across `go_lake_havasu` + `river_scene_import`.

## Phase 2 — Prod data triage (each op: dry-run -> counts -> approval -> apply; ~2 sessions + Casey review time)
- **2.1 Miscategorization hot list (B-05/M-01..M-07):** audit query listing every suspected (provider, category, subtype) mismatch -> dry-run report -> targeted UPDATE. Gets A Toe Truck out of Restaurants; detailers out of On the Water; supermarkets out of Cafés; brokerages out of Lodging; Attractions junk purge. Interim until Phase 3 taxonomy.
- **2.2 Event backfill** for ED-1 corruption: null organizer-address venues, split venue/address, purge description-in-venue rows, fix NLake concat; fake-noon times -> null + "Time TBD" (M-15); past-event handling (M-16).
- **2.3 Provider dedupe — finish the shipped system:**
  - Commit the uncommitted `--max-distance-m` edit to `scripts/merge_existing_dups.py` (fast-follow PR).
  - Prod website pass: `--reason website --require-identical-name --max-distance-m 500` dry-run -> eyeball -> apply (per CROSS_SOURCE_DEDUP "NOT done" list).
  - Merge `-2`/`-3` slug dupes on google_place_id (M-21) via the admin merge UI / scripts; street disambiguators for chains.
  - Decide on enabling `INGEST_CONTACT_TIER_ENABLED` only after full provider suite runs green with the flag on.
- **2.4 Subtype backfill** for dead chips (martial arts off "Kids Lessons"; lodging into hotels/vacation-rentals/rv-parks).
- **2.5 Liveness ranking** (LIVENESS_RANKING_HANDOFF — spec is implementation-ready): migration (`newest_review_at`, `liveness_score`), `app/core/liveness.py`, extraction in `places_load.py`, `backfill_liveness.py --dry-run`, multiplicative dampener in ranking paths. Buries likely-dead businesses; complements 2.1.
- **2.6 Name-cleaning pass** (M-22 OTA titles, scraped `<title>`s), re-geocode 2-decimal coords (M-23), gas provider records for Pilot/Hacienda/Terrible Herbst (N-12), verify the (999) review-count sentinel (N-24).
- **2.7 golakehavasu leftovers:** approve ~91 pending partners at /admin/providers/pending; re-run partner load (or let Sunday cron) for the attractions mapping (~65 rows).

## Phase 3 — Structural fixes (the main event; ~3-5 sessions)
- **3.1 Taxonomy / primary category (R2)** — the structural core. Triage recommends extending the existing deterministic `subcategory` system into a single primary-category model (no LLM needed): filter listings on primary only, single source of truth for Home/Explore/Map label sets, validate card subtype ∈ page chip set, invariant test for single membership. Gated on decisions D-9/D-10/D-11 below.
- **3.2 Pagination (M-20):** real pagination/load-more; honor `?page=`; keep chips on paged views; crawlable next links. Cap is `_DEFAULT_CARD_LIMIT = 60` in `app/categories/queries.py`.
- **3.3 Routing (M-30):** JSON off `/events` and `/programs` to `/api/*`; stop serializing `embedding`/`source`/internal fields; human page gets the clean slug.
- **3.4 Count reconciliation (S4):** one count query; hub = page = chip sums.
- **3.5 Profile/meta batch (W2-7):** canonical/og/LocalBusiness JSON-LD; proximity-based "While you're here"; hours fallback + 11:59 PM clamp fix; website row; sunset extraction fix (M-18 — safety-adjacent); map pin popup-first + empty state; event lat/lng/cost population (the `image_url` field exists on events — wire it, closing ED-3).
- **3.6 Search fallback (W2-6):** degraded keyword path if the LLM pipeline is down, or accept risk explicitly (D-7).

## Phase 4 — Decisions only Casey can make (answer async; several gate phases above)
Blocking launch: **D-1** accounts vs "no accounts" terms/privacy claim (pair with B-06).
Gating Phase 3: **D-9** out-of-area listings, **D-10** "On the Water" identity, **D-11** low-data record policy, **D-2** one nav/design system, **D-6** one product name.
Non-blocking: D-3 claim copy, D-4 review labeling, D-5 map scopes, D-8 sponsor naming, D-12 rating threshold, D-13 events on venue profiles.

## Phase 5 — Verify, then launch
- Run the full SITE_AUDIT §7 verification checklist (Waves 0-2 sections) against prod, two fetches 10 min apart on different instances.
- Add the regression guards from §7: single-primary-category invariant; Wed/Sat/Sun bucket tests; event-ingest venue shape validation + cross-source dedupe; no raw JSON at non-/api paths.
- Re-run a scoped live audit pass (the 8 fetch auditors were cheap) as the final gate.

## Suggested sequencing
1. Phase 0 (one session, mostly investigation + ops) — unblocks everything.
2. Phase 1 lanes A/B/C in parallel sessions or sequential PRs; each is shippable independently.
3. Phase 2 interleaved as PRs from Phase 1 land (parser fix before event backfill); Casey approval is the throughput limit — batch dry-run reports for one review sitting.
4. Phase 3.1 taxonomy last among the big items (largest blast radius), after Wave-1 data triage buys breathing room. 3.2/3.3/3.5 are independent and can run parallel to 3.1.
5. Phase 4 answers collected early (a 30-minute decision pass unblocks D-1/D-9/D-10/D-11 dependencies).

## Explicitly out of scope for launch
- CRITIQUE_AND_REDESIGN.md visual redesign (2026-05-08, partially superseded by shipped work) — post-launch.
- docs/FEATURE_OPPORTUNITIES — post-launch.
- Auto-deactivating likely_inactive listings (Casey: bury-only).
- Tuning liveness weights (iterate via the xlsx prototype).
- Repo-root hygiene (stray logs, `_*.cmd`, throwaway files from GOLAKEHAVASU §7) — cheap cleanup PR whenever, not gating.
