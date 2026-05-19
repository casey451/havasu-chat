# Operator Action Items Walkthrough — 7 V1-operator-action carries from V1.5 triage

> **What this is:** the single walkthrough doc covering the 7 V1-operator-action items from `outputs/v1_5_carry_inventory_triage.md` §7. Triage estimated ~2h total operator time; this walkthrough pre-organizes each item so you can chip away in 5–20 min chunks between Cursor checkpoints + other work.
>
> **Author:** Cowork primary, 2026-05-20 post-`99eb12c`.
>
> **Order of items** (easiest first; gates the harder ones):
> 1. `.bak` file prune (~2 min) — pure file ops, zero decisions
> 2. Untracked-file cleanup from 2026-05-19 close-out §4 (~3 min) — bonus item not in triage but pairs naturally
> 3. ASU SWANSON FIELDS — casing fix (~10 min)
> 4. Butterfly Garden — cat-7 fit investigation (~10 min)
> 5. Anderson AZ West — un-DRAFT decision (~15 min)
> 6. Simply Savage Designs — DRAFT review (~10 min)
> 7. 5 zero-review Slice E entries — DRAFT batch (~25 min)
> 8. Google Places API key rotation — NOT YET ACTIONABLE (operator lock: "all keys changed at project end")
>
> **Total estimated time:** ~75 min active + the API key rotation deferred indefinitely.
>
> **Safety:** All actions in §3–§8 below run against your local SQLite DB at `data/events.db`. Recommend taking a fresh backup before the first DB-touching item:
> ```powershell
> Copy-Item data\events.db "data\events.db.bak-2026-05-20-pre-action-items"
> ```
> Roll back via `Copy-Item "data\events.db.bak-2026-05-20-pre-action-items" data\events.db` if anything goes sideways.

---

## §1 `.bak` file prune

**What:** `data/events.db.bak-*` files accumulating since Phase 5.3. Carry from 5.3 → 5.4 → 5.5 → 5.6 → 5.7 → 5.8 → 5.9 → 5.10 → 5.11.

**Inventory first:**

```powershell
Get-ChildItem data\events.db.bak-* | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
```

**Decision:** which to keep? Recommended: keep the most recent 2 (rollback safety) + delete the rest.

**Action:**

```powershell
# Keep the most recent 2; delete the rest
Get-ChildItem data\events.db.bak-* | Sort-Object LastWriteTime -Descending | Select-Object -Skip 2 | Remove-Item
# Verify
Get-ChildItem data\events.db.bak-*
```

**Skip / defer if:** disk space isn't tight + you'd rather keep all .bak files as a paranoia archive. Pure operator preference.

---

## §2 Untracked-file cleanup (bonus — not in triage but pairs naturally)

**What:** 5 untracked files flagged in 2026-05-19 close-out §4 + 3 sandbox probe leaks per phase5_closeout_loose_ends pattern. Operator-discretion cleanup.

**Inventory:**

```powershell
git status --short | Where-Object { $_ -match '^\?\?' }
# Look for: hava_api_catalog.docx, outputs/phase5_11_ambig_audit_data.json,
#           outputs/phase5_11_top10_data.json, outputs/post_phase5_11_boot_prompt.bundle,
#           outputs/post_phase5_11_starter_prompt.bundle, .preflight, probe1.txt, probe3-renamed.txt
```

**Decision per file:**

| File | Recommended | Why |
|---|---|---|
| `hava_api_catalog.docx` | Keep OR delete — operator preference | Long-standing artifact; not actively referenced. Some operators like to keep the API catalog as a reference; safe to delete since git has prior versions in history |
| `outputs/phase5_11_ambig_audit_data.json` | Delete | Regenerable from `outputs/phase5_11_ambig_audit_dump.py` |
| `outputs/phase5_11_top10_data.json` | Delete | Regenerable from `outputs/phase5_11_top10_discovery.py` |
| `outputs/post_phase5_11_boot_prompt.bundle` | Delete | Served its purpose; superseded by `outputs/session_close_out_2026_05_19.md` |
| `outputs/post_phase5_11_starter_prompt.bundle` | Delete | Same as above |
| `.preflight` (if present) | Delete | Sandbox probe leak from earlier FUSE diagnostic |
| `probe1.txt` (if present) | Delete | Same |
| `probe3-renamed.txt` (if present) | Delete | Same |

