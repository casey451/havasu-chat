# v4.4 BUILD PLAN — 8 PRs, zero questions

Mission: evolve the live v4 home + gas surfaces to the approved v4.4 design and fix the
three trust bugs underneath it. Every PR is a small diff on the real templates, judged
on the real site. `main` deploys prod on merge, so each PR must be complete and safe
alone.

## Workflow: integration branch, walk-away autonomy

Casey wants to walk away and return to a finished product. The model:

1. Create `v44-integration` off `main` once, at the start.
2. Do each work item on `feat/v44-NN-slug` branched off `v44-integration`; when its
   gates pass (pytest, ruff, refs, acceptance boxes), **merge it into
   `v44-integration` yourself** — that branch is yours, no approval needed. Log it in
   PROGRESS.md and move on. Do not wait for anything.
3. After PR-9, open ONE pull request: `v44-integration → main`, with the full
   changelog, before/after screenshots, and every acceptance checklist ticked.
4. **Final merge to main:** governed by the autonomy grant in the kickoff prompt.
   If the grant is present (it is, unless Casey deleted the line), merge when — and
   only when — ALL of these hold: CI fully green on the PR · local pytest + ruff
   green · visual refs regenerated and committed · PROGRESS.md complete · the
   §Post-deploy smoke steps are ready to run. Then run the smoke steps immediately
   after deploy. If smoke fails: `git revert` the merge commit on a branch, open an
   emergency PR titled `revert: v4.4 integration (smoke failure)`, merge that revert
   under the same grant, and stop with a clear PROGRESS.md note.

Post-deploy smoke (≤5 min after merge): fetch `/home` → 200, contains today's
Phoenix date and a `feed.total`-consistent headline; fetch `/gas` → 200, label from
§1.3 tiers, no station older than 7 days; fetch `/calendar` → current month. Any
failure = revert path above.

Branch naming: `feat/v44-01-gas-truth` … `feat/v44-09-dead-code`. Commit style:
scoped, tests in the same commit as behavior. Each merged item's entry in the final
PR body: what/why, before/after screenshots, acceptance checklist, "refs updated",
and a **"Removed"** list (see §Dead code policy).

---

## PR-1 · `feat/v44-01-gas-truth` — one gas source, honest clocks, grades data (W1/W2/G2)

The June bug: home said $3.69 ">4h ago" while /gas said $4.19 from June 10 labeled
">6h ago", with a station /gas didn't have. Root cause: two data paths + a label
ceiling.

Build (see DATA_CONTRACTS §1 for the full contract):
- One `GasService` consumed by ALL surfaces: strip tile, home panel, /gas page.
- Honest label tiers (exact strings in DATA_CONTRACTS §1.3); drop stations with
  price age > 7 days; log + admin-visible alert when the pull itself fails or goes
  silent > 12h (reuse the existing alerting pattern; if none exists, a WARNING log
  with a distinctive token `GAS_PULL_STALE` is enough — do not build new infra).
