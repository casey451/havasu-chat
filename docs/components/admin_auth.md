# admin_auth

`app/admin/auth.py` (~45 lines)

## Purpose

Cookie-based admin session authentication. Admin-side HTTP routes use the cookie produced by this module to gate access — login posts a password, the server signs a session cookie, subsequent requests verify the cookie. The verification is read-only and side-effect-free; it doesn't refresh expiry, doesn't write to a session store, doesn't log access. Designed for single-admin use, not multi-tenant.

The module is **security-sensitive.** Edits should be reviewed against the threat model below.

## Public surface

**`COOKIE_NAME = "admin_session"`** — Cookie name used by FastAPI's `request.cookies` and response `set_cookie` calls. Other modules (`app/admin/router.py`, the contribution-mention promotion routes) reference this constant rather than hard-coding the string.

**`MAX_AGE_SECONDS = 86400`** — Cookie expiry (24 hours from sign time). Both the cookie's `max-age` attribute and the serializer's `max_age` validation parameter use this constant.

**`sign_admin_cookie() -> str`** — Returns a signed cookie value encoding `{"ok": True}`. Caller (login route) sets this as the cookie on a successful password match.

**`verify_admin_cookie(value: str | None) -> bool`** — Returns `True` iff the cookie value is well-formed, unexpired, and decodes to `{"ok": True}`. Returns `False` on missing cookie, expired signature, tampered signature, or any other validation failure. Never raises.

**`admin_password_ok(password: str) -> bool`** — Compares the submitted password (stripped) against the configured admin password. Returns `True` iff they match exactly. Used by the login POST route.

## Inputs and outputs

**`sign_admin_cookie`:** no input; output is a serialized signed string.

**`verify_admin_cookie`:** input is the cookie value (or `None` for missing). Output is a `bool`.

**`admin_password_ok`:** input is a string (typically from a form post). Output is a `bool`.

## Internal structure

The module is functional, not class-based. Key elements:

1. **`_admin_password_from_env()`** reads `ADMIN_PASSWORD` env at call time, **not at import time**. The comment is explicit: "Read ADMIN_PASSWORD at call time (not import time) for correct Railway/runtime values." Railway-deployed services receive env vars after Python starts; reading at import time captured stale defaults. Falls back to the `_LOCAL_DEFAULT = "changeme"` constant if the env is unset or whitespace-only.

2. **`_serializer()`** constructs an `itsdangerous.URLSafeTimedSerializer` with the admin password as the secret and `"havasu-admin-session"` as a domain-separating salt. The salt prevents this serializer's signatures from validating against any other serializer in the codebase, even if they shared the same secret.

3. **`sign_admin_cookie`** returns `_serializer().dumps({"ok": True})`. The payload is intentionally minimal — no user ID (single admin), no timestamp (the serializer's `max_age` provides expiry).

4. **`verify_admin_cookie`** runs `_serializer().loads(value, max_age=MAX_AGE_SECONDS)`. Catches `BadSignature` and `SignatureExpired` from `itsdangerous`. Verifies the decoded payload has `ok=True`.

5. **`admin_password_ok`** is a stripped-string equality check. **No constant-time comparison.** Acceptable trade-off given the single-admin model and the absence of a public registration flow; an attacker would need to brute-force from outside, where rate limiting (slowapi) and the 24-hour cookie expiry are the actual defenses.

## Threat model

**In scope:**

- **Cookie tampering.** `itsdangerous`-signed cookies fail validation if any byte is altered. Verified via the `BadSignature` exception path.
- **Cookie expiry.** 24-hour `max_age`. Past that, the user re-authenticates.
- **Replay outside expiry.** Same as above — expired cookies fail validation.
- **Brute-force password guessing via the login form.** slowapi rate-limits the `/admin/login` POST route at the application layer (see `app/core/rate_limit.py`). The auth module itself doesn't rate-limit.
- **Stolen cookie via XSS.** Cookies should be set with `httponly=True` and `secure=True` (production HTTPS) by the route handler. The auth module produces the value but does not set the cookie attributes — that's the route's responsibility.

**Out of scope (by design, single-admin model):**

- **Session revocation before expiry.** No session store; cookies are valid until they expire naturally. To force logout, either rotate `ADMIN_PASSWORD` (invalidates all signed cookies because the serializer's secret changed) or wait 24 hours.
- **Multi-admin or per-user sessions.** Single shared password.
- **Audit logging of admin actions.** Not in this module; would live in route handlers or a dedicated audit-log table.
- **Constant-time password comparison.** Direct equality is deliberate; the slowapi rate limit on the login route is the brute-force defense.

## Conventions

**`ADMIN_PASSWORD` is read at call time, not import time.** Critical for Railway / dev-vs-prod env switching. If a future refactor moves to import-time reading, document why and verify the deploy posture.

**`_LOCAL_DEFAULT = "changeme"` is the literal default password in dev.** Production deploys MUST set `ADMIN_PASSWORD`. Slice 31's options doc surveyed `safety.bandit-style` linters that catch hard-coded credentials; if Phase D adds bandit, this constant would need an explicit `# nosec` annotation and a rationale.

**Salt is hard-coded.** `"havasu-admin-session"`. Don't change this without a coordinated rotation — every existing cookie becomes invalid the instant the salt changes.

**Cookie payload is minimal.** `{"ok": True}` and nothing else. If a future feature needs per-action authorization (e.g., super-admin vs ordinary admin), this minimal payload becomes a constraint to deliberately reconsider.

**No `Optional` annotation for `MAX_AGE_SECONDS`.** Tests can monkeypatch the module attribute; `verify_admin_cookie` reads it via the module-level name, not via a function arg.

## Related

**Direct callers:**

- `app/admin/router.py` — login routes, dashboard routes, every cookie-gated admin endpoint. `verify_admin_cookie` is read inside `_guard(request)`.
- `app/api/routes/admin_contributions.py` — contribution review API; uses `Depends(require_admin)` which delegates to `verify_admin_cookie`.
- `app/api/routes/admin_mentions.py` — mention promotion API; same dependency pattern.
- `app/main.py` — `RequestValidationError` handler doesn't touch auth; cookies are read by the dependency layer.

**Direct dependencies:**

- `itsdangerous` — `URLSafeTimedSerializer`, `BadSignature`, `SignatureExpired`.
- `app.bootstrap_env.ensure_dotenv_loaded` — populates `ADMIN_PASSWORD` from `.env` in dev.

**Cross-references:**

- `app/admin/router.py` — see `docs/components/admin_router.md` for the full route inventory.
- `app/core/rate_limit.py` — slowapi config; the brute-force defense for the login route.
- `docs/maintainability/http_api.md` — admin-route auth posture summary.
