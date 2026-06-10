# golakehavasu integration -- project close-out (2026-05-30)

ASCII-only. Single source of truth for the whole golakehavasu arc: the four
inbound follow-ups, the cron outage found + fixed mid-stream, and the full
partner feature shipped to prod. Written so a future session (or Casey in a
month) has the complete picture in one place.

====================================================================
## TL;DR -- where things stand
====================================================================
- golakehavasu EVENTS: live, auto-approved, cron Tue/Thu/Sat. (Pre-existing.)
- golakehavasu PARTNERS: NOW LIVE in prod for the first time. 543 listings
  loaded; surfaced in chat + category pages. Weekly cron (Sun 09:40 UTC) keeps
  them fresh.
- Prod cron outage (events crons failing): root-caused + fixed (schema drift +
  no auto-migrate on deploy).
- All shipped via PR #62 (merged, c99ed33) + post-merge hotfixes on main.

====================================================================
## 1. The four inbound follow-ups (original handoff)
====================================================================
TASK A -- fuzzy-name-at-geo merge for pending partners: DONE. Plus a SECOND tier
added after a live dry-run review showed name-fuzzing alone only caught 5 of 320:
the website/phone CONTACT tier (_contact_match), which became the workhorse (190
of 241 prod merges). Both tiers only merge onto a unique Google-backed row;
anything ambiguous stays pending.

TASK C -- per-listing partner categories: DONE + extended. Found the reliable
source the original handoff missed: <main data-dms-category-name> on each detail
page. Built CVB->Hava Tier-1 map AND (this session) a CVB->legacy-string map so
BOTH category surfaces match (see section 3). Census: 543 listings, 60 distinct
CVB categories.

