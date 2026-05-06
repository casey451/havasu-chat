# confabulation_invoker

`app/eval/confabulation_invoker.py` (~150 lines)

## Purpose

Provides invocation strategies for confabulation evaluation probes, abstracting how a `Probe` is executed and normalized into a common `InvocationResult` payload. Supports:

- **In-process mode**: direct `unified_router.route(...)` call with Tier 2 evidence capture.
- **HTTP mode**: `POST /api/chat` request against a deployed base URL (degraded; no evidence rows).

This module is the harness bridge between generated probe inputs and detector/report consumers.

## Public surface

**`InvocationResult` (dataclass, slots)** — Unified per-probe execution record:
- `response_text: str`
- `evidence_row_dicts: list[dict[str, Any]]`
- `tier_used: str | None`
- `latency_ms: int`
- `raw_log: dict[str, Any]`
- `error: str | None = None`

**`Invoker` (Protocol)** — Strategy interface:
- `invoke(self, probe: Probe, flag_state: str) -> InvocationResult`

**`InProcessInvoker`** — Calls `unified.route` in-process:
- constructor: `session_id: str = "confab-eval"`
- captures Tier 2 evidence via `confabulation_evidence.install()/consume_last_evidence()/restore()`

**`HttpInvoker`** — Calls deployed API endpoint:
- constructor: `base_url`, `timeout_sec=30.0`, `session_id="confab-eval"`
- uses `requests.post(.../api/chat, json={"query","session_id"})`

**Note on `InvocationResult` naming:** `app/eval/confabulation_detector.py` also defines an `InvocationResult` dataclass, but with a narrower detector-input shape (`http_degraded`, `is_http_mode` instead of `tier_used`, `latency_ms`, `raw_log`, `error`). The harness pipeline must adapt invoker output into detector input; see `scripts/confabulation_eval.py` for the bridge.

## Inputs and outputs

**Inputs.**
- `Probe` from `confabulation_query_gen`.
- `flag_state`: `"on"` or `"off"` (router flag state).
- In HTTP mode: reachable base URL.

**Outputs.**
- Always returns `InvocationResult`.
- Errors are encoded in `error` string (`route_error:*`, `http_error:*`, `http_status:*`) rather than raised.

## Internal structure

### Router flag handling

- `_set_router_flag(flag_state)` sets `USE_LLM_ROUTER` env to `1` or `0`, returns prior value.
- `_restore_router_flag(prior)` restores prior env state (or unsets when originally absent).
- Both invokers wrap execution in `try/finally` to guarantee restoration.

### In-process flow (`InProcessInvoker.invoke`)

1. Set router flag.
2. Start latency timer.
3. `confabulation_evidence.install()`.
4. Open DB session (`SessionLocal`), call `unified.route(probe.query_text, session_id, db)`.
5. On route exception: return `InvocationResult(error="route_error:...")`.
6. Consume captured evidence snapshot (`consume_last_evidence`).
7. Return successful `InvocationResult` with response/tier/chat_log_id metadata.
8. Finally: `confabulation_evidence.restore()` and restore env flag.

### HTTP flow (`HttpInvoker.invoke`)

1. Set router flag.
2. Start timer.
3. `requests.post` to `/api/chat`.
4. On transport exception: return `error="http_error:..."`.
5. Parse JSON body best-effort (fallback to raw text).
6. On `status_code >= 400`: return `error="http_status:<code>"`.
7. Return success with response/tier from body; evidence rows always empty.
8. Finally: restore env flag.

## Conventions

**Error-as-data.** Invokers do not raise on expected runtime failures; they return structured error strings for downstream aggregation.

**Minimum latency floor.** `latency_ms` uses `max(1, int(...))` so zero-ms artifacts do not appear in reports.

**Flag restoration discipline.** Every invocation restores `USE_LLM_ROUTER` even on exceptions.

**Degraded HTTP evidence model.** HTTP mode intentionally emits `evidence_row_dicts=[]`; detector/report logic must account for this path.

## Configuration

- `USE_LLM_ROUTER` env is toggled per-invocation.
- HTTP mode uses:
  - `base_url` constructor arg
  - `timeout_sec` constructor arg (default 30s)
  - `session_id` constructor arg

## Known limitations and design notes

**Global env mutation.** Router-flag toggling is process-global; concurrent harness runs in same process can interfere.

**No retry/backoff in HTTP mode.** Transport errors fail immediately into `error` field.

**Evidence capture only for in-process mode.** HTTP mode cannot inspect Tier 2 formatter rows without separate instrumentation.

**Raw log shape differs by mode.** In-process success includes probe/flag/chat_log_id; HTTP success includes status/body.

## Related

**Direct callers:**
- `scripts/confabulation_eval.py`.
- `tests/test_confabulation_invoker.py`.

**Direct dependencies:**
- `app.eval.confabulation_query_gen.Probe`
- `app.eval.confabulation_evidence`
- `app.chat.unified_router`
- `app.db.database.SessionLocal`
- `requests`

**Cross-references:**
- `app/eval/confabulation_detector.py`
- `app/eval/confabulation_report.py`
