# Claude Code Implementation Brief — Tech-Direction Rollout

**Created:** 2026-06-04 · **For:** a Claude Code session working in this repo · **Status:** ready to execute

This is a self-contained work order. It distills four read-only audits into an ordered, verifiable implementation plan. You do not need to re-run the audits — but you should confirm each claim in the file you're editing before changing it. The full reasoning lives in the companion docs (see References); this brief is the executable layer.

---

## 0. Read this first — repo guardrails (non-negotiable)

These come from `CLAUDE.md` and override default behavior:

- **`main` auto-deploys to production on Railway** (predeploy runs `alembic upgrade head`). Pushing/merging to `main` = a live prod deploy. **Never push or merge to `main`.** Work on a feature branch off `main`; open a PR and stop. Casey is the merge gate.
- **Before every commit:** `python -m pytest -q` green **and** `ruff check .` clean. On Windows/PowerShell, bare `pytest` may not resolve — use `.venv\Scripts\python.exe -m pytest -q`.
- **No production DB writes** without Casey's explicit approval: dry-run → show counts → wait for approval → apply. The index migration in Tier 3 below touches schema and therefore needs this gate.
- **No `railway` commands, no reading/printing secrets or `railway variables`.** Some Tier-1 items require confirming env vars are set in prod — that confirmation is **Casey's to do**, not yours. Flag it; don't attempt it.
- **No destructive git** (force-push, history rewrite, `reset --hard` dropping unpushed commits).
- **One session per working directory.** If another session may be active here, confirm it's stopped before doing git work. For parallelism use a separate `git worktree`, never the same checkout.
- **On a genuine judgment call, STOP and ask Casey** — don't guess.

Suggested branch naming: one feature branch per Tier (e.g. `typing-mypy-bootstrap`, `security-hardening`, `leak-fixes`), each its own PR, so Casey can review and merge independently.

### Environment facts you'll rely on
- Python **3.11** (ruff `target-version = "py311"`, CI uses 3.11).
- Lint: `ruff==0.15.12` (in `dev-requirements.txt`), config in `pyproject.toml`, currently `select = ["F", "I", "W", "E402"]`, `line-length = 100`.
- Tests: `pytest.ini` sets `testpaths = tests`, one marker `integration`. CI runs `python -m pytest -q -m "not integration"` with `DATABASE_URL=sqlite:///./test.db` and placeholder API keys. **2,827 tests, single-process, ~minutes.**
- CI: `.github/workflows/ci.yml` has two jobs (lint, test) on PR + push to main. No type-check job, no branch protection.

---

## 1. The goal and the decision (why we're doing this)

Casey explored rewriting in Rust to improve agent-driven development, security, memory safety, and speed. Four audits concluded: **adopt a "typed Python core," do not rewrite in Rust.** Rust's one categorical advantage (memory-corruption safety) is moot in a memory-safe language, and every real finding (security gaps, the one memory leak, the speed hot spots) is language-agnostic and cheaply fixable in Python. The highest-leverage change for safe future agent edits is **static type checking**, which the repo has never had despite being 76% annotated.

So this brief implements, in priority order: **(Tier 1)** mypy + CI gate + the top security fixes; **(Tier 2)** typed payload boundaries + the memory-leak fixes + faster tests; **(Tier 3)** the performance fixes + hygiene. Rust is explicitly out of scope except as an optional future PyO3 crate (not in this brief).

---

## TIER 1 — Highest ROI, low risk (do first)

### T1.1 — Turn on mypy incrementally
**Why:** No `mypy`/`pyright` config exists anywhere (verified). The code is already ~76% return-annotated (1,430/1,884 defs) and `app/db/models.py` uses 574 typed `Mapped[]` columns, so adoption is cheap. A type checker catches the #1 agent-bug class (wrong dict/payload shapes) before runtime.

