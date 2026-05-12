# Cursor Brief — Phase 2A: Account-lite v0.1 (magic-link auth + claims + favorites)

> **Operator note:** paste this brief to a fresh Cursor chat. **This is the first lane of Phase 2 of the master build plan** (`docs/maintainability/master_build_plan.md` §4 Phase 2). Phase 1 (unified ENTITY schema foundation) is SHIPPED on origin (HEAD `4a5ee246`, alembic head `f8e9d0c1b2a3`). Phase 2A is file-disjoint from Lane 2B (image storage + search) per dispatch_protocol Rule 3 — both lanes can dispatch concurrently, though this brief assumes 2A goes first.
>
> The brief is structured around **three explicit sub-phase boundaries (Phase 2A.1 schema, 2A.2 auth flow, 2A.3 claim + favorites + close-out)**, each independently committable + pytest-green. **You are expected to HALT and report after each sub-phase so the operator can commit before you proceed.** Each sub-phase is sized to one Cursor session. Authored by Cowork primary at session-17 boot from `docs/maintainability/account_lite_v01_design.md`, `docs/maintainability/master_build_plan.md` §4 Phase 2, and the Phase 1 brief shape (`outputs/cursor_brief_phase_1_entity_schema.md`).
>
> **Operator prereq:** Resend account + sender domain + API key dropped into Railway as `RESEND_API_KEY` (see `outputs/operator_prereqs_phase_2.md` §1). The brief is authored against the stable Resend public API shape; the exact env var names (§7 below) are the canonical names — if the operator's Railway config uses different names, halt + report at §0.

---

## §0 Baseline confirmation (do this FIRST and report before touching code)

Before any edits, confirm and report:

