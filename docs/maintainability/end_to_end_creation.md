<!--
PURPOSE: Single reference for the multiple paths that produce catalog
rows (Provider, Program, Event) in production. After the 2026 RS-only
cleanup, several seed/import lanes were removed; what remains is
documented here so contributors don't grep across app/contrib/, app/db/,
app/admin/, and app/api/routes/ to understand "how does data get into
the catalog?"

AUDIENCE: Anyone debugging a contribution flow, adding a new approval
path, or onboarding to the catalog write surface.
-->

# End-to-end provider / program / event creation

## The four paths

1. **Public submission → admin review → approval** — user submits via `/contribute`, admin reviews, approval service promotes to catalog row.
2. **River Scene auto-import → admin review → approval** — CLI fetches RS magazine, creates contribution-shaped rows, admin reviews same queue.
3. **Tier 3 mention scan → admin review → promotion** — chat handler finds provider mentions in LLM responses, admin promotes from a separate queue.
4. **Admin direct create** — bypasses Contribution entirely (programs only today).

All four converge on the same `Provider` / `Program` / `Event` SQLAlchemy models in `app/db/models.py`.

## Path 1 — Public submission

1. User visits `GET /contribute` (`app/api/routes/contribute.py:get_contribute`) — HTML form.
2. User submits `POST /contribute` (`post_contribute`).
3. `_rate_limited()` check — DB-tracked IP-hash limit (custom, not slowapi).
4. `contribution_store.create_contribution(...)` writes a `Contribution` row with `status='pending'`, `source='user_submission'`, `entity_type` ∈ {`event`, `program`, `provider`}.
5. Optional background enrichment populates `google_enriched_data` (Places lookup) and/or `url_fetch_status` on the row.
6. Admin reviews in `/admin/contributions` (HTML) or `/admin/api/contributions` (JSON).
7. Admin clicks approve → handler calls one of `approval_service.approve_contribution_as_provider` / `_as_program` / `_as_event` based on `entity_type`.
8. The approval service:
   - Loads via `_load_pending_contribution` (validates `status='pending'` + matching `entity_type`).
   - Computes `verified` via `enrichment_suggests_verified` (true when Places lookup succeeded or URL fetch status was `success`).
   - Builds the catalog row from `edited_fields` (a Pydantic schema from `app/schemas/contribution.py`) plus contribution metadata.
   - `db.add(row)` + `db.flush()` to get the row's id.
   - Updates Contribution: `status='approved'`, `reviewed_at=now`, `created_<entity>_id=row.id`, clears `rejection_reason` / `review_notes`.
   - `db.commit()` (rollback on failure).
9. Catalog row is live (`is_active=True` for Provider/Program; `status='live'` for Event).

## Path 2 — River Scene auto-import

Same approval mechanics as Path 1; the difference is how Contribution rows get created.

1. CLI: `python scripts/river_scene_pull.py` (thin wrapper over `app.contrib.river_scene_pull.run_pull`).
2. `run_pull` uses `app.contrib.river_scene` to fetch the RS magazine sitemap and event pages, normalize each into a contribution-shaped payload.
3. Each event → `contribution_store.create_contribution(...)` with `source='river_scene_import'`, `entity_type='event'`.
4. **Dedupe**: `has_pending_or_approved_duplicate_url(...)` skips contributions whose normalized `source_url` already has a pending or approved Contribution.
5. Admin reviews the same `/admin/contributions` queue.
6. Approval flow same as Path 1, but `approve_contribution_as_event` recognizes `c.source='river_scene_import'` and sets `event.source='river_scene_import'` for traceability. `created_by` is set to `'admin'` since it wasn't a user submission.

See `docs/maintainability/river_scene_event_output_decision.md` and the `river_scene_backfill_*.md` runbooks for the full RS pipeline.

## Path 3 — Tier 3 mention scan → admin promotion

Different queue from Contribution: the `LlmMentionedEntity` table.

