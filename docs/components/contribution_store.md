# contribution_store

`app/db/contribution_store.py` (~151 lines)

## Purpose

CRUD and query helpers for the **`contributions`** intake queue (Phase 5.1). Public contribution POSTs, River Scene import, admin review APIs, and approval flows all funnel through these functions rather than ad hoc `Session` queries in route handlers. Responsibilities: create rows from `ContributionCreate`, list/count with filters, status transitions with validation, URL normalization for dedupe, and IP-hash rate-limit counting.

## Public surface

**`normalize_submission_url(url: str | None) -> str | None`** — Strip, lowercase, drop trailing slash; `None`/empty → `None`. Shared by ingestion lanes and duplicate detection.

**`has_pending_or_approved_duplicate_url(db, normalized_url) -> bool`** — True if any contribution with status `pending` or `approved` has the same normalized URL (linear scan of URL column — acceptable at queue scale).

**`count_submissions_since_by_ip_hash(db, ip_hash, since) -> int`** — Anti-abuse helper: counts rows where `submitter_ip_hash` matches and `submitted_at >= since`. Uses naive UTC comparison consistent with stored timestamps.

**`create_contribution(db, data: ContributionCreate, submitter_ip_hash=None) -> Contribution`** — Insert + commit + refresh; returns the hydrated row.

**`get_contribution(db, contribution_id) -> Contribution | None`** — Primary-key lookup via `db.get`.

**`list_contributions(db, status=None, entity_type=None, source=None, limit=50, offset=0) -> Sequence[Contribution]`** — Ordered **`submitted_at DESC`**.

**`count_contributions(db, ...)`** — Same filter semantics as `list_contributions`.

**`update_contribution_status(db, contribution_id, status, review_notes=None, rejection_reason=None) -> Contribution | None`** — Validates `status` against **`pending` / `approved` / `rejected` / `needs_info`**; sets `reviewed_at` to **now (UTC, naive)** on every update; clears `rejection_reason` when leaving `rejected`.

## Inputs and outputs

**`ContributionCreate`** (Pydantic) drives inserts — entity type, submission fields, optional event datetimes, email, `source`, `llm_source_chat_log_id`, `unverified`, etc. Store passes through to ORM columns with minimal coercion (strip name, stringify optional email/URL).

**Status updates** raise **`ValueError`** for unknown status strings before touching the DB.

## Internal structure

Module-level **`_VALID_STATUSES`** frozenset guards `update_contribution_status`.

**`has_pending_or_approved_duplicate_url`** executes a `select(Contribution.submission_url)` filtered to pending/approved with non-null URLs, then compares normalized forms in Python — mirrors normalization rules used at insert time.

**List/count** share filter wiring via duplicated `where` clauses (intentionally parallel for readability).

## Conventions

**UTC naive `reviewed_at`.** Matches other timestamp columns that strip tzinfo for SQLite/Postgres portability in this codebase.

**Commit per mutating call.** Creates and status updates commit immediately; callers relying on larger transactions must not nest incompatible assumptions.

**URL dedupe is normalization-shaped.** Two URLs that normalize ident collide; typos that don’t normalize the same way won’t.

## Known limitations and design notes

**Duplicate scan loads URLs.** No partial index on normalized URL — scalability assumption is a modest pending queue.

**Email stored plain.** Privacy posture is documented at project level; this module doesn’t hash emails.

**Rate-limit count only.** `count_submissions_since_by_ip_hash` doesn’t enforce caps; `app/api/routes/contribute.py` applies policy.

## Configuration

None. DB session and schema from `app/db/database.py` and `app/db/models.py`.

## Related

**Direct callers:**

- `app/api/routes/contribute.py` — public submission + enrichment task scheduling.
- `app/api/routes/admin_contributions.py` — JSON queue API.
- `app/admin/contributions_html.py` — HTML review flows.
- `app/api/routes/admin_mentions.py` — promotion path creates linked contributions.
- `app/admin/mentions_html.py` — HTML promotion wiring.
- `app/contrib/approval_service.py` — `normalize_submission_url` for helper paths.
- `app/contrib/river_scene_pull.py` — bulk create via module alias `cs`.
- `app/contrib/river_scene.py` — URL normalization import.
- `scripts/backfill_river_scene_urls.py` — normalization reuse.

**Direct dependencies:**

- `app.db.models.Contribution`
- `app.schemas.contribution.ContributionCreate`

**Cross-references:**

- `docs/components/models.md` — `contributions` table and FK links.
- `docs/components/approval_service.md` — catalog materialization from pending rows.
- `docs/maintainability/end_to_end_creation.md` — Contribution lifecycle.
- `tests/test_contribution_store.py` — unit coverage.
