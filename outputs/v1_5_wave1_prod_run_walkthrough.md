# V1.5 wave-1 prod-run walkthrough — operator action

> **Status:** verifier code shipped at `52f82f2` (AZDHS) + `bae8690` (AZRE) on
> origin/main 2026-05-23; prod providers still un-stamped because the verifier
> scripts haven't run against the prod Postgres yet. This doc walks through
> the 2 verifier invocations + verification smoke. ~10 minutes operator-side;
> idempotent (re-runnable without harm).
>
> **Sibling docs:**
> - `outputs/phase8b_prod_population_walkthrough.md` (Phase 8b cat-13 entity population)
> - `outputs/azdor_lodging_verifier_action_package.md` (V1.5 #18 AZDOR — blocked autonomously; needs operator public-records request)
>
> The 3 docs collectively close the autonomous-ship → prod-deployed gap for
> the entire 2026-05-23 ship arc.

---

## §1 Prereqs

- Railway CLI installed + linked to `havasu-chat-production` service:
  ```powershell
  railway --version
  railway status
  ```
- Code is current at HEAD `4441231` or later (the v10 handoff commit ships ON TOP of
  both verifiers).
- Last 24h's prod CI is green (#409 on `bae8690` confirmed AZRE shipped clean; #412 on
  `c84ac58` confirmed the prod-pop walkthrough doc landed).
- Phase 8b cat-13 population (`outputs/phase8b_prod_population_walkthrough.md`) does
  NOT need to run first; the verifiers operate on cat-12 health-wellness-care +
  cat-10 lodging-vacation-rentals which have been populated since Phase 5.4 / 5.10.

---

## §2 Dry-run first (no DB writes)

Both verifier scripts default to `--dry-run`-equivalent behavior: they fetch the
external registry, fuzzy-match against the catalog, and log matches but do NOT write
without the `--dry-run` flag. Wait — read that again: the scripts use `--dry-run` as
an explicit flag that SUPPRESSES writes. Default (no flag) is the COMMIT path. So
ALWAYS pass `--dry-run` first.

### §2.1 AZDHS childcare verifier dry-run

```powershell
railway run python -m scripts.azdhs_verify --dry-run
# Expected output:
#   --- azdhs_verify summary ---
#   candidates: ~265   (count of active cat-12 health-wellness-care providers)
#   matched: ~15-18    (LHC childcare facilities that fuzzy-match against AZDHS)
#   skipped_already: 0  (first run; nothing previously verified by AZDHS)
#   skipped_no_match: ~247-250
```

The matched count should land roughly in the 15-18 range based on Cursor's recon: 18
active LHC childcare facilities exist in AZDHS; some catalog entries may have
significant name drift from the registry name and miss the threshold (86). Anything
substantially below ~15 suggests either (a) the catalog's cat-12 entries don't
include many childcare facilities (cat-12 is broader: dentists, doctors, urgent care)
or (b) the threshold tuning needs review — surface to me if so.

### §2.2 AZRE LHC vacation-rentals verifier dry-run

```powershell
railway run python -m scripts.azre_verify --dry-run
# Expected output:
#   --- azre_verify summary ---
#   candidates: ~50-80  (count of active cat-10 lodging-vacation-rentals providers)
#   matched: ~5-30      (depends on what's in catalog vs the 545-row LHC registry)
#   skipped_already: 0
#   skipped_no_match: <rest>
#   skipped_no_address: 0-5  (cat-10 providers without Provider.address populated)
```

