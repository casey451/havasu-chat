# River Scene backfill — prod dry-run runbook

Post–fix 2 (`5ec85da`). Parser-followup chain is complete at the code level; this document banks state and sets up the **owner-only** production dry-run.

## Push / branch state

After `git fetch origin`:

- Expect `main` aligned with `origin/main` at `5ec85da` (no local-only fix 2).
- If `main` is **ahead** of `origin/main`, push before the prod run.

Untracked doc (optional to commit): `docs/maintainability/river_scene_backfill_fix2.md`.

## State of the stream (reference)

| Commit     | Note |
|-----------|------|
| `83e4995` | H2-followup commit 0.5 (source_url column add) |
| `fcc8d25` | H2-followup commit 1 (River Scene ingestion fix, dedupe via source_url) |
| `5cfd1cd` | H2-followup commit 2 (render-time guard) |
| `3081bde` | H2-followup commit 3 (backfill script) |
| `6bec1ec` | H2-followup commit 2.1 (tier2 legacy strip) |
| `21f86c3` | River Scene event-output fix: post-ship documentation pass |
| `0051f17` | Parser orphan-`<td>` recovery + Facebook fallback (fix 1 of 2) |
| `f3f79e9` | Bad chore commit — reverted locally, never pushed (UTF-16 `.gitignore` append) |
| `610df268` | Clean chore: ignore `*.log` |
| `e62ac21` | Cursor rule: UTF-8 text-file appends on Windows |
| `5ec85da` | River Scene backfill: `--dry-run`, counter expansion, `source_url` in diff (fix 2 of 2) |

## Next operational turn — owner runs prod dry-run

Cursor cannot run this: production DB requires env your machine has, not the repo `.env`.

### 1. Confirm push state

```bash
git status
```

If `main` is ahead of `origin/main`, push before the prod run.

### 2. Set the prod connection string

Use the same Railway (or other) connection string as for the original `--apply` run, in your shell session.

### 3. Run dry-run and capture output

Send **stdout** and **stderr** to separate files so tracebacks and warnings are not buried inside per-row diffs. Use a second filename ending in `.log` so both stay under the existing `.gitignore` `*.log` rule (simpler than adding `*.err`).

```bash
python scripts/backfill_river_scene_urls.py --dry-run > backfill_dryrun_postfix.log 2> backfill_dryrun_postfix_err.log
```

The `postfix` suffix distinguishes these from older `backfill_dryrun_prod.log` files.

### 4. Spot-check the logs before declaring success

**A. Failure / partition signals**

If the script raised `RuntimeError("counter partition broken: ...")` or hit an assertion, you get a Python traceback instead of a clean summary. Before trusting the run:

- Scan both files for **`Traceback`**, **`RuntimeError`**, **`AssertionError`** (e.g. no matches expected).

PowerShell quick check:

```powershell
Select-String -Path backfill_dryrun_postfix.log, backfill_dryrun_postfix_err.log -Pattern "Traceback|RuntimeError|AssertionError"
```

Expect **no output** (zero matches).

**B. End-of-run summary**

Confirm the **summary block** appears and matches this shape (numbers vary):

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

**`applied:` must be `0`.** If it is not, treat dry-run as broken — halt before any `--apply` or other reruns.

### 5. Report back

Post the **summary block** and, if anything is unusual, relevant lines from **`backfill_dryrun_postfix_err.log`**. You do **not** need to paste all per-row diffs unless something looks wrong.

---

## `total` is not a fixed target

**`total = 71`** reflects the original prod `--apply` run. River Scene ingestion has stayed live since then — new magazine events may have been admitted. If **`total`** is **73**, **75**, etc., that is **not a bug**; the world moved. The headline for go/no-go is still **`would_change`** (and the gates below). Note a different `total` when reporting; **do not halt** on `total` alone.

---

## What to watch for in the summary

### Hard gates (halt if violated)

