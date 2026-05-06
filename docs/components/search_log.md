# search_log

`app/core/search_log.py` (~86 lines)

## Purpose

**Operator-only diagnostic logging** for search internals. When **`SEARCH_DIAG_VERBOSE`** is enabled, structured lines append to **`search_debug.log`** at the **repository root** (resolved via **`os.path.join(os.path.dirname(__file__), "..", "..", ...)`** — **`app/core` → repo root**). Never user-visible; safe to ignore in production unless debugging relevance pipelines.

## Public surface

**`LOG_PATH`** — Absolute-ish relative path string pointing at **`search_debug.log`**.

**`is_search_diag_verbose() -> bool`** — **`True`** iff env **`SEARCH_DIAG_VERBOSE`** strips to lowercase **`true`**, **`1`**, or **`yes`**.

**`log_query(raw, intent, slots, strategy)`** — Writes **`=== SEARCH QUERY ===`** block with raw input, intent, JSON **`slots`**, strategy (**`date` objects JSON-encoded via `_j`** helper).

**`log_db_params(date_ctx, activity, keywords, audience, query_message)`** — Logs structured DB parameter snapshot.

**`log_candidates(query_text, scored)`** — Logs candidate **`Event`** list length plus top **10** **`(score, id, title, date)`** lines.

## Inputs and outputs

All **`log_*`** functions early-return when verbose flag false — **no file IO**.

When verbose: **`_ensure_file_handler`** attaches a **`logging.FileHandler`** exactly once (lazy singleton pattern keyed off **`_diag_file_handler_present()`**).

## Internal structure

- Logger **`search_diag`** at **`DEBUG`**, module-level.
- **`_j`** JSON serializer uses **`default=str`** with **`date.isoformat()`** handling.

## Conventions

**Std stdout diagnostics live separately.** **`emit_search_diag_embedding_block`** in **`search.py`** prints **`[search_diag]`** lines when verbose — not routed through this file.

## Known limitations and design notes

**`log_query` / `log_db_params` have no live call sites at Slice 67a audit** — only **`log_candidates`** is invoked ( **`search.py`** dynamic **`import search_log as _sl`**). Earlier instrumentation helpers remain available.

**Root-level log file** may accumulate credentials-bearing queries if operators paste secrets — treat **`SEARCH_DIAG_VERBOSE`** as privileged-debug posture.

## Configuration

- **`SEARCH_DIAG_VERBOSE`** — case-insensitive **`true` / `1` / `yes`** enables logging.

## Related

**Direct callers:**

- **`app/core/search.py`** — **`log_candidates`** after candidate merge.

**Tests:**

- **`tests/test_phase87_privacy.py`** — verbose predicate + skip/write behaviors.

**Cross-references:**

- **`docs/components/search.md`** (Slice **67b**) — overarching **`search.py`** behavior once documented.
