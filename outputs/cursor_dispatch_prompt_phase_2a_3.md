# Cursor Dispatch Prompt — Phase 2A.3 (claim flow + favorites + admin role + viewer_is_owner + close-out)

> Short paste-into-Cursor prompt for Phase 2A.3 dispatch — the final sub-phase of Lane 2A (account-lite v0.1) of Phase 2 of the master build plan. The heavy-prescriptive operating doc remains `outputs/cursor_brief_phase_2a_account_lite.md` (read it again, especially §3 + §7 + §9 + §10 + §11 + §12). After 2A.3 ships + commits, Lane 2A is COMPLETE — Phase 2 closes out once Lane 2B ships, after which Phase 3 (v1.1 schema + categories + districts) becomes the next dispatchable lane.
>
> **Operator gate:** none specific to 2A.3 (Resend prereq is already locked from before 2A.2 dispatch).
>
> **Author note:** this prompt was pre-positioned while 2A.2 was in flight. The §0 baseline values (top SHA, pytest count) reference Phase 2A.2's ship; fill in after 2A.2 §13 report lands. Pragmatic-deviation references in §7 expectations may need amendment based on what 2A.2 actually shipped (e.g., the `last_seen_at` debounce mechanism, the `_hourly_cleanup_loop` fold).

---

