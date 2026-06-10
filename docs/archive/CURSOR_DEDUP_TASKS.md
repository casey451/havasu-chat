# Cursor task: finish the cross-source dedup work

You are working in the havasu-chat repo (FastAPI + SQLAlchemy, "Ask Hava"). A
prior session built a full cross-source duplicate detection/merge system. The
code is written and verified-by-read but NOT yet test-run or committed. Your job
is to verify it, run the one safe local cleanup, and prepare (not execute) the
prod + flag steps. Read this whole file before doing anything.

## Hard rules
- ASCII only in any file you edit (use -- not em-dash, plain apostrophe '). Unicode
  dashes/quotes have corrupted edits in this repo before.
- Stage commits by EXPLICIT path. NEVER `git add -A` -- the working tree carries
  unrelated changes (gas-prices, session handoffs).
- Do NOT enable the INGEST_CONTACT_TIER_ENABLED flag anywhere. Leave it OFF.
- Do NOT create or run any Alembic migration (the Attractions category question
  is deferred -- out of scope).
- Do NOT touch prod yourself. You do not have the database URL. Where prod is
  needed, STOP and print the commands for the human to run.
- Do NOT merge the 16 distinct co-located website pairs. Only identical-name
  website pairs may merge (the --require-identical-name flag enforces this).

## Files involved (already written; do not rewrite from scratch)
- scripts/cross_source_dedup_audit.py        (audit scorer; _AUTO_REASONS = {"google_place_id"})
- scripts/merge_existing_dups.py             (cleanup CLI; has --apply, --reason, --require-identical-name)
- app/contrib/provider_merge.py              (merge primitive)
- app/contrib/ingest_reconciler.py           (Item B contact tier, flag-gated OFF)
- app/utils/contact_norm.py                  (norm_domain / norm_phone)
- app/admin/provider_merge_review.py         (admin merge UI at /admin/providers/duplicates)
- app/admin/router.py                        (dashboard duplicate count)
- scripts/golakehavasu_partners_load.py      (loader idempotency fix: _register_cvb)
- tests: test_cross_source_dedup_audit.py, test_provider_merge.py,
  test_ingest_reconciler_contact_tier.py, test_contact_norm.py,
  test_admin_provider_merge_review.py, test_golakehavasu_partners.py

## Step 1 -- Verify (run, report results, do not continue if red)
    python -c "import app.main"
    python -m pytest tests/test_cross_source_dedup_audit.py tests/test_provider_merge.py tests/test_ingest_reconciler_contact_tier.py tests/test_contact_norm.py tests/test_admin_provider_merge_review.py tests/test_golakehavasu_partners.py -q
If anything fails, STOP and show me the failure. Do not "fix" by changing test
expectations without explaining the root cause first.

## Step 2 -- Local audit snapshot (read-only)
    python scripts\cross_source_dedup_audit.py --out provider_dup_candidates.csv
Confirm the summary shows: geo+name 0, website pairs all action=needs_review,
auto_merge_eligible 0, and 3 shared-key flags. Report the numbers.

## Step 3 -- Merge ONLY the 2 identical-name website self-dups (LOCAL db)
Dry run first and show me the output:
    python -m scripts.merge_existing_dups --reason website --require-identical-name
EXPECTED: pairs_considered: 2, both named "Express Getaway" and "Empty Spaces
Vacation Rental Management". If you see ANY other names or a count != 2, STOP and
report -- do not apply. If it matches, apply:
    python -m scripts.merge_existing_dups --reason website --require-identical-name --apply
Then re-run Step 2's audit and confirm website pairs dropped by 2.

## Step 4 -- Commit (explicit paths only)
Stage exactly these (skip any that show no changes), then commit:
    git add app/utils/contact_norm.py app/contrib/provider_merge.py app/contrib/ingest_reconciler.py app/admin/provider_merge_review.py app/admin/router.py app/main.py scripts/cross_source_dedup_audit.py scripts/merge_existing_dups.py scripts/golakehavasu_partners_load.py .github/workflows/cross-source-dedup-audit.yml tests/test_cross_source_dedup_audit.py tests/test_provider_merge.py tests/test_ingest_reconciler_contact_tier.py tests/test_contact_norm.py tests/test_admin_provider_merge_review.py CROSS_SOURCE_DEDUP_SESSION.md CURSOR_DEDUP_TASKS.md
    git status        # show me what is staged BEFORE committing
Show me `git status` and wait for my OK before `git commit`. Use a message like:
"Cross-source dedup: audit, merge primitive, admin UI, loader idempotency fix,
contact tier (flagged off), shared normalizers".
Do NOT push.

## Step 5 -- PROD (do NOT run; print these for me)
Print this block for me to run myself once I have the rotated DATABASE_PUBLIC_URL.
Do not ask for the URL; just output the commands:
    set DATABASE_URL=<Railway public URL>
    $env:DATABASE_URL="<Railway public URL>"
    python -m scripts.merge_existing_dups
    python -m scripts.merge_existing_dups --apply
    python -m scripts.merge_existing_dups --reason website --require-identical-name
    python -m scripts.merge_existing_dups --reason website --require-identical-name --apply
    python scripts\cross_source_dedup_audit.py --out prod_dups.csv

## Step 6 -- Push the branch (do this; it needs git credentials I lack)
The dedup work is committed (89d116b) on feat/golakehavasu-partners-closeout,
2 commits ahead of origin. Push it:
    git push -u origin feat/golakehavasu-partners-closeout
Do NOT open or merge the PR yourself -- that is being handled separately in the
browser, and the human will click the final Merge. Just push and confirm the
branch is on origin.

## Out of scope (do nothing, just confirm you understand)
- Item B flag stays OFF (enable later only after a full provider-suite run with
  INGEST_CONTACT_TIER_ENABLED=1).
- Attractions Tier-1 category migration: deferred.

## Final report
Summarize: test results, audit numbers before/after, what got merged locally,
what is staged, and paste the prod command block. Flag anything surprising.
