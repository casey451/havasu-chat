# Security Audit — havasu-chat

**Date:** 2026-06-04 · **Mode:** read-only (no changes made) · **Method:** 3 parallel security agents (auth/authz, injection/untrusted-input, secrets/deps/infra) + manual verification of the top findings against the code.

---

## Executive summary

The codebase is **notably disciplined on security** — more so than typical for a solo-operated app. No SQL injection, no unsafe deserialization, no command injection, no CORS wildcard, constant-time token comparison, Sentry body-scrubbing, hashed user queries, a well-built SSRF guard, and modern pinned dependencies. `.env` is correctly gitignored and **never appears in git history** — the biggest theoretical risk does not materialize and no key rotation is forced by git tracking.

The findings that matter cluster into a small set. The single most important one — independently surfaced by all three agents and verified in code — is a **fail-open credential default**: when `ADMIN_PASSWORD` is unset, it defaults to the literal `"changeme"`, and that same value is the fallback signing secret for *every user session cookie*. The rest are a CSRF gap on admin forms, a DNS-rebinding hole in the SSRF guard, an unbounded chat-input length (DoS/cost), and dependency/config hygiene.

**Do this week:** confirm `ADMIN_PASSWORD` and a *separate* `HAVA_SESSION_SECRET` are both set to strong values in Railway prod, and make the app fail-closed when they're unset.

---

## Findings ranked by severity

### CRITICAL (conditional on prod config)

**C1 — `ADMIN_PASSWORD` defaults to `"changeme"`, which also signs all user session cookies.** *Verified.*
`app/admin/auth.py:14,17-23` — `_admin_password_from_env()` returns `"changeme"` (`_LOCAL_DEFAULT`) whenever `ADMIN_PASSWORD` is unset or blank. That value is used for (a) admin login, (b) the admin cookie HMAC secret, and — via `app/auth/session.py:33-37`, also verified — (c) the **user** session cookie secret, because `_session_secret()` falls back to `_admin_password_from_env()` when `HAVA_SESSION_SECRET` is unset.

**Exploit:** If `ADMIN_PASSWORD` is unset in prod, an attacker logs into `/admin/login` with `changeme` (full admin: approve/reject/merge/delete). If `HAVA_SESSION_SECRET` is *also* unset, the public default key lets them forge `hava_session` cookies for any user — full account takeover. The two secrets collapsing into one shared default also means an admin-password leak compromises all user sessions.

**This is a deployment-config question.** Confirm both env vars are set to strong values in Railway prod (the startup log line `ADMIN_PASSWORD loaded: True` at `app/main.py:305` is the quick check). If both are set, real-world risk drops to Medium but the code footgun remains.

**Fix:** Remove the `"changeme"` fallback; refuse to start (or refuse to sign) when `ADMIN_PASSWORD`/`HAVA_SESSION_SECRET` are unset and `RAILWAY_ENVIRONMENT` is set (that env var is already detected at `session.py:61`). Decouple the user-session secret from the admin password — require `HAVA_SESSION_SECRET` independently.

### HIGH