```
Read outputs/cursor_brief_phase_2a_account_lite.md end-to-end again,
especially §3 (sub-phase boundaries, halt etiquette), §7 (Phase 2A.3
deliverable list -- the close-out sub-phase of Lane 2A), §9 (what
NOT to do), §10 (acceptable deviations), §11 (risk register), §12
(final report format).

Phase 2A.1 SHIPPED on origin (commit 6000138 + 5bf4c14 dispatch
artifacts + 9150be5 docs ship-line + 2423d4f Phase 2A.2 dispatch
artifact). Phase 2A.2 SHIPPED at commit 714ca52 (master plan §4
Phase 2 "Shipped (incremental)" list). Origin/main HEAD tops at
0d73b0f (session-17 close-out: handoff + session-18 boot prompt +
STATE refresh — pure docs, no code); the substantive Phase 2A.2
ship is 714ca52 with 9e672b5 docs ship-line + 95d9f79 Phase 2A.3
dispatch artifact + 7f5b1f7 Phase 3 district paragraphs ChatGPT
draft + 0d73b0f session-17 close-out docs above it. Run git log
--oneline -10 and confirm. Pytest collect baseline going in is
**1563** tests. Alembic head is **92ce4899dc08** (Phase 2A.1
account-lite v0.1 schema — unchanged through 2A.2 since 2A.2
added no migration).

Ship Phase 2A.3 ONLY per §3 + §7 of the brief — claim flow + admin
review queue + viewer_is_owner plumbing + favorites + admin role
parallel-path + close-out. **No new auth routes that 2A.2 didn't
already ship** (the four magic-link routes + middleware are locked
from 2A.2); **no R2 / photo upload / search FTS** (those are Lane
2B). After this sub-phase ships, Lane 2A of Phase 2 is COMPLETE.

ORDER MATTERS WITHIN PHASE 2A.3:
1. First: read the docs + source files in brief §0. Line offsets in
   models.py / main.py / providers/router.py / admin/router.py /
   view_models.py / tier2_catalog_render.py may have moved since
   the brief was authored — verify before anchoring edits.
2. Then: factor app/auth/claims.py per brief §7.1 (helper functions):
   entity_is_claimable(entity_type: str) -> bool
     (True iff entity_type IN ('commercial', 'place'))
   find_existing_claim(db, user_id, entity_id) -> Claim | None
   create_pending_claim(db, user_id, entity_id) -> Claim
     (validates entity_type at insert time via Entity JOIN; raises
      on duplicate via unique constraint)
3. Then: extend app/auth/routes.py per brief §7.1. New routes:
   GET  /claim/<slug>             -- requires login (redirect to
                                     /login?next=/claim/<slug> if
                                     anonymous). Looks up Entity by
                                     slug (entities.slug, NOT just
                                     providers.slug since Phase 1
                                     unified the namespace; same value
                                     in the common case per derive_provider_slug
                                     reservation). 404 if not found.
                                     Renders claim_form.html or
                                     claim_status.html depending on
                                     existing claim state.
   POST /claim/<slug>             -- creates pending Claim. Renders
                                     claim_submitted.html.
   GET  /admin/claims             -- admin-only (via existing _guard
                                     extended in step 5 below).
                                     Renders admin_claims_queue.html
                                     listing pending claims with
                                     verify/reject buttons.
   POST /admin/claims/<id>/verify -- admin-only. Flips status to
                                     verified + verified_by +
                                     verified_at + verification_method
                                     (Form value). Auto-promote
                                     claimant User.role from end_user
                                     to merchant if currently end_user.
   POST /admin/claims/<id>/reject -- admin-only. Flips status to
                                     rejected + rejected_at +
                                     rejection_reason (Form value).
   ALTERNATIVELY, factor admin claim routes into app/admin/router.py
   if cleaner; the brief is agnostic.
4. Then: factor app/auth/favorites.py per brief §7.3 (helper functions):
   entity_is_favoritable(entity_type: str) -> bool
     (True iff entity_type IN ('commercial', 'place', 'event'))
   toggle_favorite(db, user_id, entity_id)
     -> tuple[Literal["added", "removed"], int]
     (find-or-insert / delete-if-exists; returns action + count)
   list_user_favorites(db, user_id) -> list[Entity]
     (eager-loads UserFavorite.entity via joinedload)
5. Then: extend app/auth/routes.py per brief §7.3 with favorite
   routes:
   POST /api/favorites/toggle -- body {entity_id: str}. 401 if anon.
                                 Validates entity_is_favoritable.
                                 Returns {action, favorite_count}.
   GET  /api/favorites        -- list current user's favorites JSON.
   GET  /account/favorites    -- HTML render of favorites.
   GET  /account              -- simple "signed in as <email>" page
                                 (may already exist from 2A.2 — verify
                                 and extend if so, or create cleanly).
6. Then: anchored Edit on app/admin/router.py per brief §7.4. Find
   the existing _guard dependency and extend to ALSO accept a user-
   session with role == 'admin':
     if verify_admin_cookie(...): return  # existing path
     current_user = getattr(request.state, "current_user", None)
     if current_user is not None and current_user.role == "admin":
         return  # new path
     raise HTTPException(403)
   No other admin/router.py changes. The existing admin-cookie path
   remains primary; user-session role==admin is the new parallel
   path. Both work simultaneously.
7. Then: anchored Edit on app/providers/router.py per brief §7.2 —
   wire viewer_is_owner. Find the call to the view-model factory
   (grep "viewer_is_owner=" in app/providers/router.py) and replace
   the hard-coded False with a call to a new helper
   _viewer_owns_provider(db, current_user=..., provider=...) that
   queries Claim for current_user.id + provider.entity_id +
   status=='verified'. Admin role short-circuits to True. Anonymous
   short-circuits to False.
8. Then: anchored Edit on app/providers/view_models.py if claim_url
   needs adjustment per brief §7.2 — verify the slug used in
   f"/claim/{slug}" at :178 matches the Entity.slug for commercial
   entities (it should, per Phase 1D's derive_provider_slug
   reservation). No change if it already matches.
9. Then: new templates in app/templates/:
   - claim_form.html  -- "Are you the owner of <Name>? Tell us how to
                         verify." Single Form, optional notes field.
   - claim_submitted.html -- "We'll be in touch within 48 hours" copy.
   - claim_status.html -- "Your claim for <Name> is <status>" copy.
                         Branches on pending/verified/rejected.
   - admin_claims_queue.html -- admin-only. Table of pending Claims
                         with claimant email, entity name, claimed_at
                         timestamp, verify/reject buttons.
   - account/favorites.html (or account_favorites.html) -- HTML
                         render of current user's favorites with
                         links to each provider profile.
   Reuse the visual treatment of app/templates/home.html for
   header/footer; the existing 2A.2 login templates are the most
   recent precedent for auth-adjacent template style.
10. Then: heart-icon JS — small inline script (or factor to
    app/static/favorites.js) that:
    - reads data-current-user attribute on body / provider card
    - hides heart icons if anonymous
    - on click: POST /api/favorites/toggle with entity_id; flip
      icon state on success; show a tiny "Saved!" toast
    Wire into app/templates/provider_profile.html (next to provider
    name) AND into the Tier 2 catalog card render at
    app/chat/tier2_catalog_render.py (anchored Edit at the card-render
    function — grep "provider-card" or similar).
11. Then: new tests per brief §7.5. Multiple test files:
    - tests/test_claims.py (~8 tests): anonymous redirect; signed-in
      claim creation; duplicate claim handling; non-claimable
      entity_type (event); admin view; admin verify -> role auto-
      promote to merchant; admin reject with reason; viewer_is_owner
      flip after verify
    - tests/test_favorites.py (~8 tests): anonymous 401; signed-in
      add; toggle remove; non-existent entity 404; non-favoritable
      400; list endpoint; /account/favorites render; heart-icon
      hidden anonymously
    Extensions to existing test files:
    - tests/test_admin_router.py (or whatever it's called): admin-
      cookie regression + role==admin parallel-path acceptance +
      end_user role 403
    - tests/test_provider_profile_page.py: anonymous regression
      (viewer_is_owner=False) + authenticated with verified claim
      (True) + authenticated with pending claim (False — only
      verified counts) + admin (True regardless)
12. After all of the above: confirm full pytest stays green, ruff
    clean, that `python -m alembic upgrade head` against a fresh
    dev DB still reaches 92ce4899dc08 cleanly (no new migration in
    2A.3), and manually smoke the full happy path:
    AUTH_DEV_MODE=1 -> POST /login -> click magic URL -> /account
    renders -> visit /provider/<slug> -> click "Claim this listing"
    -> submit claim -> admin (separate session) visits /admin/claims
    -> verify -> reload /provider/<slug> as the claimant -> see
    viewer_is_owner affordances. Favorite a provider; see it on
    /account/favorites; remove favorite; verify removed. /logout
    clears cookie + redirects to /.

POSTGRES COMPATIBILITY (carried forward from brief §9):
- No new migration in 2A.3 (no schema changes). The portability
  rules carry forward only if you discover a need for a new column
  (unlikely; flag in §13 if so).
- App-layer queries on Claim / UserFavorite should use SQLAlchemy
  Core / ORM constructs that translate cleanly to both dialects.
- No raw SQL inside any new code path unless verified portable.

DEVIATION INVITATIONS (per brief §10):
- before_flush Session listener safety net for Claim / UserFavorite
  creation. If your test fixtures create Claim or UserFavorite rows
  directly bypassing the helpers in app/auth/claims.py /
  app/auth/favorites.py, consider registering listeners to
  default-fill or validate entity_type. Same precedent as 2A.1 +
  Phase 1D. Optional — flag if you do.
- factor admin claim routes into app/admin/router.py vs keeping in
  app/auth/routes.py — pick whichever fits the existing router
  organization; flag your choice.
- account/favorites.html shape (subdirectory vs underscore-prefix
  flat) — pick what matches the existing template tree; flag.
- heart-icon implementation: inline JS in templates vs separate
  app/static/favorites.js file — pick smaller/cleaner; flag.

WHAT NOT TO DO (per brief §9):
- Don't add new auth routes beyond the claim/favorites/account
  endpoints listed above. The four magic-link routes from 2A.2
  (/login, /api/auth/request-link, /auth/callback, /logout) are
  LOCKED.
- Don't drop or alter the existing admin-cookie auth path. The
  role==admin parallel path is ADDITIVE. Both work.
- Don't add merchant-edit-form UI for the claimed provider. That's
  out of scope per brief §11 -- the viewer_is_owner flag plumbing
  is the deliverable; the actual edit UI is a follow-up lane.
- Don't auto-promote User.role from merchant to admin under any
  circumstance. Admin promotion is SQL-only in V1 per design memo
  §10 Q7.
- Don't add demographic/profile/avatar surfaces to /account. V1
  account page is just "signed in as <email>" + logout + link to
  favorites.
- Don't add R2 / photo / search FTS — Lane 2B scope.
- Don't introduce circular imports: app/admin/router.py may import
  from app/db/models.py (User class for role check) but should NOT
  import from app/auth/ modules.
- Don't touch chat-route response shape for anonymous viewers.

HALT at the §3 Phase 2A.3 boundary. After 2A.3 ships + commits,
Phase 2 Lane 2A is COMPLETE — the master plan §4 Phase 2 "Shipped
(incremental)" list gets a 2A.3 ship-line AND a Lane 2A SHIPPED
header per the Phase 1 cd079fc precedent. Phase 2 Lane 2B is the
remaining lane; Lane 2B is parallel-eligible (file-disjoint per
Rule 3) and 2B.2 may have already shipped depending on operator
dispatch cadence.

Same constraints as 2A.1 + 2A.2:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits — Rule 2+12)
- Pytest must stay green throughout
- Report per brief §12 (final report format) for sub-phase 2A.3 only

Operator note: AUTH_DEV_MODE=1 should still be set in tests/conftest.py
from 2A.2; the 2A.3 work doesn't change Resend integration so
auth-test isolation is unchanged.
```

