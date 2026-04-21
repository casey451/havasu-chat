# Phase 6.2.3 — Admin feedback analytics view report

## Scope completed

Implemented a new admin feedback analytics page at `GET /admin/feedback` with:

- Cookie guard via `_guard()` and `/admin/login` redirect.
- `window` query param support: `7d`, `30d`, `all` (invalid/missing falls back to `7d`).
- Tier-3-only summary grouped by `(mode, sub_intent)`:
  - `total`
  - `positive` (`feedback_signal == "positive"`)
  - `negative` (`feedback_signal == "negative"`)
  - `feedback_rate = (positive + negative) / total`
  - `positive_rate = positive / (positive + negative)`
- Recent negatives list (latest 25), not window-filtered.
- Empty states:
  - "No Tier 3 responses in this window."
  - "No negative feedback yet."
- `positive_rate` denominator-zero handling renders `—`.

Exact filter contract used: `"positive"` and `"negative"` only.

## Files changed

### New

- `app/admin/feedback_html.py`
  - Added `register_feedback_html_routes(router)`.
  - Added page rendering, summary query, recent negatives query, and window links.
- `tests/test_admin_feedback.py`
  - Added route/auth, empty-state, grouped summary/negatives, window behavior, and invalid-window fallback tests.
- `docs/phase-6-2-3-admin-feedback-view-report.md`
  - This delivery report.

### Modified

- `app/admin/router.py`
  - Imported and registered `register_feedback_html_routes(router)`.
  - Added `Feedback` tab link after `Analytics` in router-level admin tab shells.

## Line delta (implementation files)

- `app/admin/feedback_html.py`: +195
- `tests/test_admin_feedback.py`: +138
- `app/admin/router.py`: +5 / -0
- **Total**: +338 / -0 (plus this report file)

## Test runs

Required interpreter used throughout:

```powershell
.\.venv\Scripts\python.exe -m pytest ...
```

### Focused new tests

```text
.\.venv\Scripts\python.exe -m pytest tests/test_admin_feedback.py -q
....                                                                     [100%]
4 passed in 1.93s
```

### Full suite

```text
.\.venv\Scripts\python.exe -m pytest -q
...
679 passed in 14.65s
```

## STOP triggers

No STOP triggers were hit:

- `feedback_signal` contract remained `positive` / `negative` (local data currently mostly `NULL`).
- `created_at` conventions were consistent with existing admin usage.
- Response snippet source is straightforward from `ChatLog.message` (assistant response text).
- Auth pattern matched existing admin tests (`POST /admin/login` with `changeme` in tests).

## Rendered page behavior summary

### Empty / near-empty data

- Summary section renders a clear no-data message:
  - **"No Tier 3 responses in this window."**
- Recent negatives table renders:
  - **"No negative feedback yet."**
- Rates with zero denominator display `—` (not `0%`/`NaN%`).

### Populated data

- Summary table appears with one row per `(mode, sub_intent)` group.
- Counts and rates compute from Tier-3 rows only.
- Recent negatives shows newest negative feedback rows (up to 25), including:
  - created timestamp
  - mode/sub-intent
  - query snippet (normalized query fallback behavior)
  - response snippet
  - chat log ID (plain text; no `/admin/chat_logs/<id>` route exists).

## Out-of-scope note (as requested)

Only router-level nav tabs were updated. No nav updates were made inside
`contributions_html`, `mentions_html`, or `categories_html` shells.
Cross-module nav consistency cleanup remains a follow-up item.
