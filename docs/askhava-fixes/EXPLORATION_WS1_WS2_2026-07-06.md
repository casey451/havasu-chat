# Ask Hava fix spec — repo exploration report (WS1 + WS2)

**Date:** 2026-07-06 (~22:00 UTC / 15:00 Phoenix)
**Author:** Claude Code
**Scope:** §0 architecture-map confirmation + WS1 (cache/freshness) and WS2 (dead routes/404),
per `askhava-fix-spec-for-claude-code.md`. **No code edited yet** — this is the pre-edit gate the
spec (§0.2) and the task ask for.

Verification method = spec-mandated: cold, no-cookie, `curl -A Googlebot` against **live production
(`https://askhava.com`)**, plus repo reading. Every live fetch below is reproducible.

---

## TL;DR

The spec's inferred architecture (§0) is **materially wrong for the current codebase**, and the two
headline blockers it opens with **do not reproduce on live production right now**:

- **B1 (stale content served cold):** ❌ does not reproduce. Cold Googlebot fetches of `/home`,
  `/events-ui`, `/events-ui?view=week`, `/calendar`, `/movies`, `/map`, `/gas` all render **today**
  ("Monday, July 6") with **one** gas price ($3.59 cheapest). Every HTML response is
  `Cf-Cache-Status: DYNAMIC` — Cloudflare is **not** caching HTML.
- **B2 (blank routes / no 404 template):** ❌ does not reproduce. Unknown URL → **HTTP 404** with a
  7 KB styled Hava 404 page. `/seniors` → **200, 11 KB** content page. `/sponsor` → **200**, real
  rate card.
- **B3 (blank rate card at `/portal/advertise`):** partially stale. `/portal/advertise` is **not a
  registered route** → styled **404** (not a blank 200). The rate card already lives at `/sponsor`
  (and `/advertise` 301s to it). No user-facing CTA links to `/portal/advertise`.

The app already carries the exact fixes the spec prescribes: a `no-cache` transport header on all
HTML (`SecurityHeadersMiddleware`), a per-request `now_lake_havasu()` recompute (no in-process page
cache), a styled 404 handler, and a P0 freshness regression test. **What's genuinely missing** is
narrower than the spec implies (details in each section).

**Recommendation:** don't build WS1 "as written" (date-partitioned keys for a full-page cache that
doesn't exist). Do the real, smaller punch-list instead. See "Recommendation & decision" at the end.

---

## §0 — Corrected architecture map

The spec inferred: flat providers/events → SSR with **~6 header chromes** + **per-template count
queries** → **full-page cache per-URL, no TTL discipline** → Cloudflare → **cold/bots get stale**.

What the repo actually is:

```
FastAPI (app/main.py), ~40 modular routers via include_router — NOT a monolith.

Render path (per request, no full-page cache):
  Request
   → SessionMiddleware, SecurityHeadersMiddleware (stamps Cache-Control: no-cache on ALL text/html),
     CanonicalHostRedirectMiddleware (301 legacy hosts → askhava.com)
   → route handler recomputes now_lake_havasu() fresh every request
   → Jinja render on ONE v4 shell (base_redesign.html / base_plain.html → lake_redesign.css).
     The "≥6 header chromes" were consolidated in the v4.4–v4.6 migration (2026-07-02..04).
   → conditions + gas baked SERVER-SIDE via one shared module app.home.redesign
     (conditions_tiles(), gas_panel_data()) — same code on every page.
   → Cloudflare passes HTML through as Cf-Cache-Status: DYNAMIC (does NOT cache HTML).

Data caches that DO exist (payload, not HTML; short TTL; NOT date-keyed):
  - app.categories.router._index_cache   (category index, 3600 s)
  - app.api.routes.map_data._map_cache    (map payload, 600 s)
  - conditions/gas via external_conditions_cache table (source rows), llm caches
  None of these can explain 26-day staleness (max TTL 1 h) — so they are not the B1 mechanism.

Endpoints already present that the spec assumes are missing:
  - GET /api/conditions  → app/api/routes/conditions.py (build_conditions_api_payload)
                           EXISTS, but templates do NOT hydrate from it (they bake server-side).
  - Styled 404           → @app.exception_handler(StarletteHTTPException) → not_found_lake.html.
```

### §0 grep-anchor mapping (where each anchor actually lives)

