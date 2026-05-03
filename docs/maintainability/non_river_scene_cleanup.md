<!--
PURPOSE: Non–River-Scene cleanup stream — retrospective documenting why the
production catalog is RS-only, which code and data were removed, verification,
and post-ship smoke-test outcomes.

AUDIENCE: Future maintainers and sessions touching ingestion, bulk data paths,
or seed-adjacent tooling. Post-ship filing; not a session bootstrap prompt.

DO NOT paste this file into a new chat as a kickoff document — it is a
post-ship filing, not a session bootstrap prompt.
-->

# Non–River-Scene Cleanup — Retrospective (RS-Only Catalog)

**Status:** Shipped operationally (code deletion, DB cleanup script, production dry-run and apply, verification, smoke test). **Primary ship window:** 2026-04-29–2026-04-30 (git commits through `80f8383`); cleanup script landed `81fe20c`; production apply **2026-04-30**; smoke test **2026-05-03**.

---

## Background

The stream started from a **launching question**: chat surfaced an **Aqua Aerobics**-style event tagged Aquatic Center / May 8 that traced to **`app/db/seed.py`** (`REAL_SEED_EVENTS`) rather than a live municipal calendar feed. The owner asked for **data lineage**; an audit surfaced **multiple non–River-Scene lanes** — curated `REAL_SEED` events, `HAVASU_CHAT_MASTER.md`–backed provider seed, `HAVASU_CHAT_SEED_INSTRUCTIONS.md` / instruction import, field-history baseline tooling, Google bulk JSONL ingest/embed paths, and related admin surfaces.

**Decision:** Remove **all non-RS catalog data** and the **code that seeds or imports it**, leaving **River Scene** as the **sole** first-party ingestion lane. Any future ingestion is rebuilt **deliberately** on a clean slate instead of carrying legacy seed complexity forward.

---

## Pre-cleanup inventory

Row counts that drove the **1,204**-row deletion plan:

| Table / slice | Count | Notes |
|---------------|------:|-------|
| `events` (total) | 114 | **71** `river_scene_import` + **43** `admin` |
| `providers` | 25 | all `source = 'seed'` |
| `programs` | 98 | **28** `admin` + **70** `scraped` |
| `contributions` | 72 | **71** `river_scene_import` + **1** `operator_backfill` |
| `field_history` | 983 | all `source = 'seed'` |
| `llm_mentioned_entities` | 54 | no `source` column; **all** rows targeted for delete |
| **Total deletable** | **1,204** | Sum of the six deletion slices |

**FK verification before apply:**

| Check | Result |
|-------|-------:|
| RS contributions joining `events` with `source = 'admin'` on `created_event_id` | **0** |
| RS contributions with `created_provider_id IS NOT NULL` | **0** |
| RS contributions with `created_program_id IS NOT NULL` | **0** |
| RS contributions with `created_event_id` populated | **71**, all referencing RS events |

No FK remapping was **load-bearing** in production: `scripts/cleanup_non_river_scene.py` still runs **defensive `UPDATE`s** nulling `created_provider_id` and `created_program_id` on surviving contributions before `DELETE` from `programs` / `providers`; in prod those updates were **no-ops** (both counts zero).

---

## Code deletion (turn 2)

Seven commits on `main` (extract + six cleanup commits + project-handoff follow-up):

| Hash | Summary |
|------|---------|
| `5e75bf5` | `refactor: move _norm_provider_name to app/core/provider_name.py` |
| `ac5f92a` | `chore: remove provider seed module, master concierge populate, and tests` |
| `0674467` | `chore: remove Google bulk ingest/embed and event-provider backfill lane` |
| `da8734f` | `chore: remove REAL_SEED lane, admin /reseed, and Railway auto-seed startup` |
| `d84b9c1` | `chore: remove Havasu instructions seed lane and related backfills` |
| `6af8430` | `docs: align ops copy with River-Scene-only ingestion (pytest + env vars)` |
| `80f8383` | `docs: align project-handoff.md with River-Scene-only ingestion` |

**Pytest baseline:** Before cleanup, **eight** failures depended on **`HAVASU_CHAT_MASTER.md`** seed fixtures at repo root. Removing those lanes and tests brought the suite to **931 passed, 0 failed** immediately after the code-deletion stack. After turn 3 added `tests/test_cleanup_non_river_scene.py`, the count rose to **950 passed** (same **0** failures).

