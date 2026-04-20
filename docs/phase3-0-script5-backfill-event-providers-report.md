# Phase 3.0 — Script 5 report: `backfill_event_providers`

**Environment:** Railway production Postgres (`railway run` from `havasu-chat` repo)  
**Command:**

```bash
railway run .\.venv\Scripts\python.exe -m app.db.backfill_event_providers
```

**Exit code:** `0`  
**Approx. duration:** ~7.2 seconds  

---

## Alembic

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

**Expected:** `PostgresqlImpl` (production Postgres, not SQLite).

---

## Full CLI output

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
=== Backfill event.provider_id ===
events scanned: 43
already linked (skipped): 0
linked via contact_name exact: 16
linked via contact_name fuzzy: 4
  contact fuzzy  score=100.0  event_title='Aqua Aerobics — Aquatic Center'  -> provider='Lake Havasu City Aquatic Center'  (event.id=7015d0e1-aeb4-437b-a425-d2160f65ec26)
  contact fuzzy  score=100.0  event_title='Open Swim — Aquatic Center'  -> provider='Lake Havasu City Aquatic Center'  (event.id=71c14f03-5ab9-4f7c-a036-93a6150024a1)
  contact fuzzy  score=100.0  event_title='Iron Wolf Golf & Country Club Open Play'  -> provider='Iron Wolf Golf & Country Club'  (event.id=75558b6a-c582-4980-a159-1b937437f45d)
  contact fuzzy  score=100.0  event_title='Swim Lessons for Kids — Aquatic Center'  -> provider='Lake Havasu City Aquatic Center'  (event.id=ec3e939d-865a-4bac-8d41-1b50aed66b13)
linked via source exact: 0
linked via source fuzzy: 0
linked via title/description/location blob: 0
ambiguous (skipped): 3
  event id=c3414f3f-65e7-40c4-b53a-8dc33148409e  title='Havasu Stingrays Swim Team Tryouts'  step=contact_name_fuzzy
    candidate: 'Havasu Stingrays Masters Team'  score=100.0
    candidate: 'Havasu Stingrays Swim Team'  score=100.0
  event id=c3414f3f-65e7-40c4-b53a-8dc33148409e  title='Havasu Stingrays Swim Team Tryouts'  step=title_description_location_blob
    candidate: 'Havasu Stingrays Swim Team'  score=100.0
    candidate: 'Lake Havasu City Aquatic Center'  score=100.0
  event id=cf620aa3-3356-48b7-9527-bfc96ea24271  title='July 4th Fireworks & Celebration'  step=contact_name_fuzzy
    candidate: 'Altitude Trampoline Park — Lake Havasu City'  score=91.4
    candidate: 'Lake Havasu City Aquatic Center'  score=91.4
    candidate: 'Lake Havasu City BMX'  score=91.4
    candidate: 'Lake Havasu City Parks & Recreation'  score=91.4
events updated this run: 20
events with provider_id set (after run): 20
events with provider_id null (after run): 23
```

*(If your terminal used mojibake for en-dashes in titles, compare against this file’s Unicode em/en dashes.)*

---

## Summary table

| Metric | Value |
|--------|------:|
| events scanned | 43 |
| already linked (skipped) | 0 |
| linked via `contact_name` exact | 16 |
| linked via `contact_name` fuzzy | 4 |
| linked via source exact | 0 |
| linked via source fuzzy | 0 |
| linked via title/description/location blob | 0 |
| ambiguous (skipped) | 3 |
| events updated this run | 20 |
| events with `provider_id` set (after run) | 20 |
| events with `provider_id` null (after run) | 23 |

---

## Fuzzy links (script-printed)

All four fuzzy matches at **score 100.0**:

| Event title | Linked provider | Event id |
|-------------|-----------------|----------|
| Aqua Aerobics — Aquatic Center | Lake Havasu City Aquatic Center | `7015d0e1-aeb4-437b-a425-d2160f65ec26` |
| Open Swim — Aquatic Center | Lake Havasu City Aquatic Center | `71c14f03-5ab9-4f7c-a036-93a6150024a1` |
| Iron Wolf Golf & Country Club Open Play | Iron Wolf Golf & Country Club | `75558b6a-c582-4980-a159-1b937437f45d` |
| Swim Lessons for Kids — Aquatic Center | Lake Havasu City Aquatic Center | `ec3e939d-865a-4bac-8d41-1b50aed66b13` |

---

## Ambiguous / not linked (script-printed)

**Counter:** `ambiguous (skipped): 3` (log lines include two steps for the *same* Stingrays event.)

1. **`c3414f3f-65e7-40c4-b53a-8dc33148409e`** — *Havasu Stingrays Swim Team Tryouts*  
   - **contact_name_fuzzy:** tie between `Havasu Stingrays Masters Team` and `Havasu Stingrays Swim Team` (both 100.0).  
   - **title_description_location_blob:** tie between `Havasu Stingrays Swim Team` and `Lake Havasu City Aquatic Center` (both 100.0).

2. **`cf620aa3-3356-48b7-9527-bfc96ea24271`** — *July 4th Fireworks & Celebration*  
   - **contact_name_fuzzy:** four candidates at 91.4 — Altitude Trampoline Park — Lake Havasu City; Lake Havasu City Aquatic Center; Lake Havasu City BMX; Lake Havasu City Parks & Recreation.

No links via `source_*` or blob for any event in this run.

---

## Remaining `provider_id` null

**23** events still have `provider_id` null after the run.

The script **does not** print a full inventory of those 23. They include at least the ambiguous cases above; the rest are likely no-match paths (e.g. original seed events whose `contact_name` / blob did not resolve uniquely). A follow-up `railway run` SQLAlchemy or SQL query can list `id`, `title`, `contact_name` for `provider_id IS NULL` if needed.

---

## Warnings

None in stdout beyond the intentional ambiguous-skip diagnostics.