The matched count depends heavily on catalog content — many cat-10 entries are
hotels/resorts (which AREN'T in the vacation-rental registry — they're full-service
hospitality) and some are short-term-rental listings (which ARE in the registry).
The AZRE registry is specifically for STRs (Lake Havasu's 5.20 ordinance).
Substantially-zero match count is fine; substantially-high match count is also fine
— the verifier doesn't validate scope, it attaches signals where signals exist.

**If either dry-run fails:** STOP. Surface the error before any --commit. Likely
failure modes:
- Live URL change (AZDHS FeatureServer moved; AZRE LHC City MapService URL changed —
  both unlikely since they're hosted on stable Esri / city infrastructure)
- Network/timeout error (60s timeout per fetch; transient errors retry)
- Schema regression (Provider.attributes column missing — would be a Phase 1A regression
  and extremely unlikely; would surface in CI before this point)

---

## §3 Commit each separately

If both dry-runs returned non-zero match counts (or zero if catalog content doesn't
overlap, which is acceptable), commit each verifier's stamps to prod Postgres:

```powershell
# AZDHS — stamps Provider.verified + verification_method='scraper' + attributes['azdhs']
railway run python -m scripts.azdhs_verify
# Expected output mirrors dry-run summary; matched count should be IDENTICAL to dry-run
```

```powershell
# AZRE — stamps Provider.verified + verification_method='scraper' + attributes['azre_lhc']
railway run python -m scripts.azre_verify
# Same expected shape
```

**Idempotency note:** both verifiers gate on the source-specific attribute key
presence (`attributes['azdhs']['LICENSE_NUMBER']` for AZDHS; `attributes['azre_lhc']['USER_Parcel_Number']`
for AZRE). Re-running either script after a successful first run is safe — the
already-verified providers land in `skipped_already`, not re-matched.

**verification_method='scraper' note:** both verifiers use the same `scraper`
verification_method enum value (the ck_providers_verification_method CHECK allowlist
doesn't include granular per-source enums; that's a separate-cleanup-lane ship if
ever needed). Per-source distinction lives in `attributes['<source>']` provenance.
This means a provider verified by BOTH AZDHS and AZRE (unlikely; cat-12 vs cat-10
should be disjoint, but theoretically possible if a catalog entry got mis-categorized)
would have both attribute keys + verification_method='scraper'.

---

## §4 Verify the prod counts

### §4.1 Count verified-by-AZDHS providers

```powershell
railway run python -c "from app.db.database import SessionLocal; from app.db.models import Provider; from sqlalchemy import select, func; db = SessionLocal(); count = db.scalars(select(func.count(Provider.id)).where(Provider.verified == True, Provider.attributes['azdhs'].isnot(None))).first(); print(f'AZDHS-verified providers: {count}')"
# Expected: matches dry-run match count
```

### §4.2 Count verified-by-AZRE providers

```powershell
railway run python -c "from app.db.database import SessionLocal; from app.db.models import Provider; from sqlalchemy import select, func; db = SessionLocal(); count = db.scalars(select(func.count(Provider.id)).where(Provider.verified == True, Provider.attributes['azre_lhc'].isnot(None))).first(); print(f'AZRE-verified providers: {count}')"
# Expected: matches dry-run match count
```

### §4.3 Sample a verified record to confirm payload shape

```powershell
railway run python -c "from app.db.database import SessionLocal; from app.db.models import Provider; from sqlalchemy import select; db = SessionLocal(); row = db.scalars(select(Provider).where(Provider.attributes['azdhs'].isnot(None)).limit(1)).first(); print(f'name: {row.provider_name}'); print(f'method: {row.verification_method}'); print(f'azdhs payload: {row.attributes.get(\"azdhs\")}')"
# Expected: verification_method=scraper, azdhs payload dict with LICENSE_NUMBER + Capacity + CAPACITY_INT + OPERATION_STATUS + match_score etc.
```

---

## §5 Optional — sample chat smoke

After verifiers run, the trust signals are attached to providers but no rendering
surface exists yet (rendering is V1.5 future work: chip badges, profile-page
attribution chips, etc.). For now, the verification stamps are queryable via API
and DB only. Chat surfaces will eventually leverage `attributes['azdhs']` for things
like "this childcare facility is state-licensed (license # CDC-XXXX)" disclosure
chips.

To confirm the verification doesn't BREAK chat (regression check):

```powershell
# Browser test: visit https://havasu-chat-production.up.railway.app/
# Try queries like "Hilltop Learning Center" or "Redemption Kids Day Care" (known
# AZDHS-listed LHC facilities). Should return a Tier-2 cited response with the
# entity's structured info; verification doesn't change response shape (yet).
```

---

## §6 Cron candidate (V1.5 deferred)

Both verifiers could become quarterly cron candidates (AZDHS facility licensing
changes quarterly; AZRE vacation-rental registry grows weekly). Per the
operator-runnable lock from Phase 5.3+5.4 (parks-rec-scrapes-style ORM-vs-DB-schema
drift risk), ingest-style scripts are V1 operator-runnable rather than auto-cron'd.
A V1.5 task could register them as monthly cron workflows mirroring
`.github/workflows/parks-rec-scrapes.yml` shape. Deferred until operator demand or
data-drift signal surfaces.

---

## §7 Rollback (if needed)

Both verifiers are purely additive — they set `Provider.verified=True` and add a
key to `Provider.attributes`. They don't delete data, don't modify schema, don't
change category routing. Rollback:

### §7.1 AZDHS rollback

```powershell
railway run python -c "from app.db.database import SessionLocal; from app.db.models import Provider; from sqlalchemy import select, update; db = SessionLocal(); rows = db.scalars(select(Provider).where(Provider.attributes['azdhs'].isnot(None))).all(); rolled = 0; [_ for p in rows if (p.attributes.pop('azdhs', None), setattr(p, 'verified', any(k in (p.attributes or {}) for k in ['npi_number', 'az_roc', 'azre_lhc'])), (rolled := rolled + 1))]; db.commit(); print(f'rolled back AZDHS verification on {rolled} providers')"
```

This pops `attributes['azdhs']` from each verified provider, and only flips
`verified=False` if NO OTHER verifier (NPI, AZ ROC, AZRE) has also signed off.
Conservative rollback.

### §7.2 AZRE rollback

```powershell
railway run python -c "from app.db.database import SessionLocal; from app.db.models import Provider; from sqlalchemy import select; db = SessionLocal(); rows = db.scalars(select(Provider).where(Provider.attributes['azre_lhc'].isnot(None))).all(); rolled = 0; [_ for p in rows if (p.attributes.pop('azre_lhc', None), setattr(p, 'verified', any(k in (p.attributes or {}) for k in ['npi_number', 'az_roc', 'azdhs'])), (rolled := rolled + 1))]; db.commit(); print(f'rolled back AZRE verification on {rolled} providers')"
```

---

## §8 Smoke after population

After all three walkthroughs (this one + Phase 8b's + AZDOR's pending) complete,
recommended end-of-day smoke battery:

```powershell
# /health still 200
curl https://havasu-chat-production.up.railway.app/health

# /api/conditions invariants intact
curl https://havasu-chat-production.up.railway.app/api/conditions | findstr aqi_source_distance_mi

# cat-13 page renders >= 15 cards (Phase 8b L1)
curl https://havasu-chat-production.up.railway.app/category/public-civic-resources | findstr "<article" /c

# Sample provider profile shows AZDHS verification chip if/when rendering ships
# (no rendering surface yet; verify via DB query in §4 instead)
```

---

## §9 Cross-references

- `52f82f2` — AZDHS verifier feat commit (V1.5 wave 1 ticket #17)
- `bae8690` — AZRE verifier + AZDOR action package feat commit (V1.5 wave 1 tickets #19 + #18)
- `c84ac58` — Phase 8b prod-population walkthrough (sibling doc; cat-13 population)
- `outputs/azdor_lodging_verifier_action_package.md` — AZDOR action package (ticket #18; blocked autonomously)
- `outputs/v1_5_carries_inventory.md` §2.3 — original triage of the verifier bundle (tickets #17-#19)
- `outputs/session_handoff_2026-05-23_v10.md` §6 — operator follow-up #2 (this doc)

---

*Authored 2026-05-23 ~12:00Z as the wave-1-verifier prod-deploy operator handoff,
companion to `c84ac58` Phase-8b-population + `outputs/azdor_lodging_verifier_action_package.md`
AZDOR-public-records. Together the 3 docs close the autonomous-ship → prod-deployed
gap for the full 2026-05-23 ship arc.*