**Action (delete all the recommended-deletes in one shot):**

```powershell
$toDelete = @(
    "outputs\phase5_11_ambig_audit_data.json",
    "outputs\phase5_11_top10_data.json",
    "outputs\post_phase5_11_boot_prompt.bundle",
    "outputs\post_phase5_11_starter_prompt.bundle",
    ".preflight",
    "probe1.txt",
    "probe3-renamed.txt"
)
foreach ($f in $toDelete) {
    if (Test-Path $f) { Remove-Item $f -Force; Write-Host "Deleted $f" }
    else { Write-Host "Skipped $f (not present)" }
}
# Verify
git status --short
```

For `hava_api_catalog.docx` — leave it alone unless you have a strong opinion. If you want to delete it too, append `"hava_api_catalog.docx"` to the `$toDelete` array.

---

## §3 ASU SWANSON FIELDS — casing fix

**What:** Carry from Phase 5.7. Entity name was loaded from Google with all-caps "ASU SWANSON FIELDS" — uppercase is non-idiomatic for our display surface. Investigation: confirm the entity exists, normalize the casing, and decide if it's correctly categorized (cat-7 outdoors-parks-trails OR cat-12 classes-sports-recreation since "fields" is sports-suggestive).

**Find the entity:**

```sql
-- Run in your SQLite client of choice (DB Browser for SQLite, sqlite3 CLI, etc.)
-- Database: data/events.db
SELECT
    e.id, e.name, e.is_active, e.draft,
    e.category_id, c.slug AS category_slug,
    p.primary_type, p.google_place_id
FROM entities e
LEFT JOIN providers p ON p.entity_id = e.id
LEFT JOIN categories c ON c.id = e.category_id
LEFT JOIN entity_categories ec ON ec.entity_id = e.id
LEFT JOIN categories cc ON cc.id = ec.category_id
WHERE e.name LIKE '%SWANSON%' OR e.name LIKE '%Swanson%'
ORDER BY e.id;
```

**Decision tree:**

1. **Confirm casing:** if the result row's `name` is "ASU SWANSON FIELDS" (all caps), proceed to normalize. If it's already "ASU Swanson Fields" or "Swanson Fields", skip this item — already normalized.
2. **Confirm Google source:** check `primary_type` — if it's `athletic_field` or `sports_complex`, this entity belongs in cat-12. If it's `park` / `point_of_interest`, cat-7 is right.
3. **Decision:** normalize the name AND (if applicable) adjust the category.

**Action — normalize casing:**

```sql
-- Replace <ENTITY_ID> with the actual id from the find query
UPDATE entities
SET name = 'ASU Swanson Fields'
WHERE id = <ENTITY_ID>;
```

**Action — if also flipping category** (e.g., cat-7 → cat-12 if primary_type is athletic_field):

```sql
-- Flip on the entity table
UPDATE entities SET category_id = (SELECT id FROM categories WHERE slug = 'classes-sports-recreation')
WHERE id = <ENTITY_ID>;
-- Flip the EntityCategory row too
UPDATE entity_categories
SET category_id = (SELECT id FROM categories WHERE slug = 'classes-sports-recreation')
WHERE entity_id = <ENTITY_ID>;
```

**Skip / defer if:** the entity isn't actually in the DB (search returns 0 rows) — that means it was a 5.7 ambig candidate that never landed; close as no-action.

---

## §4 Butterfly Garden — cat-7 fit investigation

**What:** Carry from Phase 5.7. "Butterfly Garden" surfaced under cat-7 outdoors-parks-trails but the name suggests it could be a community garden (still cat-7) OR a public garden/conservatory (cat-7) OR a private garden / nursery (cat-8 shopping-essentials). Operator investigates + decides.

