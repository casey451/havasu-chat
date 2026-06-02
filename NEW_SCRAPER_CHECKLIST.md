# Adding a new scraper without creating duplicates

Ask Hava ingests from many sources. Duplicates stay OUT of what users see only if
every scraper follows the same path. This is the checklist. Follow it and a new
source cannot surface a duplicate to a user.

## The 4-layer defense (why this works)
1. Clean inputs -- normalize before matching.
2. Prevent at ingest -- the reconciler merges identity matches; uncertain ones
   are held HIDDEN, never shown.
3. Catch weekly -- the cross-source audit surfaces anything that slipped.
4. Resolve -- admin merge UI (/admin/providers/duplicates) + merge_existing_dups.

A new scraper only has to get layer 1-2 right; 3-4 are already running.

## Required for every new provider scraper

1. Produce an `EntityPayload` (app/contrib/ingest_base.py) per listing. Populate
   as many of these as the source has -- they are what dedup keys on:
   - `name` (required)
   - `lat` / `lng` -- REAL coordinates, not a generic office/visitor-center
     address. Junk geo is the #1 cause of missed matches.
   - `website` and `phone` -- even when geo is missing, a shared site/phone is a
     strong identity signal the reconciler's contact tier uses.
   - `google_place_id` when available (strongest identity key).
   - `source` -- a NEW string; add it to `SOURCE_PRIORITY` in
     ingest_reconciler.py so merge precedence is defined.

2. Route EVERY payload through the shared funnel -- do NOT call reconcile_hit and
   re-implement insert/merge yourself:

       from app.contrib.scraper_ingest import decide_ingest

       d = decide_ingest(db, payload)
       if d.action == "update":
           # merge onto d.existing_id (gap-fill; combine source). No new row.
       elif d.should_hide:
           # AMBIGUOUS: write the provider with draft=True + pending_review=True
           # so it is captured for /admin/providers/pending but NEVER shown.
       else:
           # insert as a normal live row.

   The one rule that prevents user-visible dups: when `d.should_hide` is True,
   the row MUST be written hidden (draft=True + pending_review=True). Consumption
   queries filter draft=False, so held rows are invisible until a human approves.

3. In-batch idempotency: if your source can list the same business under multiple
   URLs in one run (the CVB sitemap does), register each freshly-inserted row in
   an in-run snapshot so a later identical payload updates it instead of inserting
   a second copy. See `_register_cvb` in scripts/golakehavasu_partners_load.py.

4. Add an idempotency / dedup regression test for the source (see
   tests/test_golakehavasu_partners.py::
   test_ingest_partners_dedupes_same_name_within_one_run).

## Adoption status of existing scrapers (Item D, 2026-06-02)
- `scripts/osm_overpass_load.py` and `scripts/places_load.py` route their insert
  path through `decide_ingest` and honour `should_hide` -- an ambiguous match is
  now HELD (draft + pending_review) for review, not dropped (the old behavior
  silently discarded uncertain rows).
- `scripts/golakehavasu_partners_load.py` intentionally calls `reconcile_hit`
  directly: it layers two CVB-specific confident-merge tiers (exact contact
  match, fuzzy-name-within-50m of a Google row) on top of the reconciler before
  deciding to hold. It already honours the hide-on-doubt rule (draft +
  pending_review), which is the invariant the funnel enforces. New scrapers
  without such bespoke tiers should use `decide_ingest` per step 2 above.

## After the scraper is live
- The weekly `cross-source-dedup-audit` workflow will report any cross-source
  pairs the new source introduces. Review them at /admin/providers/duplicates.
- For a backlog clean-up of a specific reason, use scripts/merge_existing_dups.py
  (dry-run default; --reason, --require-identical-name, --max-distance-m, --apply).

## The strongest prevention lever
`INGEST_CONTACT_TIER_ENABLED=1` turns on website/phone identity matching at
ingest for ALL sources (a shared site/phone merges even when name+geo diverge).
It is OFF by default. Enable it after a full provider-suite run with the flag on.
With it enabled, a new source whose names diverge but whose contact info matches
an existing row will merge at ingest instead of becoming a dup.
