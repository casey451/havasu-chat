# Ask Hava re-audit punch list — 2026-07-08

Findings from Casey's re-audit (verified live that night). This doc tracks the
disposition of each item: what was actually wrong, what shipped, and what is
gated on Casey (prod data writes, Cloudflare, backlog).

Live evidence was gathered with a cold, cookieless Googlebot-UA fetch against
`https://askhava.com` (per the "verified live = cold fetch" rule). Build in
production at audit time: `build_sha = 1db980b6057e` (matches `main` #788).

| # | Item | Disposition | Branch / PR |
|---|------|-------------|-------------|
| 1 | `/calendar?cal=` stale renders | Not reproducing live; ship canary coverage | `fix/calendar-cal-canary` |
| 2 | Styled 404 for `/provider/` | **Already live** — no change needed | — (verified) |
| 3 | Gas M12 (Cheapest-today + expander) | Ship UI change | `fix/gas-m12-dedupe` |
| 4 | Homepage "Local news" = Local only | Ship classifier + homepage gate | `fix/news-homepage-local-only` |
| 5 | GLH event-venue lint + Big Fish routing | Ship lint/routing (code); re-venue rows gated | `fix/glh-venue-lint` |
| 6 | 911 Mobile Mechanic ×2 dedup; search-rank v2 | Dedup gated (dry-run first); rank v2 = backlog | data-op + backlog |

---

## 1 — `/calendar?cal=YYYY-MM` stale renders

**Reported:** July-1-vintage renders with no `build-sha` meta; date-partition or
short-TTL the `?cal=` cache keys and add a `?cal=` variant to the canary matrix.

**Findings (code):** The calendar page has **no in-process cache**. HTML responses
are sent `Cache-Control: no-store, no-cache, max-age=0, must-revalidate` by the
security-headers middleware (`app/main.py`), and `build-sha` + `render-ts` meta are
inherited by every page (incl. `?cal=` variants) via `base_redesign.html`. So there
is no app-level cache key to partition — a stale `?cal=` render can only come from a
**Cloudflare edge PoP** that froze a copy of a pre-#763 build (which predated the
`build-sha` meta, hence "no build-sha meta").

**Live check (cold):** `/calendar`, `/calendar?cal=2026-07`, `/calendar?cal=2026-06`
all serve `build-sha=1db980b6057e` (matches `/health`) with a fresh `render-ts`. Not
reproducing now — the frozen PoP has since revalidated.

**Shipped:** add a `?cal=` (current-month) variant to the freshness-canary matrix
(`scripts/freshness_canary.py`) so a future frozen month-variant is caught
post-deploy — today the canary only checks bare `/calendar`.

**Casey-owned:** the durable fix if it recurs is a Cloudflare cache-key / cache-rule
that includes the query string (or honours `no-store`). No CF creds in-repo.

## 2 — Styled 404 for `/provider/`

**Reported:** if a nonexistent `/provider/` URL has no styled 404 body, ship WS2.3.

**Disposition: already live — no change.** The WS2.3 template `not_found_lake.html`
landed (v4.6 PR-1), is wired via the `StarletteHTTPException` handler in
`app/main.py`, and is covered by `tests/test_lake_errors.py`.

**Live check (cold, Googlebot UA):**
`GET /provider/this-does-not-exist-xyz-999` → **HTTP 404**, 7,284-byte styled body
containing `class="errx"`, `<div class="big num">404`, "Can't find that", and
`build-sha=1db980b6057e` (matches `/health`). Bare `/provider/` → 404 styled too.
`curl` sends `Accept: */*`, so the handler renders HTML (JSON only for `/api/*` or
an explicit `application/json` Accept).

## 3 — Gas page M12 (never implemented)

**Reported:** remove the "Cheapest today" block (duplicates the sorted table) and
collapse the per-page gas expander to the header chip site-wide.

**Shipped:** removed the `Cheapest today` card from `gas_prices_lake.html`; removed
the `#gasPanel` expander from `base_redesign.html` and made the header gas chip a
link to `/gas` instead of a panel toggle. See PR for the JS cleanup.

## 4 — Homepage "Local news" = Local tab only

**Reported:** module showed NYC wire + opinion columns.

**Findings (live):** the 3-slot homepage module showed exactly three non-local items:
`/opinion/dave-eaton-world-cup...` (Opinion), and two bare-URL national wire stories
(`/unstable-nyc-building...`, `/half-of-americans...ten-commandments...`) that
inherited the **Local catch-all** because their News-Herald URLs carry no
`/nation`, `/opinion`, `/lifestyle` path marker.

**Shipped (`app/news/sections.py`, `app/news/store.py`):**
1. `NON_LOCAL_SECTIONS` now also drops `Opinion` (homepage only; `/news` keeps its
   Opinion tab).
2. A homepage-only local gate: a catch-all `Local` item from a syndication-prone
   source (News-Herald wire) must carry a Havasu-proper signal, a `/news/local/`
   path, or an immediate-region label to reach `/home`. Trusted-local sources
   (City Hall / River Scene / Sheriff) always pass. `/news` is unaffected.

**Note / reversible knob:** the gate is precision-first, so generic statewide
Arizona items without a Havasu token are also dropped from the front page (they
remain on the `/news` Local tab). Widen `_LOCAL_SIGNAL_RE` if Casey wants statewide.

## 5 — GLH event-venue lint + Big Fish routing

**Reported:** "Red, White and Blue Bunco Party" has venue "Go Lake Havasu Visitor
Center" but its description names Mudshark Public House — apply the landmark-venue
check to GLH-sourced events. Also route "Big Fish Little Fish" to kids/swim, not
Around Town.

**Shipped (code):** landmark/placeholder-venue lint for events + GLH scraper
description-fallback for venue; Big Fish Little Fish name/venue → aquatic/kids
routing. (see PR)

**Casey-gated (data):** re-venue the existing Bunco row to Mudshark and re-route the
existing Big Fish rows — dry-run → counts → approve → apply (reversible undo CSV).

## 6 — 911 Mobile Mechanic dedup + search ranking v2

**911 Mobile Mechanic ×2:** two catalog rows for the same provider — queue through
the dedup reconciler. **Casey-gated:** dry-run → counts → approve → apply.

**Search ranking v2 (backlog):** weight name/tag matches + review count in the
provider search ranker. Logged as a backlog item; not started.

---

## Cosmetics (batch later — per Casey)

- FAQ `###` markdown artifact rendering literally.
- Dora `/deals` link.
- `/events-ui` route rename.
- Canonical `advertise` URL.
