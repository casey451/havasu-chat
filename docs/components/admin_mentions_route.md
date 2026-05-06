# admin_mentions_route

`app/api/routes/admin_mentions.py` (~152 lines)

## Purpose

Admin-gated **JSON API** for the LLM-mention review queue (Phase 5.5). Four endpoints under `/admin/api/mentioned-entities*` — list, single fetch, dismiss, promote (creates a `Contribution` row from a mention). The HTML surface at `app/admin/mentions_html.py` (`/admin/mentioned-entities*`) is the operator-facing page; this module is the JSON-shaped sibling that powers programmatic clients.

A "mention" is a Tier 3 LLM-extracted catalog candidate (title-case noun the assistant said about a place / program / event). Upstream extraction lives in `app/contrib/mention_scanner.py`; rows land in `LlmMentionedEntity` with `status='unreviewed'`. Operators triage them here: dismiss with a reason, or promote into the contribution queue for full review.

## Public surface

**`router: APIRouter`** — Sole export. **Prefix `/admin/api`**, tag `admin-mentions`. Mounted from `app/main.py` via `app.include_router(admin_mentions_router)`.

**`require_admin(request: Request) -> None`** — Module-local dependency (same body as `admin_contributions_route.require_admin`). Validates the admin cookie via `verify_admin_cookie`; raises `HTTPException(401)` on missing or invalid cookie.

**`_parse_day_bounds(detected_from, detected_to) -> tuple[datetime | None, datetime | None]`** — Module-private helper. Parses `YYYY-MM-DD` strings into naive day-start / day-end `datetime` for filtering on the `detected_at` column. Bad format raises `HTTPException(422)`.

## Route inventory

| Route | Method | Status | Purpose |
|---|---|---|---|
| `/admin/api/mentioned-entities` | GET | 200 / 422 | List with filters: `status`, `detected_from`, `detected_to` (YYYY-MM-DD), `limit` (1–200, default 50), `offset` (≥0). 422 if either date is malformed. |
| `/admin/api/mentioned-entities/{mention_id}` | GET | 200 / 404 | Single mention by integer id. |
| `/admin/api/mentioned-entities/{mention_id}/dismiss` | POST | 200 / 400 / 404 | Body `MentionDismissBody` (`reason`). 400 if mention is not in `unreviewed` status. |
| `/admin/api/mentioned-entities/{mention_id}/promote` | POST | 200 / 400 / 422 / 404 | Body `MentionPromoteBody`. Builds `ContributionCreate` (`source="llm_inferred"`, `llm_source_chat_log_id=row.chat_log_id`), calls `create_contribution`, schedules `enrich_contribution`, then `promote_mention` to flip the mention's status. 422 if URL is missing for provider/program; 400 if mention is not `unreviewed`. |

## Inputs and outputs

**Auth:** Every route is `Depends(require_admin)` (via the `AdminAuth = Annotated[None, Depends(require_admin)]` alias). Same cookie surface as `admin_contributions_route.md`.

**List filtering:** `status_filter` is exposed as `?status=...` (alias for the in-Python name; avoids shadowing `fastapi.status`). Date filters accept ISO `YYYY-MM-DD`; `_parse_day_bounds` expands them to day-start (`00:00:00`) and day-end (`23:59:59`) naive datetimes for column comparison.

**Promote — what gets created:** A new `Contribution` row with `source="llm_inferred"` and `llm_source_chat_log_id` carried over from the mention. Provider/program entity types require a non-empty `submission_url`; events and tips don't. The mention's status flips to `promoted` only after the contribution row is committed and enrichment scheduled.

**Promote — required-only-on-some-entity-types validation:** The route checks `body.entity_type in ("provider", "program") and body.submission_url is None` explicitly and raises 422. This is in addition to whatever `MentionPromoteBody` enforces at the schema level — the route guard is defensive.

**Side effect on promote:** Enrichment background task scheduled via `BackgroundTasks.add_task(enrich_contribution, contrib.id, SessionLocal)`. The new contribution then flows through the normal admin contribution-review surface for full triage.

## Internal structure

**Module shape mirrors `admin_contributions_route.py`:**

