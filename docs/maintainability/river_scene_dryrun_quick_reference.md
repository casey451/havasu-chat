# River Scene prod dry-run — quick reference

Full detail: [`river_scene_backfill_prod_dryrun_runbook.md`](river_scene_backfill_prod_dryrun_runbook.md).

## Capture (stdout / stderr split, both `.log` → gitignored)

```bash
python scripts/backfill_river_scene_urls.py --dry-run > backfill_dryrun_postfix.log 2> backfill_dryrun_postfix_err.log
```

## Success scan (no crash mid-run)

PowerShell:

```powershell
Select-String -Path backfill_dryrun_postfix.log, backfill_dryrun_postfix_err.log -Pattern "Traceback|RuntimeError|AssertionError"
```

Expect **no matches**.

## Summary shape (numbers vary)

```text
River Scene URL backfill (rescrape) complete
  total:                         ?
  would_change:                   ?
  no_change:                      ?
  no_organizer_url_available:     ?
  applied:                        0
  skipped_fetch:                  ?
  no_article_url:                 ?
```

**Gate:** `applied` **must** be `0`.

## `total`

**~71** was the count at the original `--apply`; ingestion may have added events (**73**, **75**, …). **Not a bug** — do not halt on `total` alone. Headline remains **`would_change`**.

## Halt rules (summary)

| Condition | Action |
|-----------|--------|
| `Traceback` / `RuntimeError` / `AssertionError` in either log | Halt — script crashed mid-run; a summary line may still print but is untrustworthy |
| `applied ≠ 0` | Halt — dry-run broken |
| `would_change` in **0–5** | Halt — parser fix likely not taking effect |
| `would_change` in **70–71** (with `total` ~71) | Halt — possible regression on already-good rows |
| `would_change` ~**30–60** and `applied = 0` | Clean at summary level → per-row spot-check, then `--apply` when ready |
| `skipped_fetch` high | Halt or retry before `--apply` |

## Partition (sanity)

`would_change + no_change = total − skipped_fetch − no_article_url`

## Before `--apply` (sentinel UUIDs)

Unchanged rows **do not** call `_print_diff` — they never appear in the dry-run log. Would-change rows show `--- event <uuid>` plus field blocks.

**Sentinel check:** for each of the **7** known-good event ids (organizer URL in DB, not article-only), that id must **not** appear in the log at all.

List the ids once (verification SQL below), then e.g.:

```powershell
Select-String -Path backfill_dryrun_postfix.log -Pattern "<sentinel-event-uuid>"
```

Expect **no matches** for every sentinel id.

```sql
SELECT id, event_url
FROM events
WHERE source = 'river_scene_import'
  AND event_url NOT LIKE '%riverscene%';
```

That returns **7** rows (at last verification). Save the `id` values; none should appear in `backfill_dryrun_postfix.log`.

Optionally still sample **3–5** would-change blocks from the log to sanity-check proposed URLs.