**Find the entity:**

```sql
SELECT
    e.id, e.name, e.description, e.is_active, e.draft,
    e.category_id, c.slug,
    p.primary_type, p.address, p.google_place_id
FROM entities e
LEFT JOIN providers p ON p.entity_id = e.id
LEFT JOIN categories c ON c.id = e.category_id
WHERE e.name LIKE '%Butterfly Garden%';
```

**Investigation steps:**

1. **Read the Google place data:** look at `address` + `description` from the query. If it's at a residential address, likely a private garden — flip to DRAFT or DELETE.
2. **Cross-check with Google Maps:** copy the `google_place_id` into a URL like `https://www.google.com/maps/place/?q=place_id:<id>` and visit. Verify it's a public-access location with sensible visiting hours.
3. **Decision tree:**
   - Public-access garden / conservatory → keep in cat-7; no action needed
   - Community / volunteer garden → keep in cat-7; consider whether it deserves a `crowd_notes` snippet
   - Private garden / nursery sales → flip to DRAFT (`UPDATE entities SET draft = 1 WHERE id = <ENTITY_ID>`)
   - Doesn't exist / closed → soft-delete (`UPDATE entities SET is_active = 0 WHERE id = <ENTITY_ID>`)

**Action — based on decision** (replace `<ENTITY_ID>`):

```sql
-- Option A: keep + add a crowd_notes snippet
UPDATE entities
SET crowd_notes = '<your-30-to-60-word-description>'
WHERE id = <ENTITY_ID>;

-- Option B: flip to DRAFT (operator-curated re-review later)
UPDATE entities SET draft = 1 WHERE id = <ENTITY_ID>;

-- Option C: soft-delete (entity stays in DB but excluded from queries)
UPDATE entities SET is_active = 0 WHERE id = <ENTITY_ID>;
```

**Skip / defer if:** the entity isn't found.

---

## §5 Anderson AZ West — un-DRAFT decision

**What:** Carry from Phase 5.6. "Anderson AZ West" landed as DRAFT during the 5.6 shopping-essentials load — flagged as B2B wholesale by default since the name pattern + Google data was ambiguous. Operator investigates + decides whether to un-DRAFT (publish) OR keep DRAFT (hidden from public surfaces) OR soft-delete.

**Find the entity:**

```sql
SELECT
    e.id, e.name, e.description, e.is_active, e.draft,
    e.category_id, c.slug,
    p.primary_type, p.address, p.google_place_id, p.website_url
FROM entities e
LEFT JOIN providers p ON p.entity_id = e.id
LEFT JOIN categories c ON c.id = e.category_id
WHERE e.name LIKE '%Anderson%';
-- May return multiple Andersons (Auto, Health, etc.) -- look for the AZ West entry
```

**Investigation steps:**

1. **Check the website:** copy `website_url` into a browser. If it's clearly B2B wholesale (warehouse-only, no retail hours posted, "wholesale only" language), keep DRAFT.
2. **Check the address:** if it's in an industrial zone vs. retail strip, that's a B2B signal.
3. **Check Google reviews:** if there are consumer reviews mentioning walk-in / retail, that's a consumer-retail signal — un-DRAFT.
4. **Decision tree:**
   - Consumer-retail → un-DRAFT (`UPDATE entities SET draft = 0 WHERE id = <ENTITY_ID>`)
   - B2B wholesale only → keep DRAFT, consider soft-delete (`UPDATE entities SET is_active = 0 WHERE id = <ENTITY_ID>`)
   - Mixed B2B/retail → keep DRAFT for now; revisit V1.5

**Action (un-DRAFT path):**

```sql
UPDATE entities SET draft = 0 WHERE id = <ENTITY_ID>;
```

**Action (soft-delete B2B-only path):**

```sql
UPDATE entities SET is_active = 0 WHERE id = <ENTITY_ID>;
```

**Skip / defer if:** the website is dead AND there are no Google reviews — can't decide either way; leave DRAFT, defer to V1.5.

