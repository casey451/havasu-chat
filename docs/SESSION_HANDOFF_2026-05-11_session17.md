# Session-17 Handoff — 2026-05-11

> **Audience:** the next Cowork primary on havasu-chat. **Read time:** ~3 minutes. Then boot per `outputs/session_18_boot_prompt.md`. Most state is durable on origin; this doc captures the deltas since the session-16 close (`1c98365` + three close-out hygiene commits through `dcf2f7a`) + what's queued.

---

## §1 — What session-17 accomplished

Eleven commits on origin, all pushed. Origin/main HEAD = `7f5b1f7`. **Phase 2 Lane 2A is 2/3 complete on origin (2A.1 + 2A.2 shipped); Phase 2A.3 + Phase 2B.2 both have pre-positioned dispatch prompts ready to paste.**

| Commit | Summary |
|---|---|
| `4a5ee24` | Session-17 boot prompt SHA-baseline patch (carry-over from session-16 close; landed at boot) |
| `6000138` | **Phase 2A.1 — schema + ORM + Resend scaffold.** 7 files (+1114/-2). Cursor session, single dispatch. Five new tables (`users`, `magic_link_tokens`, `sessions`, `user_favorites`, `claims`) with FK ondelete cascades + CHECK constraints + Postgres-portable `sa.true()` / `sa.func.now()` defaults. New `app/auth/` package with `email_sender.py` (`AUTH_DEV_MODE` dev-mode fallback). Migration `92ce4899dc08` chains off `f8e9d0c1b2a3`. `user_favorites` + `claims` FK to `entities.id` (master plan amendment over design memo's polymorphic shape). Pytest **1518 → 1543** (+25 net-new). Three deviations: `Session` → `AuthSession` rename (brief §4.3 allowance); `alembic/env.py` import-order reorder to prevent circular import; dev-mode test asserts `logger.info` mock instead of `caplog`. |
| `5bf4c14` | Phase 2A dispatch artifacts — `outputs/cursor_brief_phase_2a_account_lite.md` (~720 lines, heavy-prescriptive operating doc mirroring Phase 1 brief shape) + `outputs/cursor_dispatch_prompt_phase_2a.md` (~80 lines, paste-into-Cursor wrapper for 2A.1). Primary authored. |
| `9150be5` | Docs: Phase 2A.1 shipped line on master plan + STATE.md session-17 refresh (round 1). |
| `2423d4f` | Phase 2A.2 dispatch prompt artifact (`outputs/cursor_dispatch_prompt_phase_2a_2.md`, ~175 lines). Pre-positioned during 2A.1 close-out so 2A.2 dispatch was instant. |
| `37e7770` | **`dispatch_channels.md` gotcha #14** — reflog (`.git/logs/HEAD`) vs ancestry forensics. Lesson absorbed during session-17 boot false alarm: when bash mount git is broken per Rule 7, walk parent links from HEAD via `python3 + zlib.decompress` on `.git/objects/<sha[:2]>/<sha[2:]>`; **don't** grep the reflog (records HEAD movements through abandoned branches + dead experiments, not the current ancestry). Includes a 12-line Python walker snippet. |
| `0e8e9e3` | **Lane 2B brief + 2B.2 dispatch prompt artifacts.** Sub-agent authored `outputs/cursor_brief_phase_2b_image_storage_search.md` (~928 lines, mirrors Phase 2A brief shape: 3 sub-phase split, FTS-on-SQLite dialect-gated fallback, `Photo.entity_id` FK to `entities.id` per master plan amendment). Primary authored `outputs/cursor_dispatch_prompt_phase_2b_2.md` (~175 lines, paste-into-Cursor wrapper for 2B.2 — the FTS sub-phase, dependency-free of 2A.3, no operator prereq needed). |
| `714ca52` | **Phase 2A.2 — magic-link auth flow + session middleware + login UI.** 12 files (+1000/-4). Cursor session, single dispatch. Four routes shipped (`GET /login`, `POST /api/auth/request-link` with 10/hr IP rate-limit + 5/email/hr DB silent path, `GET /auth/callback`, `POST /logout`) plus `GET /account` landing. New `app/auth/session.py` (136 lines) with `SessionMiddleware` (Starlette `BaseHTTPMiddleware`), itsdangerous-signed `hava_session` cookie (`HAVA_SESSION_SECRET` → `ADMIN_PASSWORD` fallback, 30-day max age, `RAILWAY_ENVIRONMENT`-keyed Secure flag), `_LAST_SEEN_MONO` dict + `time.monotonic()` 60s debounce, `db.refresh` + `db.expunge` after commit for Jinja survival. New `app/auth/dependencies.py` + `email_helpers.py` + `routes.py`. Four new templates. Pytest **1543 → 1563** (+20 net-new in `tests/test_auth_flow.py` + bonus 21st test). Alembic head unchanged (no migration in 2A.2). Six deviations all within §10 guardrails: `GET /account` + template; `send_magic_link(next_path=...)`; detached User via expunge; `_LAST_SEEN_MONO` choice; `_hourly_cleanup_loop` fold deliberately deferred to 2A.3; tests import order to avoid circular imports. |
| `9e672b5` | Docs: Phase 2A.2 shipped line on master plan + STATE.md session-17 refresh (round 2). |
| `95d9f79` | Phase 2A.3 dispatch prompt artifact (`outputs/cursor_dispatch_prompt_phase_2a_3.md`, ~250 lines). Pre-positioned during 2A.2 close-out. Mirrors 2A.2 dispatch prompt shape; 12-step ordered sequence covering claim flow + favorites + admin role parallel-path + viewer_is_owner + close-out. |
| `7f5b1f7` | Phase 3 district paragraphs ChatGPT draft — `outputs/chatgpt_prompt_district_paragraphs_v1.md` (the dispatch prompt) + `outputs/chatgpt_response_district_paragraphs_v1.md` (10 paragraphs returned, with 5 `[CASEY: ...]` placeholders + 5 "Casey to verify" items). Forward-looking Phase 3 V1 deliverable (per session-15 lock `ec84eb4`); operator effort drops from ~1 hour to ~15-20 min for polish + verification. |

**Phase 2 Lane 2A scorecard:** 2 of 3 sub-phases shipped on origin. Cumulative pytest delta: 1518 → 1563 (+45). Final alembic head: `92ce4899dc08` (added in 2A.1; unchanged through 2A.2). 2A.3 is the only Lane 2A sub-phase remaining; dispatch prompt is pre-positioned.

---

## §2 — What's in flight or queued

- **Phase 2A.3 — ready to dispatch.** Dispatch prompt at `outputs/cursor_dispatch_prompt_phase_2a_3.md`. Brief §7 specifies the deliverables: claim flow (`/claim/<slug>` route, claim_form/submitted/status templates, admin claim review queue at `/admin/claims`) + favorites (toggle/list/account/favorites + heart-icon JS on Provider profile + Tier 2 cards) + admin role parallel-path on `app/admin/router.py::_guard` + viewer_is_owner wiring through `app/providers/router.py`. ~2-3 day Cursor estimate.
- **Phase 2B.2 — ready to dispatch in parallel (file-disjoint with 2A.3 per dispatch_protocol Rule 3).** Dispatch prompt at `outputs/cursor_dispatch_prompt_phase_2b_2.md`. Brief §6 specifies: Postgres FTS (`entities.search_vector` tsvector generated column + GIN index) + `pg_trgm` extension + trigram name index + chat tier 2 `LIKE → FTS` swap (preserving `_category_needle_set` synonym expansion) + new `app/search/` package with `fts.py` / `sqlite_fallback.py` / `ranking.py`. FTS DDL dialect-gated; SQLite LIKE fallback path stays alive permanently for tests. ~3-4 day Cursor estimate. **No operator prereq needed for 2B.2** (R2 only gates 2B.1 photos).
- **Phase 2B.1 — pending (gated on 2A.3).** Photo schema + R2 client + Pillow pipeline + upload route. Requires Phase 2A.3's claim flow + viewer_is_owner for upload-auth. ~3-4 day Cursor estimate. Operator prereq: R2 setup per `outputs/operator_prereqs_phase_2.md` §2 (~30-45 min).
- **Phase 2B.3 — pending (gated on 2B.2).** Search bar UI + `/api/search` endpoint + close-out. ~1-2 day Cursor estimate.
- **Production deploy of `7f5b1f7`** — Phase 1C + 1D + 2A.1 + 2A.2 are NOT yet deployed. Operator-cadence call. Chat-route response shape + anonymous-viewer experience pinned unchanged across the entire stack; safe whenever. When deploy ships, alembic advances production through `b2c3d4e5f6a7 → f8e9d0c1b2a3 → 92ce4899dc08` (Phase 1D NOT NULL flip + Phase 2A.1 account-lite tables; 2A.2 ships no migration).
- **Phase 3 district paragraphs polish** — 5 `[CASEY: ...]` placeholders (Mesquite Bay, Pittsburgh Point ×2, Castle Rock, South side) + 5 "Casey to verify" items in `outputs/chatgpt_response_district_paragraphs_v1.md`. ~15-20 min operator polish; no rush (Phase 3 isn't dispatching anytime soon).

---

## §3 — Open operator-decision items

| Item | When | Notes |
|---|---|---|
| Deploy `7f5b1f7` to production | Anytime | Carries Phase 1C + 1D code + Phase 2A.1 schema + Phase 2A.2 auth flow. Chat-route shape pinned via regression. Alembic advances two heads (`f8e9d0c1b2a3` Phase 1D NOT NULL flip + `92ce4899dc08` Phase 2A.1 account-lite schema). Watch for any migration surprise on first deploy (the `5132162` hotfix lesson) — both migrations use only portable constructs so should land cleanly. |
| Dispatch Phase 2A.3 + 2B.2 in parallel | Anytime | File-disjoint per Rule 3. Two Cursor chats. ~2-3 day + ~3-4 day estimates. |
| Cloudflare R2 setup | Pre-Phase-2B.1 dispatch | ~30-45 min per `outputs/operator_prereqs_phase_2.md` §2. Path A (default `r2.dev`) is the fastest unblock; custom domain `cdn.askhava.com` can land any time before public launch. |
| Polish district paragraphs `[CASEY: ...]` placeholders + verify items | Pre-Phase-3 dispatch | ~15-20 min. `outputs/chatgpt_response_district_paragraphs_v1.md`. |
| 3 trivial category audit lock-now items + 4 Phase-3 review questions | At Phase 3 start | Carry-over from session-15 §3; not relevant before Phase 2 ships. |
| AirNow API key registration | Pre-Phase-8 (months out) | ~20 min; signup + Railway env var drop. |

---

## §4 — Pragmatic deviations to remember

Phase 2A.1 (commit `6000138`):
- **`Session` ORM class renamed to `AuthSession`** (table still `sessions`) — avoids `sqlalchemy.orm.Session` namespace clash on the models.py module. Brief §4.3 explicitly allowed. References in code use `AuthSession` consistently; the table name on the DB layer is unchanged.
- **`alembic/env.py` import-order reorder** (`from app.db.database import Base` BEFORE `import app.db.models`, with `noqa: I001`) — prevents circular-import deadlock when Alembic loads `Base.metadata` cold. The app path (`app/main.py`) already imports `database` first so no app-side change needed.

Phase 2A.2 (commit `714ca52`):
- **`GET /account` route + `account.html` template** — brief §6.4 implied via the callback redirect target but didn't list as explicit deliverable. Cursor filled the gap cleanly. Mirrors `home.html` chrome.
- **`send_magic_link(email, token_plaintext, *, next_path=None)`** — optional `next_path` param via `urllib.parse.urlencode` so emailed links carry a safe `next` query through verify. Backward-compatible.
- **Detached User on `request.state`** — `SessionMiddleware` calls `db.refresh(user)` + `db.refresh(sess)` + `db.expunge(user)` + `db.expunge(sess)` after the `last_seen_at` commit so Jinja templates can read `current_user.email` post-session-close. Logout uses `db.get(AuthSession, sess.id)` for the detached-row delete. **Operator note:** future code MUST NOT lazy-load unloaded relations on `current_user` — they'll fail with `DetachedInstanceError`.
- **`last_seen_at` debounce** = module-level `_LAST_SEEN_MONO: dict[str, float]` keyed by session id + `time.monotonic()`, 60s window. Tests pin behavior with `time.monotonic` patched to `lambda: 1.0` so other code calling monotonic doesn't widen the window.
- **`_hourly_cleanup_loop` fold NOT added** — would have exceeded the anchored "only middleware + router" `main.py` edit scope per brief §6.6. Recommended as 2A.3 deliverable or follow-up commit. Brief §10 invited the deviation; Cursor deliberately held back to keep scope tight.
- **Tests import `app.main` before other `app.auth` imports** to avoid models ↔ database listener circular-import edge during pytest collection.
- **Bonus 21st test** pinning `send_magic_link` exception path → still renders check-email HTML.

---

## §5 — New lessons absorbed in session-17

1. **Reflog vs ancestry forensics** (gotcha #14, commit `37e7770`). When verifying repo state from the bash sandbox (which has broken git per Rule 7), DON'T grep `.git/logs/HEAD` — the reflog records HEAD movements over time including abandoned branches + dead experiments, NOT the current ancestry. The decisive verification is walking parent links from HEAD via `python3 + zlib.decompress` on `.git/objects/<sha[:2]>/<sha[2:]>`. Session-17 boot false-alarmed on this; the lesson is durable.

2. **Parallel-dispatch posture for Phase 2.** Phase 2A and Phase 2B are file-disjoint per dispatch_protocol Rule 3. Once both operator prereqs are locked (Resend ✅ this session; R2 still pending), 2A.3 + 2B.2 can dispatch concurrently to two Cursor chats. The brief §0 baseline checks in both dispatch prompts halt gracefully if the operator hasn't locked the relevant prereq — no babysitting needed.

3. **Pre-author-dispatch-prompt-while-Cursor-works pattern.** During session-17, the primary pre-authored 3 dispatch prompts (2A.2 during 2A.1 review, 2A.3 + 2B.2 during 2A.2 in-flight time). Each pre-position reduces next-dispatch latency from ~30 min (brief authoring) to ~0 min (paste). Worth doing whenever there's a clean next-sub-phase scope already locked.

4. **ChatGPT-as-Phase-3-prep channel.** District paragraphs were a queued operator-time task (~1 hour). ChatGPT drafted 10 paragraphs voice-anchored against Opus samples in ~30 seconds; operator polish drops to ~15-20 min for placeholders + verification. Pattern generalizes to any Phase 3+ deliverable that's prose-shaped + voice-anchorable + has clear failure-mode flagging (`[CASEY: ...]` placeholders + verify appendix).

5. **Auth deviation patterns worth carrying forward into future write-path / auth-adjacent dispatches:** (a) detached-ORM-via-expunge for cross-request survival; (b) module-level `_LAST_SEEN_MONO`-style debounce; (c) `_safe_next` whitelist with `unquote` + leading `/` + reject `//` / `://` / `..`; (d) parallel-path auth (admin-cookie OR role==admin) for non-breaking transitions; (e) test conftest `setdefault` for `AUTH_DEV_MODE=1`.

---

## §6 — Pointers for the next agent

Boot order:
1. `outputs/session_18_boot_prompt.md` (the boot prompt Casey pastes; see that file)
2. `docs/STATE.md` (refreshed 2026-05-11 at session-17 close — start with the Production block)
3. `docs/maintainability/master_build_plan.md` §4 Phase 2 ("Shipped (incremental)" list now has both 2A.1 + 2A.2 ship-lines + the 2A.3 pending stub)
4. `outputs/cursor_dispatch_prompt_phase_2a_3.md` (if dispatching 2A.3) + `outputs/cursor_dispatch_prompt_phase_2b_2.md` (if dispatching 2B.2, optionally in parallel)
5. `outputs/cursor_brief_phase_2a_account_lite.md` §7 (for 2A.3 reference) + `outputs/cursor_brief_phase_2b_image_storage_search.md` §6 (for 2B.2 reference) — the heavy-prescriptive operating docs
6. `docs/maintainability/dispatch_protocol.md` (12 rules) + `docs/maintainability/dispatch_channels.md` (14 gotchas as of session-17 — gotcha #14 reflog-vs-ancestry is new this session)
7. `outputs/chatgpt_response_district_paragraphs_v1.md` (if you have spare cycles for the placeholder polish; not blocking)

Session-17 absorbed five new lessons (above) worth carrying into future briefs. The narrative in `docs/STATE.md` "Recently shipped" §1 captures every commit + decision + deviation with enough detail that the next agent shouldn't need to re-read this handoff except for §3 + §4 above.

---

*Authored at session-17 close, 2026-05-11. Next agent picks up at Phase 2A.3 + 2B.2 parallel-dispatch posture — operator prereqs (Resend ✅; R2 ❌ until needed for 2B.1) usefully scope what can dispatch when.*
