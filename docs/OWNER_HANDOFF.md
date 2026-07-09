# Owner handoff — operating Hava (askhava.com)

**Purpose:** everything a new owner needs to run the site from the admin panel +
Stripe alone. The site is built to run itself; this document is what you read when
you take the keys, plus the two owner-only activations (Stripe billing, feedback
email) that are intentionally left dormant until you do them.

**Companion docs:** day-to-day operations live in [`docs/runbook.md`](runbook.md)
(emergencies, daily/weekly checks, SQL). Ship discipline lives in
[`docs/POST_SHIP_CHECKLIST.md`](POST_SHIP_CHECKLIST.md). This file is the handoff
overview and the activation steps; it does not repeat the runbook.

---

## 0. The one rule that protects production

`main` auto-deploys to production on Railway (the deploy runs `alembic upgrade
head`). **Pushing or merging to `main` = a live production deploy.** Work on a
branch, review, then merge deliberately. Prod database changes always go
dry-run → check the counts → then apply. (Full guardrails: `CLAUDE.md`.)

Rollback for a bad deploy: in Railway, redeploy the previous successful
deployment. The theme can be reverted independently with
`THEME_DEFAULT=desert` (see §6).

---

## 1. What runs without you

These are scheduled GitHub Actions (in `.github/workflows/`) that write to the
production database on a cron. You do not start them; they run on `main`.

| Feed | Workflow | Cadence |
|------|----------|---------|
| Events (River Scene) | `river-scene-events.yml` | every other day |
| Events (GoLakeHavasu) | `golakehavasu-events.yml` | every other day |
| Civic meetings | `civic-events.yml` | every other day |
| Aggregator events | `aggregator-events.yml` | every other day |
| Classes / parks-rec | `parks-rec-scrapes.yml` | every other day |
| Business partner load | `golakehavasu-partners.yml` | every other day |
| Gas prices | `gas-prices.yml` | 3×/day |
| Movie showtimes | `star-cinemas-showtimes.yml` | 2×/day |
| Senior Center | `senior-center.yml` | Mondays |

You don't have to babysit these. The freshness monitor below tells you if one
silently breaks.

---

## 2. Staleness monitoring — how you know a feed died

The failure that used to be invisible: a scraper's workflow stays green, the
upstream site is reachable, but a layout change broke the parser and it has
ingested nothing for days — while the page still shows old data labeled "today."
Two guards now catch that automatically:

1. **Daily alert (`data-freshness-check.yml`, 10:00 AM Arizona).** It queries the
   database directly for the freshest row of every feed (events, **gas**,
   **movies**) and **fails the workflow if any feed is older than its budget**.
   A failed GitHub Actions run emails you — that email *is* the page. Scripts:
   `scripts/freshness_check.py` (events) + `scripts/data_freshness_monitor.py`
   (all feeds, incl. the gas/movies feeds whose staleness caused the original
   sitewide date-desync bug).
2. **Admin "Feed freshness" table.** `/admin/overview` ("Dashboard") shows every
   feed with its freshest row, age, and an OK / STALE / MISSING status, plus the
   conditions-cache data sources. A STALE/MISSING row is the same signal the cron
   pages on — you can eyeball it any time.

**If a feed shows STALE / MISSING:**
- Open the feed's workflow in the repo's Actions tab; check the latest run's log.
- Most often the upstream site changed its HTML. The fix is a parser update in
  the scraper (`scripts/*_pull.py` / `app/events/scrapers/`) — a developer task.
- Budgets (how old is "too old") live in `app/monitoring/freshness.py`
  (`FEED_CHECKS`). Gas pages after ~1 day stale; movies after ~2 days; events
  after ~5 days. Adjust there if a feed's cadence changes.

---

## 3. Admin panel — what's where

Log in at **`/admin/login`** with `ADMIN_PASSWORD` (set in Railway env). There are
two surfaces, both behind that password:

- **`/admin`** (legacy ops): the approval queues (events / providers / claims),
  `/admin/overview` (dashboard + the freshness table above + a "Run sync now"
  button), `/admin/analytics`, `/admin/feedback`.
- **`/admin/portal`** (unified dashboard): traffic, search intelligence (top
  queries, query→click flows), **placement performance** (impressions / clicks /
  CTR by slot), user management, ops, and the audit log.

Daily/weekly rhythm (detail in `runbook.md` §2): clear the contribution queue,
skim the feedback queue, glance at the freshness table.

---

## 4. OWNER-ONLY: turn on Stripe billing (P4 is built but dormant)

All the billing code exists (`app/billing/*`: checkout, customer portal, webhook,
refunds, revenue ledger) but is **inert** until you complete the steps below.
Until then, `/billing/*` returns 404 and no Stripe call is ever made
(`app.billing.config.billing_enabled()` is the single gate). An agent never
handles your keys — you set them in Railway.

