# Ask Hava — Full-Site Audit & Remediation Plan
**Date:** 2026-07-04 · **Author:** Cowork session (investigation only — no fixes applied)
**Method:** Live site walked in Chrome at mobile (390px) and desktop (1024px) widths; three parallel codebase/data agents mapped the frontend, the scraper/data pipeline, and data quality; competitor and copycat sites fetched; GitHub exposure verified anonymously.

> **This is a plan, not a change.** Nothing on the site or in the repo was modified. Prod data ops below all follow the repo rule: dry-run → show counts → your approval → apply.

---

## 1. Synthesis — the root themes (and the ones you didn't name)

Almost everything you flagged collapses into **eight root causes**. Fixing the cause (not the symptom) is what keeps the fix from recurring.

**A. One shared view-model drives both home and the events page (this is good news).**
`app/home/events_views.py::calendar_day_view_model()` is the single builder both `/home` and `/events-ui` consume ("parity Rule 0"). So the accordion, default-open, nesting, tag, and count changes you want are each **one edit that fixes both surfaces**. Low risk, high leverage.

**B. Layout state is decided in Python, then frozen in the template.** Default-open sections and forced-closed subgroups are set in `day_groups()` (`events_views.py` ~lines 609–623: `g["open"]=True` for sections with a real event, `sub["open"]=False` for *every* subgroup). Your "collapse everything by default" and "open a section → expand all subgroups (except Fitness)" asks are all changes to that one function plus the `feed_macros.html` accordion macros.

**C. Backend/orga­nizational metadata is leaking into the UI.** The "Jump to" box, the repeating category pill row, the "30 going on" count, the sorting tags ("CHURCH, EVENTS", "farmers market"), the sign-in avatar, and "Open now & popular" are all **presentational chrome** rendered from data the user doesn't need. These are the cheapest wins on the board and the biggest driver of the "drowning in headers / unfinished" feel.

**D. There is no ingest-time dedup, and the render-time dedup has gaps — duplication is systemic, not stray.** Confirmed live: the **Calvary Baptist 6 PM** event appears twice (one rich w/ address + "CHURCH, EVENTS" tag, one thin "Family Water Night / Calvary" w/ "EVENTS" tag, neither with a flyer), and **"Billiards" is duplicated ×2 every single day**. The 100%-crawl audit found **35 exact same-title-same-date event clusters** and dozens of listing "shadow mirror" duplicates. Root cause: dedup relies on fuzzy title + venue matching thresholds that near-generic titles (church services, "Billiards") slip through, and cross-source merges require a specific venue string that bare "Lake Havasu City" never satisfies. This is your recurring "dedup artifact leaks into the UI" problem.

**E. Source attribution is driven by a provenance *string*, not by whether a primary URL exists.** The displayed source label comes from `Event.source` (e.g. `river_scene_import`, hardcoded in `app/contrib/river_scene.py`), **regardless** of whether the event already has a primary `event_url`. That's exactly why the **Lake Havasu Farmers Market** shows "source: River Scene Magazine" even though the direct `lakehavasufarmersmarket.com` URL is available — and why its **time is blank** (the River Scene detail table often has no "Time" cell, and the parser deliberately leaves it null rather than guess). Both are pipeline-level, not one-off.

**F. Category assignment and listing completeness are the largest debt, and it's structural.** Across ~2,445 listings the 100%-crawl audits found **10.6% with no address, 8.3% with no phone, 70 name-only "ghost" rows, 131 "browse-orphans"** (on zero leaf pages), and ~24 near-empty leaves. Water-tour operators, fishing guides, and captained charters are **trapped in the generic "boat rentals" leaf (114 listings)** instead of Boat Tours & Charters (10) / Fishing Charters (7). This is the "full category audit," and it is genuinely multi-session.

**G. Refresh is fragile, so "everything must be scraper-backed" is violated in places.** There is **no production worker** — every scrape runs as a GitHub Actions cron off `main` with `DATABASE_URL` set; if a workflow isn't merged/enabled, that source silently never runs. Hand-curated data (`app/home/family_venues.py` hours, several `seed_*.py` scripts) and pending vision/flyer events **will go stale** with nothing refreshing them.

