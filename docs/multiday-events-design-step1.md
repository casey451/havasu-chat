# Multi-day events — design (Step 1)

## Decisions recorded (Step 2+)

1. **`_find_seed_overlap` (RiverScene pull):** range-aware comparison is **deferred to backlog**. This initiative does **not** change its single-day comparison logic. If dedupe becomes a real issue post-fix, run a separate diagnostic-then-fix pass.

2. **`Date:` line formats in `submission_notes`:** diversity will be **surveyed at Step 5** (backfill). **Step 2 is migration-only**; note-parsing implementation is **out of scope** for the migration step.

3. **Step 3 scope:** include **`app/chat/tier1_handler.py`** and **`app/core/event_quality.py`** per section G (confirmed at Step 3 design time).

---

Design-only pass: schema, migration shape, code paths, backfill, tests, risks, and alignment with the 10-step plan. **No** `railway` commands, **no** code commits in this document’s authoring step.

**Context:** `Event` and `Contribution` are single-day at the DB layer; `RiverSceneEvent` and `submission_notes` already carry multi-day text. Retrieval uses `Event.date == query_date` style filters, so middle days of a range are missed.

---

## A. Schema decision

- **`Event.end_date` — Yes.**  
  Store the **inclusive** end date. Keep existing `date` as **start** (same meaning as `RiverSceneEvent.start_date` / `event_date` today). A calendar day *q* matches when `date <= q <= coalesce(end_date, date)`.

- **`Contribution.event_end_date` — Yes.**  
  The normalizer only encodes the range in `submission_notes` today; `event_date` is start-only, so the contribution row is **lossy** for anything that reads the DB without re-fetching HTML. A column keeps approval, Fix 2 (`scripts/approve_pending_river_scene.py`), and the queue consistent with the parser. Naming: e.g. `event_end_date` on `Contribution`, `end_date` on `Event`.

- **Nullability — Recommended: nullable on both.**  
  **`NULL` `end_date` / `event_end_date`:** treat as single-day; effective end = `date`. Use `coalesce(end_date, date)` in queries. (Alternative: backfill `end_date = date` for all rows to avoid NULL in DB—slightly more redundant.) Given a separate data backfill step, **nullable + coalesce** is a clear model: multi-day is explicit; single-day is default.

- **Index — Defer or minimal.**  
  Catalog is ~10² events; likely no new index is required for v1. If needed later, consider something aligned with range overlap and existing `date` usage.

---

## B. Migration plan

- **Alembic location:** `alembic/versions/` (not `migrations/`). **Current head (at design time):** `d1e2f3a4b567` (`d1e2f3a4b567_normalize_json_null_embeddings_to_sql_null.py`), `down_revision` = `b8c9d0e1f2a3`.

- **One migration (recommended):** add `events.end_date` and `contributions.event_end_date` in a **single** revision: one `upgrade head` per environment, one deploy artifact.

- **Shape:**

  - `events.end_date`: `Date`, **nullable**
  - `contributions.event_end_date`: `Date`, **nullable**

- **Data inside the migration file:** keep **schema only**; do not embed heavy `submission_notes` parsing in Alembic. Use a **separate backfill script** (see D).

---

## C. Code path changes

### `app/contrib/river_scene.py`

- `RiverSceneEvent` already has `end_date` from HTML.
- **Change:** in `normalize_to_contribution`, set `ContributionCreate.event_end_date` from `rse.end_date` (always set is simplest: matches parser). Keep `submission_notes` for operators as today.

### `app/db/models.py`

- Add `end_date` on `Event` and `event_end_date` (name TBD) on `Contribution`.
- Extend `Event.from_create` to pass through optional `end_date` from `EventCreate`.

### `app/db/contribution_store.py`

- `create_contribution`: map the new Pydantic field into the `Contribution` row.

### `app/schemas/contribution.py`

- Add optional `event_end_date` to `ContributionCreate` and to `ContributionResponse` if the API should expose it.

### `app/schemas/event.py`

- Add optional `end_date: date | None` to `EventBase` / `EventCreate` with validation (`end_date >= date` when present).

### `app/contrib/approval_service.py`

- `EventApprovalFields`: add optional `end_date`.
- `approve_contribution_as_event`: pass `end_date` into `EventCreate`; prefer contribution’s `event_end_date` when set, else approval field, else `None`.

### `app/contrib/river_scene_pull.py` (Fix 1)

- In auto-approval, pass `end_date=rse.end_date` in `EventApprovalFields` (not only `date` from `payload.event_date`).

### `scripts/approve_pending_river_scene.py` (Fix 2)

- Build `EventApprovalFields` with `end_date` from `c.event_end_date` when set; else parse the first `Date:` line in `submission_notes` (formats consistent with `_format_date_heading` / RiverScene output). Factor shared parse helpers to avoid drift.

### `app/chat/tier2_db_query.py`

