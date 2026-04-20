# Phase 3.0 — Script 3 report: `backfill_program_providers`

**Environment:** Railway production Postgres (`railway run` from `havasu-chat` repo)  
**Command:**

```bash
railway run .\.venv\Scripts\python.exe -m app.db.backfill_program_providers
```

**Exit code:** `0`  
**Approx. duration:** ~9.8 seconds  

---

## Alembic

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

**Expected:** `PostgresqlImpl` (writes against production Postgres, not SQLite).

---

## Full CLI output

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
=== Backfill program.provider_id ===
programs scanned: 98
already linked (skipped): 0
no provider_name (skipped): 0
linked via exact match: 98
linked via fuzzy match (threshold 90): 0
ambiguous matches: 0
no match: 0
programs updated this run: 98
programs with provider_id set (after run): 98
programs with provider_id null (after run): 0
```

---

## Summary table

| Metric | Value |
|--------|------:|
| programs scanned | 98 |
| already linked (skipped) | 0 |
| no provider_name (skipped) | 0 |
| linked via exact match | 98 |
| linked via fuzzy match (threshold 90) | 0 |
| ambiguous matches | 0 |
| no match | 0 |
| programs updated this run | 98 |
| programs with `provider_id` set (after run) | 98 |
| programs with `provider_id` null (after run) | 0 |

---

## Warnings

None reported in the command output.

---

## Notes for review

- All 98 programs received `provider_id` via **exact** name match; no fuzzy path used.
- Post-run: **zero** programs left with null `provider_id`.
