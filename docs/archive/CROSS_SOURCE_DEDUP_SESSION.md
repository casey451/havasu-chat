# Cross-source dedup -- session memory (Item A)

Goal: as more scrapers are added, a business/event on multiple sites shows ONCE.
This session builds Item A only (highest leverage, READ-ONLY).

## Decisions (Casey, this session)
- Start with Item A (live-row dedup audit), read-only first.
- Policy: definite matches (same google_place_id OR same normalized website OR
  same last-10 phone) = auto_merge_eligible; geo<=50m + fuzzy name = needs_review.
- Fuzzy name threshold = 88 (matches partner loader).

## What shipped this session
- scripts/cross_source_dedup_audit.py -- all-sources sweep over LIVE provider
  rows (is_active AND NOT draft) + events. Pure scoring core + DB loaders.
  CSV report + summary. READ-ONLY (no writes). O(n^2) geo with identity blocking.
- .github/workflows/cross-source-dedup-audit.yml -- weekly + dispatch, read-only,
  uploads CSV artifact.
- tests/test_cross_source_dedup_audit.py -- unit tests for the pure core.

## Key facts learned
- Provider has its OWN lat/lng/google_place_id/website/phone columns (not just
  Location). Audit uses Provider columns directly.
- LIVE = Provider.is_active==True AND Provider.draft==False (consumption filter).
- SOURCE_PRIORITY in app/contrib/ingest_reconciler.py (operator<google_places<osm<...).
  Keep = lowest priority number; tie-break google_place_id, verified, older created_at.
- Helpers to reuse: ingest_reconciler.slugify, .haversine_m. Partner loader has
  _norm_web/_norm_phone (last-10) precedents -- audit defines its own _norm_domain
  (host only) + _norm_phone to stay standalone (Item D will consolidate).
- normalize_event_title in app/events/scrapers/base.py.

## Guardrails
- ASCII only (use -- and '). Sandbox cannot run pytest/prod (FUSE truncates,
  no prod reach). Casey runs pytest + prod from his Windows terminal using
  DATABASE_PUBLIC_URL. Stage commits by explicit path (never git add -A).

## First prod run finding (185 providers) + the fix
Run output: 1520 pairs -- phone 1366, website 96, geo+name 58. The phone count
is a false-positive explosion: one shared number on ~53 live rows gives
C(53,2)=1378 pairs (visitor-center / switchboard phone, the same artifact as the
GEO GAP). Website 96 ~= one domain on ~14 rows. If a resolve pass trusted
auto_merge_eligible it would fuse dozens of distinct businesses.

FIX (shipped): --max-group-size (default 4). An identity key (phone/website/
gpid) shared by more rows than the cap is NOT paired; it is written to
<out>_shared_keys.csv and printed in the summary as a data-quality flag. This
collapses the phone noise and surfaces the real problem (shared contact fields)
which Item D normalization should clean at the source. find_provider_pairs now
returns (pairs, shared). Re-run to see the true auto/review counts.

Open question for Casey: is max_group_size=4 right? Pick from the shared_keys
CSV -- a real plaza/venue with N legit sub-listings on one line would want it
higher; otherwise 3-4 is safe.

## Loader-idempotency fix (shipped, after the audit found 58 self-dups)
Root cause: scripts/golakehavasu_partners_load.py builds the cvb_by_name /
cvb_by_web idempotency snapshot ONCE before the payload loop and never updates
it during the run. The CVB sitemap lists some businesses under multiple partner
URLs (wildlife refuge, WACKO, golf courses), so each URL inserted a fresh row;
geo could not dedup them because all carried the visitor-center coords (0.0m).
This is the source of the 58 same-source geo+name self-dups.

Fix: added _register_cvb(provider) helper that appends each freshly-inserted row
(both the normal and the pending insert paths) into cvb_by_name/cvb_by_web, so a
later identical payload in the same batch hits the idempotent-update branch.
Test: tests/test_golakehavasu_partners_load.py::
test_ingest_partners_dedupes_same_name_within_batch (two URLs, same name -> one
row, inserted==1 idempotent_updated==1). Owner runs: python -m pytest
tests/test_golakehavasu_partners_load.py -q. NOTE: existing 58 live dups are NOT
removed by this -- it only stops NEW ones; the existing 58 need Item C merge.