---

## §6 Simply Savage Designs — DRAFT review

**What:** Carry from Phase 5.8. "Simply Savage Designs" surfaced under cat-2 events with `art_gallery` primary type, but the name suggests a design shop (cat-8 shopping-essentials) rather than an art gallery. Operator investigates + decides un-DRAFT / DELETE / re-categorize.

**Find the entity:**

```sql
SELECT
    e.id, e.name, e.description, e.is_active, e.draft,
    e.category_id, c.slug,
    p.primary_type, p.address, p.google_place_id, p.website_url,
    p.google_review_count
FROM entities e
LEFT JOIN providers p ON p.entity_id = e.id
LEFT JOIN categories c ON c.id = e.category_id
WHERE e.name LIKE '%Simply Savage%';
```

**Investigation steps:**

1. **Check the website + Google place page:** is it a gallery (displays + sells art), a design shop (graphic design / signs / customs), or a retail boutique (clothing + accessories)?
2. **Decision tree:**
   - Art gallery → un-DRAFT, keep in cat-2 events
   - Design shop / boutique → flip to cat-8 shopping-essentials + un-DRAFT
   - Defunct / no info → soft-delete

**Action — un-DRAFT in cat-2:**

```sql
UPDATE entities SET draft = 0 WHERE id = <ENTITY_ID>;
```

**Action — flip to cat-8 + un-DRAFT:**

```sql
UPDATE entities
SET draft = 0,
    category_id = (SELECT id FROM categories WHERE slug = 'shopping-essentials')
WHERE id = <ENTITY_ID>;
-- Also update the EntityCategory row
UPDATE entity_categories
SET category_id = (SELECT id FROM categories WHERE slug = 'shopping-essentials')
WHERE entity_id = <ENTITY_ID>;
```

**Action — soft-delete:**

```sql
UPDATE entities SET is_active = 0 WHERE id = <ENTITY_ID>;
```

---

## §7 5 zero-review Slice E entries — DRAFT batch

**What:** Carry from Phase 5.11. Five cat-11 pets entries were created in 5.11 Slice E with 0 Google reviews — flagged as possibly defunct OR placeholder OR sub-service of a parent franchise. Operator reviews each + decides un-DRAFT / DELETE / consolidate. The 5 entries:

1. Obedience Please
2. PetSmart Grooming
3. PetSmart Dog Training
4. Penney's Pampered Pawz
5. TagWorks

**Find all 5 at once:**

```sql
SELECT
    e.id, e.name, e.is_active, e.draft,
    p.primary_type, p.address, p.google_place_id, p.website_url,
    p.google_review_count
FROM entities e
LEFT JOIN providers p ON p.entity_id = e.id
WHERE e.name IN (
    'Obedience Please',
    'PetSmart Grooming',
    'PetSmart Dog Training',
    'Penney''s Pampered Pawz',
    'TagWorks'
)
ORDER BY e.name;
```

**Per-entity decision template:**

| Entity | Likely disposition | Why |
|---|---|---|
| Obedience Please | Investigate website + Google place page; un-DRAFT if active dog trainer, soft-delete if defunct | Single-trainer business; high churn |
| PetSmart Grooming | Likely DUAL ADD parent (existing PetSmart in cat-8 + this as sub-service in cat-11) — triage §4 carry #24 captures this. Keep DRAFT until DUAL ADD pattern is locked V1.5 | Sub-service of franchise parent |
| PetSmart Dog Training | Same as above — keep DRAFT pending V1.5 DUAL ADD pattern | Sub-service of franchise parent |
| Penney's Pampered Pawz | Investigate; small local business | Possessive in name; may be one-person operation |
| TagWorks | Investigate; if it's actually a pet ID tag retail store, un-DRAFT in cat-11 OR flip to cat-8 + un-DRAFT | Name suggests retail, not service |

**Action — for each entity, pick one** (replace `<ENTITY_ID>`):