**H. Provenance is invisible in the UI.** Conditions tiles aren't links, and **water temp comes from a physically different source** than temp/wind: temp + wind are NWS station **KHII** (the airport); water temp is **USBR RISE item 6127, Parker Dam**. (A USGS alternative gage, 09426630, has been emitting a −100000 error sentinel since 2026-05-21 and is off by default — good.) Your instinct is right: the water number *should* be clickable to its source, and the sources should be made transparent site-wide.

**I. (Not on your list, but the meta-cause behind the copycats) — the repo is public.** `github.com/casey451/havasu-chat` is **Public**. The entire `app/` tree, every scraper and its source list, the category taxonomy, and the data-ops plans are browsable by anyone, signed out. This is both a standalone security issue and the most likely answer to "how did copycats find it so fast."

---

## 2. Symptom → cause → where it lives (your specific items)

| # | Your item | Root cause | Where to fix |
|---|---|---|---|
| 1 | Remove "31/30 going on" | `feed.total` printed next to "Happening today" | `home_redesign.html` ~line 113 |
| 1 | Remove "Jump to" box | Presentational dropdown of sections | `home_redesign.html` ~114–121 + `lake_redesign.js` 131–166 |
| 1 | Remove repetitive category pills | Duplicate of sections below | `home_redesign.html` ~124–133 |
| 1 | Collapse all sections by default | Python sets `open=True` per section | `events_views.py::day_groups` ~609–623 |
| 2 | Flatten nested collapses; Fitness stays nested | Subgroups forced `open=False`; recursion in `sub_tree` | `events_views.py` ~623 + `feed_macros.html::sub_tree` |
| 3 | Music & Nightlife + Lake & Boating under Things to Do | Top-level taxonomy tuple | `event_buckets.py::GROUP_DEFS` + routing |
| 4 | Water temp different source; make tiles clickable to source | Tiles are non-link; water = USBR RISE, temp/wind = NWS KHII | `base_redesign.html` 54–71 + `redesign.py::conditions_tiles` + `app/conditions/*` |
| 5 | Everything must be scraper-backed | Hand-curated + pending data won't refresh | `family_venues.py`, `scripts/seed_*`, pending vision queue |
| 5 | Surface primary URL, drop aggregator source | Label from `Event.source` string, not `event_url` | `river_scene.py` + display logic |
| 5 | Farmers Market missing time | River Scene table has no Time cell; parser leaves null | `contrib/river_scene.py::_parse_time_cell` |
| 6 | Dedup Calvary / Billiards etc. | No ingest dedup; render-time thresholds miss generic titles | `contrib/event_reconciler.py`, `events/dedup.py` |
| 7 | Hide backend tags | `tags()` macro renders every plain tag | `feed_macros.html` 7–9 |
| 8 | Remove sign-in button (keep code) | Header avatar/link | `_partials/site_header.html` 50/60/61 |
| 8 | Remove "Open now & popular" (keep code) | Department landing section | `category_department_lake.html` 26–30 + `categories/router.py::_landing_cards` |
| 9 | Gas labels "gas / gas mid / gas premium"; Diesel green | Tile echo appends grade to word "gas"; two label sets exist | `redesign.py` `GAS_GRADE_LABELS_*` + `echo` suffix; `/gas` page already clean; unify with `gas.py` |
| 10 | Full category audit; remove vacation rentals | Categorization + completeness debt | `askhava-directory-data-ops-plan.md` + `docs/audits/2026-07/*` |

**Live confirmations captured this session:** the Calvary duplicate; Billiards ×2; leaking "CHURCH, EVENTS" / "EVENTS" tags; "Things to Do" auto-expanded with all subgroups collapsed; Jump-to, pill row, "30 going on", sign-in avatar, and the "AD SPACE" house-ad all above the fold; "Open now & popular" on the Places to Stay page; and **Vacation Rentals now split into its own leaf with 50 listings** (Hotels & Motels 31, RV Parks 23) — several linking out to OTA aggregators.

---

## 3. Additional issues found (not on your list)