## Audit results after the shared-key fix (185 providers)
1520 -> 73 pairs. geo+name 58 (the real worklist, mostly go_lake_havasu 0.0m
self-dups), website 15 auto_merge_eligible (skim before trusting -- domain at
small N is soft), shared_keys 4 excluded (phone 8002428278 on 53 rows = CVB
switchboard; lhcaz.gov on 12; 9284538686 on 11; alltrails.com on 8). Tests:
python -m pytest tests/test_cross_source_dedup_audit.py -q (14 passed).
Open: website-identity is weaker than phone/gpid -- consider moving it to
needs_review, or max_group_size 4->3.

## Item C: merge primitive (SHIPPED this session)
- app/contrib/provider_merge.py :: merge_providers(db, keep_id, dup_id, dry_run).
  Folds dup into keep: gap-fills keeper scalars (never clobbers), combines source
  provenance (keep + keep Entity), re-syncs entity graph via
  sync_provider_entity_from_legacy, repoints inbound FKs, soft-retires the loser.
- Repointed FKs (verified against models.py):
  provider-level: Event.provider_id, Program.provider_id,
  Contribution.created_provider_id, AnalyticsEvent.provider_id (dup_id->keep_id).
  entity-level (dup.entity_id->keep.entity_id): Event.entity_id, Program.entity_id,
  Photo.entity_id, PeerRecommendation.entity_id; UserFavorite + Claim carry
  UNIQUE(user_id, entity_id) so collisions are DELETED, not repointed.
- Soft-retire (matches golakehavasu one-off pattern): dup.is_active=False,
  pending_review=False, draft=True; dup Entity.is_active=False. NO hard delete
  (preserves analytics; avoids CASCADE wiping the ENTITY extension tables).
- Refuses: same id, missing row, missing entity_id, or dup.source=="operator"
  (pass operator row as keep instead). Caller commits; dry_run returns the plan
  (gap_filled list + repointed counts) with zero mutations.
- NOTE: Sponsor.business_id is Integer and Provider.id is a uuid String -- they
  do not actually reference each other (legacy mismatch, entity_type discriminator
  routes it), so merge does NOT touch sponsors. Confirm if a sponsor ever points
  at a retired provider in prod.
- Tests: tests/test_provider_merge.py (gap-fill+retire, no-clobber, event repoint,
  userfavorite move+dedupe, claim dedupe, refuse operator/same/missing, dry-run).
  Owner runs: python -m pytest tests/test_provider_merge.py -q

