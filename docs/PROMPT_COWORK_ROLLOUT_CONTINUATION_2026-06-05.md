# Cowork Continuation — Tech-Direction Rollout (after Claude Code PRs 1–6)

**Created:** 2026-06-05 by the Claude Code session executing
`docs/PROMPT_CLAUDE_CODE_KICKOFF_2026-06-05.md`. This hands off (a) the
human/infra actions only Casey can do, (b) one strategic decision that needs
Casey, and (c) the remaining build queue.

---

## 1. What's done — 6 stacked PRs (all full-suite green, ruff + mypy clean)

Built in **isolated git worktrees** (the main checkout had another active
session). Each stacked on the previous so dependency order == merge order.

| PR | Branch → base | Contents |
|----|---------------|----------|
| [#138](https://github.com/casey451/havasu-chat/pull/138) | `fix/hint-extractor-signal-gate` → main | PR1: per-turn hint-extractor signal gate (cost/latency); `HINT_GATE=off` kill switch |
| [#140](https://github.com/casey451/havasu-chat/pull/140) | `typing-mypy-bootstrap` → main | T1.1 mypy gate + CI job; T1.4 chat `max_length=2000` |
| [#142](https://github.com/casey451/havasu-chat/pull/142) | `security-hardening` → #140 | T1.3 fail-closed auth secrets in prod; T1.5 admin cookie `SameSite=Strict` |
| [#143](https://github.com/casey451/havasu-chat/pull/143) | `perf/category-pages-n-plus-one` → #142 | T3.2 batched card view-models (kills the category N+1) |
| [#146](https://github.com/casey451/havasu-chat/pull/146) | `seo/base-url-canonicals` → #143 | P1.0 + P1.3 canonical/og plumbing (`app/seo/urls.py`, https fix) |
| [#147](https://github.com/casey451/havasu-chat/pull/147) | `fix/session-last-seen-leak` → #146 | T2.2 bound the last-seen debounce map (memory leak) |

### Merge sequence (CASEY ONLY — `main` auto-deploys to prod)
1. **#138** — independent, merge any time.
2. Then **#140 → #142 → #143 → #146 → #147** in that exact order (each targets
   the previous branch; GitHub will retarget each to `main` as its parent merges).

### Casey infra gates (do these around the merges; Claude/Cowork cannot)
- **Before merging #142:** verify in Railway that `ADMIN_PASSWORD` **and** a
  *distinct, strong* `HAVA_SESSION_SECRET` are both set. #142 makes the app
  **fail closed** if they're unset/`changeme` in prod — that's intended, but you
  don't want a prod outage on deploy. If `HAVA_SESSION_SECRET` was ever unset,
  existing sessions were signed with the admin password → rotate/invalidate.
- **T1.2 branch protection** (GitHub setting): require a PR + the lint/test/
  typecheck checks, block direct pushes to `main`. The single biggest safety rail
  for agent sessions.
- **D2 domain:** when a custom domain is attached, set `BASE_URL` in Railway —
  the canonical/og/sitemap/iCal plumbing (#146) then points at it with no code
  change. Then do the 301-from-railway + Search Console/Bing steps.

---

## 2. DECISION NEEDED — D1 route family (was "singular", evidence says "plural")

Casey answered D1 = keep singular `/category/`. **But the live code says the
opposite is the de-facto canonical**, discovered while building #146:

- **Plural `/categories/` is what everything links to and renders:** the
  homepage (`home_sandstone.html` → `/categories/eat-drink`,
  `/on-the-water`, `/things-to-do`), `events_sandstone.html`, `categories_index`,
  and all of `app/home/queries_c.py` / `sandstone.py` generate `/categories/{…}`.
  The sitemap is plural-only. Plural renders the **new Sandstone** template
  (`category_sandstone.html`).
- **Singular `/category/` is an orphan:** rendered by the **old Lake Light**
  template (`category_landing.html`), linked only by `app/home/browse_tiles.py`
  — which is itself on the **dead-code removal list** (T3.4). It also has the
  P1.2 empty-render bug.

**Recommendation:** flip D1 to **keep plural `/categories/` (Sandstone) as
canonical**, and 301 the singular orphan → plural (plus the legacy-slug map:
things-to-do, services, professional, beauty-care, attractions). This avoids
migrating all live infra + the Sandstone design onto the orphan slug for a
marginal singular-vs-plural SEO gain.
**If Casey still wants singular**, the route-collapse PR must additionally
repoint the singular route to render the Sandstone template and port the plural
route's context-building — a much larger, riskier change. **Confirm with Casey
before building P1.1.** Everything downstream (sitemap, nav, breadcrumbs, trade
pages) keys off this.

---

## 3. Remaining build queue (Cowork or a fresh Claude Code session can do these)

Branch each off `main` **after the stack above merges** (so they're built on the
mypy gate + perf fix). Same guardrails: feature branch, `pytest -q` + `ruff` +
`mypy app` green, tests with behavior, never touch `main`.

**Gated on the D1 answer (section 2):**
- **P1.1** route collapse + legacy-slug map (301s), sitemap/nav/breadcrumb to the
  survivor only.
- **P1.2** empty `/category/home-property-services` render — moot if we 301 the
  singular orphan; otherwise fix the category-mapping gap.
- **P1.4** real pagination (`?page=N`, crawlable prev/next, page in `<title>`) —
  build on the batched provider fetch from #143.
- **P1.5** canonicalize faceted URLs (already half-done: `canonical_url` drops the
  query string in #146 — verify it covers the survivor's template).

**D1-independent (can start now after the stack merges):**
- **P1.6** sitemap upgrade (real `lastmod`, sitemap index split).
- **P1.7** visible NAP block on provider pages (schema.org PostalAddress).
- **P1.8** meta-description sanitizer (strip newlines, sentence-boundary truncate).
- **P1.9** og:image + og tags on all page types (base already has og:url from #146).
- **Phase 2** trade pages (10 home-services trades) + JSON-LD; gate sitemap
  inclusion on a min provider count. Apply **D4** to P2.3 (recommend: keep visible
  stars, drop the self-serving `AggregateRating` JSON-LD field — needs Casey's D4).

**Tier 2 / 3 (typing/perf/hygiene):**
- **T2.1** TypedDicts for `component_builders.py` shapes + `SessionState`; then
  enable strict mypy on those modules (remove from the `ignore_errors` list in
  `pyproject.toml`). Byte-stable output — lean on the disclosure golden test.
- **T2.3** OpenAI client singleton. **Depends on PR1 (#138)** — it touches
  `app/chat/hint_extractor.py` and must preserve the
  `patch.object(hint_extractor, "OpenAI", …)` mock seam #138's tests rely on
  (an accessor like `get_openai_client()` is fine; update those tests in the same
  commit). Base it on #138 + the mypy gate.
- **T2.4** pytest-xdist — RISKY (test isolation: the SQLite test DB + cleanup
  fixtures may collide under `-n auto`). Kickoff says **stop and report if flaky**,
  don't ship flaky parallelism.
- **T3.1** O(N) dedup in `app/events/dedup.py` / `ingest_reconciler.py` — add an
  exact-normalized-name dict lookup before the fuzzy fallback.
- **T3.3** composite indexes — alembic migration, **prod schema change → Casey
  dry-run/approve/deploy gate**. Don't apply.
- **T3.4** dead-code/hygiene sweep (grep-verify each before removing):
  `program_search.py`, `core/dedupe.py`, `events/view_model.py`,
  `home/browse_tiles.py` (+ its test), the `test_diag_*.py` probes, unused deps
  (python-jose/ecdsa/rsa). **Ask Casey** before removing `contrib/lhcaz_aquatic.py`.

**Data ops (CASEY-GATED — dry-run → counts → approve → apply):**
- **P1.10** duplicate provider slugs (ZENSHI ×2 etc.) — merge + 301; code the
  `--dry-run`, do **not** run against prod.

**Still-pending decisions:** D2 (domain), D4 (AggregateRating — recommend drop the
JSON-LD field), D5 (review-signal strategy).

---

## 4. Housekeeping debt (left untouched on purpose)
- Stale `.git/config.lock` in the main checkout (blocks `git config` writes for
  both sessions) and a stale locked `/tmp/hc` worktree — **clean only once the
  other session in the main checkout is confirmed stopped.**
- The ~35 untracked handoff docs at repo root/`docs/` — Casey wanted them in one
  `docs:` commit, but they sit next to another session's modified tracked files in
  the shared checkout, so committing them was deferred for the same reason.
- Local-only helpers to leave/remove per the Wave-1 notes: `pull_prod_env.ps1`
  (do not commit), `scripts/oneoff_assign_primary_2026_06_04.py` (safe to delete).
