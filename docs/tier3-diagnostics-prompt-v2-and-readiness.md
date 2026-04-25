# Tier 3 unlinked-events — diagnostics prompt (v2) and readiness report

**Purpose:** Single file with the **approved** read-only prod diagnostics + branching-plan prompt (v2), plus review notes and execution pointers.

**Status:** v2 approved for paste (see Review outcome). **No prod commands are run** in creating this document.

---

## Paste to Cursor — preamble (optional tightenings in-scope)

Paste this **one line** immediately before the main v2 prompt body:

> Optional tightenings applied: (1) if D2 output is noisy, secondarily filter to rows where `mode IS NOT NULL` to isolate unified-router traffic; (2) adjust D5's `'2026-07-04'` literal if the specific July 4 event under test has a different date; (3) for Branch 2 follow-up, reference the exact `logger.info` sketch in `docs/tier3-unlinked-events-readonly-investigation.md` §5.

### Frame-setter when results land

The most interesting failure mode is not Branch 1 vs Branch 2 cleanly — it is **all four validation queries having no `chat_logs` row**. That means **tier attribution is impossible** and **logging may be broken**, which would prioritize a **real-Python install** and a **logging-reliability pass** ahead of any further Option B work. Low probability, but know the shape in advance so interpretation does not scramble.

---

## Review outcome (v2)

- **Verdict:** Approve to run. D2/`normalized_query`, D5 Option B predicates, `chat_logs` schema note, and Railway fallback are correct.
- **Optional micro-tightenings** (not blockers): (1) If D2 is noisy, filter unified-router rows (e.g. `query_text_hashed IS NOT NULL` and/or `mode IS NOT NULL`). (2) D5 July 4 cutoff: if the event under test is not `2026-07-04`, adjust the literal. (3) Branch 2: point executors at `docs/tier3-unlinked-events-readonly-investigation.md` §5 for the exact `logger.info` sketch.
- **Missing `chat_logs` rows:** Not proof Tier 3 didn’t run — `log_unified_route` can fail silently. If **all four** validation queries lack rows, treat as logging/query-match failure before trusting tier mix. If `tier_used` unknown, note alternate evidence (e.g. client capture of `tier_used` from `POST /api/chat`).

---

## Prompt — READ-ONLY DIAGNOSTICS + PLAN (v2)

**Scope: read-only prod DB diagnostics and written plan only.** Do not modify any file. Do not run migrations. Do not commit. Do not push. If diagnostics reveal something that looks like an easy fix, DO NOT fix it — note it in the plan section for later review.

### State coming in

Your previous investigation (`docs/tier3-unlinked-events-readonly-investigation.md`) confirmed that `_handle_ask` in `app/chat/unified_router.py` tries Tier 2 before Tier 3 for non–explicit-rec queries. If Tier 2 returns anything, Option B’s entire code path is skipped. The four validation queries (“summer,” “July 4 show,” “July 4 events,” “fireworks 4th of July”) are almost certainly not explicit-rec matches.

**Leading hypothesis:** Tier 2 answered some or all of the validation queries, and Option B never ran. Oct/Jan events surfacing is explainable if Taste of Havasu and Balloon Festival are `provider_id IS NOT NULL` (linked events surfaced by Tier 2’s sample or Tier 3’s linked path), not by Option B’s unlinked block.

**Prod DB is authoritative.** Diagnose against it.

### Important schema note

- `ChatLog` maps to table **`chat_logs`** (`__tablename__ = "chat_logs"`). Use the table name in raw SQL.
- In `log_unified_route` (`app/db/chat_logging.py`), column **`message`** stores the **assistant response**, truncated — NOT the user query. The user’s query is stored in **`normalized_query`**. Do not confuse these.

### Environment notes

- Use `railway run python -c "..."` for all DB queries. Local `python` on Windows may be shadowed by Microsoft Store aliases and will not work.
- Confirm venv / shell expectations per your team (e.g. `(.venv)` active) before running commands.
- Do not print full secrets, full URLs, or full env var values. For env checks, truncate (e.g. first 20 chars) to verify shape only.
- If any command errors, STOP and report the exact error. Do not proceed or paper over failures.
- **Railway auth fallback:** If `railway run` fails (not logged in, no project link, network error), STOP. Do not attempt to install Railway CLI, re-auth, or work around. Report the exact error and the list of commands you were about to run (as copy-pasteable `railway run python -c "..."` one-liners). Casey will run them from their terminal and paste output back for analysis.

### Diagnostics to run (in order)

#### D1. Introspect the `ChatLog` model

