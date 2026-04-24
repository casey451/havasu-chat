# Phase 8.10-read — River Scene Event Pull: Read-Only Audit

**Date:** 2026-04-23  
**Mode:** Read-only (no code changes, no external network requests). Map current event ingestion and what 8.10 would need.

---

## 1. Handoff §5 — Phase 8.10 (verbatim)

From `HAVA_CONCIERGE_HANDOFF.md`:

```text
### Phase 8.10 — River Scene Event Pull (pre-launch, ~1 week, 10–15 hours)

**Goal:** Ingest events from River Scene local event calendar into the events catalog. Single source, structured ingestion, operator review pass, dedup against existing seed events.

**8.10.1 Scraper + parser.** Fetch logic for River Scene event pages, parse into structured event records (title, date, time, location, description, source URL). Respect robots.txt and reasonable rate limits.

**8.10.2 Dedup against seed.** Compare ingested events against existing 43 seeded events. Fuzzy match on title + date. Flag duplicates for operator review rather than auto-dropping.

**8.10.3 Operator review queue.** Ingested events land in existing `/admin/contributions` review queue with `source='river_scene_import'`. Operator approves, rejects, or edits before events go live.

**Exit criterion:** River Scene events visible in `/admin/contributions`, approved events queryable via chat, no test regressions, no voice battery regressions.
```

### Cross-references (event ingestion)

Elsewhere, §1c / §1d-style material documents the contribute stack and Phase 5 operator review (`/admin/contributions`, `approval_service`, etc.). A grep hit at `HAVA_CONCIERGE_HANDOFF.md` ~606 mentions `source` for provenance in a table-style note (`admin` / `scraped` / `user`). **Phase 8.11** nearby references `havasu-enrichment` and provider **catalog** ingestion, not the events calendar. The 8.10 block is self-contained.

---

## 2. Persona brief — events / ingestion (verbatim excerpts)

`docs/persona-brief.md` does **not** define a River Scene or scraper; **§9.6** is only event **ranking** (classification, not ingestion). The only substantive “events + provenance/ingestion” text found:

**§6.1–6.2** (event voice, not ingestion):

- §6.1: *"When the Phase 8.9 event-ranking retrieval returns no one-time/special events in the window:"* + example.
- §6.2: *"When one-time events exist in the window:"* + example.

**§6.7** (bulk **providers**, not events — clarifies data-model stance for voice):

- *"**No provenance flag required in the data model.** The framing-vs-specifics split is content-semantic, not source-tagged. Bulk ingestion landing in the **provider catalog** does not require a `source` column addition for voice purposes."*

**Summary:** No persona-brief section dedicated to River Scene or event import; 8.10 is driven by handoff, scope-revision, and checklist.

---

## 3. `docs/pre-launch-scope-revision-2026-04-22.md` — Phase 8.10

**§2.1 — River Scene event pull — pre-launch**

- *"Pull events from **River Scene (local events calendar)** into the events catalog before launch. Scope: one source, structured event data ingestion, operator review pass, dedup against existing **43** seeded events. Low-risk, small-to-medium execution phase."*

**§3** sequence lists `→ 8.10 (River Scene event pull)` after 8.9.

**§4** checklist items include *"River Scene event pull operational, events ingested, operator-reviewed."*

**§7** states the River Scene pull “Cursor prompt” is drafted separately when 8.10 starts.

**No URL, API, or robots.txt** detail in this doc beyond what’s in the handoff.

---

## 4. Map: code paths that create `Event` rows

| Location | Lines (approx.) | Description |
|----------|-----------------|-------------|
| `app/main.py` | 536–543 | `POST /events` — `Event.from_create(payload)`; `EventCreate` from API. |
| `app/contrib/approval_service.py` | 172–213 | `approve_contribution_as_event` — builds `EventCreate`, `Event.from_create`, links `contribution.created_event_id`. |
| `app/db/seed.py` | 500–559 (`run_seed`) | `EventCreate` + embeddings from `generate_query_embedding`; `created_by="seed"`, `status="live"`, `__seed__:lhc_XXX` tags. |
| `app/chat/router.py` | 444, 484, 524 | Call sites that persist events. |
| `app/chat/router.py` | 858–875 | `_store_event` → `try_build_event_create` + `Event.from_create` (live add-event flow). |
| `app/chat/router.py` | 867–875 | `_store_pending_review` → `build_pending_review_create` + `Event.from_create` with `status="pending_review"`. |
| `app/core/event_quality.py` | 152–188 | `build_pending_review_create` only builds `EventCreate` (no DB). |

**User contribution (web):** `app/api/routes/contribute.py` — builds `ContributionCreate`, `create_contribution` in `app/db/contribution_store.py` (54–79); **no `Event` row** until **approval** in `approve_contribution_as_event`.

**Tests / fixtures:** Various tests call `Event(...)` or `Event.from_create(...)`; same pattern, not a separate production path.

**Scrapers / importers for events:** **None** in `app/`. `httpx` usage: `app/contrib/places_client.py`, `app/contrib/url_fetcher.py` (enrichment/URLs), not an event calendar. `scripts/`: e.g. `smoke_*.py`, `activate_scraped_programs.py` (programs), `seed_from_havasu_instructions.py` — not a River Scene event pipeline. **`havasu-enrichment`**: mentioned for **8.11 provider** catalog, not 8.10 events in-repo.

---

## 5. `Event` / `EventCreate` / `EventRead` — import-relevant fields

**`app/db/models.py` `Event`:** `id`, `title` / `normalized_title`, `date`, `start_time` / `end_time`, `location_*`, `description`, `event_url`, contacts, `tags`, `embedding`, `status`, **`source`**, `verified`, `created_at`, `created_by`, `admin_review_by`, `provider_id`, `is_recurring`, …

