# River Scene backfill: fix 2 (dry-run, counters, source_url in diff)

**Commit:** `5ec85da` (subject: *River Scene backfill: --dry-run flag, counter expansion, source_url in diff*)

Fix 2 of 2 in the parser-followup chain. With fix 1 (commit `0051f17`) the parser now extracts organizer URLs from ORPHAN_TD listings and falls back Website → Facebook → article URL. Before re-running `--apply` against production with that fixed parser, the backfill script needs richer preview output and stronger guarantees that the script’s self-reported counts match what actually happened. Last turn’s verification showed that the script’s `applied=71` was “rows touched” not “rows materially changed” — the failure mode this change hardens against.

## Changes to `scripts/backfill_river_scene_urls.py`

- Add explicit `--dry-run` flag, mutually exclusive with `--apply` via `argparse.add_mutually_exclusive_group`. Backward-compatible: no flag still means preview, same as before. `--cleanup-only` stays outside the group; it can pair with either `--dry-run` or `--apply`.

- **New counter: `no_change`.** Increments on the branch where `_event_needs_update` returns False (row was fetched, parsed, but proposed state matches current). Together with `would_change`, partitions successful-parse rows.

- **New counter: `no_organizer_url_available`.** Increments when proposed `event_url` equals `normalize_submission_url(_article_url_with_scheme(rse.url))` — i.e. the parser found no Website or Facebook URL and fell back to the article URL. Orthogonal to `would_change` / `no_change`: measures parser output quality, not DB delta. Computed exactly once per row, immediately after `_payload_targets`, regardless of `--apply` vs `--dry-run`.

- **Helper** `_proposed_event_url_is_article_fallback_only(rse, event_url)` encapsulates the normalized-equality check.

- **Partition check** at end of `run_rescrape`: `total == no_article_url + skipped_fetch + would_change + no_change`. Raises `RuntimeError` if violated.

- **Sanity check** at end of `run_rescrape`: `applied == would_change` under `--apply`, `applied == 0` under preview. Same pattern in `run_cleanup_only`. Surfaces silent commit-loss or write-when-not-asked immediately rather than only via downstream verification SQL.

- **`_print_diff`:** `source_url` block prints unconditionally on every call. Previously gated on `cur_src != new_src` (normalized compare), which hid `source_url` when description-only or event_url-only changes drove `_event_needs_update`. Mirror change in `run_cleanup_only` diff output.

- **`run_rescrape` return tuple** expanded to:

  `(total, would_change, no_change, no_organizer_url_available, applied, skipped_fetch, no_article_url)`.

### End-of-run summary (stable order)

- `total`
- `would_change`
- `no_change`
- `no_organizer_url_available`
- `applied`
- `skipped_fetch`
- `no_article_url`

## Tests (`tests/test_backfill_river_scene_urls.py`, 8 cases)

**CLI**

- `--dry-run` + `--apply` rejected (`SystemExit` code 2).
- No flag and `--dry-run` alone both produce `apply=False`.
- `--apply` alone produces `apply=True`.

**Counter accuracy**

- Five-row partition test: change / match / article-only / fetch failure / no article URL. Asserts every counter including `no_organizer_url_available`.
- Apply matches dry-run: same DB seed run twice, dry-run then apply, `applied == would_change == 1`.

**Diff format**

- Description-only delta exercises the “`_print_diff` source_url always present” change. Asserts both URLs in the `source_url` block.

**Idempotency**

- Two consecutive `--apply` runs with mocked HTTP returning identical RSE. First: `applied > 0`. Second: `applied == 0`, `no_change > 0`. Confirms the script re-fetches and re-parses every row but only writes when state actually differs.

All tests use mocked `fetch_and_parse_event` and `time.sleep`; no network; DB is the same SQLAlchemy-backed test DB pattern as other script tests.

## Notes

- Partition check uses `RuntimeError`; idempotency / sanity checks use `assert`. Mixed exception classes are a known coherence nit (`assert` can be stripped by `python -O`). Acceptable for this script, which is not expected to run under `-O`. Optional follow-up to unify on `RuntimeError`.

- Direct unit tests for `_proposed_event_url_is_article_fallback_only` were intentionally omitted; the helper is covered end-to-end by the partition test. Optional follow-up if direct cases become useful.

- After this lands, the owner runs `--dry-run` against production (env not available in Cursor), reviews output, runs `--apply`, then runs the verification query. A later commit may add a verification addendum to `docs/maintainability/river_scene_event_output_decision.md`.

**Refs:** `docs/maintainability/river_scene_event_output_decision.md`, `0051f17`.