1. `git log --oneline -5` — top of `main` should top at **`4a5ee246`** ("docs(outputs): patch session-17 boot prompt SHAs to current origin head"); next four are `dcf2f7a` (operator prereqs guide), `4bb74bc` (gotcha #13), `03f7160` (session-16 handoff + boot prompt), `1c98365` (STATE session-16 close-out). The session-16 handoff doc + boot prompt may both reference an older expected HEAD (`dcf2f7a`) — `4a5ee246` is one docs-only commit on top of that. Report the actual top-5 SHAs.
2. `git status` — should be clean.
3. `python -m pytest -q --collect-only 2>&1 | tail -3` — collected count should be **≥1518** tests (Phase 1 close-out baseline). Treat 1518 as floor, not exact.
4. `python -m alembic heads` — single head **`f8e9d0c1b2a3`** (Phase 1D legacy entity_id NOT NULL flip).
5. `python -m alembic current` — should match head when local SQLite is clean. If you see `(mergepoint)` on an unexpected revision, **don't alarm** — chain-walk down_revision via `grep ^down_revision alembic/versions/*.py` first. Local dev SQLite drift is benign per dispatch_channels.md gotcha #10.
6. **Read these five docs end-to-end before writing any code:**
   - `docs/maintainability/account_lite_v01_design.md` (the design memo this brief implements — every schema field + auth flow + decision in §10 is locked here; this brief points at it constantly)
   - `docs/maintainability/master_build_plan.md` §4 Phase 2 (the deliverables checklist + the explicit "user_favorites and claims now point to entities.id" amendment vs the design memo's original provider/place pointers)
   - `outputs/cursor_brief_phase_1_entity_schema.md` §10 + §11 + §12 + §13 (the brief-shape precedent — Postgres portability rules in §10, deviation guardrails in §11, risk register in §12, final report format in §13; mirror that voice + density)
   - `docs/maintainability/dispatch_protocol.md` (12 working-agreement rules — anchored Edit on shared files; no `git add` until explicit report; sequential lanes when files overlap)
   - `outputs/operator_prereqs_phase_2.md` §1 (Resend env vars + dev-mode fallback)
7. **Read these source files** so you have current line offsets for the anchored edits in §5–§8:
   - `app/db/models.py` end-to-end (~970 lines; you'll append five new model classes — `User`, `MagicLinkToken`, `Session`, `UserFavorite`, `Claim` — at the bottom alongside the existing Phase 1 Entity + extension classes; `Entity` is at line ~624, extensions follow)
   - `app/admin/auth.py` (46 lines; the itsdangerous cookie precedent — `URLSafeTimedSerializer` with salt, signed payload, `verify_admin_cookie` / `sign_admin_cookie`. Your new `app/auth/session.py` mirrors this shape with `havasu-session` salt instead of `havasu-admin-session`)
   - `app/admin/router.py` (the admin-form precedent — login form rendering, cookie-set on success, cookie-clear on logout, `_guard` dependency calling `verify_admin_cookie`)
   - `app/main.py` end-to-end (~416 lines; you'll add new router includes for `app/auth/routes.py` and possibly `app/account/router.py`; you'll also add the session middleware to the FastAPI app)
   - `app/providers/router.py` + `app/providers/view_models.py` (the `viewer_is_owner: bool = False` flag at view_models.py:92 + `claim_url=f"/claim/{slug}"` at :178 are pre-built hooks for this lane — they exist but are hard-wired off today; you flip them on in Phase 2A.3)
   - `app/core/rate_limit.py` (23 lines; slowapi `limiter` + `RATE_LIMIT_DISABLED` env; you'll use the same limiter for the /api/auth/request-link IP + email caps in §6)
   - `app/templates/` directory listing (`chat.html`, `home.html`, `provider_profile.html`, etc. — the Jinja2 templates dir; your three new login templates land here)
   - `tests/conftest.py` (test-session fixtures + dev DB cleanup — your new auth tests will use the same fixture patterns)
8. Report all baseline values + confirm reads complete. Only then proceed to §1.

If any baseline value mismatches, any file has materially moved from these descriptions, or the operator hasn't confirmed Resend setup yet (env vars `RESEND_API_KEY` and `RESEND_FROM_ADDRESS` exist in `.env` or Railway), **HALT and report** before proceeding.

---

## §1 Why this lane exists

The directory currently has **zero User identity**. Every Provider profile renders the same affordances to every viewer; every chat turn is keyed by an opaque per-browser session_id with no auth meaning; every contribution is rate-limited by IP-hash precisely because there's no user to attribute submissions to. Repo-wide grep confirms no `User(Base)` class, no `app/auth/` directory, no `current_user` / `login_required` symbols anywhere under `app/`. The Provider profile view-model already exposes a `viewer_is_owner: bool` flag (`app/providers/view_models.py:92`) and a `claim_url = f"/claim/{slug}"` (`view_models.py:178`) — both are decoratively present, waiting for an account system to flip them on.

Account-lite gates the entire merchant-facing half of the pivot product:

- **Verified Presence ($79/mo) sponsor sales** require a claim flow; a claim flow requires identified claimants
- **Favorites + alert opt-in** require a User row
- **Future "AI recommendations for me"** require a knowable user (currently the chat is anonymous)
- **Future merchant-self-serve edit UI** requires a verified claim binding User to Provider

**Texture rule reminder:** every existing chat-route response, every anonymous Provider profile render, every Tier 2 catalog lookup must produce **identical output for anonymous users** after Phase 2A as before. The new login/claim/favorite affordances are additive surfaces visible only to authenticated users. This is a feature ship for *signed-in* viewers; a zero-change ship for *anonymous* viewers.

---

## §2 Locked decisions (do not relitigate)

| # | Locked answer | Source |
|---|---|---|
| Auth shape | **Option A — server-side session table.** Long-lived `sessions` row indexed by cookie value; itsdangerous-signed cookie carries session id; middleware reads cookie + looks up session + attaches `request.state.current_user`. NOT JWT (Option B) — revocation + key rotation footguns + zero throughput win at our scale. | Design memo §3 |
| Five new tables | `users`, `magic_link_tokens`, `sessions`, `user_favorites`, `claims`. Names + columns locked in §4. | Design memo §4 + master plan §4 Phase 2 |
| **`user_favorites` + `claims` FK to `entities.id`, NOT to `providers.id` / `places.id`** | Phase 1's ENTITY schema unified the polymorphic target. The design memo predates Phase 1's ship; master plan §4 Phase 2 explicitly amends to "user_favorites (now points to entities.id), claims (now points to entities.id)." Polymorphic-via-discriminator (`entity_type` column on UserFavorite/Claim) is dropped — the discriminator already lives on the `entities` row itself. App-layer validation: insert path looks up `entities.id` + asserts `entities.entity_type IN ('commercial', 'place')` for claims; `IN ('commercial', 'place', 'event')` for favorites. | Master plan §4 Phase 2 Lane 2A bullets |
| Magic-link plaintext never stored | Only SHA-256 of plaintext (`MagicLinkToken.token_hash`). Plaintext lives in the emailed URL + in transit. Same precedent as `Contribution.submitter_ip_hash` at `app/db/models.py:354`. | Design memo §4.2 |
| Cookie shape | `hava_session`; HttpOnly + Secure (prod) + SameSite=Lax; itsdangerous-signed with salt `havasu-session`; 30-day Max-Age + absolute expiry (no idle timeout in V1). Distinct cookie name from existing `admin_session` to avoid collision. | Design memo §6 + §10 Q6 |
| User-creation: implicit on first successful callback | Find-or-create User row in step 7 of the happy path. Role defaults to `end_user`; promotion to `merchant` is implicit on first verified claim; promotion to `admin` is SQL-only in V1. | Design memo §10 Q1 + Q7 |
| Session lifetime: 30 days absolute, no idle timeout | Simple, predictable. Revisit in V2 if account-takeover becomes a real concern. | Design memo §10 Q2 |
| Email content: no device/IP/location info in V1 | Body is a CTA URL + plain text. Add device fingerprint in V2 if needed. | Design memo §10 Q3 |
| Claim verification: manual in V1, Casey calls or visits | `Claim.verification_method` enum supports the eventual mix; V1 just flips rows to `verified` via the admin form. | Design memo §10 Q4 |
| Magic-link rate limits | 5 per email per hour; 10 per IP per hour; 30 per IP per day. Apply via slowapi (IP cap) + per-email DB count check (email cap). | Design memo §10 Q5 |
| `/login` UX: dedicated page, single email input | Not a popover in V1. Mirrors `app/admin/router.py:444` admin login form shape. | Design memo §10 Q8 |
| Resend integration: synchronous send in V1 | Gap #7 (background-job infra) ships later; until then, Resend POST runs inside the `/api/auth/request-link` handler. ~200ms outbound latency acceptable at V1 login volume. | Design memo §9 + audit §3.7 |
| `AUTH_DEV_MODE` env flag | Same convention as `RATE_LIMIT_DISABLED` in `app/core/rate_limit.py:17-19`. Truthy values: `1`, `true`, `yes`, `on`. When truthy: skip Resend call + log magic-link URL at INFO level. | Design memo §9 + this brief §7 |
| Admin-role auth: parallel-path the existing admin cookie | Keep `admin_session` cookie as primary admin auth (no operator-side disruption). Add `current_user.role == 'admin'` as a parallel-accepted auth path. V2 may consolidate. | Design memo §7 |
| `viewer_is_owner` plumbing | View-model already exposes the flag; Phase 2A.3 wires the route handler to set it to `True` iff `request.state.current_user` has a `verified` Claim for the Provider's `entity_id`. | Design memo §7 + view_models.py:92 |
| Sub-phase commit boundaries | Three sub-phases (2A.1 schema + Resend scaffold / 2A.2 auth flow + middleware / 2A.3 claim + favorites + admin role + close-out). Each ships green pytest. Operator commits each. | This brief §3 |

---

## §3 Sub-phase boundaries (the rhythm of this lane)

This lane will not ship in one session. The work splits into three sub-phases, each independently shippable + pytest-green. Halt-and-report after each.

### Phase 2A.1 — Schema + ORM + Resend module scaffold (target: 2-3 days)

Add `users`, `magic_link_tokens`, `sessions`, `user_favorites`, `claims` tables. Add `app/auth/__init__.py` + `app/auth/email_sender.py` with `send_magic_link()` (Resend-or-dev-log) but **no route wiring yet**. Pytest stays green at 1518+; new tests pin schema shape + relationships + `send_magic_link` dev-mode behavior. Alembic head advances by one migration. **Zero app-layer route changes. Zero behavior change.**

**Acceptance:** new tables exist; foreign keys defined (User has unique email index; UserFavorite + Claim FK to `entities.id` with `ondelete="CASCADE"`); CHECK constraints land (role, status, verification_method); relationships navigable on the ORM; new tests pin every column type + nullable + uniqueness; `send_magic_link("x@example.com", "tok")` with `AUTH_DEV_MODE=1` logs the magic URL without raising; no chat-route or Provider-profile behavior change.

### Phase 2A.2 — Auth flow + session middleware + login UI (target: 3-4 days)

The biggest sub-phase. New `app/auth/routes.py` with the four auth routes. New `app/auth/session.py` with cookie sign/verify + session middleware + `require_user` dependency. New `app/auth/email_template.py` (or inline HTML in `email_sender.py`) for the magic-link email body. Three new login templates. Rate limits on `/api/auth/request-link`. Wire session middleware into `app/main.py`. Register new auth router.

**Acceptance:** end-to-end flow works against dev DB — POST /api/auth/request-link → log shows magic URL (dev mode) → click → callback creates User + Session rows → cookie set → /account renders "logged in as user@example.com" → POST /logout deletes session row + clears cookie. Replay-protection: hitting `/auth/callback?token=X` twice second-time renders "expired or already used" page without creating a new session. Expired tokens render the same page. Invalid signatures treated as anonymous. Middleware sets `request.state.current_user` for valid sessions, `None` for missing/expired/invalid. `require_user()` dependency 401s API routes + redirects HTML routes to `/login?next=<path>`. Pytest stays green; new tests cover happy path + 6 edge cases from design memo §5.2. Rate limit blocks the 6th magic-link request from the same email in one hour with a friendly "slow down" message.

### Phase 2A.3 — Claim flow + favorites + admin role + close-out (target: 2-3 days)

New `/claim/<slug>` route (slug is the Entity.slug; V1 only accepts `commercial` entities — Place ships later). New claim-submitted confirmation page. Admin claim review queue (simple list of pending Claims with verify / reject buttons). New `/api/favorites/toggle` + `/api/favorites` endpoints. New `/account` page (current user + logout link) + `/account/favorites` page. Heart-icon JS on Provider profile + Tier 2 cards calls `/api/favorites/toggle`. Wire `viewer_is_owner` flag through `app/providers/router.py` (lookup Claim for current_user.id + entity_id; flip flag iff `status == 'verified'`). Parallel-path admin role: `app/admin/router.py::_guard` accepts EITHER existing admin cookie OR `current_user.role == 'admin'`.

**Acceptance:** signed-in user submits a claim → row created with status `pending` → admin (via existing admin form OR new role==admin user-session) sees the claim in `/admin/claims` → clicks "Verify" → row flips to `verified` + verified_by + verified_at + verification_method set → user reloads `/provider/<slug>` → `viewer_is_owner=True` + owner-edit affordances render (or at minimum the flag is set; the edit UI itself is out of scope per design memo §11). Favorite-toggle creates + deletes UserFavorite rows; `/account/favorites` page lists them. Anonymous users see no /claim or /account routes (redirected to /login?next=...). Anonymous Provider profile renders identically to pre-Phase-2A. Pytest stays green; new tests cover claim flow, favorites, admin role gating, viewer_is_owner integration, anonymous-user-isolation regression.

### Important — phase boundary etiquette

After completing each sub-phase:

1. Confirm `python -m pytest -q` is green and report final count.
2. Confirm `python -m ruff check .` is clean.
3. Confirm `python -m alembic upgrade head` applies cleanly against a fresh dev DB.
4. Produce the final report per §13 for THAT sub-phase only.
5. **STOP. Do not start the next sub-phase.** Operator commits the current sub-phase and re-dispatches you (likely in a fresh session) for the next.

If you discover mid-sub-phase that the scope is bigger than estimated, **halt early** and report what's done + what's outstanding. Do not push past a half-broken state to "make progress."

---

## §4 Target schema in detail

Five new tables. Naming follows the existing models.py convention (`String` UUID PKs for entity tables; `Integer` autoincrement PKs for join tables; `TZAwareDateTime` for any datetime that participates in time-window logic per `app/db/models.py:114` precedent). Field types + nullability + FK shapes are LOCKED — downstream V2 phases reference them.

**Postgres portability**: every Boolean default uses `sa.true()` / `sa.false()` (NOT `sa.text("1")` / `sa.text("0")`); every timestamp default uses `sa.func.now()` (NOT `sa.text("CURRENT_TIMESTAMP")`); no raw SQL inside `op.execute()` unless verified portable. This rule is absorbed from session-15's Phase 1A hotfix lesson — see brief §10.

### §4.1 `User` model — append to `app/db/models.py`

```python
class User(Base):
    """End-user / merchant / admin identity.

    Created on first successful magic-link callback. Role defaults to
    'end_user'; promoted to 'merchant' implicitly on first verified Claim;
    promoted to 'admin' SQL-only (V1) — design memo §10 Q7.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('end_user', 'merchant', 'admin')",
            name="ck_users_role",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    # email is lower-cased at write time — see normalize helper in app/auth/email_helpers.py.
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="end_user", server_default="end_user"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

### §4.2 `MagicLinkToken` model

```python
class MagicLinkToken(Base):
    """Short-lived single-use token emailed via Resend.

    Plaintext is never stored — only SHA-256 of plaintext lives in DB. Pattern
    mirrors Contribution.submitter_ip_hash at app/db/models.py:354.
    """

    __tablename__ = "magic_link_tokens"
    __table_args__ = (
        Index("ix_magic_link_tokens_email", "email"),
        Index("ix_magic_link_tokens_token_hash", "token_hash", unique=True),
        Index("ix_magic_link_tokens_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # NOT a FK to users — User row may not exist at request-link time
    # (first-time login creates the row on successful callback).
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # SHA-256 hex digest of plaintext token. 64 chars.
    expires_at: Mapped[datetime] = mapped_column(TZAwareDateTime(), nullable=False)
    # 15 minutes from created_at by default.
    consumed_at: Mapped[datetime | None] = mapped_column(
        TZAwareDateTime(), nullable=True
    )
    requested_from_ip_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
```

### §4.3 `Session` model

```python
class Session(Base):
    """Long-lived authenticated session.

    Cookie name 'hava_session'. Cookie value = itsdangerous-signed Session.id.
    Cookie is HttpOnly + Secure (prod) + SameSite=Lax. Session row is the source
    of truth for 'is logged in'; signature is the integrity check.

    Mirrors the admin-cookie pattern at app/admin/auth.py:30 but signs a session
    id (UUID) instead of {"ok": True}.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(TZAwareDateTime(), nullable=False)
    # 30 days from created_at. Absolute, no idle-extension in V1.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
```

**Naming note:** the model class is `Session` but the table is `sessions`. There's no collision with `sqlalchemy.orm.Session` because the SQLAlchemy session type is always imported under that fully-qualified path in this codebase (search `app/` for `from sqlalchemy.orm import Session` — every call site uses the dotted import). If Cursor surfaces a real collision when adding type hints, rename the model to `AuthSession` and document in §13 deviations. Likely unnecessary but flagged here.

### §4.4 `UserFavorite` model — FK to `entities.id`

```python
class UserFavorite(Base):
    """User-saved Entity (Provider / Place / Event in V1; Programs deferred).

    NOTE: master plan §4 Phase 2 Lane 2A explicitly amended the design memo's
    polymorphic (entity_type, entity_id) shape to a single FK pointing at
    entities.id. Entity.entity_type already discriminates; no duplicate column
    needed. App-layer validation at insert time asserts entity.entity_type
    is in the favoritable set (see app/auth/favorites.py validators).
    """

    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "entity_id", name="uq_user_favorites_user_entity"
        ),
        Index("ix_user_favorites_user_id", "user_id"),
        Index("ix_user_favorites_entity_id", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])
```

**Why no `entity_type` discriminator column.** The Entity row carries it (`entities.entity_type`). Adding it on `user_favorites` would denormalize the discriminator for query-speed but Phase 1's pattern is to JOIN entities when discriminator-filtering is needed. The chat-side personalization signal (audit §3.20) can JOIN entities to filter to a specific entity_type cheaply (indexed on `entities.entity_type` per Phase 1A). Save the denormalization for if/when it becomes a measured bottleneck.

### §4.5 `Claim` model — FK to `entities.id`

```python
class Claim(Base):
    """Business-owner claim on an Entity.

    V1 only accepts entity_type IN ('commercial', 'place') — events + programs
    are not claimable. Validation at insert time. Status flips from 'pending' to
    'verified' (or 'rejected') via the admin review queue. A verified claim is
    the bridge between User identity and merchant-facing edit affordances; the
    Provider profile flips viewer_is_owner to True when current_user has a
    verified claim for that provider's entity_id.
    """

    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "entity_id", name="uq_claims_user_entity"
        ),
        CheckConstraint(
            "status IN ('pending', 'verified', 'rejected')",
            name="ck_claims_status",
        ),
        CheckConstraint(
            "verification_method IS NULL OR verification_method IN ("
            "'phone_call_initiated_by_us', 'phone_call_initiated_by_them', "
            "'in_person', 'email_confirmation', 'business_card_handoff'"
            ")",
            name="ck_claims_verification_method",
        ),
        Index("ix_claims_user_id", "user_id"),
        Index("ix_claims_entity_id", "entity_id"),
        Index("ix_claims_status", "status"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    verification_method: Mapped[str | None] = mapped_column(String(48), nullable=True)
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])
    verifier: Mapped["User | None"] = relationship(
        "User", foreign_keys=[verified_by]
    )
```

### §4.6 Migration shape (single Alembic migration)

`alembic/versions/<rev>_account_lite_v01.py` chains off `f8e9d0c1b2a3`. Five `op.create_table` calls + indexes + CHECK constraints. Reversible — `downgrade()` is five `op.drop_table` calls in reverse order. No data backfill (there's no existing user data to migrate). No touch on existing tables.

Generate a fresh revision id (`alembic revision --autogenerate -m "account_lite_v01"` then fix up the autogen output — autogen sometimes mis-orders constraints; review carefully). If autogen generates `op.create_table` calls in a Postgres-Boolean-incompatible shape (text "0"/"1" defaults instead of `sa.true()` / `sa.false()`), edit before committing. Verify both fresh `alembic upgrade head` and `alembic downgrade -1 && alembic upgrade head` cycle cleanly against the sandbox SQLite DB.

---

## §5 Phase 2A.1 — Schema + ORM + Resend module scaffold (target: 2-3 days)

### §5.1 New file: `app/auth/__init__.py`

```python
"""Account-lite v0.1 — magic-link auth + sessions + favorites + claims.

See docs/maintainability/account_lite_v01_design.md for the design memo;
see outputs/cursor_brief_phase_2a_account_lite.md for the dispatched brief.
"""
```

### §5.2 New file: `app/auth/email_sender.py`

```python
"""Magic-link email sender — Resend in prod, log-only in dev.

AUTH_DEV_MODE env var (truthy values: '1', 'true', 'yes', 'on' — case-
insensitive, same convention as RATE_LIMIT_DISABLED at app/core/rate_limit.py:17)
controls behavior:

- AUTH_DEV_MODE truthy → skip the Resend API call entirely; log the magic-link
  URL at INFO level so dev can copy-paste it.
- AUTH_DEV_MODE falsy → POST to Resend's /emails endpoint with the rendered
  email body. Failures bubble up to the route handler, which 502s with a
  generic 'couldn't send email; please try again' message.

Env vars required for prod:
- RESEND_API_KEY — the secret API key from resend.com.
- RESEND_FROM_ADDRESS — verified sender (e.g., 'Hava <noreply@example.com>').
- AUTH_MAGIC_LINK_BASE_URL — public origin to embed in the link
  (e.g., 'https://havasu-chat-production.up.railway.app').

Optional:
- AUTH_DEV_EMAIL_ALLOWLIST — comma-separated list of emails that bypass
  production rate limits for test recipients (design memo §9).
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"
_DEV_MODE_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _dev_mode_enabled() -> bool:
    v = (os.environ.get("AUTH_DEV_MODE") or "").strip().lower()
    return v in _DEV_MODE_TRUTHY


def _build_magic_link_url(token_plaintext: str) -> str:
    base = (os.environ.get("AUTH_MAGIC_LINK_BASE_URL") or "").rstrip("/")
    if not base:
        raise RuntimeError("AUTH_MAGIC_LINK_BASE_URL not set")
    return f"{base}/auth/callback?token={token_plaintext}"


def _render_email_body(magic_link_url: str) -> tuple[str, str]:
    """Return (html_body, text_body)."""
    text = (
        "Sign in to Havasu Chat\n\n"
        f"Click here to sign in: {magic_link_url}\n\n"
        "This link expires in 15 minutes.\n"
        "If you didn't request this, you can safely ignore this email.\n"
    )
    html = (
        "<!DOCTYPE html><html><body>"
        '<p>Sign in to <strong>Havasu Chat</strong>:</p>'
        f'<p><a href="{magic_link_url}">Click here to sign in</a></p>'
        "<p>This link expires in 15 minutes.</p>"
        "<p>If you didn't request this, you can safely ignore this email.</p>"
        "</body></html>"
    )
    return html, text


def send_magic_link(email: str, token_plaintext: str) -> None:
    """Send the magic-link email (or log it in dev mode).

    Raises RuntimeError on configuration error (missing env vars) and
    httpx.HTTPError on Resend API failure. Route handlers catch + return
    a generic 502.
    """
    url = _build_magic_link_url(token_plaintext)

    if _dev_mode_enabled():
        logger.info(
            "AUTH_DEV_MODE: skipping Resend send — magic link for %s: %s",
            email,
            url,
        )
        return

    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("RESEND_FROM_ADDRESS") or "").strip()
    if not api_key or not from_addr:
        raise RuntimeError(
            "RESEND_API_KEY and RESEND_FROM_ADDRESS must be set in prod"
        )

    html, text = _render_email_body(url)
    payload = {
        "from": from_addr,
        "to": [email],
        "subject": "Sign in to Havasu Chat",
        "html": html,
        "text": text,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=10.0) as client:
        response = client.post(_RESEND_API_URL, json=payload, headers=headers)
        response.raise_for_status()
```

### §5.3 Edit `app/db/models.py` — append new classes

Append all five model classes from §4 at the bottom of `app/db/models.py`, after the existing `SponsorshipSlot` class and the `_register_provider_slug_listeners()` function. Import additions at the top of the file: `from sqlalchemy import CheckConstraint` (verify it's not already imported) and `from sqlalchemy.sql import true` (likely already imported per Phase 1 Entity class at :648). Use anchored Edit, not full-file Write.

### §5.4 New migration `alembic/versions/<rev>_account_lite_v01.py`

Generate via `alembic revision -m "account_lite_v01"` (NOT --autogenerate; hand-write the migration to control Postgres portability). Chain off `f8e9d0c1b2a3`. Five `op.create_table` calls + indexes per §4. **Verify Postgres portability** — every Boolean default uses `sa.true()` / `sa.false()` (NOT `sa.text("1")` / `sa.text("0")`); every timestamp default uses `sa.func.now()` (NOT raw `CURRENT_TIMESTAMP`); CheckConstraints declared at table level via `op.create_table(..., sa.CheckConstraint(...))`.

### §5.5 Tests — new file `tests/test_account_lite_schema.py`

Mirror `tests/test_entity_schema.py` shape (Phase 1A precedent). Tests pin:

1. All five tables exist after `alembic upgrade head`
2. Each model's columns + types + nullability (one parametric test per model)
3. CHECK constraints reject invalid `users.role` / `claims.status` / `claims.verification_method` values
4. Unique constraints on `users.email`, `user_favorites(user_id, entity_id)`, `claims(user_id, entity_id)`, `magic_link_tokens.token_hash`
5. FK ON DELETE CASCADE for sessions/user_favorites/claims when the parent user is deleted
6. FK ON DELETE CASCADE for user_favorites/claims when the parent entity is deleted (CRITICAL — verify this works on SQLite given Phase 1A's `passive_deletes=True` precedent; if cascade fails, follow the Phase 1A pattern at `tests/test_entity_schema.py` for `engine.dispose()` after the cascade test to clear pooled connections)
7. `Session → User` relationship navigates
8. `UserFavorite → Entity` + `Claim → Entity` relationships navigate
9. `Claim → verifier` self-FK navigates (verified_by is a User FK)
10. `User.last_login_at` is nullable + accepts datetime updates

### §5.6 Tests — new file `tests/test_email_sender.py`

1. `send_magic_link` with `AUTH_DEV_MODE=1` logs the URL at INFO level and returns None without making any HTTP call (mock `httpx.Client` and assert no `.post` call)
2. `send_magic_link` with `AUTH_DEV_MODE` unset + `AUTH_MAGIC_LINK_BASE_URL` unset raises `RuntimeError`
3. `send_magic_link` with `AUTH_DEV_MODE` falsy + valid env vars POSTs to Resend with the right payload shape (mock httpx; assert URL, headers, body keys)
4. `send_magic_link` raises on Resend 4xx / 5xx (mock httpx response with `raise_for_status`)

### §5.7 Phase 2A.1 acceptance + commit

After 2A.1:
- pytest count: 1518 + (10–14 new tests) → ~1528-1532
- alembic head advances from `f8e9d0c1b2a3` to your new `account_lite_v01` revision id
- ruff clean
- `python -m alembic upgrade head` against fresh dev DB passes
- ZERO behavior change on chat-route, /provider/<slug>, /home, /admin — verify by running the full pytest suite

HALT here. Produce the §13 report for 2A.1. Operator commits, then re-dispatches for 2A.2.

---

## §6 Phase 2A.2 — Auth flow + session middleware + login UI (target: 3-4 days)

### §6.1 New file: `app/auth/session.py`

Mirrors `app/admin/auth.py:30-41` shape but signs a session id instead of `{"ok": True}`. Provides:

- `sign_session_cookie(session_id: str) -> str` — itsdangerous-sign the session id with salt `havasu-session`. Secret key from `HAVA_SESSION_SECRET` env var, fall back to `ADMIN_PASSWORD` (the same secret-key fallback the admin cookie uses) for dev convenience.
- `verify_session_cookie(value: str | None) -> str | None` — return the unwrapped session id or None on failure.
- `SessionMiddleware` (Starlette `BaseHTTPMiddleware`) — reads the `hava_session` cookie, verifies signature, looks up `Session` row in DB (using a session-scoped factory from `app/db/database.py`), checks `expires_at > now` + `user.is_active == True`, attaches `request.state.current_user` (User row or None) + `request.state.current_session` (Session row or None). On expired/missing/invalid: leaves `current_user = None`. On valid session: also updates `last_seen_at = now` (debounced to once-per-minute to avoid write thrash — store a `_last_seen_update_at` attribute on the in-memory session object).

Constants:

```python
COOKIE_NAME = "hava_session"
COOKIE_SALT = "havasu-session"
MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days
SESSION_LIFETIME_SECONDS = 60 * 60 * 24 * 30
LAST_SEEN_DEBOUNCE_SECONDS = 60
```

Cookie attributes when setting:
- `httponly=True`
- `secure=True` in prod (key off `RAILWAY_ENVIRONMENT` env var presence — same convention as `_init_sentry` at `app/main.py:210`)
- `samesite="lax"`
- `max_age=MAX_AGE_SECONDS`
- `path="/"`
- No `domain` (host-only)

### §6.2 New file: `app/auth/dependencies.py`

```python
"""FastAPI dependencies for auth-gated routes."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.db.models import User


def get_current_user(request: Request) -> User | None:
    return getattr(request.state, "current_user", None)


def require_user(request: Request) -> User:
    user = get_current_user(request)
    if user is None:
        # API routes: 401 JSON; HTML routes: caller catches HTTPException and
        # redirects to /login. The route handler's response_class hint
        # determines the right shape.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="login_required",
        )
    return user


def require_admin(request: Request) -> User:
    user = require_user(request)
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_only")
    return user
```

HTML-route redirect handling: routes that want HTML-redirect-on-401 wrap the dependency in a try/except at handler level — see §6.4 example.

### §6.3 New file: `app/auth/email_helpers.py`

```python
"""Email + token helpers — normalization, hashing, validation."""

from __future__ import annotations

import hashlib
import re
import secrets


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(raw: str) -> str:
    return raw.strip().lower()


def is_valid_email(email: str) -> bool:
    # Lightweight validation — Resend will reject malformed addresses at send
    # time. We just block obvious garbage at the request-link step.
    if len(email) > 320:
        return False
    return bool(_EMAIL_RE.match(email))


def generate_magic_link_token() -> tuple[str, str]:
    """Return (plaintext_token, sha256_hex_hash)."""
    plaintext = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return plaintext, hashed


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def hash_request_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()
```

### §6.4 New file: `app/auth/routes.py`

Four routes. All use `templates = Jinja2Templates(directory=...)` for HTML responses; the `/api/auth/request-link` route is JSON-friendly but renders an HTML "check your email" page on success.

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session as SqlSession

from app.auth.email_helpers import (
    generate_magic_link_token,
    hash_request_ip,
    hash_token,
    is_valid_email,
    normalize_email,
)
from app.auth.email_sender import send_magic_link
from app.auth.session import (
    COOKIE_NAME,
    MAX_AGE_SECONDS,
    SESSION_LIFETIME_SECONDS,
    sign_session_cookie,
)
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.db.models import MagicLinkToken, Session as AuthSession, User

# (... template setup, helper for is-production-secure-cookie ...)

router = APIRouter()
templates = Jinja2Templates(directory=str(...))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    next_path = _safe_next(request.query_params.get("next"))
    return templates.TemplateResponse(
        request=request, name="login.html", context={"next": next_path}
    )


@router.post("/api/auth/request-link")
@limiter.limit("10/hour")
def request_link(
    request: Request,
    email: str = Form(...),
    next: str = Form(""),
    db: SqlSession = Depends(get_db),
) -> HTMLResponse:
    normalized = normalize_email(email)
    if not is_valid_email(normalized):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Please enter a valid email address.", "next": next},
            status_code=400,
        )
    if _email_rate_limit_exceeded(db, normalized):
        # Render the same "check your email" page — never reveal that the
        # email is rate-limited (design memo §5.1 step 4 doctrine: same UI
        # for existing-user / first-time / rate-limited).
        return templates.TemplateResponse(
            request=request, name="login_check_email.html",
            context={"email": normalized},
        )

    plaintext, token_hash = generate_magic_link_token()
    now = datetime.now(timezone.utc)
    db.add(
        MagicLinkToken(
            email=normalized,
            token_hash=token_hash,
            expires_at=now + timedelta(minutes=15),
            requested_from_ip_hash=hash_request_ip(_client_ip(request)),
        )
    )
    db.commit()

    try:
        send_magic_link(normalized, plaintext)
    except Exception:
        # Don't leak the failure to the user — same page as success. Operator
        # sees the exception in logs / Sentry.
        logger.exception("magic-link send failed for %s", normalized)

    return templates.TemplateResponse(
        request=request, name="login_check_email.html",
        context={"email": normalized},
    )


@router.get("/auth/callback", response_class=HTMLResponse)
def auth_callback(
    request: Request, token: str, db: SqlSession = Depends(get_db)
) -> Response:
    token_hash_val = hash_token(token)
    row = (
        db.query(MagicLinkToken)
        .filter(MagicLinkToken.token_hash == token_hash_val)
        .first()
    )
    now = datetime.now(timezone.utc)

    if row is None or row.consumed_at is not None or row.expires_at < now:
        return templates.TemplateResponse(
            request=request, name="login_expired.html", status_code=400, context={}
        )

    # Consume + find-or-create + session create + cookie set, all in one tx.
    row.consumed_at = now
    user = (
        db.query(User).filter(User.email == row.email).first()
    )
    if user is None:
        user = User(email=row.email, role="end_user")
        db.add(user)
        db.flush()
    user.last_login_at = now

    session_row = AuthSession(
        user_id=user.id,
        expires_at=now + timedelta(seconds=SESSION_LIFETIME_SECONDS),
        ip_hash=hash_request_ip(_client_ip(request)),
        user_agent_hash=hash_request_ip(request.headers.get("user-agent")),
    )
    db.add(session_row)
    db.commit()

    signed = sign_session_cookie(session_row.id)
    next_path = _safe_next(request.query_params.get("next")) or "/account"
    response = RedirectResponse(url=next_path, status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=signed,
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        secure=_cookie_secure_in_prod(),
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout")
def logout(
    request: Request, db: SqlSession = Depends(get_db)
) -> Response:
    sess = getattr(request.state, "current_session", None)
    if sess is not None:
        db.delete(sess)
        db.commit()
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response
```

Helper details (`_safe_next`, `_client_ip`, `_cookie_secure_in_prod`, `_email_rate_limit_exceeded`) are inlined or factored into `app/auth/session.py`. `_safe_next` whitelists by leading `/` + no scheme + no `..` to prevent open-redirect. `_email_rate_limit_exceeded` queries `count(*) FROM magic_link_tokens WHERE email = ? AND created_at > now - 1 hour` and returns True if ≥ 5.

### §6.5 New templates — `app/templates/login.html`, `login_check_email.html`, `login_expired.html`

Reuse the visual treatment of `app/templates/home.html` for header/footer/styling (the brand voice already lives there). Three templates:

- `login.html` — single email input, submit button, link to /privacy + /terms. Surfaces `error` and `next` context vars.
- `login_check_email.html` — confirmation copy. Reveals the email (so the user can verify they typed it right). Doesn't reveal whether the email is existing-user / first-time / rate-limited (all paths render the same page per design memo §5.1 step 4).
- `login_expired.html` — "This sign-in link has expired or already been used." Plus a link back to `/login` with a "Send me a new link" CTA.

### §6.6 Wire session middleware into `app/main.py`

Anchored Edit at the FastAPI app construction line (`app = FastAPI(title="Havasu Chat", lifespan=lifespan)` at :267). Add immediately after:

```python
from app.auth.routes import router as auth_router
from app.auth.session import SessionMiddleware

app.add_middleware(SessionMiddleware)
```

And `app.include_router(auth_router)` after the existing `include_router` block.

### §6.7 Tests — new file `tests/test_auth_flow.py`

End-to-end coverage for the four routes plus middleware:

1. `GET /login` renders the login form anonymously; renders with `next=` preserved when present in query string
2. `POST /api/auth/request-link` with valid email creates a `MagicLinkToken` row + renders "check your email" page. `AUTH_DEV_MODE=1` so no real Resend call.
3. `POST /api/auth/request-link` with invalid email returns 400 + error message in form
4. `POST /api/auth/request-link` 6th time in one hour for the same email returns the same "check your email" page but does NOT create a new token row (rate limit silent)
5. `GET /auth/callback?token=<valid>` creates User + Session rows + sets cookie + redirects to /account
6. `GET /auth/callback?token=<valid>` for existing email updates `last_login_at` instead of creating new User
7. `GET /auth/callback?token=<expired>` renders login_expired.html + creates no User/Session
8. `GET /auth/callback?token=<already-consumed>` renders login_expired.html
9. `GET /auth/callback?token=<invalid>` renders login_expired.html
10. `POST /logout` with valid session deletes the session row + clears cookie + redirects to /
11. `POST /logout` anonymously is a no-op (just clears cookie + redirects)
12. Middleware: cookie present + valid signature + session valid → `request.state.current_user` set
13. Middleware: cookie present + valid signature + session expired → `request.state.current_user = None`
14. Middleware: cookie present + INVALID signature → `request.state.current_user = None`
15. Middleware: no cookie → `request.state.current_user = None`
16. Middleware: cookie present + valid signature + session row missing → `request.state.current_user = None` + cookie cleared on response
17. Middleware: `last_seen_at` updates on subsequent requests (debounced — once-per-minute test uses `freezegun` or `monkeypatch` on `datetime.now`)
18. `require_user` dependency 401s when current_user is None
19. `require_admin` dependency 403s when current_user.role != 'admin'
20. `_safe_next` redirects to `/` when next is external (e.g., `https://evil.com`) or contains `..`

Use the existing `tests/conftest.py` fixture patterns; set `AUTH_DEV_MODE=1` in test setup so no real Resend call happens.

### §6.8 Phase 2A.2 acceptance + commit

After 2A.2:
- pytest count: 2A.1 baseline + 20 new tests → ~1548-1552
- `alembic upgrade head` still passes (no new migration in this sub-phase)
- ruff clean
- Manual smoke (operator can run locally): start app with `AUTH_DEV_MODE=1`, visit `/login`, submit email, look at logs for magic-link URL, paste URL in browser, observe redirect to `/account`, observe session cookie set in browser dev tools.
- ZERO behavior change for anonymous viewers on `/`, `/provider/<slug>`, `/home`, `/admin/*`. Run a curl/Invoke-RestMethod against `/api/chat` from an anonymous session to confirm chat-route response shape unchanged.

HALT here. Produce the §13 report. Operator commits, then re-dispatches for 2A.3.

---

## §7 Phase 2A.3 — Claim flow + favorites + admin role + close-out (target: 2-3 days)

### §7.1 Claim flow

**New file `app/auth/claims.py`** with helpers:

- `entity_is_claimable(entity_type: str) -> bool` — returns True iff `entity_type IN ('commercial', 'place')`
- `find_existing_claim(db, user_id, entity_id) -> Claim | None`
- `create_pending_claim(db, user_id, entity_id) -> Claim` — raises on duplicate via unique constraint; validates entity_type via JOIN before insert

**New routes in `app/auth/routes.py`** (or factor into `app/account/router.py` if it gets large):

- `GET /claim/<slug>` — requires login (redirect to `/login?next=/claim/<slug>` if anonymous). Looks up Entity by slug (NOT Provider by slug — go through `entities.slug` since Phase 1's slug uniqueness is on entities). 404 if not found. Renders `claim_form.html` with the entity name. If current_user already has a Claim for this entity, render `claim_status.html` showing current status instead.
- `POST /claim/<slug>` — accepts a "claim this entity" submission. Optionally captures a verification preference (e.g., "call me at <phone>") in a text field stored as `Claim.rejection_reason` repurposed → no actually add a small `claim_notes: Text | None` column to Claim if needed; OR simpler V1 just creates the row with no extra notes. Renders `claim_submitted.html`.
- `GET /admin/claims` — admin only. Lists pending Claims with verify / reject buttons + entity name + claimant email. Uses the existing `_guard` dependency (which 2A.3 extends to accept role==admin user-sessions as well as the existing admin cookie).
- `POST /admin/claims/<id>/verify` — admin only. Flips `status='verified'`, sets `verified_at = now`, `verified_by = current_admin_user.id`, `verification_method = <Form value>`. Bump the claimant's `User.role` from `end_user` to `merchant` if currently `end_user`.
- `POST /admin/claims/<id>/reject` — admin only. Flips `status='rejected'`, sets `rejected_at = now`, `rejection_reason = <Form value>`.

### §7.2 `viewer_is_owner` wiring in `app/providers/router.py`

Anchored Edit on the provider profile route handler. Currently the call to the view-model factory at `app/providers/router.py` (find via grep `viewer_is_owner=`) passes `viewer_is_owner=False` hard-coded. Replace with:

```python
viewer_is_owner = _viewer_owns_provider(
    db, current_user=request.state.current_user, provider=provider
)
```

Add helper:

```python
def _viewer_owns_provider(
    db: SqlSession, *, current_user: User | None, provider: Provider
) -> bool:
    if current_user is None or provider.entity_id is None:
        return False
    if current_user.role == "admin":
        return True
    claim = (
        db.query(Claim)
        .filter(
            Claim.user_id == current_user.id,
            Claim.entity_id == provider.entity_id,
            Claim.status == "verified",
        )
        .first()
    )
    return claim is not None
```

Update the `claim_url` value at `app/providers/view_models.py:178` from `f"/claim/{slug}"` to use the Entity.slug (same value when Provider.slug == Entity.slug per Phase 1D's `derive_provider_slug` reservation, which is the normal case). No code change needed if Provider.slug == Entity.slug holds universally; verify by grep against `derive_provider_slug` + the Phase 1D dual-write helpers.

### §7.3 Favorites

**New file `app/auth/favorites.py`** with helpers:

- `entity_is_favoritable(entity_type: str) -> bool` — returns True iff `entity_type IN ('commercial', 'place', 'event')`
- `toggle_favorite(db, user_id, entity_id) -> tuple[Literal["added", "removed"], int]` — find-or-insert / delete-if-exists. Returns the action taken + the resulting favorite-count for that user (for UI feedback).
- `list_user_favorites(db, user_id) -> list[Entity]` — eager-loads via `joinedload(UserFavorite.entity)`.

**New routes:**

- `POST /api/favorites/toggle` — body `{entity_id: str}` (JSON). 401 if anonymous. Looks up Entity; 400 if not favoritable; toggles; returns `{action: "added"|"removed", favorite_count: int}`.
- `GET /api/favorites` — list current user's favorites as JSON.
- `GET /account/favorites` — HTML render of current user's favorites with links to each provider profile.
- `GET /account` — simple landing: "Signed in as <email>. <Logout button>. <Link to /account/favorites>".

**Heart-icon JS** — add a small inline script (or factor to `app/static/favorites.js`) that:
- On page load: reads `data-current-user` attribute (rendered by templates from `request.state.current_user.id`) — if anonymous, hides heart icons.
- On heart-click: POST `/api/favorites/toggle` with `entity_id`; on success flip icon state + show a tiny "Saved!" toast.

Wire the heart-icon into `app/templates/provider_profile.html` (next to the provider name) and into the Tier 2 catalog cards in `app/chat/tier2_catalog_render.py` (anchored Edit at the card-render function — find via grep `<div class="provider-card"` or similar).

### §7.4 Admin-role parallel auth path

Anchored Edit on `app/admin/router.py::_guard` (find via grep `def _guard`). Currently it calls `verify_admin_cookie(request.cookies.get(COOKIE_NAME))` and raises 403 if false. Extend to ALSO accept a user-session with `role == 'admin'`:

```python
def _guard(request: Request) -> None:
    # Existing admin-cookie path (unchanged):
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return
    # New role-based path:
    current_user = getattr(request.state, "current_user", None)
    if current_user is not None and current_user.role == "admin":
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
```

This means a Casey-as-end-user-session with role==admin can access `/admin/*` even without the legacy admin-cookie. Both paths work; no operator-side disruption.

### §7.5 Tests — extend existing test files + new files

New file `tests/test_claims.py`:
1. Anonymous user redirected from `/claim/<slug>` to `/login?next=/claim/<slug>`
2. Signed-in user submits a claim → pending Claim row created + claim_submitted.html rendered
3. Submitting a second claim for the same entity by the same user is a no-op (unique constraint) — render claim_status.html showing the existing claim
4. `/claim/<slug>` for an event entity (entity_type='event') returns 400 — not claimable
5. Admin user (via role==admin OR admin-cookie) sees the claim in `/admin/claims`
6. Admin verifies the claim → row flips to verified + verifier set + user's role auto-promotes to merchant
7. Admin rejects with a reason → row flips to rejected + rejection_reason saved
8. `viewer_is_owner` flips to True on `/provider/<slug>` after the user's claim is verified

New file `tests/test_favorites.py`:
1. Anonymous POST /api/favorites/toggle returns 401
2. Signed-in POST adds favorite → returns `{action: "added", favorite_count: 1}`
3. Re-POST removes favorite → returns `{action: "removed", favorite_count: 0}`
4. POST with non-existent entity_id returns 404
5. POST with non-favoritable entity_type (e.g., program) returns 400
6. GET /api/favorites returns current user's favorites
7. GET /account/favorites renders the list page
8. Heart icon hidden in template when current_user is None (assert via rendered HTML)

Extend `tests/test_admin_router.py` (or wherever existing admin tests live):
- Verify the existing admin-cookie path still works (regression)
- Verify a user-session with role==admin can access `/admin/*` without admin-cookie
- Verify a user-session with role==end_user gets 403

Extend `tests/test_provider_profile_page.py`:
- Anonymous viewer sees the same affordances as pre-Phase-2A (regression — assert `viewer_is_owner=False` in the rendered VM)
- Authenticated viewer with verified Claim sees `viewer_is_owner=True`
- Authenticated viewer with pending Claim sees `viewer_is_owner=False` (only verified counts)
- Authenticated admin sees `viewer_is_owner=True` regardless of claim

### §7.6 Phase 2A.3 acceptance + commit

After 2A.3:
- pytest count: 2A.2 baseline + ~25 new tests → ~1573-1577
- `alembic upgrade head` still passes
- ruff clean
- Manual smoke: full happy path works end-to-end (login → /claim/<slug> → admin verifies via /admin/claims → reload provider page sees viewer_is_owner affordances → favorite a provider → see it on /account/favorites → /logout works)
- Anonymous viewers see identical experience to pre-2A on every public route
- Master plan §4 Phase 2 Lane 2A gets a "Shipped: <date> + commit SHA" line added by operator after commits

HALT. Produce the §13 close-out report including a Phase 2 summary: Phase 2 Lane 2A complete; Lane 2B (image storage + search) is the next dispatchable lane and is file-disjoint per dispatch_protocol Rule 3.

---

## §8 What to do, in order (across all three sub-phases)

1. §0 baseline confirmation. Report values. Confirm reads complete.
2. **Phase 2A.1:** Schema migration + ORM models + Resend module scaffold + schema tests + email-sender tests. Halt + report + operator commits.
3. **(Operator re-dispatches you in a new session.)**
4. **Phase 2A.2:** Session module + dependencies + email helpers + auth routes + templates + main.py wiring + auth-flow tests + middleware tests. Halt + report + operator commits.
5. **(Operator re-dispatches.)**
6. **Phase 2A.3:** Claim flow + favorites + viewer_is_owner wiring + admin role parallel-path + heart-icon JS + all integration tests. Halt + report + operator commits.
7. Master plan §4 Phase 2 Lane 2A gets a "Shipped: <date> + commit SHA + actual effort vs estimate" line by operator after 2A.3 commits.

---

## §9 What NOT to do

- **Don't run `git add`, `git commit`, `git push`, `--amend`.** Report when each sub-phase is done; operator commits.
- **Don't ship multiple sub-phases in one session** unless operator explicitly authorizes. Halt-and-report between each.
- **Don't store plaintext magic-link tokens.** Only SHA-256 hash. The plaintext lives in the emailed URL + in transit only. Same precedent as `Contribution.submitter_ip_hash`.
- **Don't write SQLite-only constructs in the migration.** Production runs Postgres; the sandbox + tests run SQLite. Postgres portability checklist (absorbed from session-15's Phase 1A hotfix at `5132162`):
  - Use `sa.true()` / `sa.false()` (NOT `sa.text("1")` / `sa.text("0")`) for Boolean `server_default` values. Phase 1 Entity at `app/db/models.py:648` is the precedent.
  - Use `sa.func.now()` (NOT `sa.text("CURRENT_TIMESTAMP")`) for default timestamps where the migration needs a server-side default.
  - Verify any raw SQL inside `op.execute()` works on Postgres, not just SQLite. SQLite is loose about quoting, keyword strictness, NULL-handling in unique constraints, and JSON syntax.
  - The Phase 1D `f8e9d0c1b2a3_legacy_entity_id_not_null.py` migration is the most recent precedent — `op.batch_alter_table` with portable `nullable=False`; no boolean defaults; no raw SQL. Mirror that shape.
- **Don't pre-create User rows on request-link.** The User row is created only on first successful callback (design memo §5.1 step 7). Pre-creating a User row at request-link time would let an attacker spam User creation by entering random emails.
- **Don't reveal whether an email has an existing User row.** The `/api/auth/request-link` confirmation page renders the same content whether the email is first-time, returning, or rate-limited.
- **Don't run the Resend send on a background queue in V1.** Synchronous send inside `/api/auth/request-link` is the locked V1 choice (design memo §9). Phase 4's background-job infrastructure migrates it to queued later.
- **Don't add password authentication, OAuth, MFA, or password reset.** Magic-link only; pivot §8.3 LOCKED. Design memo §13 lists every other thing NOT in v0.1.
- **Don't add a `display_name` UI for end-user self-edit.** Admin-only via the admin form in V1 per design memo §13.
- **Don't add the alerts opt-in column to `User` yet.** Pivot §5 names alerts but audit treats them as a separate lane post-Gap #7; add `User.alert_opt_in_at` in a future migration when the alerts surface ships.
- **Don't add per-user-id rate limiting in V1.** slowapi IP-keyed + per-email DB count is enough (design memo §13).
- **Don't add an `entity_type` discriminator column on `user_favorites` or `claims`.** The `entities` row carries the discriminator; the FK to `entities.id` is the polymorphic target. Master plan §4 Phase 2 amended this away from the design memo's original `(entity_type, entity_id)` shape.
- **Don't touch existing chat-route response shape or Provider profile rendering for anonymous viewers.** This is a feature add for authenticated viewers; a zero-change for anonymous viewers.
- **Don't restructure existing tests.** Extend test files in place; add new test files for new schema + new routes.
- **Don't introduce circular imports.** `app/auth/session.py` imports `app.db.models.{User, Session as AuthSession}`; `app/auth/routes.py` imports `app/auth/session.py` + `app/auth/email_sender.py` + `app/auth/email_helpers.py`. `app/db/models.py` does NOT import anything from `app/auth/`. `app/admin/router.py::_guard` may import `app.db.models.User` to check role but should NOT import `app/auth/*` modules.
- **Don't `git commit --amend` anything** (Rule 12 of dispatch protocol).
- **Don't ignore PowerShell `$` interpolation** if the operator commits via PowerShell (gotcha #8 — single-quote git commit subjects with `$` or sigils).
- **Don't use `&&` in PowerShell command chains** (gotcha #13 — PowerShell 5.1 doesn't support `&&`; use `;` or newline-separated commands instead).
- **Don't proceed past a baseline mismatch.** Halt and report.

---

## §10 Pragmatic deviations are allowed (within guardrails)

You may deviate from the brief if you discover something on the ground that materially changes the right call. **Report every deviation in the final report.** Examples of acceptable deviations:

- **`before_flush` Session listener safety net for User creation.** Phase 1D (`3f3628e`) demonstrated that a `before_flush` listener catches raw `db.add(...)` paths that bypass explicit helpers — useful for test-fixture coverage. If your tests need to create User rows directly (without going through the magic-link callback flow), consider registering a listener that auto-fills `created_at` / role default if missing, mirroring the slug-listener precedent in `app/db/seed_helpers.py::register_provider_slug_hooks` and the dual-write hooks in `app/db/database.py::_register_orm_listeners`. Document if you do this.
- **Line offsets different than this brief states** because of a recent commit. Likely — the brief was authored 2026-05-14/15.
- **Field name adjustment** because the existing data model has a name collision (e.g., `Session` class name colliding with `sqlalchemy.orm.Session` — rename to `AuthSession` if real; documented in §4.3).
- **Test fixture pattern doesn't exist** for the case the brief expects — a lighter assertion is the right fallback.
- **Session middleware uses a different mechanism than `BaseHTTPMiddleware`** if the codebase has a different middleware precedent. (Unlikely — Starlette `BaseHTTPMiddleware` is the standard FastAPI pattern.)
- **`last_seen_at` debounce uses a different mechanism** (e.g., a per-process LRU rather than a Session-instance attribute) if you find a cleaner shape.
- **Folding cleanup of expired magic-link tokens + sessions into `_hourly_cleanup_loop`** at `app/main.py:246`. The existing loop already runs `run_expired_review_cleanup` hourly; appending a `run_expired_auth_cleanup` call to delete expired `MagicLinkToken` and `Session` rows keeps the auth surface tidy without a new background-task framework. Recommended deviation; flag in §13.
- **Email-template content text adjustments** for voice / brand. The body in §5.2 is functional; if the project has a voice guide referenced in `docs/maintainability/dispatch_channels.md` or similar, match it.

Unacceptable deviations (these are LOCKED):
- **Choosing Option B (JWT) or Option C (per-request tokens) instead of Option A.** Design memo §3 LOCKED Option A.
- **Adding `entity_type` columns to `user_favorites` or `claims`.** Master plan §4 Phase 2 LOCKED the FK-to-entities-only shape.
- **Pre-creating User rows at request-link time.** Design memo §5.1 + §10 Q1 LOCKED implicit-on-callback.
- **Storing plaintext magic-link tokens.** Design memo §4.2 LOCKED hash-only.
- **Renaming `users` / `sessions` / `claims` / `user_favorites` / `magic_link_tokens` tables.** Names are LOCKED — V2 phases reference them.
- **Adding additional tables beyond the five specified.**
- **Skipping or merging sub-phases without explicit operator authorization.**
- **Adding password / OAuth / MFA / account-deletion-UI surfaces.** Design memo §13.

---

## §11 Risk register for this lane

| # | Risk | Mitigation |
|---|---|---|
| 1 | Operator's Resend setup uses different env var names than the brief specifies | §0 step 8 halts on mismatch; brief can be amended before proceeding. The names (`RESEND_API_KEY`, `RESEND_FROM_ADDRESS`, `AUTH_MAGIC_LINK_BASE_URL`, `AUTH_DEV_MODE`) are the canonical recommendation; operator can deviate but the brief should be updated to match. |
| 2 | Cookie collision between `admin_session` and `hava_session` | LOCKED in §2 — distinct cookie names. Tests cover both cookies set simultaneously on the same request (admin can be Casey + the new role==admin user-session). |
| 3 | SQLite vs Postgres divergence on CHECK constraints | SQLite enforces CHECK; Postgres enforces CHECK. Both should reject invalid `role` / `status` values. Verify with a test that inserts an invalid row + expects `IntegrityError`. Same pattern as `ck_providers_verification_method` precedent. |
| 4 | Magic-link token replay attack window | 15-minute expiry + `consumed_at` single-use check at callback time, inside the same transaction as the user/session create. Covered by test_auth_flow.py #8. |
| 5 | Email-spam abuse — attacker enters many emails to spam other people's inboxes | Rate limit at IP-level (10/hr via slowapi) + per-email-level (5/hr via DB count). Same UI for rate-limited / first-time / returning emails so attacker can't probe state. |
| 6 | Session-table growth | `Session.expires_at` index allows efficient bulk-delete of expired rows. The `_hourly_cleanup_loop` deviation in §10 keeps the table small. |
| 7 | Anonymous user regression — chat-route response shape changes when middleware lands | Middleware sets `request.state.current_user = None` for anonymous viewers; nothing else changes. Existing chat-route tests (1518 baseline) must all stay green. Run full suite after wiring middleware in §6.6. |
| 8 | Claim verification UI for admin needs to scale to many pending claims | V1 ships a simple list. At ~10-50 pending claims it's fine; if it grows past 200 a pagination + filter UI lands in V1.5. Not a Phase 2A scope concern. |
| 9 | `verifier` self-FK on Claim with `ON DELETE SET NULL` may surprise SQLite test fixtures | Verified in `tests/test_account_lite_schema.py` #5/#6 (cascade tests). The `passive_deletes=True` pattern from Phase 1A is the precedent if cascade gotchas surface. |
| 10 | `viewer_is_owner` plumbing changes test_provider_profile_page.py baseline | Phase 1C added regression tests there; mirror the pattern — anonymous case stays identical (regression), authenticated cases get new assertions. |
| 11 | Cursor over-scopes by attempting all three sub-phases in one session | Halt-and-report etiquette in §3 is the safety valve. Better to ship 2A.1 cleanly + re-dispatch than push past a broken state. |
| 12 | `_safe_next` open-redirect oversight | Whitelist by leading `/` + no `..` + no scheme + no host. Test with adversarial inputs (`//evil.com`, `/path?next=https://evil.com`, etc.). |

---

## §12 Final report format (per sub-phase)

After each sub-phase, paste back a single message:

1. **Sub-phase identifier** — 2A.1 / 2A.2 / 2A.3.
2. **§0 baseline values** (top-5 SHAs, pytest count, alembic head, alembic current).
3. **Files created** (paths + line counts).
4. **Files modified** (paths + net line counts).
5. **Migration revision id chosen** (2A.1 only) + `down_revision`.
6. **Tests added** (count + brief description of each).
7. **Final pytest count** (expected to be baseline + tests added).
8. **`python -m alembic upgrade head` result** against fresh dev DB (success/failure + any output).
9. **`python -m alembic downgrade -1 && python -m alembic upgrade head` cycle** (2A.1 only — verify the migration is reversible).
10. **Ruff status** (clean / autofixes applied / remaining issues).
11. **Manual smoke result** (2A.2 + 2A.3 only — operator runs locally with `AUTH_DEV_MODE=1`; report what you exercised: login flow, claim flow, favorites flow).
12. **Pragmatic deviations** — anything you adapted from this brief, with rationale. Be transparent; reasonable deviations are fine.
13. **Anything that surprised you** or that the operator should know before they commit. Include any baseline mismatches or env-var-name mismatches with the brief's canonical names.
14. **Confirmation you did NOT run `git add` / `git commit` / `git push` / `--amend`.**
15. **Next sub-phase preview** — 2A.1: "Ready for 2A.2 re-dispatch — schema in, Resend module scaffolded, no auth routes yet." 2A.2: "Ready for 2A.3 — auth flow works end-to-end, no claim/favorite UI yet, viewer_is_owner still hard-wired off." 2A.3: "Phase 2A complete; master plan §4 Phase 2 Lane 2A ready for Shipped: line; Lane 2B (image storage + search) is the next dispatchable lane."

---

Ready. Start at §0. Halt at the first sub-phase boundary.
