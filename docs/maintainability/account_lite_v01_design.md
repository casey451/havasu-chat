# Account-lite v0.1 — Design Memo

> **Status:** design only; no implementation, no migration. Output of the architecture-audit-driven design pass on 2026-05-14.
> **Source gap:** Gap #2 in `docs/maintainability/architecture_gaps_for_full_vision_audit.md` §3.
> **Source decision:** pivot §8.3 LOCKED ("Resend magic-link"); see `docs/STRATEGY_PIVOT_2026-05-12.md:191`.
> **Audience:** Cowork primary + Casey; future implementation-lane author (Cursor / CC).
> **Companion docs:** `docs/maintainability/place_model_design.md` (similar shape — read for voice + section structure), `docs/STRATEGY_PIVOT_2026-05-12.md` §8.3 (LOCKED decision) + §5 Days 14-35 / 46-90 (the product window this gates), `docs/maintainability/architecture_gaps_for_full_vision_audit.md` §3 Gap 8 (the gap framing).

---

## §1 Why account-lite exists (problem statement)

The operator's evolved vision needs three classes of *identity-bearing* behavior that the current codebase cannot support: business owners claiming and editing their own listings, end-users saving favorites and getting alerts, and Casey-as-operator wearing an admin role distinct from the existing process-wide admin password. None of these can be built without a `User` row, a session of some shape, and a route that knows who's asking. Today the entire application is anonymous: every `Provider` profile page (`app/providers/view_models.py:99`) renders the same affordances to every viewer; every chat turn is keyed by an opaque `ChatLog.session_id` string (`app/db/models.py:241`) that is a per-browser chat-memory handle, not an authenticated identity; every contribution is rate-limited by SHA-256 of the requesting IP (`app/api/routes/contribute.py:43-45`) precisely because there is no identity to attribute submissions to.

**Concrete features that depend on having a User identity.** The Provider profile view-model already returns a `viewer_is_owner: bool` flag (`view_models.py:89`) and a `claim_url = f"/claim/{slug}"` (`view_models.py:175`) — both are currently hard-wired off (no route serves `/claim/<slug>`, no caller passes a truthy `viewer_is_owner`). These exist as design placeholders waiting for an account system to flip them on. The pivot §5 Days 14-35 block names "Account-lite v0.1: magic-link email, favorites, alert opt-in" as the gating piece for: (a) the Verified Presence ($79/mo) sponsor package — sponsors can't be sold without a claim flow, and a claim flow can't exist without identified claimants; (b) the favorites retention loop — "save for later" is the cheapest personalization signal the directory has; (c) the future "AI recommendations for me" surface — the vision-statement headline requires *me* to be a knowable user.

**Currently NOTHING has User identity.** Grep confirms no `User(Base)` class anywhere in `app/db/models.py`. No `app/auth/` directory. No `current_user` / `get_current_user` / `login_required` symbols anywhere under `app/` (confirmed by repo-wide grep). No `cookie` references beyond two things: (a) the *admin* session cookie at `app/admin/auth.py:11` (`COOKIE_NAME = "admin_session"`, itsdangerous-signed, single global password from `ADMIN_PASSWORD` env), which is a process-wide gate not a user table; and (b) `app/core/session.py` which is an in-process **chat-memory** dict keyed by an opaque session_id (slots, flow state, onboarding hints), not auth state. The existing admin auth at `app/admin/auth.py` is fine as a precedent for the cookie-signing pattern (itsdangerous is already in `requirements.txt:27`) but is structurally different from what end-users need — there is no row anywhere for `casey@example.com`, only "did the requester present the right password."

**Why the gap matters under the pivot.** Account-lite is Phase 2 in the audit's recommended sequencing (§6 — weeks 10-22) and Days 14-35 in the pivot's product timeline. It blocks Gap 15 (Favorites), Gap 17 (Sponsor claim/edit + analytics), Gap 18 (Labeled sponsor slot — at least the merchant-facing edit path), and Gap 20 (V2 personalization). Until accounts exist, the Provider profile page CC just shipped renders only the *anonymous* view; the merchant claim CTA is decorative; sponsor copy-edit must go through Casey-via-admin-form for every change. Every week without accounts is a week where Verified Presence sales depend on Casey hand-editing every sponsor profile.

---

## §2 Three design options for the auth shape

The Resend magic-link decision (pivot §8.3) locks the *delivery mechanism* but leaves the *session shape* open. The three credible session shapes that follow from magic-link auth are:

### Option A — Magic-link with server-side session table

User enters email on `/login`, server emails a single-use token, user clicks `/auth/callback?token=…`, server validates the token + finds-or-creates a `User` row + inserts a `Session` row + sets a cookie containing the session id. Every subsequent request runs through a middleware that reads the cookie, looks up the session row, and attaches `request.state.current_user`. Logout deletes the session row; expiry is a column on the row.

**Pros:**
- Single source of truth — `sessions` table answers "is this user logged in" with no signature math, no key rotation, no JWT-replay edge cases.
- Trivially revocable — admin force-logout is `DELETE FROM sessions WHERE user_id = X`.
- Debuggable — operator can SQL-query "show me Casey's active sessions" with no decode step.
- Matches the pattern the codebase already half-uses: the admin cookie at `app/admin/auth.py` is the same shape minus the table (because admin is a singleton with no per-row identity).
- Plays well with the audit's Railway constraints (§2 audit §5.x): single-region Postgres, no Redis by default, no separate session store. Session lookups are one indexed SELECT.

