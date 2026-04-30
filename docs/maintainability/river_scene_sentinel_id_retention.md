# River Scene backfill — sentinel event id retention

Short operational note (also folded into the [runbook](river_scene_backfill_prod_dryrun_runbook.md) and [quick reference](river_scene_dryrun_quick_reference.md); committed in **`6f13e9e`**).

## Why

Dry-run uses **event `id`** strings to prove the **seven** “already had organizer URL” rows never appear in `_print_diff` output (no `--- event <uuid>` for those ids).

After **`--apply`**, verification needs the **same seven ids**. Do not assume you can re-run the discovery SQL and get the same cohort by counting rows.

## Capture (survives shell history pruning)

Prefer a **file**, not history alone:

```text
sentinel_ids.txt
```

(one UUID per line), or a scratch Markdown file / ticket comment.

## SQL (run once before dry-run / apply)

```sql
SELECT id, event_url
FROM events
WHERE source = 'river_scene_import'
  AND event_url NOT LIKE '%riverscene%';
```

Save the `id` column from that result set into `sentinel_ids.txt` (or equivalent).

## Post-apply caveat

After **`--apply`**, re-running this `SELECT` may return a **different number of rows** on purpose (events move off article URLs). Your verification step should use the **frozen list** from before the backfill, not a fresh “give me seven rows” interpretation of the query.
