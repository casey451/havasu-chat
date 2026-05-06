# admin_contributions_html

`app/admin/contributions_html.py` (~817 lines)

## Purpose

Primary **HTML contribution-review surface** (Phase 5.3): lists pending (and filtered) `Contribution` rows, shows rich detail including URL-fetch and Places enrichment blobs, and walks operators through **approve** (entity-specific forms), **reject** (reason + notes), and **needs info** flows. This module is the **form and rendering layer**; catalog writes go through **`app/contrib/approval_service.py`** and **`contribution_store.update_contribution_status`**.

## Public surface

**`register_contribution_html_routes(router: APIRouter) -> None`** — Attaches routes under the shared admin router (prefix `/admin`). High-level map:

| Route | Methods | Role |
|-------|---------|------|
| `/contributions` | GET | Filterable list + pagination + flash params |
| `/contributions/{id}` | GET | Detail, enrichment panels, action buttons when `pending` |
| `/contributions/{id}/approve` | GET | Entity-specific approve form (provider / program / event) |
| `/contributions/{id}/approve` | POST | Parses `Form` fields → Pydantic approval structs → `approve_contribution_as_*` |
| `/contributions/{id}/reject` | GET / POST | Reason (`RejectionReason`) + optional notes → status update |
| `/contributions/{id}/needs-info` | GET / POST | Required review notes → `needs_info` status |

The detail page also embeds a **POST form to `/admin/api/contributions/{id}/enrich`** (JSON router) to re-run enrichment — HTML posts without JSON; behavior lives in the API module.

## Inputs and outputs — list

**Query params:** `status` (`pending`|`approved`|`rejected`|`needs_info`|`all`), optional `entity_type`, optional `source`, `limit` (1–200), `offset`, `flash` + `kind`.

**Data:** `list_contributions` / `count_contributions` from **`contribution_store`**.

**Rendering:** Table of submitted time, entity pill, linked name, status pill, source, URL-fetch summary string, Places summary string.

## Inputs and outputs — detail

**Enrichment panel** merges:

- URL fetch fields (`url_fetch_status`, `url_title`, etc.).
- **`google_enriched_data`** dict when present — formatted addresses, hours via **`_format_opening_hours`** (supports `weekdayDescriptions` or `periods` shapes), errors.

**Actions when `status == pending`:**

- **Tips:** Approve button replaced with disabled explanatory control — tip approval not implemented in this phase; operators use Needs Info.
- **Other entity types:** Links to approve/reject/needs-info plus enrich POST button.

Non-pending contributions show review metadata and created provider/program/event IDs.

## Inputs and outputs — approve

**GET** validates `pending` and entity type; tips get a 400 explanatory page. Forms are hand-built HTML:

- **Provider:** name, address, phone, hours textarea, description (required), website, category (required, **`datalist`** fed by **`_merged_category_suggestions`** = union of distinct `Provider.category` and `Program.activity_category`).
- **Program:** title, description (min length 20), age min/max optional ints, schedule days (comma-separated, default `monday`), **start/end time text fields** with HTML `pattern` enforcing `HH:MM`, location fields, cost, provider/contact fields, tags, activity category (datalist, required).
- **Event:** title, description (min 20), date, start/end time inputs, location name, event URL, tags.

**POST** collects a **wide `Form(...)` signature** — many parameters optional because only one entity branch runs. Branch logic:

1. **`provider`** → **`ProviderApprovalFields`** → **`approve_contribution_as_provider(db, id, pf, category)`**.
2. **`program`** → Parses ages via small `_opt_int`, **`schedule_days`** via **`parse_schedule_days_field`**, tags via **`parse_comma_tags`**, builds **`ProgramApprovalFields`** (including **`schedule_start_time` / `schedule_end_time` strings** defaulting to `09:00` / `17:00` when omitted) → **`approve_contribution_as_program(db, id, pr, category)`**. This is the **`ProgramApprovalFields` writer path** called out in Slice 56 notes: the HTML layer supplies strings; **`ProgramCreate`** / ORM typing are **`approval_service`**’s concern.
3. **`event`** → Parses `event_date` ISO and `time.fromisoformat` for times → **`EventApprovalFields`** + tag list → **`approve_contribution_as_event`**.

On `ValueError` or **`ValidationError`**, returns 400 HTML with message and retry link.

Success → **303 redirect** to `/admin/contributions` with flash query string.

## Inputs and outputs — reject / needs-info

- **Reject:** GET builds `<select>` from **`get_args(RejectionReason)`** (not the older hard-coded tuple if schemas drift). POST validates membership then **`update_contribution_status(..., "rejected", ...)`**.
- **Needs info:** POST requires non-empty trimmed notes → **`update_contribution_status(..., "needs_info", ...)`**.

## Internal structure (helpers)

| Helper | Role |
|--------|------|
| `_guard`, `_esc` | Auth + XSS escaping |
| `_fmt_compact_ts`, `_ip_display` | Display utilities |
| `_places_dict`, `_places_status`, `_url_fetch_display` | Normalize / summarize enrichment |
| `_format_opening_hours` | Places hours JSON → readable text |
| `_distinct_*`, `_merged_category_suggestions` | Category datalist source |
| `_nav_shell` | Document wrapper + **`admin_phase5_nav_html()`** |
| `_status_pill`, `_entity_pill` | CSS pill fragments |
| Nested `_datalist_categories` inside register | `<datalist>` builder for approve forms |

## Conventions

**Same visual language as `router.py`** — Module docstring references matching inline HTML/CSS style.

**Escape responsibility:** User/submitter content flows through `_esc` at interpolation points; URLs in `<a href>` use `_esc` on attribute values.

**JSON/HTML split:** Listing and mutation APIs live under `/admin/api/*`; this file is browser-oriented GET/POST forms.

## Known limitations

**Tip entity type** cannot be approved through this UI (by design until a later phase).

**Large single file** — Dashboard/event flows remain in `router.py`; contributions stay isolated here but still ~800 lines.

**Reject GET fallback** — If `RejectionReason` schema changes, UI options track automatically via `get_args`; mismatched POST validation still guards.

## Configuration

**`ADMIN_PASSWORD` / cookie** per **`admin_auth.md`**; DB session via **`get_db`**.

## Related

- **`docs/components/approval_service.md`** — Canonical approval writes (`approve_contribution_as_provider/program/event`).
- **`app/schemas/contribution.py`** — `ProviderApprovalFields`, `ProgramApprovalFields`, `EventApprovalFields`, `RejectionReason`.
- **`app/db/contribution_store.py`** — List/get/count/status updates.
- **`docs/components/admin_router.md`**, **`admin_nav_html.md`**, **`admin_auth.md`**.
- **`docs/components/admin_mentions_html.md`** — Creates `llm_inferred` contributions reviewed here.
