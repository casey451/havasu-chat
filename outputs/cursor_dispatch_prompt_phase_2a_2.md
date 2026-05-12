# Cursor Dispatch Prompt — Phase 2A.2 (auth flow + session middleware + login UI)

> Short paste-into-Cursor prompt for Phase 2A.2 dispatch — the middle (and biggest) sub-phase of Lane 2A of Phase 2 of the master build plan. The heavy-prescriptive operating doc remains `outputs/cursor_brief_phase_2a_account_lite.md` (read it again, especially §3 + §6 + §9 + §10 + §11 + §12). After 2A.3 ships, Lane 2A is complete and Lane 2B (image storage + search) becomes the next dispatchable lane.
>
> **Operator gate (resolved):** Resend account + `askhava.com` sender domain verified + `RESEND_API_KEY` / `RESEND_FROM_ADDRESS` / `AUTH_MAGIC_LINK_BASE_URL` / `AUTH_DEV_MODE=false` env vars set in Railway production as of session-17 (2026-05-11). For local dev, add `AUTH_DEV_MODE=1` to your local `.env` so test runs + manual smoke don't hit Resend.

---

```
Read outputs/cursor_brief_phase_2a_account_lite.md end-to-end again,
especially §6 (the full 2A.2 deliverable list) + §9 (what NOT to do) +
§10 (acceptable deviations) + §11 (risk register).

Phase 2A.1 SHIPPED on origin per master plan §4 Phase 2 "Shipped
(incremental)" list — commit 6000138 (code) + 5bf4c14 (dispatch
artifacts). Origin/main HEAD should top at the most recent commit on
main; run git log --oneline -5 and confirm — top should be either
5bf4c14 (if 2A.2 dispatch lands before doc-update commits) or one or
two doc-update commits beyond that (master plan §4 Phase 2 ship-line
+ STATE.md refresh, both landed in session-17). Pytest collect
baseline going in is **1543** tests. Alembic head is **92ce4899dc08**
(Phase 2A.1 account-lite v0.1 schema).

Ship Phase 2A.2 ONLY per §3 + §6 of the brief — auth flow routes +
session middleware + login UI + email helpers + Resend wiring +
rate limits + main.py middleware/router registration. **No claim
flow, no favorites, no admin role parallel-path, no viewer_is_owner
wiring** — all of that is 2A.3.

ORDER MATTERS WITHIN PHASE 2A.2:
1. First: read the five docs + source files listed in brief §0 step 6
   + step 7 (most are unchanged from 2A.1 baseline; verify line offsets
   if you anchor edits into models.py or admin/auth.py).
2. Then: factor app/auth/email_helpers.py per brief §6.3
   (normalize_email, is_valid_email, generate_magic_link_token,
   hash_token, hash_request_ip). Pure functions; the easiest piece;
   gets a small test file later.
3. Then: factor app/auth/session.py per brief §6.1. The
   SessionMiddleware (Starlette BaseHTTPMiddleware) reads the
   hava_session cookie, verifies signature via itsdangerous, looks up
   AuthSession row, checks expires_at + user.is_active, attaches
   request.state.current_user + request.state.current_session.
   Mirrors app/admin/auth.py:30-41 shape but signs an AuthSession.id
   instead of {"ok": True}. Cookie name 'hava_session', salt
   'havasu-session', secret-key fallback HAVA_SESSION_SECRET →
   ADMIN_PASSWORD (the admin-cookie precedent), 30-day Max-Age.
   The last_seen_at debounce (once-per-minute) avoids write thrash;
   pick whichever in-memory mechanism is cleanest (in-session attr or
   per-process LRU) and flag in §13.
4. Then: factor app/auth/dependencies.py per brief §6.2
   (get_current_user, require_user, require_admin). FastAPI Depends
   shape. HTML-route redirect-on-401 handling is at the route handler
   layer, not the dependency — the dependency raises HTTPException
   and routes that want HTML redirect catch + redirect.
5. Then: factor app/auth/routes.py per brief §6.4. Four routes:
   GET /login (form), POST /api/auth/request-link, GET /auth/callback,
   POST /logout. Rate limit /api/auth/request-link via slowapi (10/hr
   IP-keyed via the existing limiter at app/core/rate_limit.py:22)
   + per-email DB count check (5/hr — count(*) from magic_link_tokens
   WHERE email = ? AND created_at > now - 1h, render the same
   "check your email" page even when rate-limited so attacker can't
   probe state). The callback consumes the token, find-or-creates User,
   creates AuthSession row, signs cookie, redirects to /account (or
   safe next path). _safe_next whitelists by leading / + no scheme +
   no ../ to prevent open-redirect.
6. Then: three new templates per brief §6.5 in app/templates/:
   login.html (single email input form, surfaces error + next),
   login_check_email.html (confirmation, reveals email but NOT whether
   email is existing-user/first-time/rate-limited), login_expired.html
   (expired-or-consumed link + send-me-new-link CTA). Reuse the visual
   treatment of app/templates/home.html for header/footer.
7. Then: anchored Edit on app/main.py per brief §6.6. Add
   `from app.auth.routes import router as auth_router`,
   `from app.auth.session import SessionMiddleware` imports near the
   existing import block; `app.add_middleware(SessionMiddleware)`
   immediately after `app = FastAPI(...)`; `app.include_router(auth_router)`
   in the include block. No other main.py edits.
8. Then: new tests/test_auth_flow.py per brief §6.7 — 20 tests
   covering happy path + 6 design memo §5.2 edge cases + middleware
   states + rate-limit silent path + _safe_next adversarial inputs +
   require_user / require_admin dependency behavior. AUTH_DEV_MODE=1
   in test setup so no real Resend call happens.
9. After all of the above: confirm full pytest stays green, ruff clean,
   that `python -m alembic upgrade head` against a fresh dev DB still
   reaches 92ce4899dc08 cleanly (no new migration in 2A.2), and
   manually smoke the happy path via local server (AUTH_DEV_MODE=1
   → POST /login → log shows magic URL → paste URL → /account renders
   "logged in" → /logout clears cookie + redirects to /).

POSTGRES COMPATIBILITY (carried forward from brief §9 — the same
checklist applies even though 2A.2 doesn't add a new migration):
- The bash sandbox + tests run SQLite; production runs Postgres.
- No raw SQL in any new code paths unless verified portable on both.
- Session-table SELECT-by-PK queries are trivially portable; no
  Postgres-specific JSON or array constructs needed in 2A.2.

DEVIATION INVITATIONS (per brief §10):
- `before_flush` Session listener safety net for User creation. If
  your test fixtures create User rows directly without going through
  the magic-link callback flow and you find a default-field-fill
  pattern useful, register via the slug-listener precedent at
  app/db/seed_helpers.py::register_provider_slug_hooks (session-13
  commit d967568) + the dual-write hooks in
  app/db/database.py::_register_orm_listeners (session-16 commit
  3f3628e). Flag in §13 if you do this.
- Fold session/token cleanup into _hourly_cleanup_loop at
  app/main.py:246. The existing loop already runs
  run_expired_review_cleanup hourly; appending a
  run_expired_auth_cleanup call to delete expired MagicLinkToken
  and AuthSession rows keeps the auth surface tidy without a new
  background-task framework. RECOMMENDED — flag in §13.
- last_seen_at debounce mechanism — pick what's cleanest (in-memory
  per-session attribute vs per-process LRU vs noop and accept the
  write-per-request cost). Flag your choice + reasoning in §13.

WHAT NOT TO DO (per brief §9):
- Don't pre-create User rows on request-link. Only on successful
  callback. (Pre-creating lets an attacker spam User creation by
  entering random emails.)
- Don't reveal whether an email has an existing User row. The
  request-link confirmation page renders the same content for
  first-time / returning / rate-limited.
- Don't run the Resend send on a background queue. V1 is synchronous
  inside the request-link handler (~200ms outbound latency
  acceptable). Phase 4's background-job infrastructure migrates it
  to queued later.
- Don't touch chat-route response shape or anonymous Provider profile
  rendering. Anonymous viewers see identical experience before/after
  the middleware lands.
- Don't introduce circular imports — app/db/models.py does NOT import
  anything from app/auth/. app/admin/router.py may import
  app.db.models.User for the future role check (2A.3) but should NOT
  import app/auth/* modules.

HALT at the §3 Phase 2A.2 boundary. After 2A.2 ships + commits, halt
for operator re-dispatch in a fresh session for 2A.3 (claim flow +
favorites + admin role parallel-path + viewer_is_owner + close-out).
Do NOT start 2A.3 in the same session.

Same constraints as 2A.1:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits — Rule 2+12)
- Pytest must stay green throughout
- Report per brief §12 (final report format) for sub-phase 2A.2 only

Operator note: AUTH_DEV_MODE=1 must be set in the local environment
(.env or tests/conftest.py fixture) before running the full pytest
suite so route handler tests don't try to call Resend. The dev-mode
fallback in app/auth/email_sender.py:_dev_mode_enabled() handles this
at the module layer; tests/test_email_sender.py from 2A.1 already
exercises it.
```

