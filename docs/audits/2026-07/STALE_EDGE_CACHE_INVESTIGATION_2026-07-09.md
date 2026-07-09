# Stale-cache class — full investigation (2026-07-09)

Trigger: a third sighting of bare `/categories/eat-and-drink/quick-bites-and-takeout`
and `…/bakeries-and-desserts` serving a late-June render (no `build-sha` meta, stale
`· Live` chip, "+ Advertise" card + business footer that #803/#804 hid), while
`?open=1` param variants were fresh. Requested: reproduce, enumerate the app page
cache, ship the structural fix, extend the canary, cold-verify.

## 1. Reproduce (cold curl, Googlebot UA, no cookies) — from this vantage: FRESH

```
GET https://askhava.com/categories/eat-and-drink/quick-bites-and-takeout
  Date: Thu, 09 Jul 2026 22:11:19 GMT
  Cache-Control: no-store, no-cache, max-age=0, must-revalidate
  Cf-Cache-Status: DYNAMIC          CF-RAY: a18aa9ec2eb25708-LAX
  <meta name="build-sha" content="52a9c0eed9e8">   (== running app)
  <meta name="render-ts" content="2026-07-09T22:11:19Z">  (now)
  "+ Advertise" absent · "Sponsor this category" absent

GET …/bakeries-and-desserts  → identical: build-sha 52a9c0eed9e8, render-ts now,
  Cf-Cache-Status: DYNAMIC, ad CTAs absent.
```

Repeat hits + `?open=1` + a browser UA were **all** `Cf-Cache-Status: DYNAMIC`, no
`Age` header, build-sha current. So **from the LAX PoP, Cloudflare is not caching
these HTML pages at all — every request reaches the origin and renders fresh.**
(Footer "For Business" *is* present, but that is now correct: #804 restored it as a
**claim** link; the paid "+ Advertise"/"Sponsor this category" surfaces are absent.)

## 2. App page-cache inventory — COUNT OF PAGE ENTRIES: **0** (no such store exists)

Every category / leaf / department / home page renders straight to
`templates.TemplateResponse(...)` built from the DB **per request** — `_render_leaf_page`,
`_render_department_page`, `serve_category`, the home route: none read or write a
rendered-HTML cache. There is **no** page-HTML cache — no dict, no DB table, no Redis,
no disk/volume prerender.

The complete cache inventory (every cache in `app/`, and what each holds — none is a
page-HTML store, so none can freeze a leaf render):

| # | Cache | Kind | Holds | Persists a deploy? |
|---|-------|------|-------|--------------------|
| 1 | `categories.router._index_cache` | in-proc, TTL 1h | /categories **index payload** (counts) | no (process-local) |
| 2 | `seo.site_routes._sitemap_cache` | in-proc, TTL | sitemap **XML** | no |
| 3 | `api.routes.map_data._map_cache` | in-proc, TTL 600s | map **JSON** pins | no |
| 4 | `conditions.cache._local_cache` | in-proc | weather/lake **conditions** | no |
| 5 | `core.openai_client._cache` | in-proc | OpenAI **client** objects | no |
| 6 | `core.rating_prior._mean_cache` | in-proc | a single **float** | no |
| 7 | `movies.posters._CACHE` | in-proc | poster **image bytes** | no |
| 8 | `contrib.lhc_parks_rec_calendar._IMAGE_CACHE` | in-proc | flyer **image bytes** | no |
| 9 | `categories.queries._load_category_photos` | `lru_cache` | category-photo **JSON map** | no |
| 10 | `db.models.LlmResponseCache` | **DB table** | chat **LLM responses** (keyed on query+date) | yes |
| 11 | `db.models.ExternalConditionsCache` | **DB table** | weather/gas **source data** | yes |

None of these holds page HTML. The two persistent (DB) caches are LLM responses and
conditions data. **The app page-cache store is empty by nonexistence.**

Decisive consequence: the frozen render has **no `build-sha` meta**, which was added
2026-07-01 (#763) — so it predates that build and has survived ~10 deploys since.
Nothing in-process can do that (a deploy restarts the process and wipes every cache
above), and there is no persistent page store. Therefore the frozen copy is **not the
origin/app** — it is a **Cloudflare edge copy frozen at a PoP** (survives origin
deploys). This is the exact failure documented at #766 ("the 2026-07-07 stale-day-view
was a Cloudflare edge copy frozen at one PoP"), and the bare-vs-`?param` split is the
Cloudflare signature: a "Cache Everything" rule caches the extension-less bare path
while Cloudflare's default cache key bypasses on query string.

**Per the stated criterion — inventory empty AND my curls fresh → the origin/app is
exonerated.** My cold curl (through the same CDN) does not reproduce what the fetch
proxy shows, so **the fetch proxy is unreliable for prod freshness verification**;
prod checks should use a direct cold `curl` + the freshness canary (below), not the
proxy. (Caveat: the proxy may be faithfully hitting a *different*, genuinely-frozen
PoP than LAX — either way the fix below addresses the edge, and the canary widens PoP
coverage over time.)

## 3. Structural fix shipped (kills the class by construction)

Because there is no app page cache to key, the class lives at the CDN edge and in the
few in-process content caches. Both are closed:

- **Edge (the real culprit):** every HTML response now also sends
  `Cloudflare-CDN-Cache-Control: no-store` and `CDN-Cache-Control: no-store`
  (`app/main.py::SecurityHeadersMiddleware`). Cloudflare honors
  `Cloudflare-CDN-Cache-Control` **even under a "Cache Everything" Cache Rule** —
  the precise gap that let a PoP store an HTML copy while the origin said no-store.
  With it, a PoP can no longer STORE an HTML render, so the freeze can't recur.
- **In-process content caches:** the running `build_sha` is now part of the key of
  `_index_cache`, `_sitemap_cache`, and `_map_cache`, so a deploy is a guaranteed
  cache miss (invalidation by construction), not merely a TTL wait.

Not fixable from the app: **pre-existing** frozen PoP entries. They need a one-time
Cloudflare zone purge (`scripts/purge_cdn_cache.py`, needs `CF_PURGE_API_TOKEN` +
`CF_ZONE_ID` — still unset). Casey's action. Going forward the `no-store` CDN header
means nothing new gets stored to purge.

## 4. Canary — bare long-tail subcategory URLs (`scripts/freshness_canary.py`)

Each run now samples 3 random bare `/categories/{dept}/{leaf}` URLs from the live
sitemap (158 available) and freshness-checks each across the full UA matrix
(googlebot / curl / chrome), asserting `build-sha` present **and** == the running app.
Over runs the whole long tail gets covered; a frozen-PoP copy of an older build turns
the canary red. Regression-tested both ways (stale sampled leaf → red; fresh → green).

## 5. Cold-verify — see PR (both named URLs fresh, zero ad CTAs, before/after).
