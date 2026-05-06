# timezone

`app/core/timezone.py` (~27 lines)

## Purpose

Lake Havasu City wall-clock helpers using **`ZoneInfo("America/Phoenix")`**. Arizona does not observe daylight saving time; **`America/Phoenix`** is effectively **UTC−7 year-round**, which matters for “today”, Tier 2 parser date context, Tier 3 user payloads, and Tier 1 calendar logic.

## Public surface

**`LAKE_HAVASU_TZ`** — **`ZoneInfo`** instance shared conceptually with Places/hours code paths ( **`hours_helper`** defines its own compatible zone object for older fallbacks).

**`now_lake_havasu() -> datetime`** — Current aware **`datetime`** in **`LAKE_HAVASU_TZ`**.

**`format_now_lake_havasu(dt=None) -> str`** — Human-readable stamp for Tier 3 wiring, e.g. **`Tuesday, April 21, 2026, 2:47 PM`** (12-hour clock, no leading zero on hour).

## Inputs and outputs

**`format_now_lake_havasu`** accepts optional **`dt`**; when **`None`**, uses **`now_lake_havasu()`**.

Output string is English weekday/month names via **`strftime`** plus a **manual leading-zero strip** on the hour portion for Windows compatibility (**`%-I`** is Unix-only and unreliable on Windows).

## Internal structure

1. **`strftime("%A, %B %d, %Y, %I:%M %p")`** builds **`date_part, time_part`** split on last **`", "`**.
2. If **`time_part`** begins with **`0`** followed by a digit, drop the leading **`0`** (so **`09:05 AM`** → **`9:05 AM`**).

## Conventions

**Prefer `now_lake_havasu()` for “today” in chat tiers** rather than UTC **`datetime.utcnow()`** — Backlog #3’s year inference for undated calendar phrases relies on parser-local date strings derived from this timezone (**`docs/BACKLOG.md`** Backlog #3 closure cites **`tier2_parser`** prepending **`today_iso`** from **`now_lake_havasu().strftime("%Y-%m-%d")`**).

## Known limitations and design notes

**Not every module imports from here.** **`tier2_db_query`** uses **`hours_helper.LAKE_HAVASU_TZ`** + a local **`_now_lake_havasu`** for OPEN_NOW-style comparisons — two sources of truth for “Lake Havasu local now” exist by historical import paths.

**Formatter locale** is implied English (**`strftime`**/Locale C); no i18n.

## Configuration

None — zone is fixed to **`America/Phoenix`**.

## Related

**Direct callers:**

- **`app/chat/tier2_parser.py`** — **`today_iso`** for prompt prepend.
- **`app/chat/tier3_handler.py`**, **`app/chat/unified_router.py`** — **`format_now_lake_havasu`** / **`now_lake_havasu().date()`** in user/system assembly.
- **`app/chat/tier1_handler.py`** — **`now_lake_havasu()`** for date windows and OPEN_NOW paths.

**Cross-references:**

- **`docs/BACKLOG.md`** Backlog #3 — undated calendar query year grounding.
- **`docs/components/hours_helper.md`** — parallel **`LAKE_HAVASU_TZ`** usage.