**Cons:**
- DB roundtrip on every authenticated request (mitigated by short-lived in-process cache; see §6).
- Migration adds a table and an index. Trivial.

**Fit with stack:** clean. FastAPI middleware + SQLAlchemy + a string primary key + Postgres indexed lookup. Zero new dependencies beyond the Resend SDK and a UUID generator (already used elsewhere — `app/db/models.py:34`).

### Option B — Magic-link with stateless JWT in cookie

User clicks magic-link, callback issues a signed JWT containing `user_id`, `email`, `role`, `expires_at`, stored in an HttpOnly cookie. No `sessions` table; middleware decodes + verifies the JWT on every request.

**Pros:**
- No session-table lookup per request — pure signature verify.
- `python-jose==3.5.0` already in `requirements.txt:50` (currently unused by application code).
- "Stateless" at the auth layer (the rest of the app is plenty stateful).

**Cons:**
- **Revocation is hard.** Can't log a user out server-side without a deny-list table — at which point the "no DB" advantage evaporates.
- **Key rotation is hard.** Rotating the JWT secret invalidates every live session. Need a key-id field + dual-key validation window. Operationally fiddly.
- **Clock-skew bugs.** Token expiry math runs on every request; minor clock drift between Railway and the user's browser surfaces as random 401s.
- **Token bloat.** Cookie carries the user payload on every request. ~1-2 KB per request multiplied by every static asset, every API call.
- **Debugging is worse.** Operator can't easily SQL "show me Casey's active sessions" — has to decode a token.
- The pivot's bootstrapped scale (50-100 users at V1 launch; thousands at the 1k-concurrent-user target the audit §5 calls out) never reaches the scale where JWT's stateless advantage outweighs the operational cost.

**Fit with stack:** plausible but adds complexity the codebase doesn't otherwise need.

### Option C — Magic-link with database-backed token-per-request

No long-lived session. Every page load requires presenting a valid not-yet-used short-lived token; server validates against DB on each request. (This is essentially a "no real session, just continuous magic-link-style verification" pattern.)

**Pros:**
- Maximum security — every request is independently authenticated.
- Cleanest revocation model — there is no session to revoke; tokens auto-expire fast.

**Cons:**
- **Unusable for normal browsing.** Every page-to-page click would require a fresh server-issued token. The user experience is a non-starter for end-users browsing a directory.
- DB hit + token rotation on every request — strictly worse than Option A's single SELECT.
- **Not what anyone means by "magic-link auth."** Magic-link is the *login* mechanism; the session it produces is normal cookie session.

**Fit with stack:** poor. Strawman option, included only because the brief asked for three credible shapes.

---

## §3 Recommendation — Option A (server-side session table)

Ship account-lite as a server-side session table backed by Postgres rows. User clicks magic-link, callback creates a `Session` row, sets a cookie containing the session id, middleware reads the cookie + looks up the row + attaches `request.state.current_user` on every request.

**Why Option A wins:**

1. **Operational simplicity.** One table, one indexed lookup, one revocation path. Casey can debug "why is this user logged out" with a SQL query, not by decoding a token.
2. **Matches existing patterns.** The admin cookie at `app/admin/auth.py:30-41` already uses `itsdangerous.URLSafeTimedSerializer` to sign cookie content. Same library; just sign the session id instead of `{"ok": True}`. The cookie-management primitives are already in `requirements.txt:27`.
3. **Revocation comes free.** Force-logout-everywhere is `DELETE FROM sessions WHERE user_id = X`. JWT (Option B) requires a deny-list table — at which point you've reinvented Option A worse.
4. **Scale headroom is fine.** At the audit's 1000-concurrent-user p99 target (§5.1), a primary-key lookup on `sessions.id` is well under 1ms with the proposed indexes. The audit's *first* scaling concern is DB connection pool exhaustion at ~200 users (§5.1), which both A and B share; Option A doesn't make that worse and Option B doesn't make it better.
5. **No key-rotation footgun.** Rotating the cookie-signing key only requires that signed-but-unverified sessions fall back to DB lookup (the signed body is the session id, not the user payload). With Option B, key rotation invalidates every live session.
6. **The "stateless" myth.** Option B is "stateless at the auth layer" but the application is heavily stateful (Postgres-backed). The only request that genuinely doesn't need DB is `/health` and serving static files — neither of which authenticates anyway. Trading a session-table SELECT for JWT decode saves zero meaningful infrastructure under Railway-single-region.

**The case for not picking Option B.** The single best argument for JWT is "no DB roundtrip on auth." The audit's scaling concerns (§5) make clear that DB pool sizing (Gap 14) and search-index latency (Gap 5) are the bottlenecks, not session lookups. A 0.5ms SELECT on a UUID-keyed index is invisible against a 1-3 second Tier 3 LLM call (`app/api/routes/chat.py` Tier 3 path). Picking B trades a non-bottleneck win for revocation + key-rotation pain.

**The case for not picking Option C.** Already covered — it isn't a real session shape; it's a strawman.

---

## §4 Schema specification

Five new tables. Naming follows the existing models.py convention (`String` UUID primary keys for entity tables; `Integer` autoinc PKs for join tables; `TZAwareDateTime` for any datetime that participates in time-window logic).

