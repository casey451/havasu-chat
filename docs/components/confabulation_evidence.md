# confabulation_evidence

`app/eval/confabulation_evidence.py` (~80 lines)

## Purpose

Harness-only monkeypatch seam that captures Tier 2 formatter evidence rows during in-process confabulation invocations. Replaces `app.chat.tier2_formatter.format` with a wrapper that snapshots `(query, rows)` and exposes a durable single-slot buffer retrievable after `unified.route(...)` returns.

This module enables detector Layer 1/2/3 comparisons without modifying production routing code paths.

## Public surface

**`tier2_evidence` (`ContextVar[tuple[str, list[dict]] | None]`)** — Per-context transient slot set inside wrapper execution.

**`install() -> None`** — Idempotently monkeypatches `tier2_formatter.format` with `_format_wrapper`.

**`restore() -> None`** — Idempotently restores original formatter function and clears captured state.

**`consume_last_evidence() -> tuple[str, list[dict[str, Any]]] | None`** — Returns and clears module-level `_last_captured` snapshot.

## Inputs and outputs

**Inputs.**
- Calls into patched `tier2_formatter.format(query, rows)`.
- External harness control via `install()/restore()/consume_last_evidence()`.

**Outputs / side effects.**
- Wrapper stores deep-ish copied row dicts (`[dict(r) for r in rows]`) in both:
  - transient contextvar (`tier2_evidence`)
  - durable module slot (`_last_captured`)
- Restores original formatter behavior after teardown.

## Internal structure

### Wrapper flow (`_format_wrapper`)

1. Copy incoming rows.
2. Set contextvar token with `(query, copy_rows)`.
3. Write durable `_last_captured`.
4. Call original formatter (`_original_format`).
5. In `finally`, reset contextvar token.

### Lifecycle management

- `install()`:
  - no-op if already installed
  - stores original callable in `_original_format` and `_format_restoration_ref`
  - clears `_last_captured`
  - patches `tier2_formatter.format`
- `restore()`:
  - no-op if not installed
  - restores original callable if ref exists
  - clears refs and `_last_captured`
  - flips `_installed=False`

### Snapshot consumption

- `consume_last_evidence()` is read-once: returns `_last_captured` then clears it.

## Conventions

**Harness-only module.** Not used by production request flow directly; invoked from eval harness in-process invoker.

**Idempotent install/restore.** Safe repeated calls reduce teardown fragility in error paths.

**Read-once durable slot.** Prevents stale evidence leakage across invocations.

**Copy rows before storing.** Defensive copy avoids post-capture mutation by downstream formatter logic.

## Configuration

No env vars. Behavior is entirely runtime/lifecycle driven by invoker calls.

## Known limitations and design notes

**Monkeypatch scope is global in-process.** Any concurrent code path using `tier2_formatter.format` during install window sees patched behavior.

**Single-slot capture model.** Last-write-wins design; unsuitable for concurrent multi-invocation runs without external synchronization.

**Shallow dict copy only.** `dict(r)` copies top-level keys; nested mutable values remain shared references.

**No persistence by itself.** Captured evidence exists only in memory unless caller serializes it downstream.

## Related

**Direct callers:**
- `app/eval/confabulation_invoker.py` (`InProcessInvoker`)
- `tests/test_confabulation_evidence.py`

**Direct dependencies:**
- `app.chat.tier2_formatter.format`
- `contextvars`

**Cross-references:**
- `app/eval/confabulation_detector.py`
- `app/eval/confabulation_report.py`
