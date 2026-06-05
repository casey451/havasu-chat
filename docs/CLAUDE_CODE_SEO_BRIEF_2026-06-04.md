# Claude Code Implementation Brief — SEO / Category Ranking

**Created:** 2026-06-04 · **For:** a Claude Code session · **Status:** ready, but gated (see §0)
**Source of record:** `docs/SEO_ASSESSMENT_PLAN_2026-06-04.md` (full assessment + rationale). This brief is the executable code layer only.

This is a parallel workstream to `docs/CLAUDE_CODE_IMPLEMENTATION_BRIEF_2026-06-04.md` (the typing/security/perf rollout). Same guardrails apply. Where the two touch the same files (`category_pages.py` is in both — N+1 perf fix vs. SEO template work), do the **typing/perf PRs first** so the SEO work builds on typed, deduplicated query code.

---

## 0. Guardrails + gating (read before any edit)

**Repo rules (from `CLAUDE.md`, non-negotiable):**
- `main` auto-deploys to prod. **Never push/merge to `main`.** Feature branch → PR → stop. Casey merges.
- Before every commit: `python -m pytest -q` green **and** `ruff check .` clean. (Windows: `.venv\Scripts\python.exe -m pytest -q`.)
- No prod DB writes without dry-run → counts → Casey approval. The duplicate-slug merge (P1.10) is a data op → **Casey-gated**.
- No `railway`/secret/`railway variables` access. Domain attach + env vars are **Casey's** (Phase 0).
- Stop and ask on genuine judgment calls (the route-family decision below is one).

**Two decisions block parts of this work — confirm with Casey before starting the gated items:**
1. **Domain (Phase 0).** Most on-page fixes can proceed *now* if canonical/OG URLs are built from a **configurable base origin** (see P1.3) — then the domain swap is just an env change, no re-work. So: build the base-URL plumbing first, and the rest of Phase 1 is unblocked. Only the actual 301-from-railway and Search Console steps wait on the domain.
2. **Which route family survives (`/category/{slug}` vs `/categories/{slug}`).** Verified both exist: singular in `app/api/routes/category_pages.py:1028`, plural in `app/categories/router.py:356` — and the modules' own docstrings document the split. The plan recommends keeping **singular `/category/`** and 301-ing plural → singular with a legacy-slug map. **This is Casey's call — confirm before P1.1**, because everything (sitemap, nav, breadcrumbs, new subpages) keys off the survivor.

**Note the BASE_URL gap:** the SEO plan says "code already supports a `BASE_URL` env" — grep shows only `AUTH_MAGIC_LINK_BASE_URL` (auth links), **not** a general canonical base. Treat "code supports BASE_URL" as **unverified**: P1.3 likely needs to *add* a `CANONICAL_BASE_URL`/`PUBLIC_BASE_URL` env and a helper, not just set an existing one. Verify how absolute URLs are currently built before assuming.

---

## Phase 1 — Technical fixes (code; ordered by impact)

Each task: confirm the claim in the file before editing; add/adjust tests; keep server-rendered output byte-stable except where the change is the point.

### P1.0 (do first) — Canonical base-URL plumbing + protocol fix
**Why:** Provider `canonical`/`og:url` currently emit `http://` (X-Forwarded-Proto not honored — same class as the prior ED-5 events fix). And every absolute URL must come from one configurable origin so the Phase-0 domain swap is a one-line env change.
**Do:** add a single helper (e.g. `app/seo/urls.py` or extend an existing util) `absolute_url(path) -> str` that builds `https://{PUBLIC_BASE_URL or request host}{path}`, always `https`, honoring `X-Forwarded-Proto`/`X-Forwarded-Host` behind Railway's proxy. Add a `PUBLIC_BASE_URL` env (unset in dev → fall back to request host). Route all canonical/og:url emission through it.
**Files:** find current canonical/og emission in the provider + category templates and their context builders (`app/api/routes/category_pages.py`, `app/categories/router.py`, provider page route/templates, `templates/`). Sitemap + robots are in `app/main.py`.
**Acceptance:** provider/category/home/event pages emit absolute `https` canonical + og:url; with `PUBLIC_BASE_URL` set they use that origin; unit test covers the proto/host logic. Tests green.
**Risk:** Low-Med. Centralizing URL building touches several templates — change the *source* of the URL, not the visible markup.