1. `POST /api/chat` Tier 3 response triggers a background task: `mention_scanner.scan_and_save_mentions(...)`.
2. Scanner identifies provider mentions in the LLM response text (uses `entity_matcher` rules to match catalog providers and detect new candidates).
3. Each new candidate → `LlmMentionedEntity` row (status `proposed`).
4. Admin reviews in `/admin/mentioned-entities` (HTML) or `/admin/api/mentioned-entities` (JSON).
5. Admin promotes → `POST /admin/api/mentioned-entities/{id}/promote` (or HTML equivalent).
6. Promotion handler creates a `Provider` row with the mention's name + minimal fields, marks `LlmMentionedEntity.status='promoted'`.
7. Admin can also dismiss → `LlmMentionedEntity.status='dismissed'` (no Provider created).

This path skips Contribution entirely. Mentions are a lighter-weight queue: no rich form, no enrichment, just "this name appeared in chat — should it be a Provider?"

## Path 4 — Admin direct create

Bypasses both queues.

**Programs**: `/admin/programs/new` (HTML form) → `admin_program_create` (admin/router.py) directly inserts a `Program` row with `source='admin'`. No Contribution row created.

**Events**: No standalone "admin direct create event" form anywhere. Events come via Path 1 (public submission via `/contribute` → admin review → approval), Path 2 (River Scene auto-import → contribution → admin review), or Path 3 (Tier 3 mention promotion creates Provider — events specifically don't have a mention-promotion path; just providers).

**Providers**: No standalone admin "create provider" form. Providers come via Path 1 (entity_type='provider') or Path 3 (mention promotion).

## Contribution status states

| Status | Set when | Linked field |
|---|---|---|
| `pending` | At create time | — |
| `approved` | Admin clicks approve and `approval_service` succeeds | `created_<entity>_id` |
| `rejected` | Admin clicks reject with reason | `rejection_reason` |
| `needs_info` | Admin requests clarification | `review_notes` |

Transitions managed by `contribution_store.update_contribution_status` and the admin HTML form handlers in `app/admin/contributions_html.py`. See `app/schemas/contribution.py` for the canonical enum.

## Catalog row fields touched at creation

- **`Event`** (`app/db/models.py:Event`): title, date, end_date, start_time, end_time, location_name, description, event_url, source_url, tags, `is_recurring` (heuristic from text blob via `event_recurrence.is_recurring_heuristic`), source (`'river_scene_import'` or NULL), status=`'live'`, created_by (`'user'` / `'admin'`), verified.
- **`Program`** (`app/db/models.py:Program`): title, description, activity_category, age_min/max, schedule_days/start/end_time, location_name/address, cost, provider_name, contact_phone/email/url, source=`'admin'`, verified, is_active=True, tags.
- **`Provider`** (`app/db/models.py:Provider`): provider_name, category, address, phone, hours (free text), hours_structured (parsed from Places `regular_opening_hours` via `places_hours_to_structured`), description, website, draft=False, is_active=True, verified, source (`'user'` or `'admin'`).

`FieldHistory` rows track field-level changes after creation as a separate audit trail (`app/db/models.py:FieldHistory`).

## What this doc does NOT cover

- **Contribution edit UX in admin** (per-field approval form details). See `app/admin/contributions_html.py`.
- **Field validation rules and Pydantic schemas.** See `app/schemas/contribution.py`, `app/schemas/event.py`, `app/schemas/program.py`.
- **The non-RS catalog cleanup that removed prior import lanes.** See `docs/maintainability/non_river_scene_cleanup.md`.
- **Forward-looking provider ingestion lanes** (e.g., automated provider import from external sources). Listed as a separate §5 gap in `project_index.md` for a future spec doc.
- **Mention scanner heuristics and confidence scoring.** See `app/contrib/mention_scanner.py` source.
- **Background enrichment internals** (Places lookup, URL fetch). See `app/contrib/places_client.py`, `app/contrib/url_fetcher.py`, `app/contrib/enrichment.py`.

## Related docs

- `docs/maintainability/non_river_scene_cleanup.md` — what was removed in the 2026 RS-only cleanup.
- `docs/maintainability/river_scene_event_output_decision.md` — RS event output design.
- `docs/maintainability/http_api.md` — HTTP API surface (contribution + admin routes).
- `app/contrib/approval_service.py` — promotion logic.
- `app/db/contribution_store.py` — Contribution CRUD + dedupe + rate limit.
- `app/db/models.py` — Contribution / Event / Program / Provider / LlmMentionedEntity / FieldHistory models.
