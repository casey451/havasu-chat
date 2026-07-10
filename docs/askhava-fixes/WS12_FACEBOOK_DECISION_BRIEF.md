# WS12 — Facebook Connector: Decision Brief for Casey

**Prepared:** 2026-07-09 (WS12 build session).
**Decision owner:** Casey (this is an access + **spend** + ToS call — flagged, not made).
**Companions:** `WS12_CREDENTIAL_CHECKLIST.md` §1, `WS12_CONNECTOR_FINDINGS.md`.

## TL;DR

Facebook is the **highest-yield** coverage source — it closes the two
client-named gaps at once (Altitude's camps/Glow nights, Barley Brothers' happy
hour + live music) — and the **hardest to access**. There is no free, ToS-clean
way to read ~50 pages you don't own. Pick a path with eyes open; the connector
is built and waiting.

**Recommendation:** Do **A** (Meta page tokens) for the handful of pages you have
a relationship with, and if you want full coverage, either kick off **B** (App
Review — the long pole, start early) *or* pay for **D** (a vendor API). Treat
**C** (direct scraping) as a stopgap only. All four paths deliver into the same
review queue, so you can start with A and add coverage later without rework.

## What's already built (so you're not deciding in the dark)

The plumbing is done and **safe to merge today** — it does nothing until you flip
a switch:

1. **Pull connector** — `app/events/scrapers/facebook_pages.py`
   (`FacebookPagesClient`, registry key `facebook`). Carries the seed watchlist,
   the post→event extraction seam, and a gated `discover()` that **returns 0
   rows until an access path is configured** via env. Registered in
   `SOURCE_REGISTRY`, so `scrape_events.py --all` already includes it as a no-op.
2. **Push endpoint (already live)** — `POST /api/ingest/contribution`
   (`app/api/routes/ingest.py`), bearer-token gated by `INGEST_API_TOKEN`. An
   external scraper ("OpenClaw"), a **manual relay**, or a **vendor webhook** can
   POST findings here; they land as `facebook_scrape` **pending** contributions.
3. **Both paths share one review pipeline.** Everything lands as
   `source=facebook_scrape`, which is **not** in the auto-approve registry, so
   every Facebook finding is human-reviewed in `/admin` before publish (WS12 §4
   training wheels). Post→event extraction runs with WS6 confidence gating.

So the **only** thing between "built" and "producing events" is *access* — this
brief.

## The seed watchlist (confirm handles are current + public)

12 pages seeded in `WATCHLIST` (grows toward ~50). Client-named gaps marked ★:

★ Altitude Lake Havasu · ★ Split Finger Athletics · ★ Barley Brothers ·
College Street Brewhouse · Flying X Saloon · Kokomo Beach Club · Lady Lee's ·
Calvary Baptist · Calvary Chapel LHC · Lake Havasu Baseball Academy ·
Grace Arts Live · Havasu 95 Speedway.

## The four access paths

### Option A — Meta Graph API with **Page access tokens** (pages you/owner control)
- **What:** the official API. A Page token reads *that* page's posts/events as clean JSON.
- **Requires:** you are an **admin/editor** of the page (or the owner grants a token), plus a Meta **Developer app** + a long-lived Page token.
- **Coverage:** only pages that opt in. Realistic for pages you have a relationship with (maybe Altitude, Barley Brothers, a church). **Does not scale to 50 third-party pages** — you can't get admin on Kokomo's page.
- **Cost:** **$0** (Meta API is free at this volume).
- **Setup steps:**
  1. Create a Meta Developer account → developers.facebook.com → **Create App** (type "Business").
  2. Add the **Facebook Login** / **Pages API** product.
  3. For each cooperating page, have its admin add your app and grant a **Page access token** with `pages_read_engagement` (+ `pages_read_user_content`).
  4. Exchange for a **long-lived** token (60-day; refresh via a cron).
  5. Set on Railway: `FB_ACCESS_MODE=graph`, `FB_GRAPH_TOKEN=<token>` → the connector activates for those pages.
- **Effort:** Low–Medium. **Best first move.**

### Option B — Meta Graph API with **Page Public Content Access** (read any public page)
- **What:** a special Graph permission to read **any** public Page's content — the only *official* way to cover all 50.
- **Requires:** a Meta app + **Business Verification** + **App Review** where Meta approves the "Page Public Content Access" feature. **Weeks** of lead time; Meta can reject; ongoing compliance.
- **Cost:** **$0** in fees, but real **time + uncertainty** cost (verification docs, review submission, possible rejection).
- **Setup steps:**
  1. Complete **Business Verification** (business.facebook.com — legal entity docs).
  2. In the app, request the **Page Public Content Access** feature; submit a use-case writeup + screencast.
  3. Pass **App Review**; then use an app/system-user token.
  4. Same env wiring as A (`FB_ACCESS_MODE=graph`).
- **Effort:** High, uncertain. **The long pole — start early if you want it.**

### Option C — Direct public scraping (no credentials)
- **What:** fetch each public page and parse posts/events.
- **Reality:** **violates Facebook ToS**; login walls + markup churn + aggressive bot-blocking; risk of IP bans. Brittle.
- **Cost:** ~$0 in fees; high maintenance + legal/ToS risk.
- **Setup:** would run through the existing OpenClaw push path (`INGEST_API_TOKEN`), not this connector.
- **Effort:** fastest to prototype, worst to maintain. **Stopgap only.**

### Option D — Third-party FB data vendor (paid API that already has FB access)
- **What:** a vendor returns a page's posts via API; you push results to `/api/ingest/contribution` or wire the connector's `vendor` mode.
- **Requires:** a paid account + API key. (Bright Data and similar social-data APIs are the usual suspects; check each vendor's own ToS/legality.)
- **Cost (rough, ballpark — verify current pricing):** typically **$0–$50/mo** entry tiers, scaling to **~$500/mo** for heavy volume; many price **per-record / per-1k-requests** (order of **$1–3 per 1k** page-post reads). For ~50 pages polled weekly this is a **low double-digit $/mo** workload, not hundreds.
- **Setup steps:**
  1. Pick a vendor; create an account; get an **API key**.
  2. Either: set `FB_ACCESS_MODE=vendor` + `FB_VENDOR_API_KEY=<key>` and implement the one `discover()` fetch seam against their API; **or** run their fetch off-box and POST results to `/api/ingest/contribution`.
- **Effort:** Low once you accept the spend. **Skips the FB access problem entirely.**

## Recommended sequence

1. **Now (free, high signal):** Option **A** for Altitude + Barley Brothers + 1–2 churches you can reach. Wire `FB_ACCESS_MODE=graph` + token. This alone closes two client-named gaps.
2. **In parallel, choose the scale path:**
   - Want it free and are willing to wait/risk rejection → start **B** (App Review) today; it's the long pole.
   - Want it fast and will pay → **D** (vendor), ~low-double-digit $/mo.
3. **Never rely on C** as the durable path.

## What I need from you to proceed past "built"

- [ ] **The access decision** (A / B / D / mix), and for A: which watchlist pages you can get a token for.
- [ ] If A/B: a **Meta Developer** account (+ **Business** account for B).
- [ ] If D: the **vendor + API key** (and your monthly spend ceiling).
- [ ] Confirm the 12 watchlist handles are current + public (or correct them).

Once any one path's env is set, the connector produces `facebook_scrape` rows
into the review queue on the next scheduler cycle — and the post→event
extraction prompt gets implemented behind that same switch. **No FB scraping
happens, and no spend is incurred, until you choose.**