| Anchor | Location | Note |
|---|---|---|
| `gseg` / `gsegwrap` | `app/static/styles/lake_redesign.css`, `app/templates/gas_prices_lake.html`, `lake_redesign.js` | WS8 target confirmed |
| `cpill` / `.counts` | `lake_redesign.css`, `events_redesign.html`, `base_redesign.html` | WS8 target confirmed |
| `lake_redesign.css` | `app/static/styles/lake_redesign.css` | the one live shell sheet |
| `rotating_placeholder.js` | `app/static/js/rotating_placeholder.js` | exists |
| `static/biz-photos/` | mounted from `/data/biz-photos` (Railway volume) in `main.py` | exists |
| `/api/conditions` | `app/api/routes/conditions.py` | **exists** (see above) |
| `/events-ui` | `app/home/router.py:386` | fresh per-request; `/events` permalink is separate (`app/events/permalink.py:311`) |
| `/seniors` | `app/home/static_pages.py:89` → `seniors_lake.html` | **content page, not blank** |
| `/night`,`/family`,`/lake` | `app/home/router.py` (281/287/267) | `/lake` **301s to Lake Life category**, not a 6-tile hub |
| `/today` | `app/api/routes/today.py:47` | conditions dashboard |
| `/sponsor` | `app/home/router.py:661` → `sponsor_landing_lake.html` | **the real rate card** |
| `/advertise` | `app/main.py:739` | **301 → /sponsor** (spec wants the inverse) |
| `/portal/advertise` | — | **NOT registered** → 404 |
| `/portal/placements` | `app/portal/router.py:165` | login-walled (303 → /login) — matches spec |
| `/portal/reserve` | — | **NOT registered** (referenced in comments/admin only) |
| `/provider/{slug}` | `app/providers/router.py:46` | **raises 404** on missing/inactive/draft |
| `Havasu headlines` / news | `app/news/…`, `news_redesign.html` | WS13 target |
| `Claim this category` | category templates | WS3/WS7 target |

Source ingest list is roughly as inferred, with one correction: **movies = Star Cinemas via its
public Supabase REST API** (`app/movies/store.py`), not "Veezi".

---

## WS1 — Cache & freshness

### Live evidence (cold, `-A Googlebot`, 2026-07-06 ~21:57 UTC)

| URL (cold) | HTTP | Cf-Cache-Status | Rendered date | Gas |
|---|---|---|---|---|
| `/home` | 200 | DYNAMIC | Monday, July 6 | $3.59 |
| `/events-ui` | 200 | DYNAMIC | Monday, July 6 | $3.59 |
| `/events-ui?view=week` | 200 | DYNAMIC | Monday, July 6 | — |
| `/calendar` | 200 | DYNAMIC | Monday, July 6 | — |
| `/movies` | 200 | DYNAMIC | Monday, July 6 | — |
| `/map` | 200 | DYNAMIC | Monday, July 6 | — |
| `/gas` | 200 | DYNAMIC | Monday, July 6 | $3.59 cheapest |

All carried `Cache-Control: no-cache, max-age=0, must-revalidate`, `Vary: accept-encoding`
(**not** `Vary: Cookie`), `Server: cloudflare`.

### Why B1 doesn't reproduce (root cause the spec missed)

The spec attributed B1 to an in-app "full-page cache, no TTL discipline" that is **cookie-keyed**
(warm=fresh, cold=stale). The repo has **no such cache**. The origin explicitly emits `no-cache` on
every HTML response (`SecurityHeadersMiddleware`, added 2026-06-07 for this exact P0), and each route
recomputes `now_lake_havasu()` per request. Cloudflare currently classifies HTML as `DYNAMIC`
(uncached). So the warm/cold divergence the audit saw was **edge-level, in Cloudflare's config** —
not in this repo — and it is not active now (either the CF "Cache Everything" rule was removed, or
the `no-cache` origin header now makes CF treat HTML as DYNAMIC, or the audit's own client/proxy
cached). This is Casey-owned infra (Cloudflare dashboard), consistent with the memory note "Casey
owns: Cloudflare + TRUSTED_HOSTS".

Already-present guardrails: `tests/test_events_ui_freshness.py` pins day-rollover + the `no-cache`
header for `/home` and `/events-ui`.

### What is genuinely still worth doing in WS1 (much smaller than the spec)