1. **The "AD SPACE · AVAILABLE / Claim this spot" house-ad card owns the most valuable space on the home page** — directly under the news strip, above the search and the whole calendar. For a site that hasn't been advertised and (presumably) has no paying advertisers yet, a big "your logo here" placeholder reads as unfinished. **Decision needed:** keep, shrink to a slim strip, or hide until there's real inventory.
2. **Two independent gas-label vocabularies** (`redesign.py`: reg/mid/prem/dsl vs `gas.py`: regular/midgrade/premium/diesel). The `/gas` detail page already renders cleanly (Regular/Midgrade/Premium/Diesel) — the cramped "gas / gas mid / gas premium" you saw is the **conditions-strip Gas tile echo**. Unify the two so this can't drift again.
3. **Desktop is just the centered mobile column** — no desktop-optimized layout even at 1024px. Fine for an app-like feel, but it means every fix here lands identically on both (good), and there's no wasted-space desktop treatment to worry about.
4. **Taxonomy drift between layers.** The internal `taxonomy-seed.json` (15 departments, names like "Music & Nightlife", "Seniors") doesn't match the live consumer department names ("Eat & Drink", "Lake & Boating", "Things to Do", "For Kids & Families"). The two naming systems are a standing maintenance hazard for any category work.
5. **~50% of events in the last crawl were past-dated (374/748), with 166 stale one-offs still live.** A freshness/retirement sweep belongs in the dedup session.
6. **Out-of-area lodging is live** (Black Meadow Landing — Parker Dam, **CA**; Havasu Springs Resort — Parker, AZ) and several lodging links point to OTA aggregators rather than a bookable first-party page.
7. **`admin-dashboard-pending.png` is committed to the public repo** — it leaks a screenshot of the internal admin UI.
8. **Possible touch-zoom sensitivity:** wheel-scrolling the narrow viewport repeatedly triggered a zoom during testing. This may be an automation artifact, but **worth verifying pinch/zoom behavior on a real phone** — if reproducible, it's a real mobile bug.

---

## 4. Research thread 1 — the copycats

**Verdict: one of the two "copycats" isn't one, and the other is a look-alike you can't (yet) prove copied you.**

- **havasu365.com — not a copycat.** WordPress 7.0 site, footer reads **"© 2018–2026 … Havasu365.com,"** built by a local shop ("Havasu Web Design Co."). It's a thin, older events page whose listings mostly link out to golakehavasu / havasusprings. It **predates Ask Hava** and is an independent competitor, not a clone.
- **havasu.info — the real look-alike.** Newer, and structurally very close to Ask Hava: **Lake Conditions** page, an **Events** page with category chips (Water / Music / Cars / Community), **News**, and a **Directory** whose departments mirror yours (Restaurants, Hotels & Lodging, Marine Services, Home Services & Trades, Shopping, Health & Wellness, Boat Rentals, Tours, Golf, Hiking, Parks & Beaches, Fishing). Same teal palette (`#0D4A60`), "built by locals" positioning, built by a local agency (**AstroTECH**). I **can't prove** it copied Ask Hava — "conditions + events + news + directory" is also just the obvious shape for a local hub — but the overlap is close enough to watch.

