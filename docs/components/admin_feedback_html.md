# admin_feedback_html

`app/admin/feedback_html.py` (~218 lines)

## Purpose

Operator-facing **Tier 3 feedback analytics** page: aggregates thumb-up / thumb-down signals stored on `ChatLog` rows and lists recent negative examples for qualitative review. Complements the public feedback POST on the chat API — this module only reads and renders.

## Public surface

**`register_feedback_html_routes(router: APIRouter) -> None`** — Registers:

- **`GET /feedback`** — Query parameter **`window`** ∈ `7d` | `30d` | `all` (default `7d`). Invalid values fall back to `7d`.

## Inputs and outputs

**Auth:** Same cookie gate as other admin HTML (`verify_admin_cookie` + `COOKIE_NAME`); unauthenticated → redirect `/admin/login`.

**Summary section:** SQL aggregation grouped by `ChatLog.mode` and `ChatLog.sub_intent`:

- Restricted to **`tier_used == "3"`** (Tier 3 turns only).
- If `window` is `7d` or `30d`, adds `created_at >= cutoff` (UTC now minus 7 or 30 days); `all` omits the date filter.
- Columns per row: total Tier 3 count, sum of positives, sum of negatives, derived **feedback rate** (rated ÷ total) and **positive rate** (positives ÷ rated, or em dash if rated is zero).

**Recent negatives:** Second query selects up to **25** rows where `tier_used == "3"` and `feedback_signal == "negative"`, ordered by `created_at` descending. Displays timestamp, mode/sub-intent, truncated query text (`normalized_query` preferred else `message`), truncated response snippet, and `chat_log_id`.

**Response:** `HTMLResponse(_nav_shell("Feedback", inner))` with window toggle links (`_window_links`) that flip `?window=`.

## Internal structure

- **`_WINDOW_DAYS`** — Maps `7d`/`30d` to integer days; `all` → `None` (no cutoff).
- **`_guard`, `_esc`** — Same patterns as `categories_html` / `mentions_html`.
- **`_fmt_dt`** — Strips tzinfo for display if present, formats as `"%b %d, %Y %I:%M %p"`.
- **`_pct`, `_snippet`** — Small helpers for percentages and ellipsis truncation in tables.
- **`_window_links(active)`** — Renders pill-style links for the three windows.
- **`_nav_shell`** — Shared document wrapper including **`admin_phase5_nav_html()`**.

## Conventions

**Tier 3 scope is explicit in SQL.** Summary and negatives both filter `tier_used == "3"`; Tier 1/2 feedback (if any) does not appear here.

**Display normalization:** `_fmt_dt` drops timezone for a consistent naive display string — acceptable for an internal dashboard.

## Known limitations

**No CSV export or pagination** on the summary table — full grouped result set is rendered.

**Negative sample cap is fixed at 25** — not configurable via query params.

## Configuration

Database session via **`Depends(get_db)`**; auth env vars per **`admin_auth.md`**.

## Related

- `app/api/routes/chat.py` — consumer path that records feedback onto `ChatLog` (this module reads it back).
- `docs/components/admin_nav_html.md`, `docs/components/admin_router.md`.
- **`tests/test_admin_feedback.py`** — exercises feedback persistence on `ChatLog`; this module is display-only.