1. **Header hydration from `/api/conditions` (spec WS1.4/1.7) — latent-risk fix, not active-bug.**
   Conditions/gas are baked server-side into every page. If CF (or any proxy) ever caches an HTML
   shell, that baked snapshot goes stale even though `/api/conditions` stays fresh. Wiring the
   header/util bar to hydrate from `/api/conditions` (skeleton SSR + client fetch, no-JS fallback =
   last values + timestamp) makes the shell cache-safe. The endpoint already exists; templates just
   don't consume it. **This also structurally prevents the "5 concurrent gas prices" symptom.**
2. **B6 feed parity — needs a real check (possibly still a live bug).** Spec says `/home` and
   `/events-ui?date=<today>` disagree (Classes & Workshops on one, not the other; films attributed
   to different theaters). This is independent of caching. I have **not** yet diffed the two feeds;
   it should be verified and, if real, unified behind one feed source. (Candidate for a
   snapshot-diff test.)
3. **Cold-cache freshness canary (spec WS1.6) — genuinely absent.** The repo's "canary" is the
   anti-scrape decoy-listing tripwire (`app/monitoring/canaries.py`), and `app/monitoring/
   freshness.py` grades *feed* freshness internally — neither does an external cold-cache
   `curl -A Googlebot` assert-today-and-gas-under-24h check. Worth adding (cron + alert). This also
   satisfies WS2.4 route-health.
4. **Honest staleness UI for gas >24h (spec WS1.5) — verify.** Need to confirm `gas_prices_lake.html`
   can't render a "Live" chip next to stale data. Not yet checked.

### WS1 items that are **not applicable / already satisfied**

- Date-partitioned full-page cache keys (WS1.1) — N/A; there is no full-page cache to key.
- "TTLs: HTML 10 min + SWR" (WS1.2) — would be a **regression** (HTML is correctly `no-cache`).
  If we want CDN micro-caching later that's a deliberate, separate infra decision with the date in
  the key — not a bug fix.
- Purge-on-publish (WS1.3) — only meaningful if we introduce HTML caching; currently moot.

---

## WS2 — Dead routes, 404, route health

### Live evidence (cold, `-A Googlebot`)

| URL | HTTP | Bytes | Verdict |
|---|---|---|---|
| `/nonexistent-xyz-404test` | **404** | 7147 | ✅ styled 404, correct status (not blank-200) |
| `/seniors` | **200** | 11334 | ✅ content page (Senior Center hub), not blank |
| `/sponsor` | **200** | 8571 | ✅ rate card renders |
| `/portal/advertise` | **404** | 7133 | route unregistered → styled 404 (not blank) |
| `/portal/placements` | **303** | 0 | login wall (→ /login), matches spec |

### Root causes vs the audit