- **`applied`** must be **`0`**. Anything else → dry-run broken; halt.
- **`skipped_fetch`** high (magazine flaky) → treat as risk; halt or retry before `--apply` depending on severity.
- **`would_change` in `0`–`5`** → parser fix likely not taking effect; halt and investigate before anything else.
- **`would_change` in `70`–`71`** (with `total` ~71) → possible regression on rows that already had organizer URLs; halt and investigate.
- Anything non-zero in **`applied`**, or **`skipped_fetch`** unexpectedly high → halt.

### Soft signals

- **`would_change` in ~`30`–`60`** and **`applied = 0`** → treat as a **clean** summary-level run; proceed to per-row spot-check, then `--apply` when satisfied.
- **`no_organizer_url_available`** — orthogonal counter (parser fell back to article URL only). High values (e.g. **> 20**) may warrant more parser/listing-shape work later.
- **Partition:** `would_change + no_change` should equal `total − skipped_fetch − no_article_url`. A broken partition raises **`RuntimeError`** in the script (see step 4A).
- **Regression sentinel:** Events that already had organizer URLs after the first prod `--apply` should land in **`no_change`**, not **`would_change`**. The summary alone cannot prove per-row behavior; suspicious **`would_change`** near **`total`** triggers the halt above.

### Calibration (predictions, not targets)

Use these only as **sanity ranges** when the real numbers land — wide error bars.

| Field | Expectation |
|--------|-------------|
| **`total`** | **71 ± a few** — ingestion may have added events since the original run. |
| **`applied`** | **`0`** (gate). |
| **`would_change`** | **~50–60** plausible. Prior verification: **64** of **71** had article URLs in `event_url`; **7** had organizer URLs and should be **`no_change`**. Of the **64**, some share of listings have NO_WEBSITE_ROW and no Facebook → **`no_organizer_url_available`** and no URL change (article remains best). If a **~33%** “stuck on article” rate (from a small phase-2 sample) applied roughly to those **64**, that is **~21** still article-only post-fix → **~43** **`would_change`** — illustrative only. |
| **`no_change`** | Includes the **7** “already good” rows plus any row where DB already matches proposed state (including rows that stay on article URL when that is genuinely best). Roughly **`no_change ≈ total − would_change`** when **`skipped_fetch`** and **`no_article_url`** are **0**. |
| **`no_organizer_url_available`** | Independent of **`would_change`** / **`no_change`**. Sample order-of-magnitude **~23** of **71** if **~33%** of rows truly have no distinct organizer URL — very wide range. |
| **`skipped_fetch`** | **0** unless River Scene is having a bad day. |
| **`no_article_url`** | **0** expected; original ingestion populated article URLs. |

---

## Per-row spot-check before `--apply`

When the **summary** looks reasonable, **before** running **`--apply`**:

Unchanged rows **do not** call `_print_diff` — they produce **no** lines in the dry-run log. Rows that would change appear under `--- event <uuid>` with field diff blocks.

**Sentinel check (cleaner than grepping URLs):** the **7** events that already had organizer URLs after the first prod `--apply` must **not** appear in the log at all — grep each sentinel **event `id`**; expect **zero matches**.

List the ids from your DB (same shape as the verification addendum precursor):

```sql
SELECT id, event_url
FROM events
WHERE source = 'river_scene_import'
  AND event_url NOT LIKE '%riverscene%';
```

**Keep a durable copy of those `id` values** (scratch file, shell transcript, ticket note) before you run `--apply`. Post-apply verification should use the **same sentinel cohort**; re-deriving mid-verification is easy to get wrong.

PowerShell example (repeat per id, or build one alternation pattern):

```powershell
Select-String -Path backfill_dryrun_postfix.log -Pattern "<sentinel-event-uuid>"
```

Expect **no output** for each of the **7** ids.

**Optional:** still sample **3–5** would-change blocks in the log to eyeball proposed `event_url` / `source_url` values.

---

## After dry-run

When satisfied, owner runs **`--apply`**, then the agreed verification query / doc addendum on `docs/maintainability/river_scene_event_output_decision.md` as planned.