### §4.1 `User` model

```python
class User(Base):
    """End-user / merchant / admin identity.

    The primary identifier is `email` (case-insensitively unique). A User
    is created on first successful magic-link login — there is no separate
    "sign up" flow. Role defaults to `end_user`; promotion to `merchant`
    happens implicitly on first verified Claim; promotion to `admin` is
    operator-set via SQL or the admin form.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    # email is lower-cased at write time (see app-layer normalization in §5).
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="end_user")
    # Allowed values: "end_user" | "merchant" | "admin". CHECK constraint.

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Kill switch — admin can flag a user without deleting the row.

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

**Why these fields and not more.** The pivot §5 list deliberately omits profile pages, password change, email change, demographics quiz. Every column above is consumed by V1 routes (claim flow uses `id` + `role`; favorites use `id`; magic-link sender uses `email`; staleness flag uses `last_login_at`). Anything else (avatar, bio, demographic preferences, alerts) is a V2 column add via migration — additive, non-breaking.

### §4.2 `MagicLinkToken` model

```python
class MagicLinkToken(Base):
    """Short-lived single-use token emailed via Resend.

    Token plaintext is never stored — only SHA-256 of the plaintext. On
    callback, server hashes the inbound token and looks it up; this means a
    DB compromise does not yield usable login links. Pattern mirrors the
    submitter_ip_hash convention at app/db/models.py:354.
    """

    __tablename__ = "magic_link_tokens"
    __table_args__ = (
        Index("ix_magic_link_tokens_email", "email"),
        Index("ix_magic_link_tokens_token_hash", "token_hash", unique=True),
        Index("ix_magic_link_tokens_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # email is the lookup key on link-request time. NOT a FK to users — the
    # User row may not exist yet (first-time login creates the user).

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # SHA-256 hex digest of the plaintext token. Plaintext lives only in
    # the emailed URL and in transit.

    expires_at: Mapped[datetime] = mapped_column(TZAwareDateTime(), nullable=False)
    # 15-minute window by default; see §5 + §10 for the open question.

    consumed_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime(), nullable=True)
    # Set on first successful redemption. A token is replay-safe: callback
    # rejects rows where consumed_at IS NOT NULL.

    requested_from_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 of requester IP; same pattern as Contribution.submitter_ip_hash
    # at app/db/models.py:354. For abuse tracking + rate-limit forensics.

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
```

**Why hash the token.** The plaintext exists only in the emailed URL and during the few seconds between click and callback. A DB compromise — say, an accidental backup leak — should not yield usable login URLs. Cost is one `hashlib.sha256` per callback, which is invisible.

**Why no FK to users.** The token-request path doesn't know whether the email is an existing user or a first-time login. Forcing a FK means either pre-creating a stub User row (which means anyone can spam User creation by entering random emails) or branching on existence at every email lookup. Indexed string column is simpler.

### §4.3 `Session` model

```python
class Session(Base):
    """Long-lived authenticated session.

    The session id is the cookie value. Cookie is HttpOnly + Secure + SameSite=Lax.
    Cookie value is signed via itsdangerous (same pattern as admin cookie at
    app/admin/auth.py:30) so a stolen unsigned cookie cannot impersonate.
    Session row is the source of truth for `is logged in`; cookie signature is
    the integrity check.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(TZAwareDateTime(), nullable=False)
    # Default 30 days from created_at. Absolute timeout — not idle-extended
    # in V1 (see §6 rationale).

    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 of the IP that created the session. Used to flag suspicious
    # session resumption from a different /16 — log only; no auto-revocation
    # in V1.

    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 of the User-Agent header that created the session. Same purpose.

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
```

### §4.4 `UserFavorite` model

```python
class UserFavorite(Base):
    """User-saved Provider or Place.

    Polymorphic entity reference via (entity_type, entity_id). Mirrors the
    pattern Sponsor uses for cross-entity references (app/db/models.py:547
    business_id with no DB-level FK + app-layer validation), but with an
    explicit entity_type discriminator and a uniqueness constraint to
    prevent double-favoriting.
    """

    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_user_favorites_user_entity"),
        Index("ix_user_favorites_user_id", "user_id"),
        Index("ix_user_favorites_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False
    )

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # Allowed values: "provider" | "place". CHECK constraint at app layer.
    # Place is included for forward-compat with the Place model design
    # (docs/maintainability/place_model_design.md §4); both entity tables
    # use String UUID PKs so the entity_id column has consistent type.

    entity_id: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
```

**Why a unified table and not `provider_favorites` + `place_favorites`.** The chat-side personalization signal (audit §3.20) and the `/account/favorites` list view both need to enumerate "everything this user saved" in one query. Two tables means two queries + union; one table means one indexed scan keyed by `user_id`. The cost is the application-layer validator that confirms `entity_id` actually resolves in the relevant table — same pattern Sponsor already uses for `business_id` (see audit §3.1 / `app/db/models.py:547`).

### §4.5 Claim model — one unified `Claim` table

```python
class Claim(Base):
    """Business-owner claim on a Provider or Place.

    Unified table with entity_type discriminator (same shape as UserFavorite
    above). A claim is the bridge between User identity and merchant-facing
    edit affordances: claimant submits a claim, Casey verifies via phone /
    in-person / email confirmation, claim flips to `verified`, the
    Provider/Place profile now renders owner-edit UI for that user.
    """

    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_claims_user_entity"),
        Index("ix_claims_user_id", "user_id"),
        Index("ix_claims_entity", "entity_type", "entity_id"),
        Index("ix_claims_status", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False
    )

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # "provider" | "place"
    entity_id: Mapped[str] = mapped_column(String, nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Allowed values: "pending" | "verified" | "rejected". CHECK constraint.

    verification_method: Mapped[str | None] = mapped_column(String(48), nullable=True)
    # Allowed values: "phone_call_initiated_by_us" | "phone_call_initiated_by_them"
    # | "in_person" | "email_confirmation" | "business_card_handoff". Mirrors
    # the existing Provider.verification_method enum semantics (app/db/models.py:115-119)
    # but for claim-time verification rather than catalog-row verification.

    claimed_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    verified_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id"), nullable=True
    )
    # The admin User that verified the claim. NULL for any future
    # automated verification path. In V1 always Casey.
```

**Why unified vs. `ProviderClaim` + `PlaceClaim`.** Same reasoning as UserFavorite: the admin-side review queue ("show me all pending claims") is a single screen; a unified table is one indexed scan. The application-layer entity-type validator runs on insert and is the same shape as the favorites validator — write the helper once, reuse twice. The cost (no DB-level FK to providers/places) is identical to the cost the codebase already accepts for `Sponsor.business_id`.

---

## §5 Auth flow (end-to-end)

The numbered sequence below is the happy-path login. Edge cases follow.

### §5.1 Happy path

1. **User visits `/login`.** Anonymous GET; server renders a single-input form: "Enter your email; we'll send you a sign-in link." No password field.
2. **User submits email; browser POSTs `/api/auth/request-link`.** Server normalizes the email (lower-case, strip whitespace), generates a 256-bit token via `secrets.token_urlsafe(32)`, hashes it with SHA-256, inserts a `MagicLinkToken` row with `email`, `token_hash`, `expires_at = now + 15min`, `requested_from_ip_hash`. The plaintext token is never stored.
3. **Server emails the link via Resend.** Email body contains a single CTA URL: `https://havasu-chat.example.com/auth/callback?token=<plaintext>`. Email is sent via the background-job runner (Gap #7 in the audit; see §9 for the dev-mode fallback when no job runner exists yet).
4. **Server returns a confirmation page.** "Check your email — we sent a link to user@example.com. The link expires in 15 minutes." The page does NOT reveal whether the email already has a User row — same response for first-time and returning emails.
5. **User clicks the link in email; browser GETs `/auth/callback?token=<plaintext>`.** Server hashes the inbound token, looks up `MagicLinkToken` by hash. Conditions all must hold: row exists, `expires_at > now`, `consumed_at IS NULL`. If any fail, render a "this link is expired or already used" page with a "Send me a new link" button.
6. **Server marks the token consumed.** `UPDATE magic_link_tokens SET consumed_at = now WHERE id = ...` runs inside the same transaction as steps 7-8 to prevent races.
7. **Server find-or-creates the User row.** `SELECT * FROM users WHERE email = ? LIMIT 1`; if found, update `last_login_at = now`; if not found, INSERT with `email`, `role = 'end_user'`, default columns. The user's role on first-create is always `end_user` — promotion to `merchant` happens implicitly when their first claim is verified; promotion to `admin` is operator-set via SQL.
8. **Server creates the Session row.** INSERT into `sessions` with `id = uuid4()`, `user_id`, `expires_at = now + 30 days`, `ip_hash`, `user_agent_hash`.
9. **Server signs the session id with itsdangerous and sets a cookie.** Cookie name `hava_session`, value = signed session id, HttpOnly, Secure (in prod), SameSite=Lax, Max-Age = 30 days. Same pattern as `app/admin/auth.py:30` but the signed payload is the session id rather than `{"ok": True}`.
10. **Server redirects** to a post-login destination. Default `/account` if no `next` query-string parameter on the original `/login` request; honored `next` if it's a same-origin path (whitelist by leading `/`, no scheme, no host).
11. **Subsequent requests.** A new middleware reads the cookie, verifies the signature, looks up the session row, checks `expires_at > now`, updates `last_seen_at` (cheap UPDATE; can be debounced to once-per-minute in V2 if needed), and attaches `request.state.current_user`. Routes that need auth use a `require_user()` dependency that 401s when `request.state.current_user is None`.
12. **Logout.** User POSTs `/logout`; server DELETEs the session row + clears the cookie; redirects to `/`.

### §5.2 Edge cases

- **Token expired.** Render an "expired link" page; do not log the user in. Same UI as "already consumed."
- **Token already consumed (replay attempt).** Same UI as "expired." Operator-facing: log the attempt with `requested_from_ip_hash` for forensics.
- **Multiple outstanding tokens for the same email.** Allowed. A user re-requesting a link before clicking the first one shouldn't fail. Each is independent. The most recent one usually wins because users click the most recent email; older ones expire untouched.
- **Email doesn't correspond to an existing User row.** Always allowed at the request-link step. The User row is created on first successful callback (step 7). This is the "implicit first login" recommendation — see §10 Q1 for the operator decision.
- **Session expired during use.** Middleware returns `request.state.current_user = None`; protected routes 401 (API) or redirect to `/login?next=<original-path>` (HTML). User re-runs the magic-link flow.
- **Session cookie present but signature invalid.** Middleware treats it as no cookie. Probably indicates cookie-tampering or a key rotation; no auth.
- **Session cookie present + valid + session row missing or expired.** Middleware treats as no cookie. Clear the cookie on response (avoid the user being stuck in a "looks logged in but isn't" state).
- **User account `is_active = false`.** Middleware treats as no cookie + clears it. Force-logout the user. (V1 has no UI to flip this; SQL only.)
- **Concurrent magic-link requests rate limit.** See §10 Q5 for the open call on the specific cap. Suggested default: 5 per email per hour, 10 per IP per hour.

---

## §6 Session management

**Cookie shape.**

- **Name:** `hava_session` (distinct from `admin_session` at `app/admin/auth.py:11` so the two auth surfaces don't collide).
- **Value:** itsdangerous-signed session id (UUID). Pattern: `URLSafeTimedSerializer(secret_key, salt="havasu-session").dumps(session_id)`. The signature gives us a tamper-detection bit on top of the random UUID.
- **HttpOnly:** yes — XSS-injected JS cannot read the cookie.
- **Secure:** yes in production, off in dev (controlled by `HAVA_COOKIE_SECURE` env or by detecting `RAILWAY_ENVIRONMENT`).
- **SameSite:** Lax. Allows the cookie to ride along on top-level navigations (so the magic-link click works), blocks it on cross-site POSTs (CSRF baseline).
- **Path:** `/`.
- **Domain:** unset (host-only).
- **Max-Age:** 30 days.

**Session lifetime.**

- **Absolute timeout:** 30 days from `created_at`. After 30 days, the user re-runs the magic-link flow. Simple, predictable, no idle-vs-absolute distinction.
- **No idle timeout in V1.** Adding "idle for 7 days = invalid" doubles the state-machine surface for marginal security benefit at the bootstrapped-trust scale. Revisit in V2 if a merchant-self-serve sensitive surface lands.
- **`last_seen_at` is observability, not policy.** Middleware updates `last_seen_at` so the admin "show me active users" view is accurate, but the column doesn't gate access.

**Invalidation paths.**

- **Explicit logout.** DELETE the session row + clear the cookie.
- **Expiry.** Lazy — middleware treats `expires_at < now` as no session. A daily background job (Gap #7 in audit) deletes expired rows to keep the table small.
- **Admin force-revoke.** Admin route DELETEs `WHERE user_id = X`. All that user's devices are logged out on next request.
- **User force-revoke-everywhere.** V2 feature; surface a "log out everywhere" button on `/account`. V1 omits — admin can do it via SQL.

**Where session state lives.**

- **DB only.** No Redis, no in-process cache in V1. The audit (§3.4 Gap 4) recommends Redis comes in via the background-job lane (Gap #7); account-lite ships *before* Gap 7 in the audit's Phase 2 sequencing but doesn't *depend* on it for session storage. The per-request session lookup is a single indexed SELECT on a UUID PK — sub-millisecond.
- **Future:** if `sessions` table grows past ~1M rows or the lookup becomes a hot-path concern, layer a Redis cache on top with a TTL slightly shorter than the session expiry. Out of scope for V1.

---

## §7 Integration points

Where account-lite plugs into the existing app.

- **Provider profile page (`/provider/<slug>`)** — the view-model already exposes `viewer_is_owner: bool` (`app/providers/view_models.py:89`) and `show_claim_cta` / `claim_url` (`view_models.py:87, 95, 175`). The route handler in `app/providers/router.py` becomes responsible for setting `viewer_is_owner = True` iff `request.state.current_user` has a `verified` Claim row for this provider. The template branches on those flags already exist — they're just hard-wired off today. Owner-only affordances render inline (edit hours, edit hero photo, edit service chips) when `viewer_is_owner` is true.

- **Place profile page (`/place/<slug>`)** — same pattern as Provider when the Place model lands per `docs/maintainability/place_model_design.md`. Places are claimable in the same way (e.g., a marina-as-business claiming the marina-as-Place soft-linked row), with the same `Claim` row shape.

- **Category landing pages** — when the Home Services landing page ships, sponsor-related affordances ("Sponsor this category", "Edit your sponsored slot") render only for users with `role in ('merchant', 'admin')`. For anonymous viewers and end-users, the slot is purely informational. This matches the pivot UX direction (Eat & Drink UX spec "No sponsor state").

- **Claim flow** — new route `GET /claim/<entity_type>/<slug>` that is *not* anonymous (redirects to `/login?next=/claim/...` if no current_user). Renders a "Are you the owner of <Name>? Tell us how to verify." form. POST creates a `Claim` row in `pending` status; user sees a "We'll be in touch within 48 hours" page. Admin reviews and flips to `verified` (or `rejected` with a reason).

- **Edit UI** — protected routes (`/provider/<slug>/edit`, `/place/<slug>/edit`) accessible only to users who pass `current_user.role in ('admin',)` OR have a `verified` Claim for that entity. The auth dependency is shared.

- **Favorites** — new routes `POST /api/favorites/toggle` (body: `{entity_type, entity_id}`) and `GET /api/favorites` (list current user's favorites). New page `/account/favorites` renders the list. Heart-icon button on every Provider/Place card calls `/api/favorites/toggle` via fetch; UI flips state optimistically. The chat-side personalization signal that Tier 3 builds (audit §3.6 / §3.20) can include "you've favorited X in this category" as a hint to the LLM context once the favorites table exists.

- **Admin tooling** — the admin password gate at `app/admin/router.py:32-35` (`_guard` calling `verify_admin_cookie`) is a process-wide singleton. Under account-lite, admin routes additionally accept a user-session whose `role == 'admin'`. The transitional approach: keep the existing admin-password cookie as the *primary* admin auth (no operator-side disruption); add user-session admin as a *parallel* auth path so Casey can use the same magic-link flow as everyone else. V2 may consolidate them.

- **Existing `app/core/session.py` chat-memory state** — *unchanged*. That dict (chat slots, flow state, onboarding hints) is keyed by an opaque per-browser session id from the chat UI and has no auth meaning. Account-lite layers on top; the two are orthogonal. If a User is logged in, the chat memory can be cross-referenced with `current_user.id` for personalization signals, but the chat memory's lifecycle is not tied to auth session lifecycle.

---

## §8 Migration strategy

Single Alembic migration adds: `users`, `magic_link_tokens`, `sessions`, `user_favorites`, `claims` tables plus the indexes specified in §4.

The migration is **purely additive**:

- No existing table is touched.
- No data backfill required — there are no existing users to migrate.
- No drop / rename of any column.
- Reversible — `downgrade()` is a five-line `op.drop_table()` sequence.

Indexes to ship with the initial migration:

- `users.email` — unique, indexed.
- `magic_link_tokens.token_hash` — unique, indexed.
- `magic_link_tokens.email` — indexed (lookup on link-request).
- `magic_link_tokens.expires_at` — indexed (background cleanup job range scan).
- `sessions.user_id` — indexed (admin force-revoke).
- `sessions.expires_at` — indexed (background cleanup).
- `user_favorites` — unique on `(user_id, entity_type, entity_id)`; indexed on `user_id` and on `(entity_type, entity_id)`.
- `claims` — unique on `(user_id, entity_type, entity_id)`; indexed on `user_id`, `(entity_type, entity_id)`, `status`.

CHECK constraints to declare at the DB level (operator-curated string enums; same pattern as `ck_providers_verification_method` per `app/db/models.py:115-119`):

- `users.role IN ('end_user', 'merchant', 'admin')`.
- `user_favorites.entity_type IN ('provider', 'place')`.
- `claims.entity_type IN ('provider', 'place')`.
- `claims.status IN ('pending', 'verified', 'rejected')`.
- `claims.verification_method` — when not NULL, in the enumerated set per §4.5.

---

## §9 Resend integration

**Operator-side setup (Casey).** Casey signs up at resend.com, verifies the sending domain (DNS records on the hava-chat domain — SPF, DKIM), creates an API key scoped to "send emails," and provisions a "transactional" template called `magic-link-v1` containing the CTA URL placeholder. Sender identity is `Hava <noreply@havasu-chat.example.com>` or whatever Casey-locked.

**App-side setup.** New env vars:

- `RESEND_API_KEY` — the secret.
- `RESEND_FROM_ADDRESS` — the verified sender.
- `AUTH_MAGIC_LINK_BASE_URL` — public origin to embed in the link (so dev/staging/prod each issue links to themselves).
- `AUTH_DEV_MODE` — when truthy (`1`, `true`, `yes`, `on`; same convention as `RATE_LIMIT_DISABLED` per `app/core/rate_limit.py:17-19`), the app *skips* the Resend API call and prints the magic-link URL to logs at INFO level. This lets local dev work without burning Resend credits or requiring a real email account.

**Code module.** New `app/auth/email_sender.py` with a single function `send_magic_link(email: str, token_plaintext: str) -> None`. Internally branches on `AUTH_DEV_MODE`; in dev, logs; in prod, POSTs to Resend's `/emails` endpoint. Failures bubble up to the route handler, which 502s with a generic "couldn't send email; please try again" message — never exposing the underlying error to the user.

**Queueing.** Per audit §3.7 (Gap 7), background-job infrastructure is a separate lane. Account-lite ships *before* that lane; in the interim, the Resend call runs synchronously inside the `/api/auth/request-link` handler. Worst case: a 200ms outbound HTTP call extends request latency. Acceptable for V1 login traffic (low volume). Once Gap 7 ships, the email send moves to a queued job and the route returns immediately.

**Rate-limiting the email send.** See §10 Q5. The slowapi limiter already shipped (`app/core/rate_limit.py`) can gate `/api/auth/request-link` by IP. A second per-email gate (insert into `magic_link_tokens` only if `count(*) WHERE email = ? AND created_at > now - 1h < N`) prevents an attacker from spamming a user's inbox.

**Test email recipients.** During local dev with `AUTH_DEV_MODE=true`, logs print the link; Casey copy-pastes. For end-to-end testing with real Resend, suggest a hardcoded `casey-test@…` whitelist that bypasses production rate limits — implemented as a small env var `AUTH_DEV_EMAIL_ALLOWLIST=email1,email2` checked at request-link time.

---

## §10 Open questions for Casey

1. **User-creation on first login: implicit or explicit?** Recommendation: **implicit** — any valid email that completes the magic-link callback creates a User row. Friction-free, matches Substack / Notion / most modern magic-link products. The cost is that a typo'd email creates an orphan row that never logs in again (cheap; cleanup is a quarterly admin sweep). The alternative — admin pre-creates User rows, only allowlisted emails can sign in — is appropriate for an invite-only beta and adds operator friction every time a real merchant wants to claim. Recommend implicit.

2. **Session lifetime: 30 days, or different?** Recommendation: **30 days absolute**, no idle timeout. Long enough that a merchant who logs in once a month stays logged in; short enough that an abandoned device session doesn't live forever. Alternatives worth considering: 14 days (more conservative) or 90 days (more convenient). Worth a Casey gut-check.

3. **Email content: should magic-link emails include device + IP / approximate-location info?** "You signed in from Lake Havasu City, AZ on Chrome / Mac." Recommendation: **not in V1**. Adds complexity (IP-to-city lookup, IP geolocation service signup, privacy-doc updates), low security benefit at the bootstrapped scale. Add in V2 if account-takeover becomes a real concern.

4. **Claim verification process: V1 manual = Casey calls the business and confirms?** Recommendation: **yes, V1 manual.** The `verification_method` enum on `Claim` (§4.5) is shaped to support the eventual mix: `phone_call_initiated_by_us`, `phone_call_initiated_by_them`, `in_person`, `email_confirmation`, `business_card_handoff`. V1 is "Casey calls or visits; flips the row to `verified` in the admin form." V2 might add automated paths (IVR phone confirmation, business-card photo OCR). Confirm V1 manual is fine.

5. **Rate-limit on magic-link requests per email and per IP.** Suggested defaults: **5 per email per hour**, **10 per IP per hour**, **30 per IP per day**. Tight enough to prevent inbox-spam abuse; loose enough that a legitimate user who keeps mis-typing their email isn't locked out. Casey may want stricter or looser; recommend these as starting numbers and adjust based on actual abuse signal.

6. **Cookie `hava_session` name and prefix.** Recommendation: literal `hava_session`. Distinct from `admin_session` so the two auth surfaces don't collide if Casey is signed in as both admin and end-user (which is normal for an operator). Alternative: `__Host-hava_session` with the `__Host-` prefix for additional browser-side security (requires Secure, Path=/, no Domain). Worth doing in production; adds local-dev friction (the prefix mandates `Secure`, so localhost over HTTP doesn't get the cookie). Recommend `hava_session` for V1 and revisit prefix in V2.

7. **Should admin role be settable via the admin UI, or SQL-only?** Recommendation: **SQL-only for V1.** The blast radius of an accidental admin-promotion bug is high (admin can mutate any catalog row). Operator-only via SQL is fine for a 1-3 admin org. Add admin-UI controls in V2 with confirmation prompts and an audit log.

8. **`/login` UX details — single page with email input, or one-step popover?** Recommendation: **dedicated `/login` page** with a single email input + a "Send sign-in link" button + privacy/terms links. Same shape as `app/admin/router.py:444` admin login form (which is HTML POST → cookie set). Keeps the failure / "check your email" / "expired link" flows all on a real page rather than embedded in a popover. V2 can layer a popover login on top of category pages for low-friction in-context auth.

---

## §11 Effort estimate

Sub-lanes and effort sizing (mirrors the place-model memo's `S` / `M` / `L` shape):

- **Schema migration + ORM models (`User`, `MagicLinkToken`, `Session`, `UserFavorite`, `Claim`):** S (hours). Five tables, all additive, no backfill. Pattern-match to existing models.

- **Auth flow routes (`GET /login`, `POST /api/auth/request-link`, `GET /auth/callback`, `POST /logout`):** M (1-2 days). Four routes, two templates, the find-or-create-User + Session-row + cookie-set logic, error pages for expired/consumed/invalid tokens.

- **Session middleware + `require_user()` dependency:** S (hours). One middleware reads cookie + verifies signature + looks up session + attaches `request.state.current_user`. One FastAPI `Depends` that 401s when current_user is None.

- **Resend integration + email template + dev-mode fallback:** S (hours of dev work, plus Casey's operator-side Resend signup + DNS verification — separate operator-time effort).

- **Login + logout UI templates (`login.html`, `login_check_email.html`, `login_expired.html`):** S (hours).

- **Claim flow + edit affordances on Provider page:** M (2-3 days). New `/claim/<entity_type>/<slug>` route, claim form, claim-submitted confirmation page, admin review queue for pending Claims, `verified`-status branch on Provider profile to flip `viewer_is_owner`. The view-model already exposes the flag (`app/providers/view_models.py:89`); plumbing it through the route handler is the main work. Edit UI itself (the merchant-facing edit form) is its own scope and probably runs as a follow-up lane after the basic claim flow is verified.

- **Favorites UI + API:** M (1-2 days). Two routes, one page (`/account/favorites`), heart-icon JS on Provider/Place cards. Cheap; small surface.

- **Admin-role gating on `/admin/*`:** S (hours). Parallel-path the new role check next to the existing admin-cookie path. Both work; admin-cookie remains primary until V2 consolidates.

- **Tests:** M (1-2 days). Schema tests (5 models), auth flow tests (request-link → email → callback → session created), middleware tests (cookie present/absent/invalid/expired), favorites tests, claim flow tests, edge-case tests (token replay, expired token, force-revoke, admin role).

**Total: roughly 7-10 engineering days of focused work**, dispatchable as 2-3 Cursor or CC lanes. Maps to the audit's "L effort (1-2 weeks)" classification at Gap #8, on the low end.

---

## §12 Sequencing implications

Account-lite is **Phase 2 lane 7** in the audit's recommended sequencing (`architecture_gaps_for_full_vision_audit.md` §6, weeks 10-22). In the pivot's product timeline it lands in **Days 14-35** (pivot §5).

Within Phase 2, account-lite's order relative to its neighbors:

- **Ships AFTER:** background-job infrastructure (Gap #7) **ideally** — once Gap #7 lands, magic-link emails queue via RQ/Redis instead of synchronous HTTP. But the audit's sequencing has Gap #8 listed before Gap #7 in §6 ordering; per §9 of this memo, account-lite can ship before Gap #7 with a synchronous Resend send and migrate to queued later.
- **Ships AFTER:** the Provider profile page (already in flight per STATE.md). The `viewer_is_owner` flag plumbing depends on the view-model that the profile page introduces.
- **Ships BEFORE:** the Verified Presence ($79/mo) sponsor sales push — no sales without a claim flow.
- **Ships BEFORE:** favorites (Gap #15) — favorites depend on User identity.
- **Ships BEFORE:** any V2 personalization (Gap #20 in audit) — same dependency.

If schema migrations are batched into one "Phase 2 schema landing" PR (Place model + account-lite + image storage), all three can ship as a single Alembic migration with related but independent ORM additions. This is preferable to three separate migrations because Alembic's serial-migration ordering on a single-region Postgres is one of the rougher operational footguns; combining additive migrations reduces the deploy steps. The implementation lane should confirm with the Place model design memo author and the image-storage lane author whether batching is preferable.

---

## §13 What we explicitly DON'T build in v0.1

Calling these out so the implementation lane doesn't over-scope.

- **Password authentication.** Magic-link only. No password column, no password reset, no password change. Pivot §8.3 locked this.
- **OAuth (Google / Apple / Facebook / etc.).** Not in v0.1. Magic-link is the only path. Adding OAuth is V2 if and only if user research surfaces a demand we don't see today.
- **Password reset.** No passwords → nothing to reset. If a user "forgets" how to sign in, they just re-enter their email and click the new magic link.
- **Account deletion UI.** Users can't self-delete in V1. Admin can delete via SQL (`DELETE FROM users WHERE id = ?` cascades through claims/favorites/sessions). Add a self-serve "delete my account" button in V2 with the GDPR/CCPA wording the privacy doc needs.
- **Email verification beyond the magic-link itself.** The magic-link click *is* the verification — the user proved they own the email. No separate "click here to verify" step.
- **Two-factor / MFA.** Not in V1. The magic-link itself is a possession factor (must control the inbox); adding a second factor for a directory product is over-built.
- **Profile pages for end-users.** No `/user/<slug>` public page. End-users are invisible to other end-users. (Merchants are visible via their claimed Provider/Place pages; that's enough.)
- **User-to-user features (messaging, follows, social graph).** Not part of the product vision at any phase.
- **Email change flow.** A user's `email` is treated as immutable in V1. If they need a different email, admin can update via SQL (one-off). Add a self-serve email-change flow in V2 — it's a real surface (token-email-to-new-address + confirm-from-old-address pattern) and not worth the cost in V1.
- **Display-name change UI.** Admin-only via the admin form in V1. The `display_name` column is settable but not user-editable; defer the self-serve edit to V2.
- **"Log out everywhere" UI.** Admin-only via SQL in V1.
- **Demographic preferences quiz.** Audit §3.20 V2 surface. The `User` schema in §4.1 deliberately omits `demographic_preferences` JSON — additive in V2.
- **Alerts opt-in UI.** Pivot §5 names "alerts" as part of the V0.1 scope but the audit treats alerts as a separate feature lane after Gap #7 (background jobs) lands. Add a `User.alert_opt_in_at` column in V2 when the alerts surface actually ships; don't add it dormant in V1.
- **Per-user rate limiting.** The slowapi IP-keyed limit (`app/core/rate_limit.py:22`) plus per-email caps on magic-link requests (§9) cover V1 needs. Per-user-id rate limits are V2.
- **Audit log of admin actions.** Recommended but out of scope. Useful for V2 when admin-role-via-UI ships.

---

## §14 Summary

Account-lite is the second-biggest schema gap in the audit and the gating piece for the entire merchant-facing half of the pivot product. The design is straightforward — three core tables (`users`, `magic_link_tokens`, `sessions`), two cross-entity tables (`user_favorites`, `claims`), one new middleware, one synchronous Resend integration, and a small set of new routes (`/login`, `/api/auth/request-link`, `/auth/callback`, `/logout`, `/claim/<…>`, `/account/favorites`). Option A (server-side session table) is the right shape: operationally simple, debuggable, matches the existing admin-cookie precedent, no JWT key-rotation footgun. Total effort 7-10 engineering days; sequenced into Phase 2 of the build after the Provider profile page is in flight and before the Verified Presence sponsor sales push. Eight open questions for operator decision; most have a clear recommendation in §10 with the operator's call needed only on the exact numeric defaults (session lifetime, rate-limit thresholds).

**Next step after this memo is reviewed:** lock the eight open questions, then file a Cursor or CC dispatch brief for the schema migration + ORM models (§4) + auth flow routes (§5.1) + session middleware (§6). Resend operator-side setup (§9) is a parallel Casey-time task that does not block the implementation lane.
