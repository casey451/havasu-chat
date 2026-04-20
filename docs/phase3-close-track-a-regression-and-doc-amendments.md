# Phase 3-close — Track A regression + doc amendments (report)

## Task 1 — Track A 120-query regression battery

### Battery location (not pytest)

There is **no** pytest module that runs the 120-query battery. The contract runner is **`scripts/run_query_battery.py`**: it POSTs to Track A **`POST /chat`** on `BASE`, classifies responses, and prints JSON. Docs also reference `docs/query-test-battery.md` for expectations; `tests/fixtures/havasu_chat_test_queries.txt` is a **different** (concierge-style) fixture file (~80+ lines), not this battery.

### How it was run

`.\.venv\Scripts\python.exe scripts/run_query_battery.py` (same mechanism as `scripts/README.md`; **not** `pytest`).

### Results

| Metric | Value |
|--------|--------|
| **Total queries** | **120** (per JSON `"total"`) |
| **Pass** | **116** |
| **Fail** | **4** |
| **Pass rate** | **96.67%** |

### vs ~96% baseline

**96.67%** matches the documented baseline (`scripts/README.md`: 116/120 ≈ 96.67%). **Within** the “3 points below 96%” stop rule (that would be &lt;93%).

### Failures (expected vs actual)

Same pattern as **venue vs events** called out in `docs/project-handoff.md` (rows 22, 44, 46, 49):

| # | Query | Expected (acceptable labels) | Actual |
|---|--------|------------------------------|--------|
| 22 | `trampoline tonight` | `NO_MATCH` | `VENUE_REDIRECT` |
| 44 | `london bridge` | `VENUE_REDIRECT` | `EVENTS` |
| 46 | `lake havasu state park` | `VENUE_REDIRECT` | `EVENTS` |
| 49 | `aquatic center` | `VENUE_REDIRECT` | `EVENTS` |

No import/fixture errors; the battery completed successfully.

### History note

Did not diff git history on the runner; `project-handoff.md` already documents these rows as **intentional product precedence**, not new router regressions.

---

## Task 2 — Doc amendments (completed)

### `bbe17` replacements in `HAVASU_CHAT_CONCIERGE_HANDOFF.md`

**1** replacement:

- `https://web-production-bbe17.up.railway.app` → `https://havasu-chat-production.up.railway.app`

### §3.3 — before (sub-intents line)

```markdown
**Sub-intents:**
- `DATE_LOOKUP`, `TIME_LOOKUP`, `LOCATION_LOOKUP`, `COST_LOOKUP`, `PHONE_LOOKUP`, `HOURS_LOOKUP`, `WEBSITE_LOOKUP`, `AGE_LOOKUP`
```

### §3.3 — after

```markdown
**Sub-intents:**
- `DATE_LOOKUP`, `TIME_LOOKUP`, `LOCATION_LOOKUP`, `COST_LOOKUP`, `PHONE_LOOKUP`, `HOURS_LOOKUP`, `WEBSITE_LOOKUP`, `AGE_LOOKUP`, `NEXT_OCCURRENCE`, `OPEN_NOW`
```

### Commit

- **SHA:** `b3439bf`
- **Message:** `Phase 3-close: Canonical URL + Tier 1 sub-intent coverage (doc)`
- **Branch:** pushed to `main`

### Stale refs noticed, not changed (per scope)

- `scripts/run_query_battery.py` still sets `BASE = "https://web-production-bbe17.up.railway.app"` — updating it would be a **code** change, outside Task 2’s docs-only fence.
- Untracked `docs/` files (e.g. older smoke notes mentioning `bbe17`) were left untouched.