**How did they find it with no advertising?** In rough order of likelihood:
1. **The public GitHub repo** (see §5) — the concept, taxonomy, and scrapers are all readable.
2. **Certificate Transparency logs.** The moment askhava.com got its TLS certificate, the hostname became public in CT logs (crt.sh etc.). Anyone monitoring "havasu" sees new domains within hours — this is a very common competitor/scraper discovery path and fits "appeared within a week."
3. **Passive DNS / host neighbors** (Railway's public domains, shared-host enumeration).
4. **Small-town web community** — havasu.info's builder is a local Havasu agency.

Notably, askhava.com **did not surface in Google** for its own name during testing, so it isn't strongly indexed yet — which makes organic-search discovery *less* likely and the repo / CT-log paths *more* likely.

**Recommended posture:** there's nothing to "fix" about havasu.info itself; it's a competitor. The lever you actually control is the exposure in §5, plus out-executing on coverage/quality (§6, §11 of your brief).

---

## 5. Research thread 2 — GitHub / code exposure (highest-priority finding)

**`github.com/casey451/havasu-chat` is Public.** I browsed it signed-out: the full `app/` tree, every scraper and its source list, the category taxonomy, the GitHub Actions workflows (which reveal your scrape schedule and sources), and multiple `*_PLAN` / audit docs are all readable. The public README is an old "Phase 1" stub, so a casual visitor sees a thin repo — but the real codebase is one click into `app/`.

**Why it matters:** this is the single most plausible answer to the copycat question, and independently it hands anyone your entire data-collection playbook. It's also the reason your CLAUDE.md already recommends branch protection.

**Recommendations (do these first — see Session 0):**
1. **Make the repo private.** Biggest single lever; reversible. If you have a reason to keep it public, that's a deliberate choice — but it should be deliberate.
2. **Audit git *history* for secrets and rotate as a precaution.** The working tree has `.env`, `.env.ghtoken`, `.env.produrl` and the prod Postgres URL lives in `.env.produrl`; those files appear gitignored (they're not in the tracked root listing), **but** history can still contain a secret committed before it was ignored. Run a scanner (gitleaks or trufflehog) over full history; **rotate the prod DB credential and the GitHub tokens** regardless — rotation is cheap insurance. (I did not run git against your checkout, per the repo rules — this is yours to run, and I can hand you exact commands.)
3. **Remove `admin-dashboard-pending.png`** from the repo.
4. **Enable branch protection on `main`** (require PR + review, block direct pushes) — already recommended in CLAUDE.md; this also enforces the "never push to main" rule physically.

---

## 6. Prioritized, sequenced remediation plan

Ordered by **impact ÷ risk**, and by dependency (declutter before restructure; restructure before the deep category grind). Effort is rough.

### Session 0 — Secure the exposure *(mostly your hands; I prep the checklist)*
Repo → private; secret-scan history + rotate prod DB credential and GH tokens; delete `admin-dashboard-pending.png`; enable `main` branch protection.
**Risk:** low. **Why first:** it's the active exposure, it's the copycat vector, and it's independent of all the UI/data work. Blocks nothing.

### Session 1 — Mobile-first declutter *(presentational only)* ← **best first build**
Remove "30 going on", the "Jump to" box, and the category pill row; **collapse all top-level sections by default**; **hide backend tags** on event rows; remove the **sign-in avatar** (CSS-hide, keep code); remove **"Open now & popular"** (keep the builder); **fix gas labels** (Regular/Mid/Premium/Diesel everywhere, **Diesel green**, unify the two label sets).
**Touches:** `home_redesign.html`, `feed_macros.html`, `site_header.html`, `category_department_lake.html`, `lake_redesign.js/.css`, `redesign.py`/`gas.py` labels. **No DB writes.**
**Risk:** low. **Payoff:** this alone makes the site feel like a finished app. Verify on mobile + desktop.

### Session 2 — Accordion behavior + (optionally) category consolidation
2a: default-collapsed top-level; **opening a section expands all its subgroups**; **Fitness stays nested**; label variants (e.g. youth Jujitsu). Change is concentrated in `events_views.py::day_groups` + `feed_macros.html`.
2b (**split this out — riskier**): fold **Music & Nightlife** and **Lake & Boating** into **Things to Do** in `GROUP_DEFS` + routing. This ripples into counts, routing, and tests, and there's a naming question with the **directory's** own "Lake & Boating" department (77 listings) — decide whether the restructure is events-feed-only or also the directory.
**Risk:** 2a low-med, 2b med.

### Session 3 — Event data integrity: dedup + provenance + freshness *(prod data op)*
Repair dedup so twins (Calvary, Billiards-daily, the 35 clusters) collapse into **one authoritative entry** that merges the richest description + correct time/location + flyer, showing a single source; fix source-label logic so **a primary `event_url` surfaces the primary and drops the aggregator label** (Farmers Market → its own site); repair the **dropped-time** parse and backfill; **retire the ~50% past-dated / stale events**.
**Risk:** med-high — touches prod data. **Gate:** dry-run → counts → your approval → apply, per CLAUDE.md.

### Session 4 — Scraper-backing + provenance transparency
Audit hand-entered/one-off data (`family_venues.py`, `seed_*` scripts, pending vision queue) and either scraper-back it or schedule a maintenance pass; **make conditions tiles clickable to source** (temp/wind → NWS KHII, water → USBR RISE Parker Dam, gas → `/gas`), with an intentional-but-not-accidental tap affordance; confirm the water-temp source is the right, consistent one.
**Risk:** low-med.

### Session 5 — Places to Stay cleanup *(contained data op)*
Remove **all vacation-rental + property-management** listings (the 50-item VR leaf + the ones misfiled under Hotels), keep only **verified hotels/motels + RV parks/campgrounds with bookable links**; drop out-of-area lodging (Black Meadow Landing CA, Havasu Springs Parker AZ) and OTA-only links. Reversible (deactivate, don't hard-delete).
**Risk:** low-med (prod data → same gate). Can fold into Session 3's op if you'd rather.

### Sessions 6+ — Full category audit + coverage expansion *(genuinely multi-session)*
Per-department completeness pass (working URL, hours, location on every listing; fix Kids → Classes & Camps); fix categorization root causes (charters/tours/guides out of the boat-rentals leaf; consolidate off-road/ATV/UTV, jet-ski/watersports, golf-cart, bike/e-bike rentals); dedup listing shadow-mirrors; fix the 131 browse-orphans and 70 ghost rows; **competitive coverage** map vs Go Lake Havasu + havasu.info (watersports, rentals, tours, guides, fishing, off-road, golf, beaches). **Build on what exists** — `askhava-directory-data-ops-plan.md` (already a 15-batch plan) and `docs/audits/2026-07/ASKHAVA_FULL_SITE_AUDIT_2026-07-01_MASTER.md` — don't restart. Quality over quantity: hide anything that can't be made complete.
**Risk:** med, spread over several sessions; sequence department-by-department.

---

## 7. Session-breakdown recommendation (one vs several)

**Several — six tracks, roughly this order.** One session can't responsibly cover pure-presentation edits, taxonomy surgery, three separate prod data ops, and a multi-department content grind without tangling risk levels and blowing past a safe review boundary.

- **Do now, in order:** Session 0 (security) → Session 1 (declutter) → Session 2a (accordion behavior).
- **Then, each as its own gated session:** 3 (dedup/provenance), 4 (scraper-backing + conditions links), 5 (Places to Stay).
- **Then ongoing:** Session 2b (category restructure) and Sessions 6+ (category audit) — these want your decisions first (below) and run department-by-department.

Sessions 0 and 1 are independent and safe enough to run back-to-back. Everything that writes prod data (3, 5, and parts of 4/6) stays behind the dry-run → counts → approval gate.

---

## 8. Decisions I need from you before building

1. **Repo visibility + rotation (Session 0).** OK to make the repo private? OK to rotate the prod DB credential + GitHub tokens as a precaution? (I'll prep exact commands; the rotation/settings are yours to execute.)
2. **The "AD SPACE / Claim this spot" home card.** Keep as-is, shrink to a slim strip, or hide until there are real advertisers?
3. **Category restructure scope (Session 2b).** Fold Music & Nightlife + Lake & Boating into Things to Do in the **events feed only**, or also rename/restructure the **directory** (where "Lake & Boating" is a 77-listing department)?
4. **Fitness nesting rule.** Always nested, or nested only on busy days (conditional)? You said "on busy days" — confirm which.
5. **Vacation rentals removal.** Confirm deactivate-and-hide (reversible) rather than delete, and that it's the whole VR leaf + the misfiled-into-Hotels ones.
6. **Prod data-op gate.** Confirm you want the standard dry-run → counts → approval flow for Sessions 3 and 5 (I'll assume yes).
7. **havasu.info.** Any action wanted, or just monitor? (My recommendation: monitor; compete on coverage/quality.)

---

## 9. What I did *not* do
- No code, template, or data changes anywhere.
- No git operations against your checkout (per CLAUDE.md sandbox rules).
- No prod DB reads/writes — data-quality numbers come from your own 100%-crawl audits in `docs/audits/2026-07/` and `taxonomy-seed.json`, cross-checked against the live site.

**Sources / evidence:** live site `askhava.com` (home, `/gas`, `/categories`, `/categories/lodging`); `github.com/casey451/havasu-chat` (verified Public, signed-out); `havasu365.com`, `havasu.info`, `golakehavasu.com/things-to-do`; internal docs `askhava-directory-data-ops-plan.md`, `docs/audits/2026-07/COVERAGE_GAP_golakehavasu_riverscene_2026-07-03.md`, `docs/audits/2026-07/ASKHAVA_FULL_SITE_AUDIT_2026-07-01_MASTER.md`, `docs/proposals/taxonomy-seed.json`.