**Do:**
1. Add mypy to `dev-requirements.txt` (pin a current version, e.g. `mypy==1.18.*` — check latest stable at install time) and `sqlalchemy[mypy]` is **not** needed as a separate pin since SQLAlchemy 2.0 ships PEP-561 types; add the plugin instead.
2. Add to `pyproject.toml`:
   ```toml
   [tool.mypy]
   python_version = "3.11"
   plugins = ["pydantic.mypy", "sqlalchemy.ext.mypy.plugin"]
   warn_unused_ignores = true
   warn_redundant_casts = true
   # Start permissive tree-wide so the gate is green on day one:
   ignore_missing_imports = true
   check_untyped_defs = false
   disallow_untyped_defs = false
   exclude = '(^|/)(alembic/versions|scripts/output|relay|outputs|\.venv)'

   # Then ratchet strictness module-by-module. Begin with the highest-value,
   # most-typed packages:
   [[tool.mypy.overrides]]
   module = ["app.db.*", "app.chat.tier2_schema", "app.schemas.*"]
   disallow_untyped_defs = true
   check_untyped_defs = true
   ```
3. Run `mypy app` locally. Fix only what's needed to make the **permissive** baseline pass (real errors, not the strict-mode noise). If a module is hopeless, add a targeted `[[tool.mypy.overrides]]` with `ignore_errors = true` and a `# TODO: type` note rather than weakening the global config.
4. Add a third CI job to `.github/workflows/ci.yml` mirroring the lint job structure:
   ```yaml
   typecheck:
     name: Type check (mypy)
     runs-on: ubuntu-22.04
     steps:
       - uses: actions/checkout@v4
       - uses: actions/setup-python@v5
         with:
           python-version: '3.11'
           cache: 'pip'
       - name: Install deps
         run: |
           python -m pip install --upgrade pip
           python -m pip install -r requirements.txt -r dev-requirements.txt
       - name: mypy
         run: python -m mypy app
   ```
   (mypy needs the real deps installed to resolve types — install `requirements.txt`, unlike the lint job.)

**Acceptance:** `mypy app` exits 0 locally and in CI under the permissive baseline; at least `app/db/*`, `app/schemas/*`, and `app/chat/tier2_schema.py` pass under the stricter override. `pytest -q` and `ruff check` still green. **Do not** flip global `disallow_untyped_defs = true` in this PR — that's a later ratchet.

**Risk:** Low. Permissive baseline can't break runtime; CI job is additive.

---

### T1.2 — Enable branch protection on `main`
**Why:** `main` auto-deploys to prod and has no protection — the "never push to main" rule is honored, not enforced. This is the single most impactful safety rail for agent sessions.

**This is Casey's action, not yours** (it's a GitHub repo setting, and per CLAUDE.md infra changes are Casey's gate). In your PR description, include this as a checklist item for Casey:
> Enable GitHub branch protection on `main`: require a PR before merging, require the CI checks (lint, test, typecheck) to pass, block direct pushes. Settings → Branches → Add rule.

**Acceptance:** documented in the PR; Casey toggles it.

---

### T1.3 — Security: fail-closed on missing auth secrets
**Why (verified):** `app/admin/auth.py:14` defines `_LOCAL_DEFAULT = "changeme"`; `_admin_password_from_env()` returns it when `ADMIN_PASSWORD` is unset, and `app/auth/session.py:33-37` falls back to that same value for the **user session cookie secret** when `HAVA_SESSION_SECRET` is unset. If both are unset in prod: admin login with `changeme` + forgeable session cookies.

**Do:**
1. In `app/admin/auth.py` and `app/auth/session.py`, when running under prod (the code already detects `RAILWAY_ENVIRONMENT` at `session.py:61` via `cookie_secure_in_prod()`), **raise on startup / refuse to sign** if `ADMIN_PASSWORD` or `HAVA_SESSION_SECRET` is unset or equals `"changeme"`. Keep the `changeme` default working **only** when `RAILWAY_ENVIRONMENT` is unset (local/test), so the test suite is unaffected.
2. Decouple the session secret from the admin password: `_session_secret()` should require `HAVA_SESSION_SECRET` independently in prod rather than falling back to the admin password.
3. **Flag for Casey** (he must verify in Railway, you cannot): confirm `ADMIN_PASSWORD` and a *distinct, strong* `HAVA_SESSION_SECRET` are both set in prod. If they were ever unset, sessions were signed with `changeme` and should be rotated/invalidated.