- **Blank routes (B2):** don't reproduce. `/seniors` is a real static hub
  (`app/home/static_pages.py` → `seniors_lake.html`, no DB, can't 500 cold). Unknown routes hit the
  `StarletteHTTPException` handler → `not_found_lake.html` at HTTP 404. `/provider/{slug}` raises a
  proper 404 for missing/inactive/draft. The spec's "empty body, no 404 template" is stale for this
  code.
- **`/portal/advertise` "blank" (B3):** it's a **404**, because the route was never registered —
  `main.py` and `models.py` comments reference it, and an admin page mentions the "Reserve this
  spot" flow, but there is no handler and no user-facing CTA points to it. The advertiser rate card
  is `/sponsor`.

### What is genuinely still worth doing in WS2

1. **Unregistered-but-referenced routes = latent dead links.** `/portal/advertise` and
   `/portal/reserve` exist only in comments/admin copy. Either register them (if the reserve flow is
   wanted) or scrub the references so nothing ever points at a 404. Low-risk cleanup.
2. **Route-health canary (WS2.4) — absent.** Same gap as WS1.6: assert every header/footer/nav URL
   returns 200 + non-empty `<main>`. Best implemented as the one canary that also covers freshness.
3. **`/seniors` content upgrade (spec WS2.2 + WS10 + Render §6) — optional.** It already renders the
   Senior Center hub; the spec/mockup want it to also pull *today's* seniors feed from the DB. That's
   a genuine enhancement, not a bug fix — belongs with WS10.

### WS2 items already satisfied

- Styled 404 template with correct status, search box, category links → **done**
  (`not_found_lake.html` + handler). Worth a spot-check that it matches Render §5 (search box +
  top-category chips + "Add it to Hava" link).

---

## Recommendation & decision

The spec was written from a black-box audit that captured an **edge-caching incident** and a
**pre-v4.6 template state**, both of which the codebase has since moved past. Executing WS1 verbatim
would build machinery (date-partitioned page-cache keys, HTML SWR TTLs, purge-on-publish) for a
cache that doesn't exist, and would *reintroduce* HTML caching the team deliberately turned off.

Proposed re-scoped WS1+WS2 (one branch, `fix/ws1-freshness-hardening`):

- Wire the header/util bar to hydrate conditions + gas from `/api/conditions` (removes the last
  server-baked-snapshot staleness vector; kills the 5-price symptom structurally).
- Add a cold-cache freshness **+** route-health canary (cron: bot-UA fetch of the defect-matrix +
  every nav URL; assert rendered date == Phoenix-today, gas `updated_at` < 24 h, 200 + non-empty).
- Verify & (if real) fix B6 `/home` vs `/events-ui` feed parity; add a snapshot-diff regression.
- Verify gas >24h honesty UI; scrub/reg the `/portal/advertise` + `/portal/reserve` references.
- Leave the origin `no-cache` + per-request recompute exactly as-is (they are the fix).

The Cloudflare "Cache Everything / bypass-on-cookie" question is **Casey-owned** and out of repo — the
canary is how we'd catch it if it ever comes back.

**Open question for Casey (genuine judgment call, per CLAUDE.md):** proceed with the re-scoped
WS1+WS2 above, or something else? (Options in chat.)

---

## Update — what `fix/ws1-freshness-hardening` actually shipped

Casey chose **re-scoped WS1+WS2**. Delivered on branch `fix/ws1-freshness-hardening`:

1. **B6 feed parity — verified not-a-defect + guarded.** Confirmed
   `redesign.feed_view_model` delegates to `events_views.calendar_day_view_model` (the builder
   `/events-ui` uses) and only enriches rows — parity is guaranteed by construction. Live prod: both
   surfaces render identical sections + counts (Things to Do 9, At the Movies 6, Fitness & Sports 42;
   57 rows). Added `tests/test_home_events_feed_parity.py` to fail loudly if the two builders ever
   fork again.
2. **Gas >24h honesty UI — already satisfied, no change.** `is_stale` (threshold
   `GAS_STALE_AFTER_HOURS=10`, stricter than 24h) gates an "out of date" flag on `/gas`
   (`gas_prices_lake.html`) and the honest `staleness_label` in the util bar; there is no false
   "Live" chip anywhere in conditions/gas. Already covered by `test_stale_banner_flags_out_of_date`.
3. **Cold-cache freshness + route-health canary — added.** `scripts/freshness_canary.py` (stdlib
   only) fetches prod cold with a bot UA and asserts: every dated page renders Phoenix-today; one
   cheapest-gas price across pages; `/api/gas` < 24h and not stale; every nav URL is 200+non-empty or
   an allowed redirect. Pure core unit-tested offline in `tests/test_freshness_canary.py` (13 cases).
   Scheduled every 15 min via `.github/workflows/freshness-canary.yml` (dormant until merged to main;
   `workflow_dispatch` to run now). Passes live today.
4. **Dead-ref scrub.** Corrected the misleading `main.py` comment claiming `/portal/advertise` is a
   real page (it 404s; the rate card is `/sponsor`). No user-facing nav/footer/CTA points at a 404.

**Deferred (with reasoning): `/api/conditions` header hydration (spec WS1.4/1.7).** Recommended
**not** shipping this in a hardening PR:
- It is **latent-only**: Cloudflare serves HTML as `DYNAMIC` (uncached), so the baked-snapshot
  divergence it guards against cannot occur now, and the canary catches a recurrence.
- Crawlers don't run JS, so hydration wouldn't change what bots see (the SSR value stays).
- `/api/conditions` doesn't even include gas — wiring the gas chip would mean a payload-contract
  change or a second fetch.
- It touches the shared shell (`base_redesign.html`) on **every page** — highest blast radius — and
  this repo has **no JS test harness**, so the hydration JS would ship largely untested.
- The clean home for it is **WS7** (shell consolidation) / **WS8** (which introduces the Playwright
  matrix that could actually test it), or whenever HTML edge-caching is turned on for performance (at
  which point hydration becomes *necessary* and should land with that cache change).

The Cloudflare "Cache Everything / bypass-on-cookie" question remains **Casey-owned** (out of repo);
the canary is the in-repo tripwire for it.
