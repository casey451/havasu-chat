# admin_mentions_html

`app/admin/mentions_html.py` (~459 lines)

## Purpose

Cookie-gated **HTML UI for LLM-mentioned entities** (Tier 3 title-case candidates): list with filters, detail view with source message, **promote** (create a `Contribution` + enqueue enrichment), and **dismiss** with a structured reason. This is the human half of **Path 3** in `end_to_end_creation.md`; extraction from assistant text happens upstream.

## Public surface

**`register_mentions_html_routes(router: APIRouter) -> None`** — Registers:

| Route | Method | Role |
|-------|--------|------|
| `/mentioned-entities` | GET | Filterable list + pagination + optional flash query params |
| `/mentioned-entities/{mention_id}` | GET | Detail + linked `ChatLog` excerpt when present |
| `/mentioned-entities/{mention_id}/promote` | GET | Pre-filled promote form |
| `/mentioned-entities/{mention_id}/promote` | POST | Validates form → `ContributionCreate` → `create_contribution` → `promote_mention` → redirect with flash |
| `/mentioned-entities/{mention_id}/dismiss` | GET | Reason picker |
| `/mentioned-entities/{mention_id}/dismiss` | POST | Validates reason → `dismiss_mention` → redirect |

Paths are under the shared `/admin` prefix from the mounted router.

## Inputs and outputs

**List GET query params:**

- **`status`** — `unreviewed` \| `promoted` \| `dismissed` \| `all` (invalid → `unreviewed`).
- **`detected_from` / `detected_to`** — Optional `YYYY-MM-DD`; parsed to day-start / day-end `datetime`. Bad format → **422** `HTTPException`.
- **`limit`** — 1–200 (default 50), **`offset`** — ≥0.
- **`flash` / `kind`** (alias `flash_kind`) — Flash banner after redirect (`ok` vs error styling).

**Data layer:** Delegates to **`app.db.llm_mention_store`**: `list_mentions`, `count_mentions`, `get_mention`, `promote_mention`, `dismiss_mention`.

**Promote POST:** Builds **`ContributionCreate`** with `source="llm_inferred"` and `llm_source_chat_log_id` from the mention row; **`BackgroundTasks.add_task(enrich_contribution, contrib.id, SessionLocal)`** schedules enrichment after commit.

**Dismiss POST:** Reason must be one of **`DismissalReason`** literals (`typing.get_args` drives both dropdown HTML and validation).

## Internal structure

1. **`_guard` / `_esc`** — Standard admin patterns.

2. **`_fmt_compact_ts`** — Short human timestamp for list rows.

3. **`_catalog_hint_pill`** — **Non-authoritative** substring check against all `Provider.provider_name`, `Program.title`, and `Event.title` (loads full name lists per request). Renders a colored pill: possible overlap vs no hit vs “?” for short strings.

4. **`_mention_status_pill`** — Maps mention status to pill CSS classes.

5. **`_nav_shell`** — Full page wrapper + **`admin_phase5_nav_html()`**.

6. **Route closures** — Inline HTML for filters, tables, forms; flash via query-string `quote()` on redirect targets.

## Conventions

**Unreviewed-only actions.** Promote/dismiss GET+POST paths return 400 HTML if `status != "unreviewed"`.

**Provider/program URL rule.** POST promote requires non-empty URL when `entity_type` is `provider` or `program`.

**Cross-session factory.** Promotion uses **`SessionLocal`** for the background enrichment task (same pattern as other enqueue paths).

## Known limitations

**`_catalog_hint_pill` scales poorly** — Selects all catalog names each call; fine for small catalogs, costly if tables grow huge.

**No CSRF tokens** — Matches single-admin model documented under `admin_router.md`.

## Configuration

Cookie auth per **`admin_auth.md`**; DB via **`get_db`**.

## Related

- **`docs/components/mention_scanner.md`** — Upstream scan → `LlmMentionedEntity` rows consumed here.
- **`app/db/llm_mention_store.py`** — Persistence API.
- **`app/contrib/enrichment.py`** — `enrich_contribution` background task.
- **`app/schemas/llm_mention.py`** — `DismissalReason`.
- **`docs/components/admin_contributions_html.md`** — Reviews contributions created from promotions.
- **`app/api/routes/admin_mentions.py`** — JSON API parallel surface (`docs/maintainability/http_api.md`).
