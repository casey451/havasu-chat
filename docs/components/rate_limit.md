# rate_limit

`app/core/rate_limit.py` (~22 lines)

## Purpose

Process-wide slowapi `Limiter` instance + the user-visible message string for rate-limit-exceeded responses. Every FastAPI route that uses `@limiter.limit(...)` shares this single limiter instance so per-IP request budgets are enforced consistently across endpoints. The module also exports an env-controlled disable flag (`RATE_LIMIT_DISABLED`) so the test suite can run without coupling to inter-test `limiter.reset()` calls.

## Public surface

**`limiter: slowapi.Limiter`** — The shared limiter instance. Constructed with `key_func=get_remote_address` (per-IP budgeting) and `enabled=not is_rate_limit_disabled()` (env-toggleable).

**`RATE_LIMIT_MESSAGE = "Slow down a sec! Try again in a minute 😅"`** — The friendly user-visible message returned when a rate limit fires. Imported by every route's rate-limit-exceeded handler so the wording stays consistent.

**`is_rate_limit_disabled() -> bool`** — Reads `RATE_LIMIT_DISABLED` env (case-insensitive `1`/`true`/`yes`/`on`). Returns `True` to skip enforcement. Pytest sets this in `tests/conftest.py`.

## Conventions

**One limiter, one process.** Importing `from app.core.rate_limit import limiter` everywhere ensures all routes share the same rolling-window state. Constructing per-route limiters would silently break the per-IP enforcement intent.

**Disable flag is process-wide.** When `RATE_LIMIT_DISABLED` is set, the limiter is constructed with `enabled=False` at import time. The disable doesn't toggle at runtime; restart the process to change the flag.

**Per-IP keying.** `get_remote_address` from slowapi reads the `X-Forwarded-For` header in production (Railway terminates TLS upstream), falling back to direct socket address. Behind a reverse proxy without forwarded headers, all traffic appears as one IP and rate-limit budgets get pooled — known limitation of this keying strategy.

**Friendly emoji message.** The trailing 😅 in `RATE_LIMIT_MESSAGE` is intentional — softens the limit response. If localization is ever added, the emoji should stay.

## Where the limiter is applied

Per the audit at `relay/component_doc_audit.md` and `docs/maintainability/http_api.md`:

- `app/main.py` — historic `POST /events` (removed in Slice 22 per Backlog #24).
- `app/programs/router.py` — program-creation endpoints, ~5/min.
- `app/api/routes/contribute.py` — public contribution intake (additionally has a custom contribute_limiter on top of slowapi).
- `app/api/routes/chat.py` — `POST /api/chat`, ~30/min for the unified concierge.

Adding a new rate-limited route: import `limiter` and `RATE_LIMIT_MESSAGE`, decorate with `@limiter.limit("N/minute")`, and register an exception handler for `RateLimitExceeded` that returns the message.

## Known limitations and design notes

**In-memory backend.** slowapi defaults to in-process state. A second worker process would track its own counters; behind a multi-worker uvicorn, per-IP budgets effectively scale with worker count. Acceptable at current Railway single-worker config.

**No per-route customization at this layer.** The shared limiter doesn't differentiate route classes. Per-route limits are set at decoration time via `@limiter.limit("N/minute")`; this module is the shared backend, not a policy layer.

**Disable is binary.** No "soft mode" that logs but doesn't reject. If a future debug session wants to see rate-limit firings without enforcement, that's a feature request — not currently supported.

**Message is hard-coded English.** Localization would require either parameterizing the message at import time or splitting the constant into per-locale variants.

**`get_remote_address` trust depends on upstream proxy.** If Railway's `X-Forwarded-For` chain is ever forged or misconfigured, per-IP budgeting becomes per-source-of-forwarded-IP. Production trust assumes Railway terminates correctly.

## Configuration

- `RATE_LIMIT_DISABLED` (env): `1`/`true`/`yes`/`on` (case-insensitive) skips enforcement. Set in `tests/conftest.py` for the suite.

## Related

**Direct callers:**

- `app/main.py` — installs `RateLimitExceeded` exception handler.
- `app/programs/router.py`, `app/api/routes/contribute.py`, `app/api/routes/chat.py` — apply `@limiter.limit(...)` to routes.

**Cross-references:**

- `docs/maintainability/http_api.md` — auth-and-limit summary.
- `docs/runbook.md` — operational notes.
- `docs/maintainability/railway_layout.md` — Railway env-var matrix (mentions the disable flag).
- `docs/components/admin_auth.md` — references this module as the brute-force defense for the admin login route.