- Capture all grades the source exposes (regular/mid/premium/diesel) into the same
  rows; `None` when a station lacks a grade. If the source only exposes regular,
  the service still ships — grade endpoints just return regular-only (PR-6 hides
  the switch when only one grade exists; that's the honest state).

Acceptance:
- [ ] Unit tests: label tier boundaries; >7d hidden; same object feeds tile/panel/page
      (assert equality in one test that renders all three contexts).
- [ ] /gas and home can never disagree by construction (single call site).
- [ ] No station appears on one surface but not another for the same grade.
- [ ] pytest + ruff green; graphify updated.

## PR-2 · `feat/v44-02-date-keys` — stale page cache (G3)

Observed live on 2026-07-02: `/home` served July 1's page; bare `/calendar` served a
June 26 page (June grid, old header, old gas). Date-keyed URLs (`?date=`, `?cal=`)
were fresh — that's the proof of mechanism and the fix shape.

Build: every cached render key for date-scoped pages includes the resolved local date
(America/Phoenix), and calendar keys include the resolved month. Default (`no param`)
routes resolve "today"/"this month" BEFORE cache lookup, not after.

Acceptance:
- [ ] Regression test: freeze time to date D, warm cache; advance to D+1; `/home`
      response contains D+1's date string and count, not D's. Same for `/calendar`
      month rollover and `/events-ui`.
- [ ] TTLs unchanged otherwise (no cache-off regressions in p95 — eyeball the timing
      test if one exists; do not add new perf infra).

## PR-3 · `feat/v44-03-count-parity` — one counting service (F6 cross-surface)

Observed live for 2026-07-01: home said 54, the calendar cell implied 87, the agenda
panel said 17. Three counting bases. F6 fixed home internally; this PR makes ALL
surfaces share one base.

Build (DATA_CONTRACTS §2): a single `day_counts(date)` used by home headline + pills,
calendar cells ("+N more" derives from it), agenda header, and the date-strip
activity dots (PR-7). Definition of the base is in the contract — do not invent one.

Acceptance:
- [ ] Test: for a fixed fixture day, home `feed.total` == calendar cell total ==
      agenda "N events & classes".
- [ ] `+N more` in a cell always equals total − chips shown.

## PR-4 · `feat/v44-04-conditions` — Water + Sunset tiles (Δ2)

DESIGN_SPEC §2, DATA_CONTRACTS §3. Clouds tile retired. Water gets the teal-soft tint;
Sunset renders `7:48` + unit `pm`. Both tiles honest-omit when data is unavailable
(strip flexes to fewer columns; template already iterates `cond_tiles`).

Acceptance:
- [ ] Template test: 6 tiles when both present, 4 when both absent, no "—" or "N/A"
      placeholders ever.
- [ ] Sunset within ±3 min of NOAA for three fixture dates (unit test on the util).
- [ ] Visual refs updated (desktop + mobile).

## PR-5 · `feat/v44-05-ads-rail` — one paid unit + a rail that works (Δ3/Δ5)

DESIGN_SPEC §3–4. Home changes only:
- Marquee: sold creative when a marquee sponsor exists (template already supports it),
  else the buyable placeholder. Either way it is the ONLY ad-shaped unit on the page.
- Delete the two rail `ad_placeholder()` calls and the mobile in-feed placeholders.
- Rail becomes: Find-any-business launcher (real category counts, mini search posting
  to the existing directory search) + Local-news card (3 most recent stored items,
  region chips per the existing `nr-region` rule). Ticker becomes mobile-only.
- Mobile: rail flows below sections; news card hidden on mobile (ticker covers it).

Acceptance:
- [ ] Template test: exactly ≤1 element matching `.feature-marquee` and 0 matching
      `.feature-slot` on rendered home, sponsor present or not.
- [ ] Launcher counts equal the directory's own numbers (same query, cached ≤ 24h).
- [ ] News card omitted entirely when no stored items (honest omission), ticker same.
- [ ] Refs updated.

## PR-6 · `feat/v44-06-gas-ui` — grade switch in panel + /gas page (Δ8)

DESIGN_SPEC §5. Depends on PR-1.
- Panel header gains the compact `Reg · Mid · Prem · Diesel` segment; list re-sorts
  per grade (top-5 of that grade); strip tile echoes the selected grade
  (`GAS · DIESEL` + that grade's cheapest) while the panel is open; reverts to
  regular on close. No persistence (stateless v1).
- /gas page: v4 shell, `Gas prices · cheapest first` head, honest `Updated …` from
  the service, large segment, full sorted table, brass `Cheapest` tag on row 1,
  stations without the grade drop off (no dashes). Footnote line as specced.
- If only one grade exists in data (PR-1 note): render no segment anywhere.
- Progressive enhancement: server renders the Regular view; the segment is JS on top.

Acceptance:
- [ ] Unit: per-grade sort + drop-off; tile echo string format.
- [ ] a11y: segment buttons carry `aria-pressed`; list container `aria-live="polite"`.
- [ ] New visual refs: `gas_desktop.png`, `gas_mobile.png`.

## PR-7 · `feat/v44-07-schedule-niceties` — previews, tpills, places pills, day dots (Δ4/Δ6/Δ7)

DESIGN_SPEC §6–7. Depends on PR-3 for dots.
- Closed-section `.sp` previews, server-built from that section's first real rows
  (macro provided in spec §6.2). Hidden when open and on mobile (CSS already handles
  via the specced rules).
- Movies rows: title-first, theater line, `.tpill` showtimes; no dead time column.
- Counts row: append `For Kids` / `For Seniors` as `.cpill.places` (brass) linking to
  /family and /seniors — no counts on them.
- Date strip: activity dots from `day_counts` thresholds (DATA_CONTRACTS §2.3) and
  the brass spark for configured headliner dates (config dict, NOT a DB change —
  seed `{"2026-07-04": "4th of July Fireworks at the Beach · 9 PM"}`).

Acceptance:
- [ ] Preview text uses only rows actually rendered in that section (test with
      fixtures; no hardcoded copy).
- [ ] Dots: threshold unit tests (0 dots never rendered — min is 1 when count>0;
      spark replaces dots on headliner dates).
- [ ] Refs updated.

## PR-8 · `feat/v44-08-shell` — six-link shell + footer/email consistency (Δ9) — LAST

DESIGN_SPEC §8. The riskiest visible change; Casey sequenced it last on purpose.
- `site_header.html`: Today · Events · Lake · Eat & Drink · Explore · For Business
  (For Kids/For Seniors/News/Movies/Gas/Calendar remain reachable via pills, cards,
  footer, and the mobile drawer — the drawer keeps the full list).
- Footer: single shared footer everywhere; every email is `hello@askhava.com`;
  `For Business` + `Advertise` links brass-emphasized; `/sponsor` de-`noindex`ed.
- Trust line kept verbatim: "Real public reviews · Sponsored clearly labeled ·
  Built in Lake Havasu".

Acceptance:
- [ ] Grep test: zero occurrences of `havasuchat.com` in templates.
- [ ] Drawer still lists all destinations (nothing becomes unreachable).
- [ ] Refs updated for every page the shared shell touches.

---

## PR-9 · `feat/v44-09-dead-code` — remove the old UX for real

After PR-1..8 land on the integration branch, sweep the corpses. Method: for each
candidate, prove unreachability with a repo-wide reference search (templates, routes,
JS, tests, docs excluded); delete; run the full gates. List every deletion in the PR
body. Never delete scraper/data-pipeline code — this sweep is UX-layer only.

Known candidates (verify, then delete):
- `.ev .ph` thumbnail styles + `.im-*` gradient classes in `lake_redesign.css`
  (dead since the plain-time-column change, Casey 2026-06-29).
- `ad_placeholder` macro if PR-5 left zero call sites; `.feature-slot` CSS likewise.
- Clouds tile plumbing (icon, provider field, template branch) after PR-4.
- Old /gas template + its page-specific styles after PR-6 replaces them.
- The `HOME_REDESIGN` flag, its `?home_redesign=` preview branch, and the
  pre-redesign home template + route branch it gated — the redesign IS home now.
- Duplicated shell chrome left in `base_lake.html`/`site_chrome.css` after PR-8
  single-sources header/footer (only what a reference search proves orphaned).
- Any `hello@havasuchat.com` strings, `noindex` on /sponsor (PR-8 should have
  caught these; PR-9 asserts zero remain with a grep test kept in the suite).

Acceptance:
- [ ] Every deletion listed with the search proving it unreachable.
- [ ] Grep tests added: no `havasuchat.com`, no `home_redesign` flag refs.
- [ ] Full gates green; refs unchanged (deletions must not move pixels).

## Dead code policy (applies to every PR, not just PR-9)

Each PR removes what it obsoletes IN THAT PR — replacement and removal travel
together, so the integration branch never accumulates zombies. PR-9 is the backstop
sweep, not the primary mechanism. If a deletion feels risky, it goes in anyway with
its reference-search proof; "we might need it" is not a keep reason (git history
keeps it forever).

## Pre-answered decisions (do NOT ask Casey — the answer is here)

1. **Water temp source?** USGS instantaneous value (param 00010) from the configured
   gauge (`WATER_TEMP_USGS_SITE`, default the Lake Havasu/Parker Dam gauge — pick the
   nearest gauge that returns 00010; verify with one manual fetch during PR-4 and
   record the site ID in config). Cache 1h. If unavailable → omit the tile. Never
   estimate, never carry a value > 6h.
2. **Sunset?** Computed locally (NOAA formula in DATA_CONTRACTS §3.2), America/Phoenix,
   no new dependency, cached per day.
3. **Gas grades missing from source?** Ship regular-only; hide every grade switch.
   No placeholder tabs, no "coming soon".
4. **A station lacks diesel?** It disappears from the diesel view. No dashes.
5. **No marquee sponsor sold?** Buyable placeholder marquee (existing template branch).
   The rail NEVER gets ad units back regardless.
6. **No news items stored?** Omit ticker/card entirely. Honest omission is the pattern
   everywhere — never an empty-state ad.
7. **Day-dot thresholds?** 1–19 → •, 20–49 → ••, ≥50 → ••• (from `day_counts`).
   Count 0 → no dots (and the day card still renders).
8. **Headliner spark?** Config dict only (`HEADLINER_DATES`). No DB, no migration.
9. **Tile echo persistence?** None. Default Regular every load, revert on panel close.
10. **Directory launcher categories?** The 8 in DESIGN_SPEC §4.1 with live counts;
    "All 16 categories →" goes to /categories. Short labels exactly as specced
    (`Health`, `Salons`, `Lodging`) — they truncate otherwise.
11. **Jump-to menu behavior?** Keep live behavior (links to /events-ui views). Do not
    copy the mock's same-page anchor behavior.
12. **Anything about recommendations, ratings, or "top picks"?** No. Never. Directory
    is a launcher; paid placement is always labeled Sponsored. (Feedback log lesson 10.)
13. **Fonts/icons?** Self-hosted variable fonts already in the repo; icons are inline
    monoline strokes per DESIGN_SPEC §9 — no icon libraries, no emoji, ever.
14. **Sticky header?** Unchanged — constant height + scroll shadow (Casey 2026-06-29).
    Don't reintroduce shrink-on-scroll.
15. **Something not covered?** Choose the option that (a) shows more real information,
    (b) fabricates nothing, (c) adds no ad surface, (d) changes the smallest diff.
    Note it in the PR body under "Judgment calls" — do not block on it.

## Stop conditions (the only ones)

Stop and leave a PROGRESS.md note ONLY if: a change would require a DB migration,
touch payment/secrets, or delete user data. Nothing in this plan should — hitting one
means a spec misread. Everything else — including test failures, flaky refs, merge
conflicts with your own branches, missing grade data, an unreachable USGS gauge —
you resolve yourself per the contracts and keep going. Casey returns to a finished
product, not questions.