---

## After Cursor returns with the §12 report

Same rhythm as 2A.1 + 2A.2: paste back to the Cowork primary chat, primary reviews against §7.6 acceptance gates, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 2 new files in `app/auth/` (`claims.py`, `favorites.py`)
- ~5 new templates in `app/templates/` (`claim_form.html`, `claim_submitted.html`, `claim_status.html`, `admin_claims_queue.html`, plus a favorites view template)
- Possibly 1 new static JS file (`app/static/favorites.js`) if Cursor factors heart-icon JS out
- 2 new test files (`tests/test_claims.py`, `tests/test_favorites.py`)
- ~4-5 modified files (`app/auth/routes.py` claim + favorites + account routes appended; `app/admin/router.py` _guard extension; `app/providers/router.py` viewer_is_owner wiring; `app/chat/tier2_catalog_render.py` heart-icon wiring; possibly `app/providers/view_models.py` if claim_url needs adjustment)
- Extensions to existing test files (`tests/test_admin_router.py`, `tests/test_provider_profile_page.py`)

Expected pytest delta: +20-28 net-new tests (the brief specifies ~25). Pre-existing chat-route + Provider-profile anonymous-viewer tests must all stay green.

Expected effort: 2-3 day brief estimate; one Cursor session realistically.

Expected pragmatic deviations: (a) admin claim routes router placement (auth/routes.py vs admin/router.py); (b) heart-icon JS factor-out vs inline; (c) account page template subdirectory shape; (d) `before_flush` safety-net for Claim/UserFavorite creation if test fixtures benefit; (e) `viewer_is_owner` helper location (module / function organization).

## After Phase 2A.3 ships

**Lane 2A of Phase 2 is COMPLETE.** Update master plan §4 Phase 2 "Shipped (incremental)" list with the 2A.3 ship-line + add a Lane 2A SHIPPED header (mirroring the Phase 1 SHIPPED header pattern from session-16's `cd079fc`). Update STATE.md Production block + "Recently shipped" §1 with the Lane 2A close-out narrative.

**Next dispatchable lane:** Lane 2B continues — 2B.1 (photos + R2, now unblocked since 2A.3 shipped the claim flow + viewer_is_owner that 2B.1's upload-auth depends on), 2B.2 (FTS, if not already shipped), 2B.3 (search bar UI). Operator's call on parallelism + ordering. Once Lane 2B fully ships, **Phase 2 of the master build plan is COMPLETE**, and Phase 3 (v1.1 schema pass + category taxonomy rewrite + districts + alerts schema) becomes the next dispatchable lane.
