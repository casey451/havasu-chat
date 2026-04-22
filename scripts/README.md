# Scripts

## 120-query production battery

- **`run_query_battery.py`** — POSTs each query to production `POST /chat`, classifies the reply, prints JSON `{ "total", "results" }` to stdout.
- **`battery_results.json`** — **Canonical baseline** for regression compares. As of Session AD (April 2026), this file matches the Session T final capture (**116 / 120** matches ≈ **96.67%** pass rate). After search/intent/slots/venues/seed/copy changes, re-run the battery and overwrite this file only when you intend to move the baseline.
- **`battery_session_t_final.json`** — Frozen historical capture from Session T (kept for archaeology and diffs). Other `battery_results_session_*.json` files in this folder are ad-hoc or session-specific snapshots; treat them as read-only history unless you are deliberately archiving a new run.

## Other utilities

- **`smoke_concurrent_chat.py`** — Phase 8.2 **local** concurrent smoke for `POST /api/chat` (8 threads × ~3 min default). Start `uvicorn` first; not a production or 50-user stress test. See module docstring.
- **`verify_queries.py`** — Short live spot-check against production.
- **`diagnose_search.py`** — Batch queries against the live app; may write `diagnose_output.txt` in this directory.