### P1.1 — Collapse the duplicate route families (GATED on Casey's choice)
**Why:** `/category/{slug}` and `/categories/{slug}` both 200 with divergent content; no canonical resolves it; sitemap lists only plural.
**Do (assuming singular survives):** make `/categories/{slug}` (and `/categories` index, `app/categories/router.py:219`) issue `301` to the `/category/` equivalent, with a legacy-slug map (things-to-do, services, professional, beauty-care, attractions → nearest Tier-1). Update sitemap (`app/main.py`), nav, and breadcrumbs to emit only the survivor. Keep the plural route handler alive solely as a 301 shim.
**Acceptance:** plural URLs 301 to singular; index 301s; no internal link emits the dead family; tests assert the redirects + updated sitemap. Existing tests that hit the plural routes are updated in the same commit.
**Risk:** Med — many tests/templates reference these paths; grep exhaustively first. If the codebase's own docstrings argue the *plural* taxonomy is the canonical Tier-1 one, **surface that to Casey** rather than overriding — the docstrings at `category_pages.py:7-16` and `categories/router.py:13-31` describe the split intentionally.

### P1.2 — Fix `/category/home-property-services` empty render
**Why (verified live):** renders "coming soon" / zero listings though 237 providers exist on the plural variant. Our most winnable vertical serving an empty page.
**Do:** make the singular handler serve the same provider set the plural one does. Likely a query/category-mapping gap in `app/api/routes/category_pages.py` (compare against the working eat-drink path). 
**Acceptance:** the page lists the providers server-side; test asserts non-empty listing for that slug.

### P1.3 — `rel=canonical` on all page types
Roll the P1.0 helper out to home, category, provider, **and** events pages (events currently lack it). Acceptance: every indexable page emits exactly one absolute-https self-canonical; test per page type.

### P1.4 — Real pagination on category pages
**Why (audit M-20):** 27/308 eat-drink listings linked; hard 60-cap; `?page=2` ignored → ~1,500–2,000 providers are sitemap-only orphans.
**Do:** `?page=N` with `LIMIT/OFFSET`, crawlable prev/next links, page number in `<title>`. Coordinate with the perf brief's N+1 fix on this same file — bulk-fetch providers once, paginate the result. 
**Acceptance:** all providers reachable via paginated links; `?page=2` returns page 2; tests cover bounds + title.
**Risk:** Med — overlaps `category_pages.py` perf work; sequence after it.

### P1.5 — Canonicalize faceted URLs
From every `?trade=/?district=/?open=` variant, emit a canonical to the clean category URL — **except** facets promoted to real pages in Phase 2. Acceptance: facet variants canonical to the base category; promoted trades excluded; test the matrix.

### P1.6 — Sitemap upgrade
In `app/main.py`: emit only the surviving route family; real `lastmod` = max provider `updated_at` per category (not `today`); split into a sitemap index (categories / providers / events). Acceptance: sitemap validates, per-section, with real lastmods; test the index structure.

### P1.7 — Visible NAP block on provider pages
Render address as visible text with schema.org `PostalAddress` fields, phone, hours (today the address hides inside the Maps Directions href). Acceptance: NAP visible in server HTML; test asserts address text present.

### P1.8 — Meta-description sanitizer
Strip newlines, sentence-boundary truncate ~155 chars (today: truncated mid-word like "…libations.\n\nTh"). Central helper, applied wherever meta descriptions are built. Acceptance: no raw newlines, no mid-word cut; unit test on edge cases.

### P1.9 — og:image + og tags on all page types
Site-default og:image + provider photo when available; og tags on home/category/event, not just provider. Acceptance: og:image present on each type; test.

### P1.10 — Duplicate provider slugs (M-21) — DATA OP, CASEY-GATED
ZENSHI ×2 etc. Merge + 301. This is a **prod data operation** → dry-run → show counts → Casey approves → apply. Code the merge/301 logic + a `--dry-run`; do **not** run against prod. Acceptance: dry-run report in the PR; redirect logic tested locally.

