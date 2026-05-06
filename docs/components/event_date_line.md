# event_date_line

`app/contrib/event_date_line.py` (~81 lines)

## Purpose

Pure helper to parse **River Scene–style “Date:” lines** embedded in submission notes: a single calendar day or a **same-month multi-day range** (`May 8–10, 2026`). Returns a **`(start_date, end_date_or_None)`** tuple for downstream event modeling. Cross-cutting ingestion utilities (`river_scene` normalization, contribution notes) can reuse this without hitting the DB.

## Public surface

**`parse_event_date_line(line: str) -> tuple[date, date | None] | None`** — Accepts either the **full line** (including optional leading `Date:` / `date:`) or the bare value; **`_strip_date_prefix`** normalizes. Returns:

- **`(start, None)`** — single-day event.
- **`(start, end)`** — inclusive end date when **`start < end`**; when **`start == end`**, normalizes to **`(start, None)`**.
- **`None`** — unparseable, invalid calendar date, reversed range, **cross-month** phrases, or unsupported multi-segment lines.

Internal helpers **`_month_num`**, **`_strip_date_prefix`** are module-private.

## Inputs and outputs

**Input:** one string line (may include whitespace/newlines at edges after strip).

**Output:** Python **`date`** pair as described above.

**Regex contracts.**

- **Single:** `Month DD, YYYY` with English full month name (via **`calendar.month_name`** lookup).
- **Range:** `Month DD1 – DD2, YYYY` where the separator is en-dash, ASCII hyphen, or em-dash between **day numbers** in the **same** month/year.

## Internal structure

1. **`_RANGE_SEP`** — Character class for dash variants inside the range pattern.
2. **`_SINGLE`** / **`_RANGE`** — Compiled **`re`** patterns anchored to the whole trimmed core string.
3. **`_month_to_index`** — Lowercased English month name → 1–12 index.

No I/O, no logging.

## Conventions

**English month names only.** Matches **`calendar.month_name`** tokens (case-insensitive after lowercasing).

**Explicit rejection of cross-range formats** — e.g. two full dates separated by a dash; covered by tests returning **`None`**.

## Known limitations

**No production caller wired at doc time** beyond tests — module is ready for note-derived date extraction; **`grep`** shows usage confined to **`tests/test_event_date_line.py`**.

**Survey reference in docstring** points to **`docs/multiday-events-step5a-survey-report.md`** — file may not exist on current **`main`**; treat as historical pointer or recover via **`git log -- <path>`**.

**Locale / i18n** — US-style month-first phrases only.

## Configuration

None.

## Related

- **`docs/components/river_scene.md`** — primary RS ingestion context where date lines matter conceptually.
- **`tests/test_event_date_line.py`** — exhaustive edge cases (dash variants, invalid ranges, case-insensitive `Date:`).
