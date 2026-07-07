# WS3 — Advertiser funnel & rate card (findings + changes)

**Date:** 2026-07-06 · **Branch:** `fix/ws3-advertise` (off `main`) · **No merge.**

Same discipline as WS1/WS2: verify each spec premise against live prod + repo before editing.

## What the audit claimed vs. what's actually true

| Audit / spec §3 premise | Reality (verified 2026-07-06) |
|---|---|
| `/sponsor` shows "4 products, **NO prices**" | **Stale.** `/sponsor` is a public, indexable rate card with 3 self-serve products (Category top spot, Category page ad, Home rotating spot) and **real prices** ($149 / $99 / $199 live) from the admin price book, plus honesty framing ("no dark patterns", "one public rate card"). Viewable **without an account**. |
| "See the rate card" → `/portal/advertise` = **BLANK** | `/portal/advertise` is **unregistered** → styled 404. Nothing user-facing links to it. The rate card is `/sponsor`. |
| Footers → `/portal/placements` = **login wall** | True, and correct: that's the merchant **dashboard** (manage placements), legitimately login-gated — not the rate card. |
| Category "Claim this category" (paid) collides with free "Claim" | **True — fixed here.** |

So B3's headline ("blank rate card, no prices") **does not reproduce**. The real, in-scope gaps were smaller.

## Changes in this PR (safe, non-outward, no keys)

1. **Terminology split (WS3.3).** Paid category-placement CTAs renamed **"Claim this category" → "Sponsor this category"** (`category_department_lake.html`, `category_trade_lake.html`); both already link to `/sponsor`. The **free** listing-ownership flow keeps the "Claim" verb ("Claim this listing", `/portal/claim`, provider pages). Test updated in `tests/test_leaf_pages.py`.
2. **Homepage empty-ad placeholder → house promo (WS3.4 / P3).** The unsold marquee was a consumer-facing empty ad slot ("Ad space · Available", "Your logo here", paid "Claim this spot"). It now promotes the **free listing claim** (`/portal/claim`) — useful to every local business — with a small, honest **"Advertise on Ask Hava →"** link to `/sponsor` beneath it. Kept `.feature-marquee` (ad-blocker-safe per house-ad rule). New `.feature-marquee-alt` style. Verified in the browser preview (house promo + right-aligned advertise link; hrefs `/portal/claim` + `/sponsor`; no console errors).
3. **Tests:** `tests/test_ws3_advertise_funnel.py` — home marquee is a house promo (not an empty slot); `/sponsor` is a public priced rate card reachable without login; `/advertise` reaches it in one hop.

## Deliberately NOT done (Casey-gated / out of scope)

- **Self-serve Stripe checkout in ≤3 clicks (WS3 acceptance).** The buy path (`/portal/placements/new`) is **login-gated**, and login/auth is currently **hidden** ("auth isn't in use yet") and Stripe billing is **dormant** (404 until `STRIPE_BILLING_ENABLED` + keys). Completing a real (test-mode) payment needs Casey to (a) enable the auth entry points and (b) set Stripe keys — key handling + a monetization go-live decision. The funnel is wired correctly up to that gate.
- **Canonicalization flip `/advertise` ⇄ `/sponsor` (WS3.1).** Spec wants `/advertise` to be the canonical page and 301 `/sponsor` → it. **Kept `/sponsor` canonical** instead: it already ranks (indexable), `/advertise` already 301s to it (so every "advertise" entry reaches the rate card in one hop), and flipping would migrate SEO for no functional gain **and** would break the WS1 freshness canary's URL classification. If Casey wants the flip, it should land together with a canary update. Substance of WS3.1 (every ad CTA reaches one public rate card; no blank/dead ends) is met.
- **Actual price numbers.** Already set in the admin price book ($149/$99/$199 live); pricing is a business decision, untouched here.

## Gate
ruff clean · mypy app clean · pytest (full) green. Browser-preview verified.
