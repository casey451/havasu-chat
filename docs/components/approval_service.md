# approval_service

`app/contrib/approval_service.py` (~243 lines)

## Purpose

Materializes catalog rows (`Provider`, `Program`, `Event`) from approved `Contribution` rows. The **sole catalog-write path** post-cleanup — every live catalog row in production was created by one of the three approve functions here. Operates within an admin-mediated approval flow: a `Contribution` row is `status='pending'`, an admin (or auto-approval logic in `river_scene_pull.py`) calls one of the approve functions, and the function creates the catalog row, transitions the contribution to `status='approved'`, and links the contribution to the new row via `created_{entity}_id`. On exception, the function rolls back the SQLAlchemy session — atomic.

## Public surface

Five functions:

**`approve_contribution_as_provider(db, contribution_id, edited_fields, category, reviewed_by=None) -> Provider`** — Create a `Provider` row from a pending provider contribution. `edited_fields: ProviderApprovalFields` carries the admin's reviewed-and-edited values; `category` is required (catalog organizing field). Returns the new `Provider` (refreshed). Raises `ValueError` if contribution is missing, not pending, or wrong entity type, or if `category` is empty.

**`approve_contribution_as_program(db, contribution_id, edited_fields, reviewed_by=None) -> Program`** — Create a `Program` row from a pending program contribution. `edited_fields: ProgramApprovalFields` carries reviewed values including `provider_id` link. Returns the new `Program`.

**`approve_contribution_as_event(db, contribution_id, edited_fields, reviewed_by=None) -> Event`** — Create an `Event` row from a pending event contribution. `edited_fields: EventApprovalFields` carries reviewed values. Returns the new `Event`. Used by River Scene auto-approval (`river_scene_pull.run_pull`) and by admin-mediated approval of operator submissions.

**`enrichment_suggests_verified(contribution: Contribution) -> bool`** — Helper: returns `True` when external enrichment (URL fetch or Google Places lookup) produced usable signal. Drives the `verified` flag on the new catalog row. Specifically: URL fetch status is "success", or Places lookup status is "success" / "low_confidence".

**`parse_comma_tags(raw)` / `parse_schedule_days_field(raw) -> list[str]`** — Parsing helpers shared with admin form handlers. Stable enough to count as public surface; tests use them directly.

## Inputs and outputs

**Inputs.**
- `db: Session` — SQLAlchemy session, caller-provided. Approval function calls `db.commit()` directly (not a context manager).
- `contribution_id: int` — primary key in `Contribution` table.
- `edited_fields` — entity-typed Pydantic model (`ProviderApprovalFields` / `ProgramApprovalFields` / `EventApprovalFields`) carrying admin's reviewed values. Distinct from the contribution's raw payload (which is what the user submitted); `edited_fields` is what the admin actually wants written.
- `category: str` (provider only) — required organizing tag.
- `reviewed_by: str | None` — accepted but currently unused (the underscore-prefix discard). Future audit-log hook.

**Outputs.**
- A freshly-inserted `Provider` / `Program` / `Event` row, refreshed from the DB so all server-defaulted fields are populated.
- Side effects on the contribution: `status='approved'`, `reviewed_at=now`, `created_{entity}_id=<new row id>`, `rejection_reason=None`, `review_notes=None`.

**Raises.**
- `ValueError` for the load-contribution preconditions: contribution missing, not pending, or wrong entity type. `category=""` for provider.
- Any DB exception during the insert/flush/commit — caller sees the original exception (after rollback). Approval functions don't catch broadly; the rollback is the only `try/except`.

## Internal structure

Each approve function follows the same six-step shape:

1. **Load + validate the contribution.** `_load_pending_contribution(db, contribution_id, entity_type)` does the existence + status='pending' + entity-type matches checks. Raises `ValueError` on mismatch.
2. **Compute derived fields.** `verified = enrichment_suggests_verified(c)` for all entity types. Source field set to `"user"` (when `contribution.source == "user_submission"`) or `"admin"` (everything else, including River Scene auto-import). For providers, hours from `Places.regular_opening_hours` get structured via `hours_helper.places_hours_to_structured` if available.
3. **Build the catalog row instance** with explicit field-by-field assignment. Strip-and-`None` for optional string fields ensures empty strings don't hit the DB as `""`.
4. **Insert + flush.** `db.add(row); db.flush()` makes the new ID available without committing.
5. **Update the contribution.** `c.status = "approved"`, `c.reviewed_at = _naive_utc_now()`, `c.created_{entity}_id = row.id`, clear `rejection_reason` and `review_notes`. All within the same uncommitted transaction.
6. **Commit + refresh.** `db.commit()` atomicizes the catalog-row insert and the contribution update. `db.refresh(row)` repopulates server-defaulted fields. On any exception in step 4-6, `db.rollback()` runs and the original exception propagates.