**`app/schemas/event.py` `EventBase`:** does **not** include `source` in the Pydantic model; `Event.from_create` uses `getattr(payload, "source", None) or "admin"`, so the ORM can still set `source` if a dict/model passes it, but the public `EventCreate` API as defined does not expose it on the schema (worth aligning in 8.10 if imports need `source`).

- **`source` (on `Event`):** free-form string, default `"admin"`. **No** `source_url` or `external_id` on `Event` (grep: **none** in `app/db` / `app/schemas/event.py`).
- **`status`:** string; live seed uses `"live"`; chat pending path uses `"pending_review"` via `build_pending_review_create` (`app/core/event_quality.py` ~185). Imported-not-reviewed: handoff implies **contribution queue first**; final `Event` is `"live"` on approve (`approval_service`).
- **`created_by`:** e.g. `"seed"`, `"user"`, or derived from contribution in `approve_contribution_as_event` (`app/contrib/approval_service.py` ~183–196). 8.10 can define a **convention** (e.g. `river_scene` on `Event` after approval) — not specified in code today.
- **Dedup keys:** no stable **River Scene** id column. In-repo: handoff **fuzzy title + date** vs seed; **contribution** duplicate URL check (`contribution_store.py` `has_pending_or_approved_duplicate_url`) is URL-based, not event-calendar id. **8.10 would need a design** (e.g. tag, hash, or new column) to avoid re-importing the same listing.

---

## 6. Operator review queue

- **List / detail / approve:** `app/admin/contributions_html.py` (`/admin/contributions`, `/admin/contributions/{id}`, POST approve → `approve_contribution_as_event` in `app/contrib/approval_service.py`).
- **CRUD / insert:** `app/db/contribution_store.py` **54–79** `create_contribution`.
- **Model:** `Contribution` in `app/db/models.py` **209–262**; `source` default `"user_submission"`. **Pydantic** `ContributionSource` in `app/schemas/contribution.py` is **`Literal["user_submission", "llm_inferred", "operator_backfill"]` only** — **no** `river_scene_import` in code. Handoff 8.10.3 references **`source='river_scene_import'`**; **implementation will require** schema/migration/validation extension (or doc/code alignment).

**Read:** Ingested rows are intended to use the **same** `/admin/contributions` queue; no separate 8.10-specific queue exists today.

---

## 7. River Scene “source” in docs (no fetch performed)

- **Handoff / scope revision:** *“**River Scene local event calendar**”* / *“**River Scene (local events calendar)**”* — **no** HTTP(S) URL, feed URL, or API named in those docs.
- **Seed provenance comment** `app/db/seed.py` **22–25** lists **`riverscenemagazine.com`** among other sites as **reference sources for hand-built seed copy**, not an automated 8.10 scrape target.
- **No** docs line specifying cadence, HTML structure, or API (beyond high-level “scraper + robots.txt” in 8.10.1).

---

## 8. Grep results (targets as specified)

| Pattern | Result |
|--------|--------|
| `river scene` (incl. variants) | `HAVA_CONCIERGE_HANDOFF.md` 1154–1166; `docs/pre-launch-scope-revision-2026-04-22.md` 17, 19, 59, 77, 120; `docs/pre-launch-checklist.md` 59; `docs/START_HERE.md` 103; `app/db/seed.py` 23 (`riverscenemagazine.com`) |
| `riverscene` | `app/db/seed.py` 23 only (`riverscenemagazine.com`) |
| `RiverScene` | **no matches** |
| `event_source` | **no matches** in app/schemas |
| `source_url` (event) | **no** event model field; no hits in `app/db` for events |
| `external_id` (event) | **no matches** in event path |
| `scrape` | Multiple docs; `app/admin/router.py` 876+ (programs “scraped”); `scripts/activate_scraped_programs.py`; not event ingestion |
| `ingest` | Mostly 8.10/8.11 in handoff/scope; `docs/persona-brief.md` 153 (provider catalog); no dedicated event ingester in `app/` |

---

## 9. Proposed fix shape (owner decisions — not implementation)

1. **Contribution `source`:** Extend **`ContributionSource`** (and DB if constrained) to include **`river_scene_import`** (or use `operator_backfill` + metadata — tradeoff: clarity vs migration).
2. **Ingestion module:** New script or service: fetch → parse → `create_contribution` (or internal insert) with `entity_type="event"`, `submission_name` / notes / URL fields from **source URL** per 8.10.1; **respect robots.txt / rate limits** (out-of-band design).
3. **Dedup (8.10.2):** Implement **fuzzy title + date** vs `Event` and vs **seed** tags; on duplicate → still queue with flag or `review_notes` — *“flag for operator, don’t auto-drop”* as handoff says.
4. **Post-approval `Event` fields:** Set **`source`** and **`created_by`** (and **`event_url`**) so chat/search behavior is clear; consider **`is_recurring`** (8.9 heuristic or import metadata).
5. **Stable id / re-run:** **No `external_id`** today — add **tag**, **hash column**, or **convention in `tags`** to support idempotent runs (decision point).
6. **Embeddings:** Seed computes embeddings; 8.10 may need **re-embed** on approve or on insert (load/cost tradeoff).
7. **Handoff / code gap:** **43** vs current seed size — re-count in DB before implementing dedup text (the number may have drifted).
8. **Persona note:** **§6.7** is **provider**-catalog voice; 8.10 does not require a provenance flag **for voice** by that text, but **operational** `source` on `Event` remains useful for ops/debugging.

**Decision points to confirm before implementation:** exact **River Scene** fetch surface (list page vs per-event); **`ContributionSource` vs new column**; **dedup** when an event is already `live` from seed vs user; **automation** (cron) vs one-shot script.

---

*End of Phase 8.10-read report.*