**One-time setup (~1–2 hours, all yours):**
1. Create a Stripe account at stripe.com; connect your real bank account; enter
   business/tax details (W-9 etc.). *(Owner-only — financial/identity.)*
2. In the Stripe Dashboard, enable the **hosted Customer Portal** (Settings →
   Billing → Customer portal) so merchants can self-manage/cancel — no UI to
   build.
3. Create your products/prices in Stripe **or** rely on the in-app catalog
   (`app/portal/products.py` / `PlacementPrice`) — prices read from config, never
   hardcoded.
4. Add a webhook endpoint in Stripe pointing at
   **`https://askhava.com/billing/webhook`**, subscribed to at least
   `checkout.session.completed`, `customer.subscription.updated`,
   `customer.subscription.deleted`, `invoice.payment_failed`, `invoice.paid`.
   Copy its **signing secret**.
5. Pin `stripe` in `requirements.txt` (a deliberate, version-locked bump verified
   against a Railway build — a developer does this; never float the version).

**Flip it live (Railway → service "Havasu chat" → Variables):**
```
STRIPE_SECRET_KEY        = sk_live_…        (from Stripe → Developers → API keys)
STRIPE_PUBLISHABLE_KEY   = pk_live_…
STRIPE_WEBHOOK_SECRET    = whsec_…          (the endpoint signing secret from step 4)
STRIPE_BILLING_ENABLED   = true             (the master switch)
```
`billing_enabled()` requires **all** of: master flag `true`, secret key set, and
the `stripe` library installed. Any one missing keeps billing fully dormant. The
webhook handler verifies the Stripe signature before processing and is idempotent
on the Stripe event id — safe to receive retries.

**Test before announcing:** start in Stripe **test mode** keys first — run a
merchant through checkout, confirm the placement renders labeled "Sponsored",
then cancel via the Customer Portal and confirm the slot releases. Swap to
`sk_live_…` only once that round-trips.

**Rollback:** set `STRIPE_BILLING_ENABLED=false` (or remove the keys) — billing
goes inert immediately, the rest of the site is unaffected.

---

## 5. OWNER-ONLY: feedback inbox + transactional email (P5 gated)

Feedback is fully built: every submission writes a `Feedback` DB row first (never
lost), appears in `/admin/feedback`, and *then* forwards one notification email.
The forward + magic-link login emails need an email sender you own.

**Receiving (an inbox):** set up a free forwarding alias — e.g. Cloudflare Email
Routing `hello@askhava.com → your Gmail`. Enough to receive. (Upgrade to Google
Workspace only when you want to *reply as* the brand.)

**Sending (Resend):** create a resend.com account, verify your sending domain,
create an API key. Then set in Railway:
```
RESEND_API_KEY        = re_…                       (Resend API key)
RESEND_FROM_ADDRESS   = Hava <noreply@askhava.com> (verified sender)
FEEDBACK_NOTIFY_EMAIL  = you@example.com            (where feedback forwards land)
```
- `RESEND_API_KEY` + `RESEND_FROM_ADDRESS` also power magic-link sign-in emails.
- If `FEEDBACK_NOTIFY_EMAIL` is unset, feedback rows still persist and show in
  admin — only the email forward is skipped (nothing is lost). A Resend send
  failure is logged and never 500s the user's submission.

---

## 6. Theme / rollback levers

- **Theme:** prod default is Lake (`THEME_DEFAULT=lake`). Instant rollback:
  set `THEME_DEFAULT=desert` in Railway.
- **Bad deploy:** redeploy the prior successful deployment in Railway.
- **Diagnostics / kill-switches:** see `runbook.md` §2.5 and §3.4 (environment
  variables).

---

## 7. Known low-priority items (not blocking; for a future developer pass)

From the P6 security/perf review — none are exploitable today, recorded so they
aren't lost (also in `docs/BACKLOG.md`):
- **Stripe redirect URLs** (`app/billing/router.py`) are built from
  `request.base_url` (Host header). Behind Railway's fixed host this is safe;
  prefer building them from the configured `BASE_URL` if billing ever moves hosts.
- **Admin audit actor** is the static string `"admin"` (single shared password).
  If more than one person operates the panel, switch admin auth to per-user
  `role=="admin"` (already supported) so the audit log names the operator.
- **Feedback rate limit** is per-process and IP-based — adequate for a low-value
  endpoint; move to the shared limiter if abuse appears.

---

## 8. The short version

1. You have `/admin` + `/admin/portal` (password in Railway). Watch the **Feed
   freshness** table; the daily cron emails you if a feed dies.
2. Scrapers run themselves on cron. A STALE feed = a parser needs a developer.
3. To take money: do the Stripe account/bank/tax setup, set the four `STRIPE_*`
   Railway vars, test in test mode, then go live (§4).
4. To get feedback/login email: set the three Resend/feedback vars (§5).
5. Never push to `main` casually (it deploys to prod); prod DB ops are dry-run
   first. Rollback = Railway redeploy, or `THEME_DEFAULT=desert`.
