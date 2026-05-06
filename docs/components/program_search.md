# program_search

`app/core/program_search.py` (~251 lines)

## Purpose

**Program-row retrieval + human-readable card formatting** for “how do I start … / ongoing classes” style queries (Session Z‑2). Designed as an **additive** path alongside dated **event** search: programs carry **`schedule_days`**, age bands, provider/cost fields unlike **`Event`** rows.

Shares **synonym expansion** with event search via **`expand_query_synonyms`** from **`app/core/slots.py`** (**`docs/components/slots.md`** lands in Slice **67b**).

## Public surface

**`search_programs(db, message, slots=None) -> list[Program]`**

1. Tokenizes **`message`** (`_query_tokens`) dropping stop words **`_STOP_TOKENS`**.
2. Pulls **`synonyms = expand_query_synonyms(message)`**.
3. Loads **active** programs (**`Program.is_active`**).
4. Optional age filter via **`_extract_age_from_query`** (regexes for **`N year old`**, **`N yrs`**, **`for N`**, etc.).
5. Scores each row (**`_score_program`**) as **`matched_tokens / len(tokens) + 0.1 * synonym_bonus`**; drops zero-score rows; sorts by **score DESC**, then title ASC.

**`format_program_results(programs) -> str`** — Returns **`PROGRAMS_NONE`** when empty; otherwise **`PROGRAMS_INTRO`** plus up to **five** **`_program_card`** blocks; surplus count summarized (“…and N more…”).

### Helpers (internal but load-bearing)

- **`_format_days`** — Orders weekday labels using **`_DAY_ORDER`**.
- **`_format_hhmm(t: time | None)`** — 12-hour **`9:05 AM`** style; tolerant **`None`**. Slice **54** (**Backlog #30** Phase 2) changed input contract from **`str`** **`HH:MM`** to **`datetime.time`** while preserving rendered shape (**`docs/maintainability/schema_time_harmonization_decision.md`** campaign context).
- **`_program_card`** — emoji-prefixed schedule line, title, optional age/cost meta, location, provider, optional trimmed description + contact line.

## Inputs and outputs

**`slots`** parameter accepted for API symmetry but **unused** inside **`search_programs`** at Slice **67a** — future hook for slot-aware narrowing.

## Internal structure

Scoring is **token overlap + synonym hits**, not embeddings — aligned with lightweight catalog scale assumptions.

## Conventions

**Depends on **`conversation_copy`** for program headings** — changing **`PROGRAMS_INTRO`** / **`PROGRAMS_NONE`** edits UX here without touching **`program_search.py`**.

## Known limitations and design notes

**No FastAPI imports found at Slice 67a audit** — module is implemented but **not wired** from **`unified_router`** / **`search.py`** yet; **`havasu-knowledge-base.md`** references **`_program_card`** / **`_extract_age_from_query`** as behavioral documentation. Treat as **staging surface** until a router branch calls **`search_programs`**.

## Configuration

None.

## Related

**Cross-references:**

- **`docs/components/conversation_copy.md`** — **`PROGRAMS_INTRO` / `PROGRAMS_NONE`**.
- **`docs/components/slots.md`** (Slice **67b**) — **`expand_query_synonyms`**.
- **`docs/components/models.md`** — **`Program`** ORM fields consumed here.