The provider and program functions hard-code their own per-field translation; the event function additionally invokes `is_recurring_heuristic(event_text_blob(...))` to populate the `is_recurring` flag.

## Conventions

**`db.commit()` inside the function, not delegated.** Approval is a transactional unit — caller can't interleave other DB ops between insert and contribution update. The function takes responsibility for the transaction boundary.

**`naive` UTC timestamps.** `_naive_utc_now()` strips tzinfo. The DB columns are TIMESTAMP WITHOUT TIME ZONE; storing tz-aware `datetime` would mismatch.

**`source` field reflects upstream provenance.** `"user"` for self-service submissions, `"admin"` for everything else (River Scene auto-import, operator direct creation). Used for catalog filtering and analytics.

**`verified` field reflects external signal, not human review.** `enrichment_suggests_verified` doesn't account for the admin's review pass; that's intentional. A human-vetted entry without external enrichment stays `verified=False` until enrichment data arrives. Reviewer notes live separately in the contribution.

**Strip-and-None for optional string fields.** `(field or "").strip() or None` is the consistent pattern. Empty strings never reach the DB; they're either populated text or NULL.

**`reviewed_by` is currently unused.** Plumbed in the signature for an eventual audit-log; functions discard via `_ = reviewed_by`. Don't remove from the signature without also removing it from the admin caller layer.

## Configuration

No configuration. Behavior is driven entirely by the contribution row contents and the `edited_fields` arg.

## Known limitations and design notes

**No upsert path.** If the admin tries to approve a contribution that's already been approved (or rejected), the load step raises `ValueError`. Re-running an approval requires the admin to reject + re-pend or to operate directly on the catalog row.

**Hours structuring is provider-only and Places-only.** Programs and events have schedule fields handled by other helpers (`parse_schedule_days_field`). Providers get `hours_structured` from Places-API JSON when present; otherwise hours stay as freeform text.

**No batch approve.** Each call processes one contribution. Bulk approval would need a wrapper that loops; the current functions assume single-contribution scope.

**`verified` is a one-shot gate.** Set at approval time from `enrichment_suggests_verified`. Re-running enrichment after approval doesn't update the flag — that requires a separate path (admin edit, or a future re-verification slice).

**`reviewed_by` plumbing is incomplete.** The arg exists but isn't persisted. Adding audit logs would mean threading `reviewed_by` into a new `ReviewLog` table or into a `Contribution.reviewed_by` column; either is its own slice.

**No rollback log.** When the rollback fires, the original DB exception propagates without being wrapped. Operationally this is fine — the admin sees the error from the route handler — but for post-mortem analysis the only artifact is whatever the framework's exception handler logged.

**Auto-approval bypasses admin review.** River Scene's `run_pull` calls `approve_contribution_as_event` directly without an admin in the loop. The contribution still records `status='approved'` and `reviewed_at`; the `reviewed_by` field just stays unset (acceptable for the auto-approval flow per upstream curation argument in `river_scene.md`).

## Related components

**Direct callers:**

- `app/admin/router.py` admin approval endpoints — the human-mediated path. Routes call `approve_contribution_as_*` after the admin reviews + edits the contribution form.
- `app/contrib/river_scene_pull.py` `run_pull` — auto-approval path. Calls `approve_contribution_as_event` directly when seed-overlap doesn't fire.
- `app/admin/router.py` mention-promotion endpoints — Tier 3 mention scan promotion path. Calls `approve_contribution_as_provider` (or `_as_program`) when an admin promotes an `LlmMentionedEntity` row to a real catalog row.

**Direct dependencies:**

- `app/contrib/hours_helper.places_hours_to_structured` — Provider hours JSON structuring.
- `app/core/event_recurrence.event_text_blob` + `is_recurring_heuristic` — Event recurrence flagging.
- `app/db/contribution_store.normalize_submission_url` — URL canonicalization (used in some helper paths; double-check cross-call).
- `app/db/models.{Contribution, Event, Program, Provider}` — DB models.
- `app/schemas/contribution.{EventApprovalFields, ProgramApprovalFields, ProviderApprovalFields}` — input schemas.
- `app/schemas/event.EventCreate`, `app/schemas/program.ProgramCreate` — internal validation paths within the event/program approve functions.

**Cross-references:**

- `docs/maintainability/end_to_end_creation.md` — documents the four paths producing catalog rows; this module is the funnel for Paths 1, 2, and 3.
- `docs/components/river_scene.md` — upstream auto-approval path.
- `docs/maintainability/non_river_scene_cleanup.md` — historical context for why this is currently the only catalog-write path.
