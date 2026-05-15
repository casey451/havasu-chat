# Cursor dispatch — OSM pull JSONL writer test

**Branch base:** the commit that ships `fix(scripts): osm_overpass_pull writes
JSONL — Phase 5.2 OSM chain unblocker` (Cowork-staged; operator-committed).
Confirm `git log -1 --oneline -- scripts/osm_overpass_pull.py` lands on that
commit before starting.

**Scope:** `tests/` only — add a focused test pair for the new JSONL-writer
behavior of `scripts/osm_overpass_pull.py`. Mirror the existing
`tests/test_phase5_osm_overpass_load.py` style.

**Why:** Phase 5.2 §0 pre-flight surfaced that the pull→load chain was broken
on disk — `osm_overpass_pull` only printed in-memory; the load expected a
JSONL at `scripts/output/osm_pull/osm_elements.jsonl` that nothing wrote.
Cowork shipped the fix (~30 LOC, scripts/-only) as `fix(scripts):
osm_overpass_pull writes JSONL — Phase 5.2 OSM chain unblocker`, but deferred
the test to keep the fix-commit narrow (matches the d34d4c3 fix-then-test
pattern from Phase 5.1). This dispatch closes the test gap.

---

## §1 The fix being tested

`scripts/osm_overpass_pull.py` now:

1. Calls `client.discover(...)` (was: `client.run(...)`) — gives access to
   `RawHit.raw["element"]` (the original Overpass element dict).
2. In non-dry-run mode, extracts those elements and writes a single
   wrapper-line JSONL to `--output` (default
   `scripts/output/osm_pull/osm_elements.jsonl`, mirroring
   `scripts.osm_overpass_load.DEFAULT_INPUT_PATH`).
3. In dry-run mode, prints count + first 5 and does **not** write.

The load's `_iter_feature_elements` handles the wrapper-line shape natively
and filters by `--tag`/`--value` at load time.

---

## §2 Tests to add

Place in **new file** `tests/test_phase5_osm_overpass_pull.py` (mirrors
`tests/test_phase5_osm_overpass_load.py`'s name shape). All tests mock
`OsmOverpassClient.discover` — no live Overpass HTTP calls.

### 2.1 `test_pull_writes_wrapper_line_jsonl_to_default_path(tmp_path, monkeypatch)`

- Monkeypatch `OsmOverpassClient.discover` to return 3 `RawHit` objects whose
  `.raw["element"]` is a realistic Overpass node dict (`{"type": "node",
  "id": ..., "lat": ..., "lon": ..., "tags": {"name": "...", "leisure":
  "marina"}}`).
- Monkeypatch `scripts.osm_overpass_pull.DEFAULT_OUTPUT_PATH` to a
  `tmp_path / "osm_elements.jsonl"`.
- Invoke `scripts.osm_overpass_pull.main` via `sys.argv` patching with
  `--tag leisure --value marina`.
- Assert: exit code 0; the JSONL exists; one line; the parsed line is a
  wrapper `{"elements": [...]}` with 3 elements; each element's `tags.name`
  matches what we injected.

### 2.2 `test_pull_dry_run_does_not_write(tmp_path, monkeypatch, capsys)`

- Same mock setup as 2.1, but invoke with `--dry-run`.
- Assert: exit code 0; the output path does **not** exist; stdout contains
  "dry-run: no JSONL written" and "Discovered 3".

### 2.3 `test_pull_output_flag_writes_to_explicit_path(tmp_path, monkeypatch)`

- Same mock setup; invoke with `--output {tmp_path}/marinas.jsonl --tag
  leisure --value marina`.
- Assert: file at the explicit path exists; default path is untouched.

### 2.4 `test_pull_output_is_consumable_by_load(tmp_path, monkeypatch)`

- Round-trip test: write a JSONL via the pull mocks; then call
  `scripts.osm_overpass_load._iter_feature_elements` directly on the parsed
  wrapper-line with `tag="leisure"`, `value="marina"`.
- Assert: 3 elements yielded, all with `tags.leisure == "marina"`.
- This guards the pull→load contract at the JSONL shape level without
  needing a DB.

### 2.5 `test_osm_client_sends_descriptive_user_agent(monkeypatch)`

**Added in the same commit as the UA + visible-logging fix** (commit
shipped post-2ef4b3b — see the kickoff context). Place this test in
`tests/test_phase4_osm_client.py` since it covers client behavior, not
the pull script.

- Use `httpx.MockTransport` (or monkeypatch `httpx.Client.post`) to
  capture the outgoing request.
- Call `OsmOverpassClient().discover({"tag": "leisure", "value": "marina"})`.
- Assert: the captured request's `User-Agent` header equals
  `OSM_OVERPASS_USER_AGENT` (i.e., starts with `"havasu-chat/"`), **not**
  `python-httpx/...`. Regression guard against the 406-from-Overpass
  failure Phase 5.2 §0 pre-flight uncovered.

### 2.6 `test_osm_client_logs_warning_on_non_200(caplog)`

- Use `httpx.MockTransport` to return a 406 response.
- Call `discover(...)`.
- Assert: returns `[]`; `caplog.records` contains one WARNING from
  `app.contrib.osm_overpass_client` whose message contains `status=406`
  and the tag/value pair. Regression guard against the silent-failure
  bug.

---

## §3 Conventions

- Don't add any new test deps; use the existing `pytest` + `monkeypatch`
  fixtures and stdlib `json` / `pathlib`.
- No live network calls. All `OsmOverpassClient.discover` invocations must
  be mocked.
- Don't modify `scripts/osm_overpass_pull.py` itself — the fix is already
  shipped.
- Ruff clean; pytest count should rise by exactly 4.

---

## §4 Definition of done

- New file `tests/test_phase5_osm_overpass_pull.py` with §2.1–§2.4 (4 tests).
- Tests §2.5 + §2.6 appended to `tests/test_phase4_osm_client.py` (2 tests).
- `python -m pytest tests/test_phase5_osm_overpass_pull.py tests/test_phase4_osm_client.py -v`
  passes all new tests.
- Full collect count goes from **1855 → 1861** (+6 tests).
- Single commit:
  `test(osm): osm_overpass_pull JSONL writer + client UA + warning surface`
  with `Co-authored-by: Cursor` trailer.

---

## §5 Reference

- The fix: `scripts/osm_overpass_pull.py` (the commit being tested)
- Pattern to mirror: `tests/test_phase5_osm_overpass_load.py`
- The load contract this test guards: `scripts/osm_overpass_load.py`
  `_iter_feature_elements` (line ~89) — wrapper-line shape with
  `obj["elements"]` iteration + `--tag`/`--value` filtering
- The RawHit shape: `app/contrib/osm_overpass_client.py`
  `_element_to_raw_hit` — `raw={"element": el, "tags": tags}`

---

*Pre-staged by Cowork primary, Phase 5 lane, Phase 5.2 session
(2026-05-15) immediately after shipping the fix. Dispatch artifact only —
operator chooses when to run Cursor.*
