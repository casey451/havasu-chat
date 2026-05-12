# Cursor Dispatch Prompt — Phase 2B.3 (search bar UI + `/api/search` endpoint + Lane 2B close-out)

> Short paste-into-Cursor prompt for Phase 2B.3 dispatch — the final sub-phase of Lane 2B (image storage + search) of Phase 2 of the master build plan. The heavy-prescriptive operating doc remains `outputs/cursor_brief_phase_2b_image_storage_search.md` (read it again, especially §3 + §7 + §9 + §10 + §11 + §12). Phase 2B.3 is the **smallest** sub-phase of Lane 2B — net-new public surface (the search bar) + one new public endpoint sitting on top of the FTS infra from 2B.2. No new ORM classes, no migration, no R2/photo touches.
>
> **Operator gate:** Phase 2B.3 has **NO R2 prereq** (search bar UI is photo-adjacent only via `hero_url` in result rows — if 2B.1 hasn't shipped yet, `hero_url` falls through the existing two-tier legacy/Google chain at `app/providers/queries.py::derive_hero_photo`). The only hard gate is **Phase 2B.2 has shipped** — 2B.3's `/api/search` endpoint dispatches through `app/search/fts.py` + `app/search/sqlite_fallback.py` + `app/search/ranking.py` from 2B.2. If 2B.2 hasn't shipped, halt at §0 step 8.
>
> **Author note:** this prompt was pre-positioned while 2B.2 was in flight to a Cursor chat. The §0 baseline values (top SHA, pytest count, 2B.2's alembic revision id) reference Phase 2B.2's ship; fill in after 2B.2 §13 report lands. Pragmatic-deviation references in §7 expectations may need amendment based on what 2B.2 actually shipped (e.g., the `_build_tsquery_string` shape, the SQLite-fallback dispatch helper name, ranking-heuristic tuning constants).

---

```
Read outputs/cursor_brief_phase_2b_image_storage_search.md end-to-end,
especially §3 (sub-phase boundaries, halt etiquette), §7 (Phase 2B.3
deliverable list -- the close-out sub-phase of Lane 2B), §9 (what
NOT to do -- search-bar surface + endpoint scope guardrails), §10
(acceptable deviations), §11 (risk register), §12 (final report format).

Phase 2A.3 SHIPPED at commit 5fea2ce (Lane 2A
COMPLETE per master plan §4 Phase 2 "Shipped (incremental)" list).
Phase 2B.2 SHIPPED at commit d631c77 (FTS infra
+ chat tier 2 LIKE->FTS swap). Phase 2B.1 (photos schema + R2 +
Pillow + upload route) MAY OR MAY NOT have shipped at dispatch time
-- 2B.3 is order-independent of 2B.1 since the search bar UI doesn't
require photos to function (hero_url in result rows falls through
the existing derive_hero_photo legacy/Google chain if 2B.1 hasn't
shipped). Run git log --oneline -10 and report the top SHAs. Pytest
collect baseline going in is **1607** tests (1 skipped under
skip-unless-postgres for the 2B.2 FTS Postgres-only execution path).
Alembic head is **c8d9e0f1a2b3** (the FTS + pg_trgm
revision 2B.2 introduced); if 2B.1 also shipped, the photos-table
revision sits between 92ce4899dc08 and c8d9e0f1a2b3 --
verify with `python -m alembic heads`.

Ship Phase 2B.3 ONLY per §3 + §7 of the brief -- new `/api/search`
endpoint + search bar UI + Lane 2B close-out. **No new ORM classes,
no migration, no R2/photo touches** (Lane 2B.1's domain -- may or
may not have shipped; 2B.3 is dependency-free of it). **No
app/auth/* changes** (Lane 2A's domain -- closed-out). After this
sub-phase ships + commits, Lane 2B of Phase 2 is COMPLETE assuming
2B.1 has also shipped; if 2B.1 hasn't shipped yet, the Lane 2B
SHIPPED header waits for 2B.1.

ORDER MATTERS WITHIN PHASE 2B.3:
1. First: read the docs + source files in brief §0. Note that the
   brief was authored before 2B.2 (and possibly 2B.1) shipped, so
   line offsets in app/main.py + app/templates/home.html +
   app/templates/provider_profile.html may have moved. Verify the
   public API of 2B.2's app/search/fts.py + app/search/ranking.py
   + app/search/sqlite_fallback.py before anchoring the route --
   the function signatures (build_fts_query, ranking_score_expr,
   build_ilike_query) are the contract you wire against.
2. Then: factor app/search/routes.py per brief §7.1 (NEW file --
   mirrors the app/photos/routes.py shape from 2B.1 if 2B.1 has
   shipped; otherwise mirrors the app/auth/routes.py shape). Route:
     GET /api/search
   Query params:
     q          (required; 400 if missing or empty)
     category   (optional)
     district   (optional)
     entity_type (optional; default any; one of commercial/place/
                  event/program if provided)
     limit      (default 20, max 50)
     cursor     (optional; opaque base64 pagination cursor)
   No auth gate -- search is public. Implementation: parse query
   params into a Tier2Filters-shaped object (or whatever shape
   2B.2's build_fts_query accepts -- verify); call
   app/search/fts.py::build_fts_query (which dialect-dispatches
   between fts.py Postgres path and sqlite_fallback.py SQLite
   path); apply ranking from app/search/ranking.py; return JSON
   shape {results: [...], next_cursor: str | None} where each
   result row is {entity_id, entity_type, slug, name, description,
   district, hero_url}. The hero_url derivation should call the
   existing app/providers/queries.py::derive_hero_photo three-tier
   chain (Photo-row if 2B.1 shipped -> legacy hero_pin_photo_url ->
   Google) -- DO NOT reinvent the chain.
3. Then: anchored Edit on app/main.py to wire the search router.
   Grep for the existing photo / auth / admin router includes
   (likely a cluster of `app.include_router(...)` calls around
   :100-:200; verify before edit). Add the search router include
   in the same block. No changes to the lifespan / cleanup loop /
   middleware -- search is a pure read endpoint.
4. Then: anchored Edit on app/templates/home.html per brief §7.2.
   Add a search bar near the top of the page (above the chat
   surface OR above the featured-providers section -- UX call;
   match existing visual treatment). Shape: single text input
   (`name="q"`) + submit button + a results-dropdown <div> that
   JS populates. Match existing template idiom -- if the project
   uses htmx attributes, prefer that; if vanilla JS, prefer that.
   Grep for hx-get / hx-post / data-* attributes in existing
   templates to confirm idiom before authoring.
5. Then: anchored Edit on app/templates/provider_profile.html
   per brief §7.2. Smaller search affordance in the header
   (matches the home-page treatment but constrained to fit the
   profile-page chrome). Same input/submit/results-dropdown
   shape; reuse the JS module from step 6.
6. Then: new app/static/search.js (or inline if the project's
   existing pattern is inline -- grep for app/static/*.js to
   verify). Submits form to /api/search?q=... via fetch, renders
   top 8 results in the dropdown with click-through links to
   entity profiles (URL shape: `/provider/<slug>` for commercial
   entities; verify the existing route shape for events/programs/
   places if results include those types). No frameworks; vanilla
   JS to match existing project style. Anonymous-viewer regression:
   the search bar visible + functional with no `current_user`
   requirement.
7. Then: new tests per brief §7.3 -- new file tests/test_search_route.py.
   Eight tests minimum (per §7.3 numbered list):
   - GET /api/search?q=plumber returns ranked JSON (top 20)
   - Anonymous viewer can call the endpoint (no auth gate)
   - q missing -> 400
   - Filter combinations: ?q=coffee&entity_type=commercial
   - Pagination cursor round-trips correctly
   - Result shape includes hero_url (uses Photo+derive-hero-photo
     chain from 2B.1 if shipped; otherwise legacy/Google chain)
   - Voice-battery synonym expansion works via the search bar
     (test q=barbershop returns barber-tagged providers; relies
     on 2B.2's _category_needle_set integration into fts.py)
   - Search bar UI rendered on home + provider profile pages
     (template smoke test asserting the input element + submit
     button are present in the rendered HTML)
8. After all of the above: confirm full pytest stays green, ruff
   clean, that `python -m alembic upgrade head` against a fresh
   dev DB still reaches the FTS revision c8d9e0f1a2b3
   cleanly (no new migration in 2B.3), and manually smoke the
   search bar: visit /home, type "plumber" into the search bar,
   submit -> dropdown renders results in rank order -> click a
   result -> lands on /provider/<slug>. Repeat from
   /provider/<slug> page (search bar in header).

POSTGRES COMPATIBILITY (carried forward from brief §9 -- no new
migration in 2B.3, so the portability rules apply only if you
discover a need for a new column or new index; unlikely):
- No new alembic migration in 2B.3. If Cursor discovers a need
  (e.g., a new pagination index on entities for cursor stability),
  flag in §13 -- do not author the migration without explicit
  operator authorization, since 2B.2 already locked the FTS
  schema shape and adding a new migration here would extend
  Lane 2B scope beyond brief §7.
- All FTS dispatch happens through 2B.2's app/search/fts.py +
  sqlite_fallback.py + ranking.py. The /api/search route is a
  pure consumer of that infra -- it does NOT add raw SQL, raw
  tsquery composition, or raw LIKE chains. If you find yourself
  reaching for raw SQL in routes.py, halt and flag in §13 --
  the dispatch should go through fts.py.
- App-layer queries on Entity should use SQLAlchemy Core / ORM
  constructs that translate cleanly to both dialects (2B.2 already
  proved this works; 2B.3 just consumes).

DEVIATION INVITATIONS (per brief §10):
- **UI mount point on home.html** -- the brief says "above the
  chat surface OR above the featured-providers section." Pick
  whichever matches the existing visual treatment cleanly;
  document choice in §13. If neither slot exists, propose a
  third (e.g., a sticky-top header bar) and flag in §13.
- **htmx vs vanilla JS for results render** -- if the project
  already uses htmx (grep for hx-get / hx-trigger), prefer that
  idiom; if not, vanilla fetch + DOM manipulation. Brief §7.2
  says "no frameworks; vanilla JS to match existing project
  style" -- verify the project style before authoring.
- **Ranking-heuristic tuning** -- if 2B.2 shipped the ranking
  defaults from brief §2 (`ts_rank` x 100 base + bonuses) and
  manual smoke produces weird top-N ordering (e.g., outdated
  verifications outrank fresh ones, or featured outweighs query
  relevance for ambiguous queries), flag in §13 with the observed
  ordering. **Do NOT silently re-tune the constants in
  app/search/ranking.py -- that's 2B.2's domain.** A re-tune is
  acceptable only if explicitly flagged + operator approves.
- **Pagination cursor shape for /api/search** -- opaque base64
  of (score, entity_id) for stable seek-pagination is the cleaner
  shape than offset; but offset is simpler. Either is fine for
  V1 per brief §10. Document choice.
- **Search bar visual treatment** -- per brief §10, if you find
  an existing search-bar slot in home.html that this brief
  didn't anticipate (e.g., a placeholder div), use it. Deviate
  to fit existing visual rhythm without breaking it.
- **Template smoke test depth** -- the brief §7.3 test #8 asks
  for "template smoke test" assertion. A grep-the-HTML assertion
  (`assert '<input name="q"' in response.text`) is acceptable;
  full BS4 / lxml parsing is overkill. Document choice.

WHAT NOT TO DO (per brief §9):
- **Don't touch app/search/fts.py, app/search/sqlite_fallback.py,
  or app/search/ranking.py from 2B.2** unless absolutely necessary
  and explicitly flagged in §13. Those modules are the contract
  the /api/search route consumes; 2B.3 is the consumer, not the
  author. If you find a bug in fts.py during 2B.3 manual smoke,
  flag in §13 -- do NOT silently fix it in the same sub-phase.
- **Don't add a new alembic migration.** No schema changes in 2B.3.
  If you discover a need (e.g., index on entities.slug for cursor
  pagination), flag in §13 -- do not author it inline.
- **Don't touch chat-route response shape.** /api/search is a NEW
  endpoint, completely separate from /chat. Tier 2 / Tier 3
  retrieval consumes 2B.2's FTS infra independently; the chat-
  route response shape stays exactly as 2B.2 left it.
- **Don't touch app/auth/*.** Lane 2A is closed-out; 2B.3 is a
  public endpoint with no auth gate -- the route does not import
  from app/auth/dependencies.py / claims.py / favorites.py / etc.
- **Don't touch app/photos/*.** Lane 2B.1's domain. The /api/search
  result row's hero_url field calls the existing
  app/providers/queries.py::derive_hero_photo helper -- that helper
  handles the Photo-row tier internally (if 2B.1 shipped) or falls
  through to legacy/Google (if 2B.1 hasn't). 2B.3 does NOT directly
  import from app/photos/.
- **Don't add user-authored search-history persistence in V1.**
  Brief §7 does not mention search history; V1 search is stateless
  per the design memo posture. Operator may add a SearchHistory
  table in a later phase if analytics need it -- not now.
- **Don't bypass the FTS infra by adding raw LIKE chains in
  routes.py.** The dispatch goes through 2B.2's fts.py (Postgres
  path) and sqlite_fallback.py (SQLite test path). Any new LIKE
  chain in app/search/routes.py is an architecture-level mistake
  -- it duplicates infra and bypasses the synonym-expansion
  semantics 2B.2 locked in.
- **Don't add a search-bar surface beyond home + provider
  profile.** Brief §7.2 explicitly names those two templates;
  do NOT also wire the search bar into chat templates, admin
  templates, claim templates, account templates, or place
  templates. Those are V1.5 surfaces.
- **Don't change the existing home.html chat-surface chrome
  or featured-providers chrome.** The search bar is ADDITIVE
  above one of them; the existing chrome stays exactly as it
  is. Anonymous-viewer regression: home page renders identically
  for anonymous viewers except for the new search-bar element.
- **Don't add search-result faceting UI (sidebar with checkbox
  facets) in V1.** The route accepts `category` + `district` +
  `entity_type` query params -- the search bar UI exposes a
  single text input + submit; facet UI is V1.5. Brief §7.2
  scope is intentionally minimal.
- **Don't proceed past a baseline mismatch.** If 2B.2 hasn't
  shipped (no app/search/fts.py on disk; no FTS alembic
  revision in heads), halt at §0.

HALT at the §3 Phase 2B.3 boundary. After 2B.3 ships + commits,
**Phase 2 Lane 2B is COMPLETE** assuming 2B.1 has also shipped --
the master plan §4 Phase 2 "Shipped (incremental)" list gets a
2B.3 ship-line AND a Lane 2B SHIPPED header per the Phase 1
cd079fc precedent. If Lane 2A is also closed-out (which it should
be by 2B.3 dispatch time), **Phase 2 of the master build plan is
COMPLETE**, and Phase 3 (v1.1 schema pass + category taxonomy
rewrite + districts table + alerts schema) becomes the next
dispatchable lane.

Same constraints as 2A.1 + 2A.2 + 2A.3 + 2B.1 + 2B.2:
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- No git add / commit / push / amend (operator commits -- Rule 2+12)
- Pytest must stay green throughout (both SQLite path AND, if
  you can boot one, the Postgres path -- /api/search dispatches
  through 2B.2's dialect-aware infra so both backends should work)
- Report per brief §12 (final report format) for sub-phase 2B.3 only
```

---

## After Cursor returns with the §12 report

Same rhythm as prior sub-phases: paste back to the Cowork primary chat, primary reviews against §7.4 acceptance gates, recommends commit batch by explicit paths (Rule 8 — one substantive lane per commit), operator commits + pushes.

Expected files touched:
- 1 new file `app/search/routes.py` (or appended to the existing `app/search/__init__.py` that 2B.2 created — Cursor's call based on shape; flag in §13)
- 1 new file `app/static/search.js` (vanilla JS; or inline-in-template if existing project style is inline)
- 1 new test file `tests/test_search_route.py` (~8 tests per §7.3)
- 1 modified `app/main.py` (search router include — single `app.include_router(...)` line in the existing router-include block)
- 2 modified templates (`app/templates/home.html` + `app/templates/provider_profile.html`) — search bar markup + a small script-tag include for `search.js`
- Possibly 1 modified `app/templates/base.html` or similar shared chrome if the search bar needs to mount at a shared header rather than per-page

Expected pytest delta: +8-15 net-new tests (the brief §7.3 specifies ~8 tests minimum, plus a couple of edge-case smoke tests Cursor may add for pagination + filter combinations). Pre-existing chat-route + Provider-profile anonymous-viewer tests must all stay green.

Expected effort: 1-2 day brief estimate; one Cursor session realistically (smallest sub-phase of Lane 2B).

Expected pragmatic deviations: (a) UI mount point on home.html (above chat-surface vs above featured-providers vs new sticky header); (b) htmx vs vanilla JS for results render (depends on existing project idiom); (c) pagination cursor shape (opaque base64 of (score, entity_id) vs simpler offset); (d) template smoke test depth (HTML grep vs structured parse).

## After Phase 2B.3 ships

Update master plan §4 Phase 2 "Shipped (incremental)" list with the 2B.3 ship-line (same pattern as 2A.1 / 2A.2 / 2A.3 / 2B.2 entries). Update STATE.md Production block + "Recently shipped" §1 with the Lane 2B close-out narrative.

**If 2B.1 + 2B.2 + 2B.3 have all shipped:** Lane 2B of Phase 2 is COMPLETE. Add a Lane 2B SHIPPED header (mirroring the Phase 1 SHIPPED header pattern from session-16's `cd079fc`). Combined with Lane 2A (closed-out by 2A.3 ship), **Phase 2 of the master build plan is COMPLETE**; mark Phase 2 SHIPPED in the master plan §4 header.

**Next dispatchable lane:** **Phase 3** (v1.1 schema pass + category taxonomy rewrite + districts table + alerts schema). The Phase 3 brief is not yet authored at the time of this 2B.3 dispatch prompt's writing — operator authors it after Phase 2 closes out, citing the Phase 1 + Phase 2 closed-out infra as the new baseline.

**If 2B.1 hasn't shipped yet** (still in flight or still gated): 2B.3 ship-line lands in the master plan, but the Lane 2B SHIPPED header waits for 2B.1's ship. Operator re-dispatches 2B.1 (if not already in flight) with a fresh dispatch prompt; the Lane 2B close-out narrative consolidates after all three sub-phases land.