---

## After Cursor returns with the §12 report

Same rhythm as 2A.1: paste back to the Cowork primary chat, primary reviews against §6.8 acceptance gates, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 4 new files in `app/auth/` (`session.py`, `dependencies.py`, `email_helpers.py`, `routes.py`)
- 3 new templates in `app/templates/` (`login.html`, `login_check_email.html`, `login_expired.html`)
- 1 new test file (`tests/test_auth_flow.py`)
- 1 modified `app/main.py` (middleware + router include)

Expected pytest delta: +18-22 net-new tests (brief specifies ~20 covering 4 routes + middleware states + edge cases + rate limits + _safe_next adversarial inputs + 2 dependency tests).

Expected effort: 3-4 day brief estimate; one Cursor session realistically (this is the biggest sub-phase of Lane 2A).

Expected pragmatic deviations: (a) `last_seen_at` debounce mechanism choice (in-session attr vs per-process LRU vs no-op); (b) `_hourly_cleanup_loop` fold for expired-token/session GC; (c) `before_flush` safety-net listener if test-fixture pattern benefits; (d) cookie-secret env var name (`HAVA_SESSION_SECRET` vs falling back to `ADMIN_PASSWORD`); (e) login template visual treatment may diverge from `home.html` if the brand voice / scaffolding doesn't transfer cleanly.

## After Phase 2A.2 ships

Update master plan §4 Phase 2 "Shipped (incremental)" list with the 2A.2 ship-line (same pattern as 2A.1 entry). Then re-dispatch for 2A.3 with a fresh dispatch prompt (`outputs/cursor_dispatch_prompt_phase_2a_3.md` — author after 2A.2 lands so the prompt can cite the actual SHA + pytest delta).

## After Phase 2A.3 (full Lane 2A) ships

Phase 2 Lane 2A is COMPLETE. Update master plan §4 Phase 2 header to mark Lane 2A as SHIPPED with overall pytest delta + total commit chain. Standby for Lane 2B dispatch (separate brief authoring required — `outputs/cursor_brief_phase_2b_image_storage_search.md`, mirrors Phase 2A brief shape scoped to R2 + Pillow + Postgres FTS + pg_trgm; gated on R2 operator prereq locking).