**Acceptance:** with `RAILWAY_ENVIRONMENT` set and secrets unset, the app refuses to start/sign (add a unit test for this); with it unset (test mode), behavior is unchanged and the full suite stays green.

**Risk:** Medium — touches auth. Add tests for both the prod-fail-closed and local-default paths. Do **not** change the cookie/signing mechanism itself (itsdangerous HMAC + server-side sessions is sound).

---

### T1.4 — Security: cap chat input length
**Why (verified):** `app/schemas/chat.py:39` — `query: str = Field(min_length=1)` has no `max_length`. The public `/chat` accepts arbitrarily large input; `normalize()` runs ~14 regex passes over it and it can reach the LLM. Unauthenticated DoS / token-cost vector.

**Do:** add `max_length=2000` (match the contribution form's `_MAX_NOTES = 2000` precedent) to the `query` field in `ConciergeChatRequest`. Optionally truncate defensively in `app/chat/normalizer.py`.

**Acceptance:** a request with an oversized `query` returns 422 (add a test); normal queries unaffected.

**Risk:** Low. Pick the cap generously enough not to reject legitimate long questions (2000 chars is ~400 words).

---

### T1.5 — Security: add CSRF protection to admin state-changing forms
**Why (verified):** admin POST forms (approve/reject/delete/merge/sponsor) authenticate via an ambient cookie with no anti-CSRF token; mitigated only by `SameSite=Lax`. A comment at `app/admin/router.py:1444` assumes "single-admin, no CSRF."

**Do (smallest safe step):** set the **admin** session cookie to `SameSite=Strict` (it's an internal tool, so Strict is acceptable and closes the cross-site POST vector with near-zero code). Locate the admin cookie set in `app/admin/auth.py` / `app/admin/router.py:662` and change `samesite="lax"` → `"strict"` for the admin cookie only (leave the user `hava_session` cookie as-is to avoid breaking magic-link return flows). If you prefer defense-in-depth, add a per-session CSRF token to the admin form templates and validate it in the `_guard` path — but that's a larger change; **ask Casey which he wants** before doing the token version.

**Acceptance:** admin login + an admin action still work end-to-end in tests; the admin cookie carries `SameSite=Strict`.

**Risk:** Low for the cookie change; the token version is Medium (touches every admin form) — hence the ask.

---

## TIER 2 — Type the boundaries, close the leaks, speed the loop

### T2.1 — Type the component-payload and session boundaries
**Why (verified):** 467 `dict[str, Any]` sites. `app/chat/component_builders.py` (1,203 LOC) returns bare `dict[str, Any]` component shapes; `app/chat/unified_router.py` threads a raw `session: dict` (slots, `prior_entity`, `last_result_set`, `listing_mode`). This is the highest-value place for types — it's exactly what agents reshape silently.

**Do:** introduce `TypedDict`s (or Pydantic models) for each component shape returned by `component_builders.py` (day_agenda, week_strip, card_row, business_list, single_card, …) and a `SessionState` `TypedDict` for the router's session dict. Annotate the builder return types and the router state accordingly. Then enable the stricter mypy override (T1.1 step 2) for `app/chat/component_builders` and `app/chat/unified_router`.

**Acceptance:** mypy passes on these modules under `disallow_untyped_defs`; `pytest -q` green (the byte-stable outputs must be unchanged — types are structural, not behavioral). Add/expand golden tests if you touch builder output.

**Risk:** Medium — large files, behavior must stay byte-identical. Change types only, not output strings. Lean on the existing golden test in `tests/test_disclosure_render.py` + `tests/fixtures/disclosure_regression_golden.json` as the model.

### T2.2 — Fix the one unbounded memory leak
**Why (verified):** `app/auth/session.py:30` `_LAST_SEEN_MONO: dict[str, float] = {}` is written at line 69 and **never pruned** — grows one entry per unique session id over process lifetime.

**Do:** replace with a size/TTL-bounded structure. Simplest: prune-on-write (drop entries older than the debounce window) or use `cachetools.TTLCache`. The debounce only needs ~60s of memory, so a small cap is safe. If you add `cachetools`, pin it in `requirements.txt`.

**Acceptance:** the dict can't grow unbounded (add a test that inserts many ids and asserts bounded size / eviction); auth flow tests stay green.

### T2.3 — Make the OpenAI client a singleton
**Why (verified):** per-call `OpenAI(...)` clients at `app/chat/hint_extractor.py:67`, `app/chat/llm_cache.py:86`, and 4 more sites — each builds an httpx pool relying on GC to release sockets. FD/socket churn on the chat hot path.

**Do:** create one process-wide lazily-initialized `OpenAI` client (module-level singleton, thread-safe per the SDK) and reuse it at all call sites; same for the Anthropic client if similarly constructed per-call. This also cuts per-request latency.

**Acceptance:** all call sites use the shared client; tests green (they mock the client — verify the mock seam still works; you may need a `get_openai_client()` accessor that tests can monkeypatch).

**Risk:** Low-Medium — make sure test monkeypatching still intercepts. Check how the current tests stub OpenAI before refactoring.

### T2.4 — Faster, shardable test loop
**Why:** 2,827 tests run single-process; the inner loop is correct but slow for agents.

**Do:** add `pytest-xdist` to `dev-requirements.txt`; verify `pytest -n auto` passes (the per-test DB cleanup fixture `_phase7_test_row_cleanup` and the session-scoped SQLite setup must be xdist-safe — if tests share a single SQLite file they may collide under parallelism; if so, make the DB per-worker using the `worker_id` fixture, or document that `-n auto` needs per-worker DBs). Update the CI test command to `-n auto` **only if** it's reliably green. Optionally add a `pre-commit` config running ruff + mypy.

**Acceptance:** `pytest -n auto -q -m "not integration"` passes deterministically; if it can't be made safe cheaply, **stop and report** rather than shipping flaky parallelism.

**Risk:** Medium (test isolation under parallelism). This is the one item most likely to surface hidden test coupling — treat a flaky result as a blocker, not a pass.

---

## TIER 3 — Performance + hygiene (opportunistic, after Tiers 1–2)

### T3.1 — Fix the O(N) brute-force dedup
**Why (verified):** `app/events/dedup.py:60-87` (`resolve_venue_entity_id`) loops over **every** active Entity running `fuzz.token_sort_ratio`, then over **every** active Provider for address `partial_ratio`. Same pattern in `app/contrib/ingest_reconciler.py:131-141`.
**Do:** add an exact-normalized-name dict lookup before the fuzzy fallback; load entities once per scrape batch instead of per event; consider a Postgres `pg_trgm` prefilter to narrow candidates in SQL. Keep behavior equivalent — add a test asserting the same match results on a fixture set.
**Acceptance:** dedup returns identical matches on existing fixtures, far fewer rows scanned; ingest tests green.

### T3.2 — Fix category-page N+1 queries
**Why (verified):** `app/api/routes/category_pages.py:1130-1135` calls `build_card_view_model(db, ent.id)` per entity; providers re-fetched at `:781-789` and `:588`.
**Do:** bulk-fetch providers for all entity IDs once (`select(Provider).where(Provider.entity_id.in_(eids))`), pass the map through filtering + ranking + view-model construction.
**Acceptance:** category landing renders identical output with far fewer queries; tests green.

### T3.3 — Add composite indexes (NEEDS CASEY APPROVAL — prod DB)
**Why (verified):** hot filters with no composite index: `(providers.entity_id, is_active, draft)`, `(events.date, entity_id)`.
**Do:** write an alembic migration adding these indexes. **This is a prod schema change** — per CLAUDE.md, do **not** apply to prod. Open the migration in the PR, describe the indexes and expected effect, and let Casey approve + deploy via the normal `alembic upgrade head` predeploy. Test the migration locally against SQLite/Postgres.
**Acceptance:** migration applies cleanly locally; PR flags it explicitly for Casey's prod gate.

### T3.4 — Hygiene (low risk, high signal-to-noise for future agents)
From the dead-code audit (`docs/` companion):
- Remove confirmed-dead modules (grep-verified zero references): `app/core/program_search.py`, `app/core/dedupe.py`, `app/events/view_model.py`, and `app/home/browse_tiles.py` **together with** `tests/test_phase6_homepage.py`. Run `pytest -q` + `ruff` after.
- Untrack accidental junk: `h`, `cripts.voice_battery.grade --judge-model gpt-4.1-mini`, `test_sync_check.tmp`, `test_write_check.tmp`, `.split_backup/` (add to `.gitignore`), `palette-options.html`, `redesign-mockup.html`.
- Drop unused deps after confirming nothing imports them: `python-jose`, `ecdsa`, `rsa` (auth uses `itsdangerous`, not jose — verify with grep first).
- **Ask Casey** before removing `app/contrib/lhcaz_aquatic.py` (deliberately retained HTML fallback) and before any `.git` branch/worktree cleanup.
**Acceptance:** suite green after each removal; each deletion is grep-justified in the commit message.

---

## Definition of done (per PR)
1. On a feature branch off `main` (never on `main`).
2. `python -m pytest -q` green and `ruff check .` clean (and `mypy app` green once T1.1 lands).
3. Tests added/updated in the same commit as behavior changes.
4. No prod DB writes, no `railway`/secret access performed by the agent.
5. PR description lists: what changed, which audit finding it closes, any **Casey action items** (branch protection T1.2, prod secret verification T1.3, index deploy T3.3, the removal asks in T3.4), and how it was verified.
6. Stop and ask on any genuine judgment call.

## Parallel workstream — SEO / category ranking
A separate, larger body of code work is specced in `docs/CLAUDE_CODE_SEO_BRIEF_2026-06-04.md` (source: `docs/SEO_ASSESSMENT_PLAN_2026-06-04.md`): collapsing duplicate category route families, fixing the `http://` canonical bug and empty home-property-services render, real pagination, JSON-LD/structured data, and dedicated trade pages so each local query ("plumbers in lake havasu") has a page. **Sequencing note:** the SEO work touches `app/api/routes/category_pages.py`, which is also the target of the perf N+1 fix in T3.2 above — **do T3.2 before the SEO pagination/template work** so the SEO changes build on the deduplicated, typed query code. Two of the SEO items are Casey-gated (custom domain in Phase 0; the route-family decision) — see that brief's §0.

## References (companion audits in this repo)
- `docs/TECH_DIRECTION_DECISION_2026-06-04.md` — the decision and scorecard (why typed-Python over Rust).
- `docs/RUST_MIGRATION_AUDIT_2026-06-04.md` — Rust feasibility, the optional PyO3 path, perf hot spots.
- `docs/SECURITY_AUDIT_2026-06-04.md` — full security findings (T1.3–T1.5 source).
- (Dead-code / memory-leak / agent-readiness findings are summarized in the decision doc; T2.2–T2.3 and T3.4 trace to them.)

## Suggested execution order
Tier 1 as **PR #1** (`typing-mypy-bootstrap`: T1.1, T1.4) and **PR #2** (`security-hardening`: T1.3, T1.5) — keep auth changes separate for clean review. T1.2 is Casey's toggle. Then Tier 2 as one or two PRs, Tier 3 opportunistically. Land mypy (T1.1) **first** so every subsequent PR is type-checked.
