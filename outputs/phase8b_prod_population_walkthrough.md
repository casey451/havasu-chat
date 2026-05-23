# Phase 8b prod-population walkthrough — operator action

> **Status:** code shipped at `73760c2` (commit on origin/main 2026-05-23 ~11:30 MST); prod
> still has the legacy 4 cat-13 entities until the two ingest scripts run against the prod
> Postgres. This doc walks through the 2 commands + a verification smoke. ~5 minutes
> operator-side; idempotent (re-runnable without harm).
>
> **Why the code-ship didn't populate prod automatically:** the scripts are
> operator-runnable per `outputs/phase_8_architecture_design.md` §10 (no cron registration
> per design lock). Cursor's §12 manual verification ran them against the local dev DB
> (4 → 21 entities); the same two commands run against prod Postgres will land the same
> 17 net-new entities.

---

## §1 Prereqs

- Railway CLI installed + linked to the `havasu-chat-production` service:
  ```powershell
  railway --version       # should print v3+
  railway status          # should show havasu-chat-production
  ```
- Code is current at HEAD `73760c2` or later (`git log -1 --format='%H %s'` should
  show the Phase 8b feat commit at the top).
- Last 24h's prod CI is green (already verified — #411 on `73760c2` completed success;
  parks-rec-scrapes cron #67 also green at 18:35Z).

---

## §2 Dry-run first (no DB writes)

Always run `--dry-run` first to confirm the scraper hits live URLs cleanly and the seed
script can resolve the cat-13 category. Both scripts default to dry-run; no flag needed.

```powershell
railway run python -m scripts.ingest.lhc_civic_scrape
# Expected output:
#   --- lhc_civic_scrape dry-run summary ---
#   library: 1 entity parsed
#   transit: 3 entities parsed
#   airport: 1 entity parsed via city page + 1 via AirNav (2 total)
#   inserts (dry): 6
#   (no DB writes)
```

```powershell
railway run python -m scripts.seed_cat13_civic
# Expected output:
#   --- seed_cat13_civic dry-run summary ---
#   inserts (dry): 11
#   (no DB writes)
```

**If either dry-run fails:** STOP. Surface the error and we'll triage before any --commit.
Likely failure modes:
- Live URL change (City of LHC migrated a page; the scraper's curated fallback should
  catch this and log "scraper-fallback-used: <source>" but if the fallback also fails, the
  count for that source will be 0)
- `categories.slug='public-civic-resources'` not found (would be a Phase 3.2 schema
  regression — extremely unlikely since cat-13 has been live in prod since Phase 5.11)

---

## §3 Commit each separately (idempotent)

If both dry-runs returned the expected counts (6 + 11 = 17 new), commit each script's
output to prod Postgres:

```powershell
railway run python -m scripts.ingest.lhc_civic_scrape --commit
# Expected: "committed 6" (or fewer if some URLs returned same name+address as a row
# already present from a previous run — idempotency suppresses dupes)
```

```powershell
railway run python -m scripts.seed_cat13_civic --commit
# Expected: "committed 11" (same idempotency rule)
```

