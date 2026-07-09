# Phase 0 — A–G stale-deploy reconciliation (verify note)

**Date:** 2026-06-23 · **Method:** each live symptom from `FIX_SPEC_2026-06-23.md` traced into
the **current code on disk** (read-only). No code changed in Phase 0.

**Conclusion:** all 7 rows (A–G) are **already fixed in `main`**. Every live symptom in the
2026-06-23 audit is explained by prod running an **old deploy**. The single fix for the A–G
cluster is **deploy `main` and re-verify** — there is no code to change for these rows.

> **Action for Casey:** deploy `main` to prod, then re-crawl A–G to tick them off live. CC cannot
> push/deploy `main` (CLAUDE.md gate). Anything that still reproduces post-deploy becomes a real bug
> and gets promoted into the matching phase.

| Row | Live symptom | Status in code | Evidence (file:line) |
|---|---|---|---|
| A | Pages show a stale "today" date | **Fixed** — every route computes the date fresh per request | `app/core/timezone.py:11-13` `now_lake_havasu()`; called at `app/home/router.py:612`, `app/categories/router.py:310`, `app/api/routes/gas.py:61`, `app/movies/router.py:88` |
| B | Home gas chip ≠ `/gas` lowest price | **Fixed** — home chip reads the same precomputed `data["cheapest"]` | `app/home/router.py:565-588` (chip at :577); pinned by `tests/test_home_gas_parity.py` |
| C | `/portal/advertise` blank page | **Fixed** — route removed; `/advertise` 301 → `/sponsor` | `app/main.py:1369-1374`; no `/portal/advertise` in `app/portal/router.py` |
| D | "Advertise" points to 3 URLs | **Fixed** — public CTAs → `/sponsor`; `/portal/placements` is the login-gated dashboard | `app/templates/_partials/site_footer.html:35,42`; `app/templates/sponsor_landing.html:28,31` |
| E | `havasuchat.com` in Terms + footers | **Fixed** — all user-facing copy uses `askhava.com` | `docs/tos.md`; `app/templates/help.html:27`, `contact.html:12`, `sponsor_landing.html:31`. Only non-user-facing use left = `DEAD_EVENT_LINK_HOSTS` at `app/events/description_clean.py:194` (a link-reject filter; never rendered) |
| F | Café slug `caf-s-and-coffee` | **Fixed** — unicode-aware slugify + alias + migration | `app/utils/slug.py:18-36` (NFKD); `app/categories/router.py:153-156` (`LEAF_SLUG_ALIASES`); `alembic/versions/c7e3a9d1f5b8_fix_cafes_leaf_slug.py` |
| G | Gas "Updated >6h ago" misleading | **Fixed** — renders absolute timestamp via `_format_fetched_at()` | `app/api/routes/gas.py:76-84`; `app/templates/gas_prices.html:25`; `app/conditions/staleness.py:24` |

**Broad grep:** zero user-facing `havasuchat.com` in `templates/` or `docs/tos.md`. The only repo
occurrence is the functional `DEAD_EVENT_LINK_HOSTS` filter (non-user-facing) — correct to keep.

**No PR for Phase 0** (all clear). This note is carried in the Phase 1 PR branch for the record.