**H1 — No CSRF protection on cookie-authenticated state-changing forms.**
Admin POST forms (approve `app/admin/router.py:768`, reject `:781`, delete `:794`, program create `:1355`, provider create `:1610`, merge `provider_merge_review.py:179`, sponsor approve/pause `sponsor_surface.py:134-180`) and user forms (claim, favorites toggle, account alerts) authenticate via an ambient cookie with no anti-CSRF token. A comment at `router.py:1444` explicitly assumes "single-admin, no CSRF." Cookies are `SameSite=Lax`, which blocks the classic cross-site POST in modern browsers — so this is mitigated, not closed (Lax doesn't cover all flows/clients, and any future move to `SameSite=None` reopens it). Highest practical impact is on destructive, irreversible admin actions (merges/deletes).
**Fix:** per-session CSRF token in state-changing forms, or `SameSite=Strict` on the admin cookie specifically.

**H2 — `RATE_LIMIT_DISABLED` is one env flag that disables ALL rate limiting process-wide.**
`app/core/rate_limit.py:17-22` builds the limiter `enabled=False` at import when the flag is truthy, killing every `@limiter.limit` including the magic-link cap (`app/auth/routes.py:116`). Docs say "emergency-only, never in prod" but nothing in code enforces that. A separate DB-backed per-email cap (5/hour, `routes.py:95-102`) still applies, which keeps this at High not Critical.
**Fix:** refuse to honor the flag when `RAILWAY_ENVIRONMENT` is set; confirm it's unset in prod.

### MEDIUM

**M1 — SSRF guard bypassable via DNS rebinding / TOCTOU.**
`app/contrib/url_fetcher.py`. The public unauthenticated `POST /contribute` accepts `submission_url` and fetches it server-side during enrichment. The guard `_is_blocked_target()` (`:38-76`) is genuinely strong — blocks non-http(s), localhost, private/loopback/link-local/reserved IPs *after* `getaddrinfo`, disables redirects, and re-validates each redirect hop. **Gap:** it resolves the host at line 56, then `client.stream("GET", current)` at line 149 resolves *again* independently. An attacker controlling DNS can return a public IP to the check and `169.254.169.254` (cloud metadata) or an internal IP to httpx's connect. Bounded by a 1/hour/IP limit, HTML-only content type, and 5 MB cap.
**Fix:** resolve once, validate the resolved IP, then pin the connection to that IP (custom resolver/transport) instead of re-resolving.

**M2 — Unbounded chat query length → DoS / LLM cost amplification.** *Verified.*
`app/schemas/chat.py:39` — `query: str = Field(min_length=1)` has **no `max_length`**. The public `/chat` accepts any size; `normalize()` runs ~14 regex passes over the whole string and it can flow to the Tier 3 LLM (token cost). Not catastrophic ReDoS (regexes are linear), but amplified linear work + LLM spend on an unauthenticated endpoint.
**Fix:** add `max_length` (~1000–2000) to `query`; truncate in `normalize()`. (The contribution form already does this — `_MAX_NOTES = 2000`.)

**M3 — No Content-Security-Policy header.**
`app/main.py:330-355` sets X-Frame-Options: DENY, nosniff, Referrer-Policy, Permissions-Policy, HSTS — but no CSP (deferred per comment at `:322`). Admin pages build HTML via f-strings; interpolated fields *are* consistently run through `html.escape` (verified — no stored-XSS found), so CSP is defense-in-depth.
**Fix:** ship CSP report-only, then enforce.

**M4 — `normalized_query` stored in cleartext in `chat_logs`.**
`app/db/chat_logging.py:54-55` — the query is also hashed (`query_text_hashed`, good), but `normalized_query` (and `response_text`, which can echo PII) is persisted in cleartext at prod scale. Product telemetry, not a leak, but user free-text at rest.
**Fix:** confirm against privacy/retention policy; consider scrubbing emails/phones or truncating before persistence.

### LOW / INFO

**L1 — Magic-link tokens not invalidated on login.** Other valid (≤15 min) tokens for an email remain usable after one is consumed (`app/auth/routes.py:177-224`). Entropy/expiry/single-use/hashing are otherwise correct. Fix: consume all outstanding tokens for the email on successful callback.

**L2 — Admin authz is per-route copy-pasted `_guard`, not a router dependency.** Every admin route I checked *is* guarded, but protection is opt-in across 11 duplicated guards, so a future route that forgets it is silently public. Fix: `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` — `require_admin` already exists in `app/auth/dependencies.py:24`.

**L3 — Unused `python-jose` (3.5.0) + `ecdsa`/`rsa` in requirements.** Auth uses `itsdangerous`, not jose — so the alg-confusion/Minerva-CVE surface isn't reached, but it's dead weight carrying CVE exposure. Fix: drop from `requirements.txt` after confirming nothing transitively needs it.

**L4 — `submission_notes` uncapped on the token-gated ingest path** (`app/schemas/contribution.py:41`). Only reachable with a valid ingest bearer token. Fix: add `max_length` to the schema so the cap holds on every entry path.

**L5 — Indirect prompt injection via catalog/scraped content in Tier 3.** `tier3_handler.py:358` concatenates system instructions and untrusted catalog data (contribution/scraper-originated) as plain text. Low because contributions require admin approval before becoming catalog entities, output is capped at 150 tokens, and the system prompt holds no secrets. Fix (defense-in-depth): wrap context in explicit `<catalog_data>…</catalog_data>` delimiters noting it's untrusted.

**L6 — Default `/docs`, `/redoc`, `/openapi.json` enabled in prod.** Reveals API shape only (no secrets). Optional: disable when `RAILWAY_ENVIRONMENT` is set.

**L7 — Tracked junk widens surface (no secrets).** `h`, `cripts.voice_battery.grade --judge-model gpt-4.1-mini`, `*.tmp`, `.split_backup/` (9 stale code duplicates). Fix: `git rm`. (Same items flagged in the dead-code audit.)

---

## Verified-good controls (no action needed)

- **No JWT alg-confusion class** — sessions use `itsdangerous` HMAC + server-side `AuthSession` rows with expiry, `is_active` checks, and real revocation (logout deletes the row). `alg=none` does not apply.
- **Ingest token** — `secrets.compare_digest` constant-time compare, 503 (fail-closed) when `INGEST_API_TOKEN` unset, token in `Authorization: Bearer` (not query string), provenance forced server-side.
- **No SQLi** — FTS binds the tsquery via `.bindparams()` with `^[a-z0-9]+$` token pre-filtering; tier2/ranking fully ORM-parameterized; the only raw `text()` calls are static strings.
- **No stored XSS found** — every `app/admin/*_html.py` applies `html.escape(quote=True)` to interpolated DB/user fields; no `|safe`/`autoescape off`/`Markup()` in templates.
- **No path traversal** — photo/capture R2 keys are fully server-generated (UUIDs, DB enums); uploads are re-encoded through Pillow.
- **No unsafe deserialization / command injection** — only `yaml.safe_load`; `subprocess` only in offline voice-audit scripts, no `shell=True`.
- **IDOR checks present** — favorites/alerts scoped to `user.id`; merchant upgrade checks `_owns_entity`; claims scoped to `(user_id, entity_id)` with a DB uniqueness constraint.
- **`.env` not tracked, not in history** — `.gitignore` covers `.env`, `.env.*`, `*.db`, `data/`, `*.log`, `*.sql` (verified). Backfill logs and `search_debug.log` grepped for secret patterns — none found. Tracked CSVs contain business data only, zero emails.
- **Sentry scrubbing** — `before_send`/`before_breadcrumb` strip `/api/chat` bodies and `query`/`message`/`normalized_query` keys before upload.
- **No CORS middleware at all** — no `allow_origins='*'` + credentials footgun. No `debug=True`, no stack traces to clients.
- **CI/CD safe** — `ci.yml` uses only placeholder keys and references no `secrets.*`; all secret-bearing workflows are `schedule`/`workflow_dispatch` only (no `pull_request`/`pull_request_target`), so fork PRs can't exfiltrate secrets; `permissions: contents: read`.

---

## Key-rotation call-out

No rotation is forced by git tracking (`.env` is clean). The **one** rotation-worthy scenario is operational: if `ADMIN_PASSWORD`/`HAVA_SESSION_SECRET` were ever left unset in prod, every admin and user session cookie has been signed with `"changeme"` — in that case, set a strong `ADMIN_PASSWORD`, set a distinct `HAVA_SESSION_SECRET`, and invalidate existing sessions. Verify via the `ADMIN_PASSWORD loaded: True` startup log.

## Suggested remediation order

1. **(C1/H2)** Verify `ADMIN_PASSWORD` + a separate `HAVA_SESSION_SECRET` are set in prod; make the app fail-closed when they (or non-disabled rate limiting) are absent under `RAILWAY_ENVIRONMENT`. Remove the `changeme` fallback and decouple the session secret.
2. **(H1)** Add CSRF tokens to admin state-changing forms (or `SameSite=Strict` on the admin cookie).
3. **(M2)** Add `max_length` to the chat `query` field.
4. **(M1)** Pin the SSRF fetch to the validated IP.
5. **(M3/M4)** Ship CSP report-only; review `normalized_query` retention.
6. **(L-tier)** Drop unused `python-jose`/`ecdsa`/`rsa`; convert admin guards to a router-level dependency; `git rm` tracked junk; delimit Tier 3 context.

All fixes are code/config changes on feature branches per CLAUDE.md — none require a production DB write. Item 1 may need a Railway variables check, which (per CLAUDE.md) is for Casey to perform.
