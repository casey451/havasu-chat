# admin_categories_html

`app/admin/categories_html.py` (~115 lines)

## Purpose

Read-only **category discovery** dashboard for operators: shows how category-like strings are distributed in the live catalog versus pending contribution hints. No writes, no filters beyond what the SQL applies — three stacked tables with counts so admins can spot taxonomy drift before approving contributions.

## Public surface

**`register_categories_html_routes(router: APIRouter) -> None`** — Side-effect registration. Attaches one GET handler to the passed router:

- **`GET /categories`** — Cookie-gated HTML page (`HTMLResponse` or `RedirectResponse` to `/admin/login`).

There are no other exports intended for reuse.

## Inputs and outputs

**HTTP:** Unauthenticated requests redirect (302) to login. Authenticated requests take no query parameters; response is always `HTMLResponse` wrapping `_nav_shell("Categories", inner)`.

**Data:** All figures come from SQL aggregates in the request handler:

1. **Provider categories** — `Provider.category` grouped and counted for rows where `is_active` is true and `draft` is false, ordered by count descending.
2. **Program activity categories** — `Program.activity_category` with the same active/non-draft filter.
3. **Pending contribution hints** — `Contribution.submission_category_hint` grouped where `status == "pending"` and the hint is non-null and non-empty.

## Internal structure

Functional layout parallel to other Phase 5 admin HTML modules:

1. **`_guard(request)`** — Returns `None` if `verify_admin_cookie` succeeds on `COOKIE_NAME`; otherwise a `RedirectResponse` to `/admin/login`.

2. **`_esc(s)`** — `html.escape(..., quote=True)` for all interpolated user/database strings in markup.

3. **`_nav_shell(title, inner)`** — Full minimal HTML document with inline CSS and **`admin_phase5_nav_html()`** from `nav_html` injected above `inner`.

4. **`categories_page`** (nested inside `register_categories_html_routes`) — Runs the three `select(...).group_by(...)` queries, renders each via a small nested **`table(rows, col)`** helper (empty state → paragraph with class `empty`, else `<table>` with two columns).

## Conventions

**Register-on-router pattern.** Same as `contributions_html`, `mentions_html`, etc.: `router.py` imports this module and calls `register_categories_html_routes(admin_router)` so routes share one mount prefix.

**Escape discipline.** Category strings from the DB are passed through `_esc` inside table cells.

**No JSON counterpart here.** Operators who want programmatic access use other admin APIs documented in `http_api.md`; this module is HTML-only.

## Known limitations

**No time window or export.** Counts are snapshot-at-request; heavy tables could be slow on large catalogs.

**NULL categories appear as literal cells.** The SQL groups NULL `Provider.category` / `Program.activity_category`; the renderer uses `str(a)` for the first column.

## Configuration

Uses standard DB session via **`Depends(get_db)`** and **`ADMIN_PASSWORD` / cookie auth** like other admin HTML (see `admin_auth.md`).

## Related

- `app/admin/router.py` — mounts the admin router that registers these routes.
- `docs/components/admin_nav_html.md` — shared nav fragment.
- `docs/components/admin_router.md` — overview of admin route wiring.
- `docs/components/admin_contributions_html.md` — contribution review; `submission_category_hint` originates there on the submission side.
