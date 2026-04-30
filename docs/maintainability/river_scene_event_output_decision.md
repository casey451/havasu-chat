<!--
PURPOSE: River Scene event-output fix — single-source retrospective for the
ingestion, dedupe, render-guard, and backfill stream (April 2026). Records the
diagnosed bug, Option A vs B vs C, commit stack, verification path, and
operational findings.

AUDIENCE: Future Claude sessions and humans reading the repo. Read in full
before changing River Scene ingestion, contribution approval, Tier 2 formatting,
or dedupe logic touching `source_url`.

DO NOT paste this file into a new chat as a kickoff document — it is a
post-ship filing, not a session bootstrap prompt.
-->

# River Scene Event-Output Fix — Decision Recommendation (Retrospective)

**Status:** Shipped, deployed, and applied (production Postgres backfill `--apply` completed). **Date:** 2026-04-30. **Commit stack (order):** `83e4995` → `fcc8d25` → `5cfd1cd` → `3081bde` → `6bec1ec`.

---

## Findings (the bug as diagnosed)

### User-visible problem

Tier 2 chat output for River Scene–sourced events showed operator scaffolding and wrong link targets: bodies included **"Imported from River Scene. Event URL: …"** with the **magazine article URL** as the markdown link target instead of the **organizer / registration URL** when the listing provided one.

### Ingestion bug

`river_scene._table_label_map` parsed the **Website** field from listing HTML, but **`normalize_to_contribution`** ignored it: **`submission_url`** was always set to the **article URL**, so the organizer URL never flowed into stored contribution data on ingest.

### Operator scaffolding leak

Empty description bodies led to fabricated **"Imported from River Scene…"** copy in **`submission_notes`**, which became **`Event.description`** and surfaced verbatim in Tier 2 chat output.

### Dedupe break if `event_url` alone were “fixed”

Pre-fix dedupe compared **`event_url`** to the **article URL** for duplicate detection. Correcting **`event_url`** to the organizer URL without a separate stable article identity would have **broken** that dedupe behavior.

---

## Decisions

### Chosen approach: Option A

**Option A (chosen):** Add a nullable **`source_url`** column on both **`contributions`** and **`events`**, **normalized on write** via **`normalize_submission_url`**, and use **`source_url`** as the **dedupe key** for River Scene (canonical listing/article identity distinct from the click-through **`event_url`** / organizer URL).

**Rejected alternatives:**

- **Option B — repurpose `Contribution.source`:** Rejected; that field is **load-bearing** as an enum-like source discriminator (`river_scene_import`, `user_submission`, etc.).
- **Option C — repurpose `Event.source`:** Rejected; used by **`backfill_event_providers.py`** and related provider-matching logic.

### Legacy-fallback dedupe

A **legacy-fallback dedupe path** remains for rows where **`source_url`** is **NULL** (pre-fix data during deploy/backfill windows), so behavior stays safe until backfill and new writes populate **`source_url`**.

---

## Commit plan (shipped)

| Hash | Summary |
|------|---------|
| `83e4995` | Migration adds **`source_url`** on **`contributions`** and **`events`**. |
| `fcc8d25` | Ingestion fix; dedupe via **`source_url`**; propagation through schemas, models, approval service, contribution store. |
| `5cfd1cd` | Render-time guard strips legacy **"Imported from River Scene…"** scaffolding from descriptions surfaced to Tier 2. |
| `3081bde` | Backfill script: **dry-run by default**, **`--apply`** writes, **`--cleanup-only`** safety hatch. |
| `6bec1ec` | Regex anchor correction: **`\b`** instead of **`^`** after dry-run showed the legacy string appears at **non-zero** offset in real descriptions. |

---

## Verification path

1. **Dry-run preview** against production: shell with **`$env:DATABASE_URL`** (PowerShell) set; run backfill without **`--apply`** and inspect planned updates.
2. **`--apply`** against **production Postgres** after application code deploy.
3. **Spot-check** via deployed app: organizer URLs surface in chat output; descriptions no longer carry the legacy scaffolding string.

---

## Mid-stream findings (posterity)

- **Local SQLite (72 rows) vs production Postgres (71 rows)** during verification — different databases hold different state; future verification must **confirm which DB** is queried before drawing conclusions.
- **Commit 2 (`5cfd1cd`)** originally used a **`^`-anchored** regex; **commit 2.1 (`6bec1ec`)** switched to a **word-boundary (`\b`)** match after dry-run showed real **`Event.description`** text has the legacy string **after** prefixes such as **`Date:` / `Time:` / blank lines**, not at character zero. Synthetic fixtures in commit 2 had the string at offset zero, so tests passed while production rows would not have been stripped.
- **Commit 3 (`3081bde`)** skipped halt-and-report and landed before owner review; recovery was **after-the-fact dry-run review**. Process gap noted; recovery worked.
- **`EventApprovalFields.source_url`** overlap with **`approve_contribution_as_event`** direct propagation is **intentional defense-in-depth** across approval paths, not duplication bug.
- **Railway query UI** showed inconsistent behavior (**COUNT** returned rows; **SELECT** with text sometimes showed **"No Results"** for the same **`WHERE`**). Treat as **UI rendering**, not data drift; use a real Postgres client (**psql**, DBeaver, TablePlus, etc.) for production verification.

---

## Effect on existing maintainability findings and backlog

- The **Phase 8.10 River Scene event-output** class of bug (wrong URL target, scaffolding in descriptions, dedupe coupling to article URL via **`event_url`**) is **closed** by this stack and backfill.
- The broader intent that **all event URLs should be clickable and correctly surfaced** across Tier 2 paths and sources remains tracked in **`docs/BACKLOG.md`** **Backlog 5**, with **River Scene–specific scope** carved out to this document.

---

## Status — completed

> Note: `6bec1ec` sits above `3081bde` on `main` because it was committed last. Order is git-chronological, not logical (0.5 → 1 → 2 → 3 → 2.1). An interactive rebase to enforce "logical" order was considered and rejected: chronological order reflects actual workflow, and rebasing would rewrite SHAs that are referenced in commit message bodies.

| Hash | Commit |
|------|--------|
| `83e4995` | H2-followup commit 0.5: add **`source_url`** column to contributions and events |
| `fcc8d25` | H2-followup commit 1: River Scene ingestion fix, dedupe via **`source_url`** |
| `5cfd1cd` | H2-followup commit 2: render-time guard for legacy operator scaffolding |
| `3081bde` | H2-followup commit 3: River Scene URL/description/**`source_url`** backfill script |
| `6bec1ec` | H2-followup commit 2.1: tier2 legacy River Scene strip uses word boundary |

**Production outcomes:** Organizer URLs in **`event_url`** where the listing provides them; cleaned descriptions without the legacy scaffolding string; **`source_url`** populated for dedupe and stable article identity; render-time guard covers any row that briefly missed backfill. Backfill **`--apply`** against production Postgres completed cleanly: all **71** rows updated, **0** errors. Idempotent re-runs would produce zero diffs.

**Gates (documentation-only commit):** No production code changes; **`pytest`** baseline unchanged from pre-doc-pass repo state.
