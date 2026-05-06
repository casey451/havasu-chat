# event_recurrence

`app/core/event_recurrence.py` (~68 lines)

## Purpose

Lightweight **regex/string heuristics** to infer whether catalog copy reads like a **recurring** event (farmers markets, weekly series, etc.). Used when approving **`Contribution`** → **`Event`** rows so **`is_recurring`** can be set without LLM inference. Not semantic parsing — substring + bounded word-boundary checks only.

## Public surface

**`event_text_blob(title, description, tags | None) -> str`** — Lowercases **`title`**, **`description`**, and tag strings; joins with spaces into one searchable blob.

**`is_recurring_heuristic(text_blob: str) -> bool`** — Returns **`True`** if either tier hits:

1. **Phrase tier:** any of **`_RECURRENCE_PHRASES`** appears as a **substring** (multi-word cues such as **`every saturday`**, **`farmers market`**, **`first friday`**).
2. **Token tier:** any token in **`_TOKENS`** matches via **`_word_pat`** — **whole-word**, case-insensitive (`(?<!\w)...(?!\w)`), so **`regular`** does **not** match inside **`irregular`**.

**`is_recurring_from_event_model(event) -> bool`** — Convenience wrapper reading **`title`**, **`description`**, **`tags`** via **`getattr`** / list coercion, then **`is_recurring_heuristic(event_text_blob(...))`**.

## Inputs and outputs

**Blob input** should already be lower-case tolerant — internally **`lower()`** again.

**`event`** may be a SQLAlchemy **`Event`** or duck-typed object with the three attributes.

## Internal structure

**`_word_pat(word)`** escapes the literal token and wraps ignore-case boundary-aware regex.

**Curated sets** (`_RECURRENCE_PHRASES`, **`_TOKENS`**) are module constants — tuning recurrence sensitivity means editing these lists.

## Conventions

**Phrase tier uses substring containment** — can false-positive if unrelated prose mentions **`farmers market`** in passing; operator review remains the safety net.

## Known limitations and design notes

**English-centric literals.** Non-Spanish/other-language recurrence wording won't hit unless added.

**No RRULE / ICS semantics.** Does not compute concrete recurrence schedules — only flags **`Event.is_recurring`** style booleans during ingestion.

## Configuration

None.

## Related

**Direct callers:**

- **`app/contrib/approval_service.py`** — builds blob from contribution-ish titles/descriptions/tags when approving events.

**Tests:**

- **`tests/test_phase8_9_event_ranking.py`** — blob/heuristic expectations.

**Cross-references:**

- **`docs/components/approval_service.md`** — approval pipeline context.