- **`_query_events`:** replace point filters on `Event.date` with **interval overlap** against the filter window, e.g. `Event.date <= win_end` and `coalesce(Event.end_date, Event.date) >= lower` (consistent with explicit past-date rules already in play).
- **`_sample_mixed` / “future”:** include events where `coalesce(end_date, date) >= today`, not only `date >= today`.
- **`_event_dict`:** add `end_date` to JSON when useful for formatters.
- **`day_of_week` filter:** match if the named weekday appears **anywhere** in `[date, coalesce(end_date, date)]` (not only `e.date`).
- **Bucketing / upper-bound helpers** that use `e.date` as the only calendar anchor: re-check against effective end for broad windows.
- **Related (same concern):** `app/chat/tier1_handler.py` — event list filters using `Event.date >= today` should use the same “effective end” / overlap idea so long spans do not vanish early.

### `app/core/search.py`

- **`_base_future_events_query`:** time-scoped `date_context` should **overlap** `[Event.date, coalesce(Event.end_date, Event.date)]` with `[start, end]`. Unbounded “future” should not rely solely on `Event.date >= today` if the event started earlier but is still running.
- **`_event_card`:** when `end_date` and `date` differ, show a short range in the card.

### `app/core/event_quality.py`

- Any `EventCreate` construction for admin/draft paths should accept optional `end_date` so new columns are populated when the product adds UI later.

---

## D. Backfill of existing data

- **RiverScene**-sourced rows often have a `Date:` line in `submission_notes` (e.g. `Date: May 7–9, 2026` from `_format_date_heading`, including en-dash and cross-month forms).
- **Admin** events may not have that pattern.
- **Recommendation:** **separate backfill script** (after migration + app deploy):
  1. **Events:** `UPDATE` `events` (at least `source = 'river_scene_import'`) by parsing the first `Date:` line; on failure, leave NULL and log id.
  2. **Contributions (optional):** set historical `event_end_date` for consistency; **retrieval reads `Event`**, so **event** backfill is the critical path for chat.

---

## E. Test plan

### Existing tests likely to update

- `tests/test_phase8_10_river_scene.py` — `ContributionCreate` / `Event` assertions; multi-day auto-approval; `normalize` tests for new field; consider `_find_seed_overlap` (currently compares on `start_date` vs `ev.date` only).
- `tests/test_approval_service.py` — `EventApprovalFields` + created `Event` with `end_date`.
- `tests/test_approve_pending_river_scene.py` — multi-day `Date:` in notes; `event_end_date` on row.
- `tests/test_tier2_db_query.py` — middle-day and overlap; extend `_evt` with optional `end_date`. **Reconcile** with any in-progress uncommitted `test_tier2_db_query.py` (past-date retrieval) in one test pass.
- **Search** tests (if present) for `date_context` and inclusion.
- **Constructors** `Event(...)` in other tests: nullable `end_date` with no server default on ORM should keep most fixtures valid without changes.

### New tests (minimum)

- Normalizer / parser: `event_end_date` (or stored field) matches `rse.end_date` for multi-day.
- Approval: `Event.end_date` set from fields/contribution.
- Tier 2: `date_exact` (or range) on a **middle** day of a multi-day event returns the event.
- Optional: unit tests for `parse_date_line_from_submission_notes` (or equivalent).
- Search: overlap + “still ongoing” event that started in the past.

---

## F. Risk callouts

- **NULL `end_date`:** All creators must set `end_date` when known, or leave NULL. Nullable column + **`coalesce` in read paths** keeps pre-backfill and admin single-day behavior correct.
- **Deploy ordering:** New columns nullable → new code → backfill. Pre-backfill, old RiverScene rows still behave as single-day until the script runs; **improvement depends on backfill completing**.
- **Recurring + bucketing:** multi-day festivals vs recurring series keys may need a sanity check; not necessarily blocking v1.
- **Production:** confirm Railway auto-deploy from `main` if that is the assumption; otherwise note manual deploy.

---

## G. Step 2–10 readiness

| Step | Alignment |
|------|-----------|
| 2 | New revision after `d1e2f3a4b567`; local `alembic upgrade head` only. |
| 3 | File list above + `tier1_handler.py` + `event_quality.py` as needed. |
| 4 | Full unit suite; merge with any local tier2 test branch. |
| 5 | Local backfill script + DB spot-checks. |
| 6–7 | Commit / push per protocol. |
| 8–9 | Casey runs production migration and backfill in his terminal; draft commands only from agent. |
| 10 | Manual production chat check. |

The **10-step bootstrap** still matches; **step 3** should explicitly include **tier1** and **event_quality** so no code path still assumes a single `date` for “is this on that day / still upcoming?”

**Post-implementation (Tier 2) backlog** — not part of the multi-day *schema* deliverable: see `docs/multiday-events-backlog.md` (parser `date_exact` vs. natural phrasing, and `_time_bucket_first_hits` behavior on broad windows).

---

*Generated for Step 1 (design). Implementation begins after explicit approval for Step 2+.*
