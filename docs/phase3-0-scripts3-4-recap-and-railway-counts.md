# Phase 3.0 — Scripts 3 & 4 recap + Railway `Program` verification

Consolidated for review (Claude / handoff). **Script 6 was not run** as part of this document’s scope.

---

## Script 3 — `backfill_program_providers`

**Environment:** Railway production Postgres (`railway run` from `havasu-chat`)  
**Command:**

```bash
railway run .\.venv\Scripts\python.exe -m app.db.backfill_program_providers
```

**Exit code:** `0`  
**Approx. duration:** ~9.8 seconds  

### Full CLI output (verbatim from run)

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

### Summary

| Metric | Value |
|--------|------:|
| Alembic context | `PostgresqlImpl` |
| programs scanned | 98 |
| linked via exact match | 98 |
| linked via fuzzy (90) | 0 |
| ambiguous / no match | 0 / 0 |
| `provider_id` set after run | 98 |
| `provider_id` null after run | 0 |

---

## Script 4 — `populate_program_concierge_fields`

**Command:**

```bash
railway run .\.venv\Scripts\python.exe -m app.db.populate_program_concierge_fields
```

**Exit code:** `0`  
**Approx. duration:** ~9.8 seconds  

### Full CLI output (verbatim from run)

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
=== Populate program concierge fields ===
programs scanned: 98
programs matched to exactly one master block: 91
programs skipped (concierge already touched / non-default): 0
programs skipped (matched, no field changes needed): 6
programs updated (>=1 concierge field written): 85
show_pricing_cta set True this run: 59
cost_description set this run: 23
schedule_note set this run: 59
draft set True this run: 1
ambiguous master key (multiple YAML rows): 0
no matching master block: 7
  program id=1a298ace-a38e-4757-904d-a4cfeca48c14  provider_name='Bridge City Combat'  title='Adult Fundamentals Gi Jiu-Jitsu'
  program id=82a1c0a3-be1a-4360-b3ad-601088c4b37a  provider_name='Universal Gymnastics and All Star Cheer'  title='Sonics All Star Cheer All Teams (20262027 Season)'
  program id=a568afd3-2ec3-42ce-8b4e-05fa43f2c79e  provider_name='Universal Gymnastics and All Star Cheer'  title='Recreational Tumbling Level 1/2/3'
  program id=bae39ca7-a42a-4331-99c6-97122e00dad4  provider_name='Havasu Lions FC'  title='Recreational Soccer Fall Season'
  program id=bbb2b205-7495-49cc-8297-f957cf2165ed  provider_name='Lake Havasu City BMX'  title='Strider/Balance Bike Track (Patrick Tinnell Balance Bike Track)'
  program id=d3f88f4a-02f4-4636-b89a-ba353427fc03  provider_name='Lake Havasu City Parks & Recreation'  title='Adventure Camp (Archery, Kayaking & More)'
  program id=d4808611-0657-4453-8f3f-3304f4c9bcee  provider_name='Havasu Lions FC'  title='Recreational Soccer Spring Season'
WARNING: no-match count exceeds 5% of scanned programs; check seed instructions vs HAVASU_CHAT_MASTER titles before loosening match logic.
```

*(Some log lines may show `` where Unicode punctuation was mojibaked in the terminal.)*

### Summary

| Metric | Value |
|--------|------:|
| Alembic context | `PostgresqlImpl` |
| programs scanned | 98 |
| matched exactly one master block | 91 |
| skipped (no field changes) | 6 |
| updated (≥1 concierge field) | 85 |
| `show_pricing_cta` set True this run | 59 |
| `cost_description` set this run | 23 |
| `schedule_note` set this run | 59 |
| `draft` set True this run | 1 |
| no matching master block | 7 |
| Warning | no-match rate **> 5%** (7 / 98) |

### Note on expectations

- **`provider_id`:** Script 3 left **98 / 98** populated (all exact match).
- **`show_pricing_cta` / `schedule_note`:** **59** rows — aligns with local-style reference.
- **`cost_description`:** **23** non-null on Railway after Script 4 — **not** the same scale as pricing CTA; matches “`cost_description` set this run: 23” in the script summary.

---

## Verification query — current Railway `Program` counts

**Command:**

```bash
railway run .\.venv\Scripts\python.exe -c "from app.db.database import SessionLocal; from app.db.models import Program; s = SessionLocal(); total = s.query(Program).count(); linked = s.query(Program).filter(Program.provider_id.isnot(None)).count(); with_pricing_cta = s.query(Program).filter(Program.show_pricing_cta == True).count(); with_cost_desc = s.query(Program).filter(Program.cost_description.isnot(None)).count(); with_schedule_note = s.query(Program).filter(Program.schedule_note.isnot(None)).count(); drafts = s.query(Program).filter(Program.draft == True).count(); print(f'total programs: {total}'); print(f'provider_id populated: {linked}'); print(f'show_pricing_cta=True: {with_pricing_cta}'); print(f'cost_description populated: {with_cost_desc}'); print(f'schedule_note populated: {with_schedule_note}'); print(f'draft=True: {drafts}'); s.close()"
```

**Exit code:** `0`

### Output

```text
total programs: 98
provider_id populated: 98
show_pricing_cta=True: 59
cost_description populated: 23
schedule_note populated: 59
draft=True: 1
```

This matches the Scripts 3–4 narrative above.

---

## Related MD reports (same Phase 3.0 runbook)

- `docs/phase3-0-script3-backfill-program-providers-report.md` — Script 3 only (earlier export)
- `docs/phase3-0-script5-backfill-event-providers-report.md` — Script 5