**Idempotency note (per Cursor's §12 deviation #1):** both scripts upsert on
case-insensitive `(name, address)`. Re-running either script after a successful first run
is safe — duplicates are detected and skipped.

---

## §4 Verify the prod count grew

```powershell
# Count of active cat-13 entities, before-vs-after expected
railway run python -c "from app.db.database import SessionLocal; from app.db.models import Category, Entity, EntityCategory; from sqlalchemy import select, func; db = SessionLocal(); cid = db.scalars(select(Category.id).where(Category.slug == 'public-civic-resources')).first(); count = db.scalars(select(func.count(Entity.id)).join(EntityCategory).where(EntityCategory.category_id == cid, Entity.is_active == True)).first(); print(f'cat-13 active count: {count}')"
# Expected: 21 (was 4 before scripts ran)
```

Or via the prod HTTP endpoint:

```powershell
# Returns the rendered category page; check for >= 15 entity cards
curl https://havasu-chat-production.up.railway.app/category/public-civic-resources | findstr "<article" /c
# Expected count: 15+ <article> tags (one per entity card)
```

---

## §5 Optional — additional Layer 5 manual entries

Per Cursor's §12 "Operator follow-up" recommendation, the master plan §10 target is
20-25 cat-13 entities. The 21 from §3 hits the low end; for the comfort range, add 3-7
manual entries via the admin form at `/admin/contribute` (or the inline contribute UI):

Suggested high-trust additions (per Cursor's recommendation):
- **Kiwanis of Lake Havasu City** — civic_org
- **Rotary Club of Lake Havasu** — civic_org
- **Mohave County Aging Services — Lake Havasu Center** — senior_resource
- Additional Havasu Hopper route/stop cards if needed beyond the 3 the scraper picks up — transit
- Utility rate-page entries for **UniSource Energy** + **Mohave Electric Cooperative** if the rate-page URLs change frequently and warrant their own catalog entries — utility/payment_licensing

Each manual entry should set `entity_type='place'` (matches Phase 8b's locked decision —
new cat-13 entries are place-typed; legacy 4 entries from Phase 5 stay as 'commercial'
per the §12 deviation #3 note).

---

## §6 Cron candidate (V1.5 deferred — optional follow-up)

The civic scraper could become a weekly cron candidate (library/transit hours change
quarterly; airport info shifts annually) — but per design lock §10, ingest is
operator-runnable for V1 to avoid the parks-rec-scrapes-style ORM-vs-DB-schema drift
risk. A V1.5 task could register the scraper as a GitHub Actions weekly cron mirroring
the `parks-rec-scrapes` workflow shape (`.github/workflows/parks-rec-scrapes.yml` is the
template). Deferred until operator demand surfaces.

---

## §7 Smoke after population

After populating, verify the surface works end-to-end:

```powershell
# Category page renders ≥15 cards
curl https://havasu-chat-production.up.railway.app/category/public-civic-resources -o tmp_cat13.html
findstr /c:"<article" tmp_cat13.html | find /c "article"

# Chat surfaces (operator-driven, in browser at https://havasu-chat-production.up.railway.app/)
# Example queries:
#   - "where's the library?"
#   - "tell me about the Lake Havasu Chamber"
#   - "visitor center hours"
#   - "Havasu Hopper bus stops"
# Each should return a tier-2 cited response with the cat-13 entity's structured info.
```

---

## §8 Rollback (if needed)

The Phase 8b shipped code is purely additive — no schema changes, no behavior changes
to existing pages. If for some reason the new entities cause prod issues:

```powershell
# Remove only the entities from the two new sources; legacy 4 entries stay.
railway run python -c "from app.db.database import SessionLocal; from app.db.models import Entity; from sqlalchemy import select, delete; db = SessionLocal(); db.execute(delete(Entity).where(Entity.source.in_(['lhc_civic_scrape', 'seed_cat13_civic']))); db.commit(); print('rolled back Phase 8b entities')"
```

This deletes only the 17 net-new entities (idempotent — re-running is safe; deletes
nothing on the second call). Legacy 4 cat-13 entries from Phase 5 are untouched.

---

## §9 Cross-references

- `73760c2` — Phase 8b feat commit (this code)
- `outputs/phase_8_architecture_design.md` §10 — Lane C cat-13 expansion design
- `outputs/cursor_dispatch_prompt_phase_8b.md` — the dispatch wrapper (already SHA-patched
  and Cursor-consumed)
- Cursor's §12 report (pasted in chat 2026-05-23 ~11:50 MST) — manual script verification
  evidence
- `outputs/v1_5_carries_inventory.md` — original V1.5 ticket #14-#16 (cat-13 expansion
  candidates that Phase 8b absorbed)

---

*Authored 2026-05-23 as the post-Phase-8b-ship operator handoff. ~5 min execution
window; idempotent; no rollback expected.*