### P1.11 — Investigate B-04 split-cache (divergent counts between requests)
Diagnose first (it'll cause inconsistent crawls); may tie to the home/category cache layers. If it's a quick fix, include it; if it needs judgment, write up findings and ask. Acceptance: root cause documented; fix only if low-risk.

---

## Phase 2 — Ranking page templates (the actual "rank for every category" work)

Gated on Phase 1 landing (especially the route family + base URL). This is where dedicated pages like `/category/home-property-services/plumbers` get built.

### P2.1 — Subcategory (trade) pages — START WITH 10 HOME-SERVICES TRADES
**Do:** add a sub-route `/category/{parent}/{trade}` (or the survivor equivalent) rendering the providers filtered to that trade, server-side, with its own title/H1/intro/FAQ, added to the sitemap. Build first: plumbers, hvac, electricians, handyman, pool-service, pest-control, roofers, garage-door, landscapers, cleaning (these map to the home-services parent and the most winnable SERPs). The trade taxonomy already exists as facet params — promote those facets to real URLs.
**Acceptance:** each trade page resolves, lists the right providers, is in the sitemap, has unique title/H1; canonical excludes the corresponding facet param (P1.5). Tests per a sample of trades.
**Risk:** Med — new route family + taxonomy mapping; lean on existing facet/trade logic in `category_pages.py`/`app/categories/`.

### P2.2 — Category + subcategory template
Title `{N} Best {Trade} in Lake Havasu City, AZ — Ask Hava` (N = live server-rendered count), H1 mirrors, 40–100 word local intro, listing cards (rating/review/attributes/open-now/photo when available), FAQ block (4–6 true templated Q&As), JSON-LD `BreadcrumbList` + `ItemList`. Acceptance: rendered HTML matches the template spec; JSON-LD validates (test with a schema validator fixture); golden test on a sample page.

### P2.3 — Provider template
JSON-LD `LocalBusiness` with the correct subtype (Restaurant/Plumber/HVACBusiness/AutoRepair/LodgingBusiness…) — name, address, phone, geo, url, openingHours, image; `AggregateRating` **only** when real ratings exist; `BreadcrumbList` JSON-LD matching the visible breadcrumb; visible NAP (P1.7); proximity/same-trade "While you're here" (M-28). Acceptance: valid JSON-LD per provider type; no fabricated ratings; test.

### P2.4 — Event JSON-LD
`Event` (name, startDate, location, image) on event pages — our best freshness play. Acceptance: valid Event schema; test.

### P2.5 — Homepage H1
H1 → "Lake Havasu City's local directory & concierge" (personality to H2); target "lake havasu business directory". Acceptance: H1 changed, visible, tested.

**Note on Phase 2 + Google scaled-content policy:** these templated pages only rank if backed by dense data (Phase 3). Don't ship hundreds of near-empty trade pages — gate publication (and sitemap inclusion) on a minimum provider count per trade so thin pages aren't exposed. Build the gate into P2.1.

---

## Phases 3–5 — mostly NOT code (route to Casey / ops)
- **Phase 3 (data depth):** hours/photos/editorial backfill, a ratings signal, categorization cleanup. Some are scripts (backfills — dry-run/Casey-gated like any data op); the editorial/ratings *strategy* is Casey's decision (§5 of the plan). Don't fabricate ratings in code (P2.3 enforces this).
- **Phase 4 (links/citations):** entirely Casey-driven (Chamber, press, partnerships). One small code piece is possible: the "Listed on Ask Hava" badge/widget — build only if Casey asks.
- **Phase 5 (measurement):** Search Console / Bing / Plausible are external. The monthly rank-check for the 13 benchmark queries *can* later become a scheduled job — propose it once pages are live, don't build speculatively.

---

## Definition of done (per PR)
1. Feature branch off `main`; never on `main`.
2. `pytest -q` green + `ruff check .` clean (+ `mypy app` once the typing brief lands).
3. Tests added/updated with each change; JSON-LD changes include a validation test.
4. No prod DB writes / no railway / no secret access by the agent. Data ops (P1.10, Phase-3 backfills) are dry-run + Casey-gated.
5. PR description: what changed, which plan item it closes, **Casey action items** (domain/Phase 0, route-family confirmation, P1.10 merge approval, ratings strategy), and how verified.
6. Stop and ask on the route-family decision and any judgment call.

## Suggested order
P1.0 (base URL) → confirm route family with Casey → P1.1–P1.9 as one or two PRs → P1.10 separately (data-gated) → Phase 2 starting with the 10 home-services trade pages → data depth (Casey) in parallel. Sequence the `category_pages.py` SEO work **after** the perf brief's N+1 fix on that file.

## References
- `docs/SEO_ASSESSMENT_PLAN_2026-06-04.md` — full assessment, SERP analysis, query→page matrix, Casey decisions.
- `docs/CLAUDE_CODE_IMPLEMENTATION_BRIEF_2026-06-04.md` — the parallel typing/security/perf rollout (do the `category_pages.py` perf fix before P1.4/Phase 2).
- `docs/TECH_DIRECTION_DECISION_2026-06-04.md` — overall direction context.