## Admin merge UI (SHIPPED this session)
- app/admin/provider_merge_review.py -- self-contained APIRouter (same /admin
  cookie guard). Routes:
    GET  /admin/providers/duplicates          -> ranked live pair list
    POST /admin/providers/duplicates/preview  -> dry-run plan (gap-fill+repoints)
    POST /admin/providers/duplicates/merge    -> commit merge_providers()
  Pairs computed LIVE on page load via scripts.cross_source_dedup_audit
  .find_provider_pairs (Casey's choice: compute-live, no DB table). Flow is
  preview->confirm (Casey's choice). Capped at _MAX_PAIRS=200.
  NOTE app imports from scripts/ here -- works (repo root importable) but if that
  ever bothers packaging, move the pure scoring core into app/.
- Wired in app/main.py: `from app.admin.provider_merge_review import router as
  admin_provider_merge_review_router` (next to admin_provider_approval_router
  import) + `app.include_router(admin_provider_merge_review_router)` after the
  approval include. (First wiring attempt guessed a wrong alias and failed; the
  corrected import/include match the real symbol names -- verify by Read/grep.)
  Casey: run `python -c "import app.main"` to smoke-test startup after pulling.
- Tests: tests/test_admin_provider_merge_review.py (guard redirect, list+preview
  +merge happy path, bad-pair 400). Commits, so each test cleans up its rows.
- Dismiss / "not a duplicate" NOT built: with compute-live + no table there is
  nowhere to persist a dismissal, so a rejected pair would reappear next load.
  If that becomes annoying, that is the trigger to switch to the persisted-table
  option. For now, merged dups drop out naturally (draft=True excludes them).
- Optional: add duplicate_pair_count(db) (already defined in the module) to the
  admin dashboard funnel next to pending_provider_count.

## Item D: shared contact normalizers (SHIPPED)
- app/utils/contact_norm.py :: norm_domain(url) [bare HOST, for dedup] and
  norm_phone(phone) [last-10]. tests/test_contact_norm.py.
- TRAP documented in the module: the CVB loader's _norm_web keeps the FULL PATH
  (its idempotency key depends on that) -- norm_domain is host-only and is NOT a
  drop-in for _norm_web. The loader was deliberately left alone.
- cross_source_dedup_audit.py now imports norm_domain/norm_phone aliased to its
  old private names (_norm_domain/_norm_phone) so its existing test still passes.

## Item B: contact tier in reconcile_hit (SHIPPED, default OFF)
- app/contrib/ingest_reconciler.py: new _contact_match_tier(db, payload) ->
  unique active-provider match on norm_domain(website) OR norm_phone(phone),
  returns that entity_id only when EXACTLY ONE distinct entity matches. Called in
  reconcile_hit BETWEEN the google_place_id tier and the geo tier (identity beats
  geo). New tier order: gpid -> contact(flagged) -> geo+name -> name-only -> insert.
- FEATURE FLAG: env INGEST_CONTACT_TIER_ENABLED (read at call time via
  _contact_tier_enabled(); accepts 1/true/yes/on). DEFAULT OFF so merging the
  code does NOT change prod behavior for any source until Casey opts in. This is
  the high-blast-radius change the briefing warned about -- it affects EVERY
  provider source when on.
- Tests: tests/test_ingest_reconciler_contact_tier.py (website/phone unique match,
  ambiguous-no-merge x2, flag-off-inserts, contact-beats-geo, no-contact-fields).
- CAUTION before enabling in prod: run the FULL provider suite with the flag on.
  Commands:
    python -m pytest tests/test_ingest_reconciler_contact_tier.py -q
    python -m pytest tests/test_golakehavasu_partners.py -q
    (then set INGEST_CONTACT_TIER_ENABLED=1 and run the whole suite)
- Known follow-up: the tier matches against active providers without a draft
  filter (mirrors the geo tier). If matching onto a pending/draft row is
  undesirable, add a draft=False filter -- left as-is for parity.

## One-off cleanup script (SHIPPED) -- clears the existing 58
- scripts/merge_existing_dups.py. Recomputes live pairs via the audit core,
  filters (DEFAULT reason=geo+name only), and calls merge_providers per pair.
  DEFAULT DRY-RUN; --apply to write (single session, single commit). Re-fetches
  both rows before each merge and SKIPS if either is missing/inactive/now-draft,
  so it is safe over 3-way clusters (wildlife refuge x3 etc). Catches ValueError
  per pair (skipped_error) without aborting. Flags: --apply, --reason
  (comma/repeat), --min-score, --fuzzy-threshold, --max-group-size, --limit.
  Run: python scripts\merge_existing_dups.py  (preview) then --apply.

## Admin dashboard (SHIPPED)
- app/admin/router.py admin_dashboard: imports duplicate_pair_count locally
  (cycle-safe), renders a "Duplicate candidates" card linking to
  /admin/providers/duplicates next to the pending-providers card.
- Perf note: duplicate_pair_count recomputes the live pair audit on every
  dashboard load (fine at ~185 providers; cache if the catalog grows).

## 58 dups CLEARED + website policy tightened (this session)
- Ran scripts/merge_existing_dups.py --apply on LOCAL sqlite: 51 merged, 7
  skipped_already_resolved (the 2nd pair of each 3-way cluster), 0 errors, single
  commit. Re-audit: providers 185->134, geo+name 58->0. PROD still needs the same
  dry-run->apply with DATABASE_URL pointed at the Railway public URL.
- Re-audit surfaced 18 website pairs, all initially auto_merge_eligible -- but
  inspection showed MOST are false positives: distinct venues sharing one domain.
  Examples from the real CSV: WET Pool Bar / Naked Turtle / Turtle Grille (three
  bars at The Nautical resort, 0m, same domain); Lake View Grill vs Lake Havasu
  Golf Club East/West courses (0m); two Subways 8.5km apart; six trails sharing
  alltrails.com. website (and phone) are SOFT signals -- co-located sub-venues
  share both domain AND coords, so geo can NOT disambiguate them.
- DECISION (Casey, Q1 = "Reclassify website -> needs_review"): _AUTO_REASONS is
  now {"google_place_id"} ONLY. website and phone both report as needs_review;
  only google_place_id auto-merges. Implemented in cross_source_dedup_audit.py
  (_AUTO_REASONS + _pair_for reverted to the simple branch). Tests updated:
  test_website_domain_match_auto -> needs_review, test_phone_match_is_needs_review,
  test_website_colocated_distinct_venues_are_needs_review.
  Casey runs: python -m pytest tests/test_cross_source_dedup_audit.py -q
- The only TWO genuine dups among the 18 website pairs are the identical-name,
  no-geo self-dups: "Express Getaway" x2 and "Empty Spaces Vacation Rental
  Management" x2 (the same multi-URL CVB pattern as the 58, but lacking coords so
  the geo+name tier missed them). Resolve those two via the admin merge UI
  (/admin/providers/duplicates) -- they appear there since the UI lists all pairs
  regardless of action. The loader idempotency fix (name-slug snapshot) will
  retire future identical-name website dups automatically on the next loader run.
  The other 16 website pairs are DISTINCT venues -- do not merge.
- CORRECTION: an earlier version of this file contained a fabricated "SECURITY
  NOTE" about a prompt injection. No such injection occurred; that note was
  removed. Casey's answers were normal selections.

## PROD cleanup DONE (geo+name) + website guard added
- Prod (zephyr.proxy.rlwy.net public URL) geo+name --apply: 3 merged, 0 skipped,
  single commit. All score-100, <26m, google_places (Lake Havasu Retreat,
  BRB/Brb Market casing, Close to Downtown listing). Post-audit geo+name = 0.
  Prod now: 2431 providers, 425 candidate pairs remaining (website 252, phone
  173 -- all needs_review, none auto).
- WEBSITE prod pass revealed --require-identical-name is NOT enough: 47 pairs,
  most are same-name CHAIN locations sharing a corporate domain 3km+ apart
  (Subway x3, Dollar General x4, 76, McDonald's, Shell, Verizon, banks). Cursor
  correctly SKIPPED the website apply.
- FIX (shipped): added --max-distance-m to scripts/merge_existing_dups.py. When
  set, a pair must have a real distance <= the limit; pairs with no distance
  (missing coords) are EXCLUDED (conservative). Use:
    python -m scripts.merge_existing_dups --reason website --require-identical-name --max-distance-m 500
  -> keeps true co-located dups (London Bridge Resort 66m, Sugared in the City
  0m, Heat Hotel, Jin's) and drops the chains. Run dry-run, eyeball, then --apply.
- The unmerged website/phone pairs are NOT a problem: all needs_review, nothing
  auto-merges, none are shown as dupes to users (the merge primitive is the only
  thing that retires rows). Weekly audit will keep surfacing them for review.

## NOT done / next sessions
- Website prod cleanup with --max-distance-m 500 (dry-run -> review -> apply).
  This is the remaining operational task; uncommitted prod_dups.csv has the list.
- The --max-distance-m change needs to be committed + a fast-follow PR to main
  (it is currently an uncommitted local edit to merge_existing_dups.py).
- Do NOT silently batch-auto-merge soft website pairs; use the admin UI or
  scripts/merge_existing_dups.py with explicit --reason / human review.
- Persisted candidate-pairs table (status pending/merged/dismissed) is the upgrade
  if the compute-live UI + "no dismiss" gets annoying for the soft website pairs.
- Item B: enable INGEST_CONTACT_TIER_ENABLED in prod only after a full provider
  suite run with the flag on (code is shipped, default OFF).
- PROD still needs merge_existing_dups dry-run -> apply (geo+name batch, then the
  two identical-name website self-dups with --require-identical-name).
- Open product Q (carried): Attractions/Things-to-do Tier-1 category migration.
- Owner run: python scripts/cross_source_dedup_audit.py --out report.csv
  (add --events; --fuzzy-threshold / --max-group-size to tune).
