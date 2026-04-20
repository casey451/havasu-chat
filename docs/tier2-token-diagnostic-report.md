# Tier 2 token diagnostic — read-only investigation report

**Scope:** Investigation only — no code changes, no commits, no production writes. Local `events.db` used for row payloads; production `llm_input_tokens` taken from Phase 4.4 voice battery (`chat_logs`).

---

## Prompt sizes

- **tier2_parser.txt:** **745** tokens (UTF-8 bytes ÷ 4); **~850** tokens (÷ 3.5). **2976** characters.
- **tier2_formatter.txt:** **283** tokens (÷ 4); **~321** tokens (÷ 3.5). **1125** characters.
- **Tokenization method:** No `tiktoken` in `requirements.txt`; `anthropic==0.96.0` has no `count_tokens` on the client used here. Numbers use **UTF-8 byte length ÷ 4** (rough budget) and **÷ 3.5** as a second bracket for reconciliation with production `llm_input_tokens`.

---

## Row dict shape (per type)

- **provider:** `type`, `id`, `name`, `provider_name`, `category`, `address`, `phone`, `hours`, `description` (see truncation below).
- **program:** `type`, `id`, `name` (from title), `provider_name`, `activity_category`, `age_range`, `schedule_days`, `schedule_hours`, `location_name`, `location_address`, `cost`, `description`, `tags`.
- **event:** `type`, `id`, `name` (from title), `date`, `start_time`, `end_time`, `location_name`, `description`, `tags`.

**Truncation / size caps** (`app/chat/tier2_db_query.py`)

- `_truncate`: event description **180**; program description **160**; provider description **160**; provider hours **120** (with `...` if longer).
- **tags:** max **8** (event/program). **schedule_days:** max **7** (program).

**Row count cap**

- **`MAX_ROWS = 8`** merged cap; SQL paths use `.limit(80)` before trimming to eight dicts.

---

## Sample query payload sizes

Read-only runs on **local `events.db`** with filters aligned to the Phase 4.4 battery / parser tests (production row text may differ slightly).

| Query | Rows returned | Payload tokens (bytes÷4) | Per-row avg (json chars / rows) |
|-------|---------------|---------------------------|-----------------------------------|
| “What should I do Saturday?” | 8 | **1168** | ~582 |
| “Stuff happening at Sara Park” | 8 | **883** | ~440 |
| “Does Rotary Park have programs for 8-year-olds?” | 1 | **143** | 571 |

**Serialization:** same as formatter — `json.dumps(..., ensure_ascii=False, separators=(",", ":"))` (**compact**).

**Formatter `user_text` UTF-8 byte sizes (query + framing + JSON):** ~**4739** (Saturday), ~**3599** (Sara), ~**658** (Rotary).

---

## Formatter user-message composition

From `app/chat/tier2_formatter.py`:

- **Includes:** `Query: <query>\n\n`, `Catalog rows:\n`, **full row JSON**, then `\n\nRespond:`.
- **Serialization:** **compact** `separators=(",", ":")`.
- **Typical size (3 samples, user message only):** ~**1354**, ~**1028**, ~**188** tokens at ÷3.5 (from byte lengths above); at ÷4: ~1185, ~900, ~165.

---

## Token accounting reconciliation

`try_tier2_with_usage` records **`llm_input_tokens` = parser input + formatter input** (summed). Production **observed** values are from the Phase 4.4 voice battery (`chat_logs`).

**Model:** per-call input ≈ `(system_prompt + user_message)` bytes for that call, summed for parser and formatter. **÷ 3.5** bytes/token (empirically close on two of three checks).

### Q1 — “What should I do Saturday?”

**Observed input:** **2566**

| Block | Estimate (÷3.5) |
|--------|------------------|
| Parser: system + `User query:\n…\n` | **~863** |
| Formatter: system + user (query + rows) | **~1678** |
| **Combined estimated input** | **~2541** |
| **Observed** | **2566** |
| **Delta** | **+25** (~1%) |

### Q10 — “Stuff happening at Sara Park”

**Observed input:** **2366**

| Block | Estimate (÷3.5) |
|--------|------------------|
| Parser | **~864** |
| Formatter | **~1352** |
| **Combined** | **~2216** |
| **Observed** | **2366** |
| **Delta** | **+150** (~6%) — likely **heavier row text on production Postgres** than local SQLite for the same filter shape. |

### Q11 — “Does Rotary Park have programs for 8-year-olds?”

**Observed input:** **1363**

| Block | Estimate (÷3.5) |
|--------|------------------|
| Parser | **~869** |
| Formatter | **~512** |
| **Combined** | **~1381** |
| **Observed** | **1363** |
| **Delta** | **−18** (~1%) |

**Conclusion:** Observed Tier 2 **input** totals are **largely explained by parser + formatter system prompts plus the formatter user blob whose dominant term is the serialized row JSON** (8 rows ≈ **3.5–4.7k** characters JSON on this DB). There is **no large unexplained bucket** once a realistic chars/token ratio is used; remaining gap on Sara Park is consistent with **catalog payload differences** between environments.

---

## Primary bloat source (diagnosis)

The **formatter user message** is mostly **up to eight full row dicts** (events/programs/providers) with descriptions, tags, addresses, and schedule fields — still **kilobytes of JSON per turn** even with truncation. That, plus **two long system prompts** (parser text is **larger** than the formatter’s), accounts for **~2000+ billed input tokens** on typical 8-row Tier 2 turns. Tier 2 is “cheap” relative to Tier 3 on **output** and **tooling**, but **input** is dominated by **row payload + both system prompts**, not by a hidden extra API surface.

---

## Sanity checks

- **`open_now` handling:** **Normal** — `open_now=True` logs a warning and returns **[]** (`tier2_db_query.query`).
- **Double-routing:** **Normal** — `_handle_ask` calls `try_tier2_with_usage` once; Tier 3 runs **only** when Tier 2 returns `None` (`unified_router.py`). No path runs **both** Tier 2 and Tier 3 LLM chains for the same ask turn.

---

## Anomalies / unexpected findings

1. **Parser live calls** were not re-run in the investigation environment (no `ANTHROPIC_API_KEY` in the agent shell); filters for samples were taken from **documented test shapes** and battery semantics; **DB + JSON sizing** used real `tier2_db_query.query` on **local `events.db`**.
2. **`anthropic` 0.96.0** did not expose a simple `count_tokens` helper in the checked client surface; reconciliation used **byte heuristics** instead.
3. **Prompt caching:** Both parser and formatter attach **`cache_control: {"type": "ephemeral"}`** on the system block; **usage** in code sums `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. That can **move** billed tokens between turns versus a naive “chars only” model; not modeled in the static breakdown above.