Read `app/db/models.py` for the `ChatLog` class. Report:

- `__tablename__` (confirm it is `chat_logs`).
- Every column name in declaration order.
- Explicit confirmation of which column holds the **user’s query** (expected: `normalized_query`) and which holds the **assistant response** (expected: `message`).

Use the column names you read for D2+. Do not guess.

#### D2. Find validation-related query rows

Query `chat_logs` where `normalized_query IS NOT NULL` and matches any of these case-insensitive patterns: `%summer%`, `%july%`, `%4th%`, `%firework%`. Return the last ~15 matching rows, sorted by timestamp descending. For each row return:

- `id`
- timestamp column (whatever D1 named it)
- `tier_used`
- `mode`
- `sub_intent`
- `entity_matched`
- first 100 chars of `normalized_query`
- first 100 chars of `message` (debug; confirm the row is what you think)

#### D3. Tier attribution per validation query

From D2’s output, identify rows that correspond to each of the four validation queries (“summer,” “July 4 show,” “July 4 events,” “fireworks 4th of July”). A query may have multiple rows if run more than once — list all. For each, state `tier_used`. If a query has no matching row in `chat_logs`, say so explicitly and flag it (possible log failure — `log_unified_route` failures can silently drop rows).

#### D4. July 4–style event rows

Query `events` where title is case-insensitively matched by any of: `%july%`, `%4th%`, `%fourth%`, `%firework%`, `%independence%`. No date filter — include past, future, live, draft, any status. For each row return:

- `id`, `title`, `date`, `start_time`, `status`, `provider_id`
- a computed column `is_unlinked` = `(provider_id IS NULL)`

#### D5. Unlinked future event ranking

Reproduce `_unlinked_future_events`’s exact filter set **without** the `LIMIT`:

- `status = 'live'`
- `provider_id IS NULL`
- `date >= <today>`
- `date <= <today> + 365 days`

Use the same “today” source as `build_context_for_tier3` — Python’s `date.today()` on the Railway container. Include a row number over `ORDER BY date ASC, start_time ASC`. Return `id`, `title`, `date`, `start_time`, and `rn`.

Then answer:

- How many rows have `rn ≤ 10`?
- How many rows (in the filtered set) have `date < '2026-07-04'`? (Adjust the calendar date if your July 4 event under test differs.)

If the count with `date < '2026-07-04'` is **≥ 10**, any July 4 **unlinked** row cannot appear in the `LIMIT 10` unlinked block delivered to the LLM.

#### D6. Taste of Havasu and Balloon Festival

Query `events` where title matches `%taste%` or `%balloon%` (case-insensitive). Report `provider_id` and `is_unlinked` = `(provider_id IS NULL)` for each.

#### D7. Container date and timezone

```text
railway run python -c "from datetime import date, datetime; import os; print('date.today:', date.today()); print('datetime.now:', datetime.now()); print('TZ env:', os.environ.get('TZ', '<unset>'))"
```

### Report format — single markdown response, sections in this order

**Section A — Environment confirmation.** Venv? Railway CLI? Did any `railway run` fail? If fallback triggered, include full copy-paste one-liners for Casey.

**Section B — Raw diagnostic output.** D1–D7, one subsection each. Tables where appropriate. Data only.

**Section C — Interpretation.** For each of the four validation queries: which tier answered, and why that tier’s behavior fits the observed response. Reconcile Oct/Jan vs July using D4–D6. State explicitly whether Option B’s code path ran for any failing query.

**Section D — Branching plan.** Three branches (Tier 2 masking / Tier 3 but block issues / mixed). Say which branch applies. Expand the active branch: files, risks, spec vs small PR, pytest gating.

**Section E — Adjacent observations.** No fixes.

### Absolute fences

- No code changes. No schema changes. No commits. No pushes. No deploys.
- If `railway run` fails, stop and hand commands to Casey — do not install CLI or re-auth.
- Report only.

---

## Related docs

| Document | Role |
|----------|------|
| `docs/tier3-unlinked-events-readonly-investigation.md` | Code-path investigation; §5 proposed `logger.info` for Branch 2 follow-up |
| `docs/tier3-diagnostics-prompt-review.md` | First-pass review (D2 column fix) |
| `docs/tier3-option-b-unlinked-events-spec.md` | Option B spec |

---

## Provenance (how this prompt reaches an agent)

The v2 prompt is **pasted by the owner** into a Cursor chat (or stored in this file and `@`-referenced). The model only sees what is in the conversation or attached files; there is no separate automatic handoff from GitHub or email unless you add that workflow yourself.