TASK B -- river_scene dedup consolidation: backfill migration written
(d3e4f5a6b7c8); river_scene_pull migrated to reconcile_event-only; 3 pinned tests
rewritten. Shipped on its own branch/PR (#63 family). NOTE: confirm #63 status
(this close-out focuses on partners/PR #62).

TASK (implicit) -- "fully working in Ask Hava": required consumption-side work
the original handoff didn't scope -> sections 2-3.

====================================================================
## 2. The cron outage (found + fixed mid-project)
====================================================================
Symptom: golakehavasu-events + river-scene-events crons emailing failures.
Root cause: prod Postgres was 3 Alembic migrations behind main. The missing
providers.google_photo_urls column made every select(Provider) (inside
reconcile_event) raise UndefinedColumn -- killing both event crons.
Deeper root cause: NOTHING ran `alembic upgrade` on deploy, so prod schema
silently drifted from main on every code-only deploy.
Fixes:
- Manually ran `alembic upgrade head` on prod (-> c2d3e4f5a6b7). Crons green.
- Added railway.json preDeployCommand "alembic upgrade head" so it never drifts
  again. (Confirmed prod at head via Railway CLI.)

====================================================================
## 3. The consumption-side work (what "fully in Ask Hava" required)
====================================================================
Verified how Ask Hava READS providers, not just how the loader writes them:
- Visibility gate everywhere = is_active=True AND draft=False (no embedding
  needed). entity_type is hardcoded "commercial" for all providers, so partners
  are chat- and category-visible.
- TWO category surfaces:
  * MODERN (app/api/routes/category_pages.py): filters category_id ->
    Category.slug; valid slugs = the 12 locked TIER_1_CATEGORY_SLUGS.
  * LEGACY (app/categories/queries.py CATEGORY_FILTERS): filters the free-text
    Provider.category string.
  Fix shipped: loader writes BOTH -- Tier-1 slug into category_id AND a legacy
  string into Provider.category. (Post-merge hotfix c303f88 corrected the loader
  that was still writing tier-1 slugs into Provider.category.)
- Pending partners were write-only (no admin approval UI -> all consumption hides
  draft=True). Fix shipped: app/admin/provider_approval.py -- queue at
  /admin/providers/pending + approve/reject + pending_provider_count on the admin
  funnel.
- Card rendering with no photo/rating/embedding: audited -> renders cleanly
  (placeholder tiles, gated rating blocks; no broken <img>, no crash). No fix
  needed.

CATEGORY MAP EXTENSION (this session, after ship): added Attractions / Family-Fun
/ Guided Tour / Tours / Entertainment / Activities / Venues to BOTH maps. They
have no dedicated Tier-1 category (the 12 are locked), so Tier-1 ->
classes-sports-recreation and legacy -> entertainment_attractions / tourism
(which route to the attractions + things-to-do legacy pages). Recovers ~65
listings; takes effect on the next partner load / cron run. Tests updated.
Coverage goes from ~74% to ~86% of 543 confidently categorized.

====================================================================
## 4. First prod partner load -- results
====================================================================
First APPLY (pre legacy-category fix): inserted 211, inserted_pending 91,
updated 241 (updated_contact 190, updated_fuzzy 2). One earlier APPLY failed on
address length -> hotfix 34b7c92 truncates Location.address to VARCHAR(255).
Legacy-category re-run (after c303f88): idempotent_updated 313, updated 230
(updated_contact 181), retired_duplicates 118, inserted 0 / pending 0. Live CVB
rows now carry legacy category strings (e.g. 27 "restaurant").
E2E verified: /categories/eat-drink lists CVB restaurants; chat "where can I eat
in Lake Havasu" returns CVB partners; reconciler merges behave as designed (e.g.
"Lobster 3 Ways" merged onto Google's "Lobster 3 Ways Food Truck" via contact).

====================================================================
## 5. OPEN ITEMS (what's left)
====================================================================
HUMAN / OPS:
- [security] Rotate prod Postgres password + Bright Data key at project end
  (exposed in chat). Casey: deferred to end-of-project credential rotation.
- [deploy] Wait for Railway to deploy latest main so the provider-approval UI +
  railway.json preDeploy are live. (/admin/providers/pending currently 303s only
  because that code isn't deployed yet.)
- [data] After deploy, run the partner load ONCE MORE so the new attractions
  category mappings (section 3) apply to the ~65 affected rows -- OR just let the
  Sunday cron do it.
- [data] Approve the ~91 pending partners at /admin/providers/pending after
  deploy.
- [verify] Confirm the weekly golakehavasu-partners cron run completes green
  (manual run 26692444397 already succeeded, 17m).

PRODUCT DECISION (not blocking):
- Ask Hava has no "Attractions / Things-to-do" Tier-1 category (the 12 are
  locked). Attractions/tours partners currently bucket under
  classes-sports-recreation on the modern surface (correct on the legacy
  attractions page). If that bucket is undesirable, the clean fix is adding a
  real "attractions" Tier-1 Category (migration + seed row + category-page
  config) -- own PR, your call.

CODE FOLLOW-UPS (nice-to-have):
- [dx] Real dry-run preview for the partner loader: ingest_partners() returns
  before the reconcile/insert section when dry_run=True, so --dry-run only proves
  the parse, not insert/merge counts. Add a plan mode that runs reconcile
  read-only and prints projected counts.
- [taxonomy] The outdoors family (hiking/parks) has Tier-1 outdoors-parks-trails
  but legacy "recreation" (routes to classes-sports-recreation / things-to-do).
  Same row, two surfaces, slightly different page. Acceptable; revisit if a
  taxonomy cleanup happens.
- [Task B] Confirm river_scene PR (#63) merged + its backfill migration applied
  to prod (chains onto c2d3e4f5a6b7; railway preDeploy now handles it).

====================================================================
## 6. Key files (final)
====================================================================
Scraper/parse:   app/contrib/golakehavasu.py (events), golakehavasu_partners.py
                 (partners + CVB->Hava + CVB->legacy maps)
Loader:          scripts/golakehavasu_partners_load.py (idempotency, contact +
                 fuzzy merge tiers, dual category write, --reconcile-pending)
Reconcilers:     app/contrib/ingest_reconciler.py (providers),
                 app/contrib/event_reconciler.py (events)
Admin:           app/admin/provider_approval.py (pending review UI)
Crons:           .github/workflows/golakehavasu-events.yml,
                 .github/workflows/golakehavasu-partners.yml
Deploy safety:   railway.json (preDeployCommand alembic upgrade head)
Tests:           tests/test_golakehavasu_partners.py,
                 tests/test_admin_provider_approval.py,
                 tests/test_event_reconciler.py, tests/test_phase8_10_river_scene.py

====================================================================
## 7. Throwaway files to delete (NOT for commit)
====================================================================
Scratch helpers created during diagnosis/load (repo root):
run_reconcile_dryrun.cmd, run_diagnose.cmd, run_dbshape.cmd, run_dbshape_prod.cmd,
run_alembic_current.cmd, run_alembic_upgrade_prod.cmd, run_partners_load_prod.cmd,
diagnose_fuzzy.py, diagnose_dbshape.py, diagnose_fuzzy.txt, diagnose_dbshape.txt,
diagnose_dbshape_prod.txt, reconcile_dryrun.txt, PATCH_contact_tier_for_cursor.md,
CURSOR_KICKOFF_partners.md, BUILD_SPEC_partners_full_implementation.md,
GOLAKEHAVASU_PARTNERS_IMPLEMENTATION_PLAN.md, PARTNERS_IMPLEMENTATION_STATUS.md.
(run_partners_load_prod.cmd is handy to keep if you re-load manually.)
KEEP: railway.json, the workflow yml, DEPLOY_MIGRATION_GAP.md, this close-out.
