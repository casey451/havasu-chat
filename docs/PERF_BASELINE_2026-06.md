# Performance baseline — 2026-06 (MEASURE-1)

First template-level performance capture for Ask Hava (the QA audits never
recorded one). Per the UX/conversion research report's measurement plan: run the
same core templates every time, treat them as separate products, and track by
template — not a sitewide average.

## How this was captured

- **When:** 2026-06-11, against live `askhava.com` (production).
- **How:** Chrome (desktop viewport 1366×900), in-page `performance` API +
  `PerformanceObserver`. DOM node count = `document.querySelectorAll('*').length`;
  timings from the Navigation Timing entry; transfer from Resource Timing.
- **Caveats (read before trusting a cell):**
  - These are **lab, single-run** numbers from one machine/network — directional, not field truth.
  - `transferKiB` is **cache-affected** (warm cache → many resources report 0 transfer); treat as a floor, not the real payload. Re-run cold (DevTools "Disable cache") for a true figure.
  - **LCP / INP / CLS are not in this table.** Lab LCP capture via buffered `PerformanceObserver` returned empty here, and INP requires real interaction. These are exactly the Core Web Vitals the report says to get from **field data** — pull them from PageSpeed Insights / CrUX (URLs below), not lab.

## Thresholds (from the report)

| Metric | Good | Warn | Fail |
|---|---|---|---|
| DOM nodes | < 800 | ~800 | ~1,400 |
| DOM depth | < 32 | — | — |
| LCP (p75, field) | ≤ 2.5s | — | > 4.0s |
| INP (p75, field) | ≤ 200ms | — | > 500ms |
| CLS (p75, field) | ≤ 0.1 | — | > 0.25 |

## Baseline (desktop, 2026-06-11, live prod)

| Template | URL | DOM nodes | DOM depth | TTFB (ms) | DOMContentLoaded (ms) | Load (ms) | Resources | Transfer (KiB, cached) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Home | `/home` | 662 | 10 | 421 | 443 | 576 | 5 | 8 |
| Restaurants leaf | `/categories/eat-and-drink/restaurants` | **1,877** ⚠️ | 10 | 1,503 | 1,527 | 1,705 | 118 | 20 |
| Provider | `/provider/thomas-dermatology` | 267 | 10 | 198 | 210 | 452 | 11 | 6 |
| Events | `/events-ui` | 392 | 11 | 117 | 131 | 155 | 7 | 5 |
| Map | `/map` | 187 | 11 | 71 | 383 | 395 | 15 | 4 |

LCP / INP / CLS columns intentionally omitted — capture via PSI field data.

## Findings

1. **Restaurants leaf is the one real problem: 1,877 DOM nodes** — past the
   ~1,400 Lighthouse *error* line and more than 2× the ~800 *warn* line. Its
   TTFB (1.5s) is also the worst of the set (server-rendering 160 cards + the
   leaf joins). **This is precisely what UX-2's pagination addresses:** at
   60 cards/page, page 1 should drop to roughly **~750 nodes** (under the warn
   threshold) and TTFB should fall once fewer cards are built per request.
   → **Re-measure this template after the UX-2 PR deploys** and record the delta here.
2. **Every other template is healthy** on DOM size (187–662 nodes) and depth
   (≤ 11, far under the 32 warn). Home, Events, Provider, and Map are fast on
   first byte and load.
3. **Map** reports a small static DOM (187) because pins/tiles hydrate via JS
   after load; its interactive cost isn't captured here — worth a dedicated
   INP/main-thread look in a future pass.

## To complete the field-data picture (Casey / next pass)

Run PageSpeed Insights (mobile + desktop) on each template and paste LCP/INP/CLS
(p75) into a field-data table:

- https://pagespeed.web.dev/analysis?url=https://askhava.com/home
- https://pagespeed.web.dev/analysis?url=https://askhava.com/categories/eat-and-drink/restaurants
- https://pagespeed.web.dev/analysis?url=https://askhava.com/provider/thomas-dermatology
- https://pagespeed.web.dev/analysis?url=https://askhava.com/events-ui
- https://pagespeed.web.dev/analysis?url=https://askhava.com/map

PSI may show no page-level CrUX data if traffic is thin — that's expected for a
new hyperlocal site; origin-level field data and lab Lighthouse fill the gap
until RUM (web-vitals → Plausible/GA4 by template) is wired (the report's
long-term item).
