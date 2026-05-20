# Lane L — Operator action items chip-away package (consolidated, paste-ready)

> **What this is:** the single consolidated paste-ready package that merges (a) the original 7-item walkthrough at `outputs/operator_action_items_walkthrough.md` with (b) the sub-agent entity research at `outputs/operator_action_items_research_findings.md`. The sub-agent's research compresses the 4 entity-review items (#32 Anderson AZ West + #34 Butterfly Garden + #35 ASU Swanson Fields + #37 Simply Savage Designs) from ~50 min of operator investigation to **~8 min of paste-and-confirm** by pre-baking the dispositions + SQL UPDATE statements.
>
> **Author:** Cowork primary, post-`1e3f291` next-session pickup.
>
> **Total effort:** ~30 min if you chip the file-system items + 4 researched entities + Slice E batch in one sitting. ~8 min if you skip Slice E (defer to V1.5).
>
> **Companion docs:** `outputs/operator_action_items_walkthrough.md` (the original full-decision-tree walkthrough; keep open as a backstop for the §7 Slice E items the sub-agent did NOT research); `outputs/operator_action_items_research_findings.md` (the sub-agent's HIGH-confidence dispositions with full source citations).

---

## §0 Pre-flight (~1 min)

> **Schema corrections (2026-05-19 post-execution):** Verified against `app/db/models.py`:
>
> - **`draft` lives on `providers`, NOT `entities`** (line 50 of models.py defines `Provider.draft`; `Entity` has no `draft` column at line 627 onwards). All UPDATEs below target `providers.draft` with `WHERE entity_id = <ID>` joining back through the FK.
> - **`crowd_notes` lives on `entities` but is JSON** (`Mapped[dict | list | None]` at line 673), not a string column. String-concatenation patterns from the original sub-agent SQL won't work. This package drops the `crowd_notes` annotation pattern entirely; defer the annotations to V1.5 when a JSON-correct convention is locked.
> - **`name` lives on BOTH `entities` and `providers`** — for renames (e.g. ASU Swanson Fields casing fix), update both tables to keep the pair consistent.
>
> The schema-corrected SQL below reflects all three findings.

Take a fresh backup before any DB-touching work. All SQL below runs against your local SQLite DB at `data/events.db` (the DB itself is gitignored, so no commit needed for DB changes).

```powershell
cd C:\Users\casey\projects\havasu-chat
Copy-Item data\events.db "data\events.db.bak-pre-lane-l-$(Get-Date -Format yyyyMMdd-HHmm)"
```

Roll back if anything goes sideways:

```powershell
Copy-Item "data\events.db.bak-pre-lane-l-<TIMESTAMP>" data\events.db
```

---

## §1 File-system chip-aways (~5 min total; zero DB touch)

### §1.1 `.bak` file prune

Inventory:

```powershell
Get-ChildItem data\events.db.bak-* | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
```

Keep the most recent 2 (the one you just took in §0 + the previous one); delete the rest:

```powershell
Get-ChildItem data\events.db.bak-* | Sort-Object LastWriteTime -Descending | Select-Object -Skip 2 | Remove-Item
Get-ChildItem data\events.db.bak-*
```

### §1.2 Untracked-file cleanup (5 regenerable artifacts + 3 sandbox probe leaks)

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
git status --short
```

`hava_api_catalog.docx` is operator-preference — keep as reference OR add to the array above if you want it gone.

---

## §2 Entity-review chip-aways (~8 min total — the sub-agent did the heavy lifting)

### §2.1 ID lookup pass — run this ONE query first

Open `data/events.db` in DB Browser for SQLite (or `sqlite3 data/events.db`) and run:

```sql
SELECT
    e.id, e.name, e.is_active,
    p.draft, p.entity_id,
    e.category_id, c.slug AS category_slug,
    p.primary_type, p.address, p.website_url, p.google_review_count
FROM entities e
LEFT JOIN providers p ON p.entity_id = e.id
LEFT JOIN categories c ON c.id = e.category_id
WHERE e.name LIKE '%Anderson%AZ%West%'
   OR e.name LIKE '%Butterfly Garden%'
   OR e.name LIKE '%SWANSON%' OR e.name LIKE '%Swanson%'
   OR e.name LIKE '%Simply Savage%'
ORDER BY e.name, e.id;
```

Note the `id` for each of the 4 entities. Substitute them into the UPDATEs below as `<ANDERSON_ID>`, `<BUTTERFLY_ID>`, `<SWANSON_ID>`, `<SAVAGE_ID>`.

If any name returns 0 rows, see the per-item "Skip / defer" callout below.

### §2.2 #32 Anderson AZ West — un-DRAFT (HIGH confidence)

**Sub-agent finding:** Consumer-retail powersports dealership (Polaris / Arctic Cat / Slingshot) at 3198 Sweetwater Ave. ~210 reviews, 4.7-star. NOT B2B wholesale despite the "AZ West" name. Walk-in showroom + sales + financing.

**Action:**

```sql
UPDATE providers SET draft = 0 WHERE entity_id = <ANDERSON_ID>;
```

**Verify:**

```sql
SELECT e.id, e.name, p.draft
  FROM entities e LEFT JOIN providers p ON p.entity_id = e.id
 WHERE e.id = <ANDERSON_ID>;
-- Expected: p.draft = 0
```

**Sister-location flag (operator note):** If the lookup also surfaced "Anderson Powersports Lake Havasu" at 1040 N Lake Havasu Ave, that's the north-Havasu sister storefront of the same dealer group. Same treatment (un-DRAFT) — they're both consumer-retail. Optional V1.5 dedupe-review candidate.

**Skip / defer if:** lookup returned 0 rows for `%Anderson%AZ%West%` — entity may have been deleted in an earlier session; close as no-action.

### §2.3 #34 Butterfly Garden — un-DRAFT in cat-7 (HIGH confidence)

**Sub-agent finding:** Public butterfly garden sub-feature inside Rotary Community Park (1400 S Smoketree Ave). Free, public-access, city-maintained, no admission gate. Distinct Google place_id from parent Rotary Park.

**Action:**

```sql
UPDATE providers SET draft = 0 WHERE entity_id = <BUTTERFLY_ID>;
```

**Note on `crowd_notes` annotation (V1.5 defer):** The original sub-agent SQL used a string-concat pattern, but `entities.crowd_notes` is a JSON column (`Mapped[dict | list | None]` per `app/db/models.py:673`). String-concat is incorrect for JSON. V1 ships without the annotation; V1.5 locks a JSON-correct convention (e.g. append to an array of typed notes) before retro-applying.

**Verify:**

```sql
SELECT e.id, e.name, p.draft, e.category_id
  FROM entities e LEFT JOIN providers p ON p.entity_id = e.id
 WHERE e.id = <BUTTERFLY_ID>;
-- Expected: p.draft = 0; category_id should resolve to cat-7 outdoors-parks-trails
```

**Rotary Community Park duplicate check (operator note):** before publishing, run `SELECT id, name FROM entities WHERE name LIKE '%Rotary%';` — if a separate "Rotary Community Park" row exists, both can stay (distinct place_ids) but the parent-child relationship is a V1.5 modeling carry.

**Skip / defer if:** lookup returned 0 rows — close as no-action.

### §2.4 #35 ASU Swanson Fields — un-DRAFT + casing fix (HIGH confidence)

**Sub-agent finding:** Two multi-use athletic fields off Swanson Avenue / Cypress Drive. **City-maintained**, not ASU property — survives the ASU Havasu academic campus closure. Listed on lhcaz.gov Parks & Trails as "ASU FIELDS". cat-7 outdoors-parks-trails is the right category (NOT cat-12 — cat-12 is for instruction/league/programmed sports; ASU Fields is a passive venue).

**Action (two-statement pattern — `name` lives on both tables; `draft` lives only on providers):**

```sql
UPDATE entities  SET name = 'ASU Swanson Fields' WHERE id = <SWANSON_ID>;
UPDATE providers SET name = 'ASU Swanson Fields', draft = 0 WHERE entity_id = <SWANSON_ID>;
```

The name change normalizes "ASU SWANSON FIELDS" all-caps → "ASU Swanson Fields" title case. Both tables get the rename to keep the entity/provider name-pair consistent. Keeps "Swanson" because that's how Google Maps surfaces it (Swanson is the street); preserves disambiguation from ASU Tempe fields.

**Optional canonical-match variant** — use `name = 'ASU Fields'` if you prefer matching the lhcaz.gov canonical listing exactly. Either is defensible.

**Verify:**

```sql
SELECT e.id, e.name AS entity_name, p.name AS provider_name, p.draft, e.category_id
  FROM entities e LEFT JOIN providers p ON p.entity_id = e.id
 WHERE e.id = <SWANSON_ID>;
-- Expected: entity_name + provider_name both = 'ASU Swanson Fields'; p.draft = 0
```

**Skip / defer if:** lookup returned 0 rows — close as no-action.

### §2.5 #37 Simply Savage Designs — keep DRAFT, defer V1.5 (HIGH confidence on ID; MEDIUM on disposition)

**Sub-agent finding:** **Solo artist's brand, not a brick-and-mortar gallery.** Tyler Savage creates upcycled mixed-media art; work shown at The Q Gallery (2102 McCulloch Blvd N) + Etsy + Instagram. No standalone storefront. Original cat-2 events + `art_gallery` primary type categorization is **wrong on both axes**.

**Three sub-options:**

1. **PREFERRED — keep DRAFT, defer V1.5 (visit-ability mismatch).** havasu-chat V1 is destination-oriented; an artist with no public studio doesn't fit "where do I go". Park for a future "Local Makers / Art Trail" V1.5 subcat.
2. **Acceptable — soft-delete.** If V1.5 local-makers subcat is unlikely, delete now to keep the directory clean.
3. **Not recommended — un-DRAFT under cat-2 or cat-8.** Misleading; user clicks lead nowhere visit-able.

**Action — preferred (keep DRAFT; `crowd_notes` annotation deferred to V1.5):**

```sql
UPDATE providers SET draft = 1 WHERE entity_id = <SAVAGE_ID>;
-- Likely already draft=1; this just confirms.
```

The `crowd_notes` annotation pattern that the original sub-agent SQL proposed (string-concat) is invalid here because `crowd_notes` is JSON. V1 ships without it; V1.5 locks JSON-correct convention.

**Action — alternative (soft-delete; both tables for full hide):**

```sql
UPDATE entities  SET is_active = 0 WHERE id = <SAVAGE_ID>;
UPDATE providers SET is_active = 0 WHERE entity_id = <SAVAGE_ID>;
```

The walkthrough convention for V1 is `is_active = 0` for soft-delete (NOT `deleted_at = NOW()` — that column doesn't exist in V1 schema). `is_active` lives on both tables; updating both ensures the row is fully excluded from any join-based query that filters on either side.

**Verify:**

```sql
SELECT e.id, e.name, e.is_active AS entity_active, p.is_active AS provider_active, p.draft
  FROM entities e LEFT JOIN providers p ON p.entity_id = e.id
 WHERE e.id = <SAVAGE_ID>;
```

**Skip / defer if:** lookup returned 0 rows — close as no-action.

---

## §3 Slice E zero-review entries — DRAFT batch (~25 min; sub-agent did NOT research these)

This section is **NOT pre-baked by sub-agent research**. The 5 Slice E entities are cat-11 pets entries with 0 Google reviews; the walkthrough at `outputs/operator_action_items_walkthrough.md` §7 has the full decision tree. Per the walkthrough's recommended batch order:

1. **PetSmart Grooming + PetSmart Dog Training** — keep DRAFT pending V1.5 DUAL ADD pattern (sub-services of franchise parent; triage §4 carry #24)
2. **TagWorks** — investigate website; if pet ID tag retail, flip to cat-8 + un-DRAFT
3. **Penney's Pampered Pawz** — investigate (small local business; possessive name)
4. **Obedience Please** — investigate (single-trainer business; high churn)

ID lookup for all 5:

```sql
SELECT
    e.id, e.name, e.is_active AS entity_active,
    p.is_active AS provider_active, p.draft,
    p.primary_type, p.address, p.website_url, p.google_review_count
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

Per-entity disposition SQL (pick one per entity; `draft` lives on `providers`, `is_active` on both):

```sql
-- Un-DRAFT (publish; keep cat-11)
UPDATE providers SET draft = 0 WHERE entity_id = <ENTITY_ID>;

-- Soft-delete (defunct or unverifiable; both tables for full hide)
UPDATE entities  SET is_active = 0 WHERE id = <ENTITY_ID>;
UPDATE providers SET is_active = 0 WHERE entity_id = <ENTITY_ID>;

-- Flip to cat-8 + un-DRAFT (retail rather than service)
UPDATE entities SET category_id = (SELECT id FROM categories WHERE slug = 'shopping-essentials')
 WHERE id = <ENTITY_ID>;
UPDATE providers SET draft = 0 WHERE entity_id = <ENTITY_ID>;
UPDATE entity_categories
   SET category_id = (SELECT id FROM categories WHERE slug = 'shopping-essentials')
 WHERE entity_id = <ENTITY_ID>;

-- Keep DRAFT (defer V1.5) — no SQL action needed
```

**Skip / defer if:** you're short on time. The 5 Slice E entries are already in DRAFT state (hidden from public surfaces); keeping them there for V1 is safe. They become a V1.5 chip-away.

---

## §4 Google Places API key rotation — DEFERRED to Phase 12

Operator lock from earlier session: "all keys will be changed at the conclusion of this project". No action this session. Coordinate with AirNow key + any other third-party rotations at Phase 12 launch prep.

---

## §5 Post-chip ledger note (optional; ~3 min)

The DB changes themselves don't commit (DB is gitignored). If you want a ledger record of what you actioned, append a §10 "Actions taken" section to `outputs/v1_5_carry_inventory_triage.md`:

```markdown
## §10 Actions taken — Lane L chip-away [YYYY-MM-DD]

- §1.1 `.bak` file prune: [N] files removed; kept most-recent 2 + the pre-Lane-L backup
- §1.2 Untracked-file cleanup: [N] files removed
- #32 Anderson AZ West: un-DRAFT (sub-agent HIGH-confidence; consumer-retail powersports dealer)
- #34 Butterfly Garden: un-DRAFT in cat-7 (sub-agent HIGH-confidence; Rotary Park sub-feature)
- #35 ASU Swanson Fields: un-DRAFT + casing normalized (sub-agent HIGH-confidence; city-maintained fields)
- #37 Simply Savage Designs: kept DRAFT (preferred — defer V1.5 local-makers surface)
- §3 Slice E batch: [list per-entity dispositions, or "deferred to V1.5"]
- §4 Google Places API key rotation: deferred to Phase 12 per operator lock
```

Then:

```powershell
git add outputs\v1_5_carry_inventory_triage.md
git commit -m "docs(triage): Lane L chip-away [YYYY-MM-DD] -- 4 sub-agent-researched items closed + file-system cleanup"
git push
```

Docs-only commit; no code; alembic head unchanged at `c9d0e1f2a3b4`; pytest count unchanged.

---

## §6 V1.5 carries surfaced by sub-agent research (capture for next-session inventory)

These didn't exist in the original walkthrough but the sub-agent research surfaced them as legitimate V1.5 backlog items. Add to next-session V1.5 inventory:

- **Anderson sister-location dedupe review** — north-Havasu Lake Havasu Ave site is a distinct Google place_id but same dealer group. V1.5 dedupe decision.
- **Rotary Community Park parent-child modeling** — Butterfly Garden is a sub-feature with its own place_id. V1.5 either-deduplicate-or-model-as-parent-child decision.
- **V1.5 Local-makers / Art Trail subcat** — covers Simply Savage Designs + likely 20+ other Havasu Art Trail artists. Surfaces the "where does art-not-galleries go" gap.
- **The Q Gallery (2102 McCulloch Blvd N) — next-scrape candidate** — actual visit-able venue hosting Simply Savage's work; if not already in DB, add to next scrape pass.

These were also flagged in `outputs/session_close_out_2026_05_20.md` §4 open carries; this is the per-item provenance.

---

## §7 Closure scorecard (post-Lane-L)

When Lane L completes:

- **§1 `.bak` prune** → operator preference, low value either way
- **§2 untracked-file cleanup** → 5+3 regenerable artifacts cleared
- **#32 + #34 + #35** → 3 un-DRAFTs locked (HIGH-confidence)
- **#37** → DRAFT-retained or soft-deleted (operator picks)
- **Slice E §3** → 5 entities triaged or deferred
- **Google Places key rotation** → still DEFERRED to Phase 12
- **V1.5 triage §8 #3** (the 7 V1-operator-action items carry) → **CLOSED**

Combined with Lane M closure, V1.5 triage §8 scorecard becomes **5 of 5 §8 items closed** (only the Google Places key rotation remains as Phase 12 carry, which is outside the §8 lock-now scope).

---

*Authored by Cowork primary at the post-`1e3f291` Lane L pre-staging step. Lives at `outputs/lane_l_operator_action_items_chip_away_package.md`. Consolidates `outputs/operator_action_items_walkthrough.md` + `outputs/operator_action_items_research_findings.md` into a single paste-ready chip-away package. Sub-agent research cuts the 4 entity-review items from ~50 min to ~8 min; Slice E (~25 min) remains operator-investigation; total ~30 min if all sections actioned in one sitting, or ~8 min minimum (skip Slice E + skip ledger note).*