---

## Cleanup script (turn 3)

**Script:** `scripts/cleanup_non_river_scene.py` (**commit `81fe20c`**), shaped like `scripts/backfill_river_scene_urls.py`:

- **Argparse:** `--dry-run` XOR `--apply`; default preview; `--yes` skips the apply confirmation prompt.
- **Pre-flight:** RS contribution and RS event counts ≥ configured floors (defaults **71**; overridable via `CLEANUP_MIN_RS_CONTRIBUTIONS` / `CLEANUP_MIN_RS_EVENTS`); **zero** RS contributions with `created_event_id` pointing at an **`admin`**-sourced event.
- **Single transaction:** six ordered `DELETE`s plus the defensive `UPDATE`s on contribution FKs, then **`COMMIT`** (full rollback on failure).
- **Apply confirmation:** user types exactly **`yes`**; otherwise exit code **5** (`ApplyAborted`). Argparse misuse exit **2**; preflight failure exit **3** (documented in script `--help` / module docstring).
- **Counters** per table + **total**; second **`--apply`** is **idempotent** (all zeros).

---

## Production verification

- **Dry-run:** Printed summary counters matching the §Pre-cleanup inventory partition **exactly** (**1,204** total across the six slices).
- **Apply:** Deleted **1,204** rows in **one** transaction; per-table deleted counts matched the dry-run **exactly**.
- **Post-apply verification (SQL):** `events` shows **only** `river_scene_import` (**71** rows); `contributions` matches the RS-only expectation; **`providers`**, **`programs`**, **`field_history`**, and **`llm_mentioned_entities`** are **empty** (zero rows each).

**Backup:** `pg_dump` captured locally before destructive work as **`havasu_chat_prod_pre_cleanup_20260430-211946.sql`** (~**5.2 MB**), **gitignored**, owner laptop only.

---

## Chat smoke test (post-cleanup)

Three manual checks after apply:

1. **"What's at the Aquatic Center this week?"** — Hava returned a **real River Scene** event (**Community Day**, **2026-05-03**, RS-imported, venue Aquatic Center). **No confabulation.** The old seeded **Aqua Aerobics** row is gone; Hava did **not** invent a replacement.
2. **"Tell me about Anderson Toyota."** — Hava **did not** confabulate deleted provider copy (**good**). Hava **did** lead with **Havasu Balloon Festival** (sponsored by Anderson Toyota), treating the prompt as **event search** rather than **provider lookup**. This is an **intent-routing** gap **unmasked** by cleanup, not a cleanup defect. **Deferred follow-up:** route **"tell me about \<business\>"** toward provider lookup vs event search explicitly.
3. **"Is the Lake Havasu Rotary Club hosting anything next month?"** — Honest **no-catalog** answer with pointers (CVB events page, contact the club). **No confabulation.**

---

## Deferred follow-ups

| Topic | Disposition |
|-------|---------------|
| **Business-name intent** | Improve routing so **provider / business lookup** is not absorbed by **event search** (see smoke #2). |
| **Empty `programs` table** | Optional future **`DROP TABLE`** migration if no program-creating ingestion returns within a reasonable window. **Not urgent.** |
| **Empty `providers` table** | Same pattern as `programs`; defer schema drop until product direction is clear. |
| **Empty `field_history` table** | Same deferral if the table remains unused. |
| **Local `pg_dump` artifact** | Delete from the owner machine once post-stream confidence is high; **owner judgment**, no committed date. |
| **Postgres credential rotation** | Any rotation tied to backup handling stays **owner-side**, outside this stream. |

---

## Refs

| Item | Reference |
|------|-----------|
| Inventory / lineage turn | Prompt-driven; not a single git commit. |
| Code deletion commits | `5e75bf5`, `ac5f92a`, `0674467`, `da8734f`, `d84b9c1`, `6af8430`, `80f8383` |
| Cleanup script | `81fe20c` — `scripts/cleanup_non_river_scene.py`, `tests/test_cleanup_non_river_scene.py` |
| Pre-cleanup backup file (local) | `havasu_chat_prod_pre_cleanup_20260430-211946.sql` (gitignored) |
| Production `--apply` | Owner PowerShell session, **2026-04-30** |
| Smoke test | **2026-05-03** |

---
