# River Scene backfill & parser follow-up — documentation index

One place to find Markdown for **fix 2**, **prod dry-run**, and related decisions.

## In repo (`main`)

| File | Role |
|------|------|
| [`river_scene_backfill_prod_dryrun_runbook.md`](river_scene_backfill_prod_dryrun_runbook.md) | Full prod dry-run procedure: capture, scans, summary gates, calibration, per-row sentinel UUIDs, SQL. |
| [`river_scene_dryrun_quick_reference.md`](river_scene_dryrun_quick_reference.md) | One-screen cheat sheet: **gate posture (7 steps)**, capture, crash scan, halt table, partition, sentinels. |
| [`river_scene_sentinel_id_retention.md`](river_scene_sentinel_id_retention.md) | Standalone: `sentinel_ids.txt`, frozen cohort, post-apply SQL caveat. |
| [`river_scene_backfill_fix2.md`](river_scene_backfill_fix2.md) | Long-form narrative of fix 2 (same story as commit **`5ec85da`** body); easier to browse than `git show`. |
| [`river_scene_backfill_documentation_index.md`](river_scene_backfill_documentation_index.md) | This index — navigation for the stream. |
| [`river_scene_event_output_decision.md`](river_scene_event_output_decision.md) | Event output / URL decision record; verification addendum may land here after `--apply`. |

**Commits (reference):**

- **`5ec85da`** — code: backfill script `--dry-run`, counters, `_print_diff` / partition / sanity checks; tests in `tests/test_backfill_river_scene_urls.py`.
- **`40d664c`** — docs: runbook + quick reference committed *before* prod dry-run so the repo matches execution intent.
- **`ddf7b65`** — docs: fix 2 narrative (`river_scene_backfill_fix2.md`), this index, sentinel-id retention note on runbook + quick reference.
- **`98aae25`** — docs: index lists `ddf7b65`.
- **`6f13e9e`** — docs: sentinel file + post-apply SQL caveat on runbook + quick ref.
- **`78f2721`** — docs: seven-step gate posture on quick ref; track `river_scene_sentinel_id_retention.md`; index links.

## Code

- `scripts/backfill_river_scene_urls.py` — rescrape backfill CLI and counters.
- `tests/test_backfill_river_scene_urls.py` — CLI, counters, diff snapshot, idempotency (mocked HTTP).

## After prod dry-run

Paste the **end-of-run summary block** (and odd stderr) for review. When `--apply` and verification are done, update `river_scene_event_output_decision.md` as planned.