1. Top: imports + `require_admin` + `AdminAuth` / `DbSession` annotations.
2. `_parse_day_bounds` helper (only mentions has this — the contributions route doesn't filter by date).
3. Four `@router.get` / `@router.post` handlers, each:
   - Auth + DB dependencies via the annotation aliases.
   - Path / query / body parameters.
   - `get_mention(db, mention_id)` to fetch + 404 check.
   - Status-state guard (`row.status != "unreviewed"` → 400) on the action endpoints.
   - Dispatch to `dismiss_mention` / `promote_mention` from `app/db/llm_mention_store.py`.
   - `assert out is not None` on the post-action store calls (defensive — the row was just verified, so the store should always return).
   - `model_validate(out)` to convert ORM → Pydantic response.

The promote handler is the longest by far (~30 lines): it composes `ContributionCreate` from `MentionPromoteBody` fields one-for-one, wraps Pydantic validation in `try/except ValidationError`, calls `create_contribution`, schedules the background task, and finally `promote_mention` to flip status.

## Conventions

**Cookie auth via duplicated `require_admin`.** Same dependency as `admin_contributions_route`; copy of the same six-line function. Consolidating into `app/admin/auth.py` is a small refactor whenever both files are edited together.

**`unreviewed`-only actions.** Both dismiss and promote raise 400 if the mention isn't in `unreviewed` status. The state machine is `unreviewed → promoted` or `unreviewed → dismissed`; no other transitions are supported. The HTML surface enforces the same gate; the JSON API rejects directly.

**Promote creates a Contribution, not a Provider/Program/Event directly.** The mention promotion is the second-to-last step of the catalog seed flow: a Contribution row enters the operator review queue, then the contribution-review path approves it into a Provider/Program/Event. Going straight to a catalog row would skip the human-review gate.

**`source="llm_inferred"` is the discriminator.** Distinguishes promoted mentions from `source="user_submission"` (public form) and `source="admin"` (direct admin create) in downstream queries and analytics.

**`assert out is not None`.** After verifying the row exists, the store call should always return. The `assert` makes the no-None assumption explicit for the type checker and catches regressions early.

**`_parse_day_bounds` raises HTTPException, not ValueError.** The helper is FastAPI-aware on purpose; the alternative (raise `ValueError` and let the handler convert) duplicates effort across two list endpoints. Other modules following the same pattern should pick one and stick with it.

**Status filter alias.** Same `?status=` alias as `admin_contributions_route.py` for the same reason — avoiding the `fastapi.status` shadow.

## Known limitations and design notes

**Pairs with the HTML surface.** This route is not the operator's primary review path; `app/admin/mentions_html.py` is. The JSON API exists for programmatic clients and any HTML buttons that POST via XHR.

**`_parse_day_bounds` is naive datetime.** No timezone handling. The mention scanner writes `detected_at` as naive UTC; the filter implicitly assumes that. If a future caller passes timezone-aware datetimes, the comparison is implicitly UTC-equivalent.

**Promote's contribution-create + mention-flip is two database commits.** `create_contribution` commits inside the store; `promote_mention` commits separately. A failure between the two would leave a `Contribution` row with no `LlmMentionedEntity` reference. Acceptable: the contribution would still flow through review on its own merits; the mention's continued `unreviewed` status would prompt re-review (and either re-promotion or dismissal).

**No pagination metadata.** Same posture as `admin_contributions_route` — the list endpoint returns rows; clients infer `more` from slice fullness. Total counts are not currently exposed.

**No bulk operations.** Each dismiss / promote operates on a single mention.

**`require_admin` duplication.** Two-file copy-paste with `admin_contributions_route`. Both are small enough that consolidation hasn't been forcing — the duplication is visible and intentional, not lurking.

**No CSRF token, no rate limit.** Same posture as the rest of the admin surface.

**Promote's URL guard duplicates schema enforcement.** The route checks `submission_url is None` for provider/program before constructing `ContributionCreate`. If `MentionPromoteBody` schema enforces the same, the route's check is defensive (and surfaces a more route-readable 422 message than Pydantic's would). Removing the route check on the assumption that the schema covers it is a small refactor — verify schema invariants first.

## Configuration

No environment configuration. `ADMIN_PASSWORD` is documented under `admin_auth.md`.

## Related

**Direct callers:** `app/main.py` mounts the router.

**Direct dependencies:**

- `app/admin/auth.py` — `COOKIE_NAME`, `verify_admin_cookie`.
- `app/db/llm_mention_store.py` — `dismiss_mention`, `get_mention`, `list_mentions`, `promote_mention`.
- `app/db/contribution_store.py` — `create_contribution` (called from the promote handler).
- `app/contrib/enrichment.py` — `enrich_contribution` (background task on promote).
- `app/db/database.py` — `SessionLocal` (background-task factory), `get_db`.
- `app/schemas/contribution.py` — `ContributionCreate` (composed by promote).
- `app/schemas/llm_mention.py` — `LlmMentionResponse`, `MentionDismissBody`, `MentionPromoteBody`.

**Cross-references:**

- `docs/components/admin_mentions_html.md` — the HTML pair: operator review forms, dismiss reason picker, pre-filled promote form.
- `docs/components/admin_auth.md` — cookie threat model and login flow.
- `docs/components/llm_mention_store.md` — store-layer helpers this route dispatches to.
- `docs/components/mention_scanner.md` — upstream extraction that creates `LlmMentionedEntity` rows.
- `docs/components/enrichment.md` — what `enrich_contribution` does on the background-task side after a promotion.
- `docs/components/schema_llm_mention.md` — request/response Pydantic shapes.
- `docs/components/admin_contributions_route.md` — sibling JSON API with mirror structure.
- `docs/maintainability/http_api.md` — full admin JSON API inventory.
- `docs/maintainability/end_to_end_creation.md` — Path 3 (Tier 3 mention scan promotion) flows through this route.