```sql
-- Un-DRAFT (publish; keep cat-11)
UPDATE entities SET draft = 0 WHERE id = <ENTITY_ID>;

-- Soft-delete (defunct or unverifiable)
UPDATE entities SET is_active = 0 WHERE id = <ENTITY_ID>;

-- Flip to cat-8 + un-DRAFT (retail rather than service)
UPDATE entities
SET draft = 0,
    category_id = (SELECT id FROM categories WHERE slug = 'shopping-essentials')
WHERE id = <ENTITY_ID>;
UPDATE entity_categories
SET category_id = (SELECT id FROM categories WHERE slug = 'shopping-essentials')
WHERE entity_id = <ENTITY_ID>;

-- Keep DRAFT (defer to V1.5)
-- (no action; entity stays as-is)
```

**Recommended batch order:**
1. Soft-delete obvious dead ones first (saves time on the rest)
2. Un-DRAFT clear local businesses
3. Keep DRAFT for the 2 PetSmart franchise sub-services pending V1.5 DUAL ADD pattern

---

## §8 Google Places API key rotation — NOT YET ACTIONABLE

**What:** Carry from Phase 5.2 onward. Triage flagged as V1 — operator action but with explicit operator lock: "all keys will be changed at the conclusion of this project" (i.e., right before launch, not now).

**Status:** **Deferred to Phase 12 launch prep.** No action this session.

**When to act:** Phase 12 launch prep — rotate Google Places API key + AirNow key (post-Phase-8) + any other third-party keys at the same time. Single coordinated rotation.

---

## §9 Post-walkthrough commit

If you applied any SQL UPDATEs in §3–§7, those changes are local-only against `data/events.db`. The DB itself is NOT committed to git (it's in `.gitignore`). So there's no commit step for the DB changes themselves.

For the file-system changes (§1 `.bak` prune + §2 untracked-file cleanup), no commit either — these are untracked files being deleted.

**The only thing worth committing:** if you want a record of which items you actioned, append a brief note to the triage doc:

```powershell
# Optional — add a "actioned" status to outputs/v1_5_carry_inventory_triage.md
# Use a code editor to add a §10 "Actions taken" section with one line per item resolved:
#   - #32 Anderson AZ West: un-DRAFT (consumer retail confirmed via website)
#   - #34 Butterfly Garden: soft-delete (Google place defunct)
#   - etc.

git add outputs/v1_5_carry_inventory_triage.md
git commit -m "docs(outputs): triage doc -- record operator action items actioned 2026-05-XX (7 items closed)"
git push origin main
```

This is optional — the local DB changes are the substantive work; the doc note is just for ledger clarity.

---

## §10 Estimated time per item (revised)

| # | Item | Estimated time | Cumulative |
|---|---|---|---|
| §1 | `.bak` file prune | 2 min | 2 min |
| §2 | Untracked-file cleanup | 3 min | 5 min |
| §3 | ASU SWANSON FIELDS casing | 10 min | 15 min |
| §4 | Butterfly Garden cat-7 fit | 10 min | 25 min |
| §5 | Anderson AZ West un-DRAFT | 15 min | 40 min |
| §6 | Simply Savage Designs DRAFT review | 10 min | 50 min |
| §7 | 5 zero-review Slice E entries | 25 min (5 min per entity × 5) | 75 min |
| §8 | Google Places API key rotation | DEFERRED to Phase 12 | – |

**Total active time:** ~75 min. Triage estimated ~2h; this walkthrough trims it ~25% by pre-organizing the SQL + decision criteria.

You can chip away at this in any order, in any combination of sittings. Each item is independent except §3–§7 which all touch the same DB (recommend the §0 backup before starting).

---

*Authored by Cowork primary at the post-`99eb12c` dispatch-pre-position session (2026-05-20). Lives at `outputs/operator_action_items_walkthrough.md`. Closes triage §7 V1-operator-action items 1-7 when applied (item #51 API key rotation deferred to Phase 12 per operator lock). All actions are local-DB / local-file ops; zero git commits required for the substantive work.*
