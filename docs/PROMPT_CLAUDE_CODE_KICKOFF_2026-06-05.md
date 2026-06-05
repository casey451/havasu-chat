# Claude Code Kickoff — Consolidated Rollout (cost fix → typing/security → perf → SEO)

**Created:** 2026-06-04 (Cowork review session) · **For:** a Claude Code session in this repo
**Status:** ready once Casey confirms no other session is active in this checkout

You are executing a consolidated, pre-reviewed plan. Read these first, in order:

1. `CLAUDE.md` (repo root) — non-negotiable guardrails. `main` auto-deploys to prod.
2. `docs/CLAUDE_CODE_IMPLEMENTATION_BRIEF_2026-06-04.md` — typing/security/perf (Tiers 1–3)
3. `docs/CLAUDE_CODE_SEO_BRIEF_2026-06-04.md` — SEO work (gated, see below)

Everything below was re-verified against the live site and code on 2026-06-04 by a
review session. Do not re-audit; do confirm each claim in the file you edit.

---

## Casey decisions — ask in chat before the gated items, then record answers here

| # | Decision | Gates | Status |
|---|---|---|---|
| D1 | Route family survivor (`/category/` singular recommended) | SEO P1.1 and everything after | PENDING |
| D2 | Custom domain purchase | Only the 301 + Search Console steps; P1.0 proceeds without it | PENDING |
| D3 | CSRF approach: admin cookie `SameSite=Strict` (small) vs per-form token (larger) | T1.5 | PENDING |
| D4 | **AggregateRating policy (NEW)** — provider JSON-LD currently marks up Google's ratings (`vm.google_rating` / `google_review_count` in `app/templates/provider_profile.html:40-44`) as our own `AggregateRating`. This violates Google's structured-data guidelines (third-party reviews must not be marked up as self-serving AggregateRating) and risks a manual action. Options: (a) remove the block, (b) keep visible stars but drop the JSON-LD field, (c) keep knowingly. Recommend (b). | SEO P2.3 | PENDING |
| D5 | Review-signal strategy (first-party reviews vs claimed attributes) | SEO Phase 3 | PENDING |

Also remind Casey (his actions, not yours): GitHub branch protection on `main`;
verify `ADMIN_PASSWORD` + distinct `HAVA_SESSION_SECRET` set in Railway (T1.3
follow-up); domain + Search Console + Bing (SEO Phase 0).

## Amendments to the two briefs (from the 2026-06-04 live re-verification)

- **SEO plan's "zero structured data" is outdated.** Provider pages already emit
  `LocalBusiness` JSON-LD via `app/templates/provider_profile.html`. P2.3 is
  therefore a *fix*, not an add: emit `address` as a `PostalAddress` object (it is
  currently a plain string), use the correct `@type` subtype per category
  (Restaurant/Plumber/HVACBusiness/AutoRepair/LodgingBusiness…), fix HTML-entity
  escaping inside the JSON (`&#39;` artifacts), and resolve D4.
- **P1.0 scope additions:** `app/main.py:557` `_base_url()` already reads a
  `BASE_URL` env (so the brief's "unverified" caveat is resolved — the helper
  exists). But (a) `app/api/routes/calendar_feed.py:106` hardcodes the railway
  origin in the iCal PRODID — route it through the helper; (b) ~30 scrapers in
  `app/contrib/` embed the railway URL in User-Agent strings — parametrize in a
  small follow-up commit, low priority. No page type currently emits
  `rel=canonical` except provider pages, which emit `http://` (verified live).
- **T3.2 N+1 confirmed still present** at `app/api/routes/category_pages.py:1156`
  (`build_card_view_model(db, ent.id)` per entity). The `joinedload`s at :743-745
  cover entity relations only. Brief stands as written.
- **Test suite is now ~4,200 tests / 352 files** (brief says 2,827). T2.4
  (pytest-xdist) is more valuable than estimated. Add the ad-hoc `test_diag_*.py`
  probe files to the T3.4 hygiene sweep (verify dead before removing).
- Live-verified today: singular `/category/home-property-services` renders 0
  providers vs 60 on plural; `?page=2` ignored; sitemap = 2,758 URLs, all
  `lastmod=today`, plural family only; homepage nav links legacy plural slugs
  (things-to-do, attractions, services, beauty-care) — the D1 legacy-slug map
  must cover these; events pages have no JSON-LD.

## PR sequence (one branch + PR each; stop after each PR — Casey merges)

**PR 1 — hint-extractor signal gate (do first; zero design work left).**
`git apply patches/0001-hint-extractor-signal-gate.patch` on a branch named
`fix/hint-extractor-signal-gate` (verified to apply clean on `main`@bb0e720).
This is recovered work from another session — review it as if new: run the full
suite + ruff, sanity-check the regex against `prompts/hint_extractor.txt`, then
commit with the patch's own message and PR. It removes a synchronous gpt-4.1-mini
call from every chat turn (~90% of projected LLM spend at 5K DAU, ~1s latency).

**PR 2 — `typing-mypy-bootstrap`:** T1.1 (mypy + CI job) + T1.4 (chat input
max_length). Land mypy first so all later PRs are type-checked.

**PR 3 — `security-hardening`:** T1.3 (fail-closed secrets in prod) + T1.5 (per D3).
Keep auth changes isolated for clean review.

**PR 4 — `perf/category-pages-n-plus-one`:** T3.2. Deliberately pulled ahead of
Tier 2 because all SEO pagination/template work builds on this file.

**PR 5 — `seo/base-url-canonicals`:** SEO P1.0 + P1.3 with the amendments above
(canonical + og:url on all page types, absolute https via `_base_url()`/
`PUBLIC_BASE_URL`, calendar_feed fix). Not gated on D1/D2.

**PR 6+ — after D1 is answered:** SEO P1.1 (route collapse + legacy-slug map,
including the homepage-nav slugs listed above) → P1.2 (home-property-services
empty render) → P1.4–P1.9 batched sensibly → P1.10 (data op, dry-run, Casey-gated)
→ Phase 2 trade pages (start with the 10 home-services trades; gate sitemap
inclusion on a minimum provider count; apply D4 to P2.3).

Tier 2 (T2.1 typed boundaries, T2.2 leak, T2.3 client singleton, T2.4 xdist)
slots in opportunistically between SEO PRs. Note T2.3 touches
`app/chat/hint_extractor.py` — sequence it after PR 1 and preserve the
`patch.object(hint_extractor, "OpenAI", ...)` mock seam the new tests rely on
(an accessor like `get_openai_client()` is fine; update the tests in the same
commit if the seam moves).

## Session-start housekeeping (before PR 1)

1. Confirm with Casey that no other session is active in this checkout.
2. The checkout may be sitting on the merged `fix/admin-contribution-proposed-record`
   branch with a stale local `main`. Update local `main` to origin and branch from it.
3. Delete the stale `0001-admin-render-proposed-record.patch` at repo root (merged
   as PR #133). `git worktree prune` if the stale `hc` worktree metadata persists.
4. Many handoff docs at root/docs are untracked — ask Casey whether to commit them
   (suggested: a single `docs:` commit on the first branch) or leave untracked.

## Definition of done — every PR

Feature branch off up-to-date `main`; `python -m pytest -q` green (PowerShell:
`.venv\Scripts\python.exe -m pytest -q`) and `ruff check .` clean (+ `mypy app`
once PR 2 lands); tests in the same commit as behavior; no prod DB writes, no
railway/secrets; PR description lists what changed, which plan item it closes,
Casey action items, and verification. Stop and ask on judgment calls.
