# Phase 6.2.3 Pre-Scoping Report (Read-Only)

Date: 2026-04-21  
Scope: Admin analytics view for feedback signals

## A) Existing Admin Panel Architecture

### 1) File layout

Under `app/admin/`:
- `app/admin/__init__.py`
- `app/admin/auth.py`
- `app/admin/router.py`
- `app/admin/contributions_html.py`
- `app/admin/mentions_html.py`
- `app/admin/categories_html.py`

Under `app/api/routes/admin*.py`:
- `app/api/routes/admin_contributions.py`
- `app/api/routes/admin_mentions.py`

Admin templates:
- No admin template files found (no Jinja template directory/files).
- Admin pages are built as inline HTML strings returned from FastAPI handlers.

### 2) Existing admin pages requested

#### `/admin/contributions`
- **Route definition:** `app/admin/contributions_html.py` via `register_contribution_html_routes(router)` called from `app/admin/router.py`.
- **Template location:** none; inline HTML builders in `app/admin/contributions_html.py`.
- **Auth/session pattern:** cookie-gated via `_guard()` using `verify_admin_cookie(request.cookies.get("admin_session"))`; redirects to `/admin/login`.
- **Render style:** server-rendered HTML (no SPA/client app shell required).

#### `/admin/mentioned-entities`
- **Route definition:** `app/admin/mentions_html.py` via `register_mentions_html_routes(router)` called from `app/admin/router.py`.
- **Template location:** none; inline HTML builders in `app/admin/mentions_html.py`.
- **Auth/session pattern:** same `_guard()` + signed admin cookie.
- **Render style:** server-rendered HTML.

#### `/admin/categories`
- **Route definition:** `app/admin/categories_html.py` via `register_categories_html_routes(router)` called from `app/admin/router.py`.
- **Template location:** none; inline HTML builders in `app/admin/categories_html.py`.
- **Auth/session pattern:** same `_guard()` + signed admin cookie.
- **Render style:** server-rendered HTML.

### 3) Shared layout/nav/index

- There is **no single shared template engine/layout file** across all admin pages.
- There are repeated HTML “shell” helpers:
  - `app/admin/router.py`: nav tabs for core admin (`Queue`, `Pending events`, `Live events`, `Programs`, `Analytics`).
  - `app/admin/contributions_html.py`: `_nav_shell(...)` with `Admin home`, `Contributions`.
  - `app/admin/mentions_html.py`: `_nav_shell(...)` with `Admin home`, `Contributions`, `Mentioned entities`.
  - `app/admin/categories_html.py`: `_nav_shell(...)` with `Admin home`, `Contributions`, `Mentioned entities`, `Categories`.
- Admin entry/index behavior is `GET /admin` (tabbed events/programs dashboard) in `app/admin/router.py`.

---

## B) ChatLog Data Surface

### 1) `ChatLog` model (full definition)

From `app/db/models.py`:

- `id: str` (PK UUID string)
- `session_id: str` (indexed)
- `message: str`
- `role: str`
- `intent: str | None`
- `created_at: datetime`
- `query_text_hashed: str | None`
- `normalized_query: str | None`
- `mode: str | None`
- `sub_intent: str | None`
- `entity_matched: str | None`
- `tier_used: str | None`
- `latency_ms: int | None`
- `llm_tokens_used: int | None`
- `llm_input_tokens: int | None`
- `llm_output_tokens: int | None`
- `feedback_signal: str | None`

### 2) Groupable columns check

Confirmed present in model:
- `mode` ✅
- `sub_intent` ✅
- `tier_used` ✅
- `feedback_signal` ✅
- `created_at` ✅

No stop trigger hit (`feedback_signal` exists in model).

### 3) How existing admin views query DB

Mixed style, mostly SQLAlchemy:
- **ORM query API:** e.g., `db.query(...).filter(...).order_by(...).all()`
- **SQLAlchemy Core select/func:** e.g., `select(...)`, `group_by`, `func.count`, `func.lag`, `cast`, etc.
- **No raw SQL strings** in reviewed admin routes.
- **No separate analytics service layer** for admin analytics; query logic is in route/helper modules.

---

## C) Proposed Meaning of “Feedback Ratio per mode/sub-intent/over time”

### Recommended v1 for 6.2.3 (most useful, low complexity)

- **Primary view: Summary table** grouped by `(mode, sub_intent)` and time window.
- Filters:
  - Time scope toggle: `7d`, `30d`, `all`.
  - Restrict to `tier_used == "3"` rows for signal relevance.
- Columns:
  - `positive` (`feedback_signal == "up"`)
  - `negative` (`feedback_signal == "down"`)
  - `total Tier 3 responses` (all tier 3 rows, including null feedback)
  - `% with feedback` = `(positive + negative) / total_tier3`
  - `% positive of feedback` = `positive / (positive + negative)` (show `—` if denominator 0)

### Optional but worthwhile (still moderate)

- **Mini time series (daily, last 30d):**
  - `date`, `positive_count`, `negative_count`, optionally `feedback_total`.
  - Keeps trend visibility without chart libraries.

### Lower ROI for 6.2.3 baseline

- **Recent list of 50 with snippets** is useful for debugging quality, but adds:
  - snippet/truncation decisions
  - potential privacy/content exposure handling
  - more UI complexity
- Defer this to 6.2.4 unless explicitly required.

---

## D) Mount Point + Nav Integration Proposal

- Route should live at **`/admin/feedback`** in `app/admin/router.py` (same pattern as `/admin/analytics`).
- Auth should reuse existing `_guard()` cookie gate exactly.
- Nav integration:
  - Add a `Feedback` link in the core admin tab nav (the nav currently includes `Analytics`).
  - Optionally add `Feedback` link in `contributions_html`, `mentions_html`, and `categories_html` shells for consistent discoverability.

---

## E) Scope Fence Suggestion (for 6.2.3 implementation prompt)

### In scope
- Add server-rendered admin page at `/admin/feedback` (cookie-gated).
- Add SQLAlchemy aggregations from `chat_logs` for:
  - grouped summary by `mode` + `sub_intent`
  - time window toggle (`7d`, `30d`, `all`)
  - tier filter fixed to `tier_used == "3"`
  - counts and ratios listed above
- Add lightweight daily table (last 30d) of positive/negative counts.
- Add nav link(s) needed so owner can reach page.

### Out of scope
- No frontend app rewrite, JS charting libs, or SPA analytics dashboard.
- No schema/migration changes.
- No changes to feedback capture pipeline or thumbs bug.
- No backfill jobs.
- No export/download endpoints.
- No per-user/session drilldown or PII-heavy recent transcript tables.
- No auth redesign.

---

## Stop-Trigger Audit Notes

- **No admin routes exist at all:** not true; many admin routes exist.
- **ChatLog missing `feedback_signal`:** not true; present in model.
- **Sketchy auth pattern:** current admin auth is simple password + signed cookie using `ADMIN_PASSWORD`; no hardcoded production password found in code path.
  - Mild caution: `/admin/debug-pw` exists (returns only `pw_set`/`pw_length`, not secret). Not a blocker for 6.2.3, but avoid adding new debug-style endpoints in this phase.
