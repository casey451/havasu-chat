# Cursor Dispatch — `az_roc_client.lookup_contractor` real implementation (Playwright)

> **Operator note:** this is the **Option A** build from
> `outputs/az_roc_client_build_or_fallback_brief.md` — turning the
> `az_roc_client.lookup_contractor` stub into a working Playwright-based lookup.
> Cowork selected Option A per your "pick the best path" delegation; the brief's
> §3 lays out why (proven approach, the consumer scaffold is already built, the
> brittleness is bounded because it's a one-time low-volume pass).
>
> **Before you dispatch this — one informed-consent point:** Option A adds
> **`playwright`** as a project dependency and requires a one-time
> `playwright install chromium` (downloads a browser binary). That's a heavier
> dependency than anything currently in the repo. If you'd rather not take that on,
> the brief's Option D (manual verification pass — ~120-220 lookups by hand) is the
> stopgap and this dispatch can sit unused. Your call at paste time.
>
> **Scope lock (gotcha #18):** touches `app/contrib/az_roc_client.py`,
> `tests/test_az_roc_client.py` (new), `tests/fixtures/` (new fixture), and the
> dependency manifest ONLY. Strict-disjoint from the parallel Phase 6 lane. Does
> NOT touch `scripts/az_roc_verify.py` — the consumer stays as-is.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat
> (post-`ca5489a`, 2026-05-15). Brand-new `outputs/` file — safe under the
> parallel-chat scope lock.

---

```
You are a Cursor session implementing a real web-lookup for the havasu-chat project
(a Lake Havasu City local-business directory). You are replacing a stub with a working
Playwright-based scraper of a public government portal.

## §0 Baseline + reads

1. `git log --oneline -8` — confirm origin is on the post-`ca5489a` chain. Unfamiliar
   commits from the parallel Phase 5.1 field-entry chat (drift #5, crowd_notes, cleanup,
   etc.) are EXPECTED and scope-disjoint from your files — proceed, don't pull-block on them.
2. `git status` — clean.
3. `python -m pytest -q --collect-only 2>&1 | tail -3` — record the baseline collected count.
4. Read before changing anything:
   - `app/contrib/az_roc_client.py` — the stub you're replacing. Note the public surface:
     `lookup_contractor(client, business_name, *, search_url=...) -> AzRocMatch | None` and
     the `AzRocMatch` dataclass (`license_number`, `classification`, `status`, `raw`).
   - `scripts/az_roc_verify.py` — the consumer. It passes `client` (an `httpx.Client`)
     POSITIONALLY and `business_name`, memoizes by normalized name, throttles >=2.0s
     between live calls. **You must NOT change this file** — keep `lookup_contractor`'s
     signature compatible (see §2.1).
   - `tests/test_phase5_az_roc_verify.py` — existing consumer tests; shows how the client
     is mocked. Your new tests go in a NEW file (§3).

## §1 Context — the portal

The Arizona Registrar of Contractors public search lives at
`https://azroc.my.site.com/AZRoc/s/contractor-search` — a Salesforce Experience Cloud
site built with Lightning Web Components. There is NO official API. A plain HTTP GET of
the search URL returns only a JS shell — the results table is rendered into the DOM only
AFTER a JavaScript-driven search action runs. That is why this needs a real browser
(Playwright), not `httpx`.

Documented DOM (verify against the live portal as your first step — see §2.0):
- A search input; a Search button.
- Results render as a server-rendered `<table>`. Rows can use `rowspan` on the Business
  Name / address / phone cells when one business holds multiple licenses — each license
  is its own `<tr>`. Grey `<td colspan="9" data-label="line">` rows are separators — skip them.
- Page-size `<select class="slds-select">` offers 10 / 20 / 50.
- Pagination buttons: `button.slds-button.right-btn` (Next) / `button.slds-button.left-btn`
  (Prev), identified by class + inner `<svg data-key="right|left">`. Pagination is purely
  DOM-level (no network request) — the full result set loads on search.
- Per-license fields available in the table / detail page: license number, license status
  (ACTIVE / SUSPENDED / EXPIRED / REVOKED / CANCELLED), business name, qualifying party,
  primary classification code + description.

## §2 The build

### §2.0 Verify the DOM first
As your first real step, navigate to the search URL with Playwright, run one search for a
common term, and confirm the DOM matches §1. **If the DOM has materially diverged from the
spec, HALT and report** — don't build against a guessed structure.

### §2.1 Signature — keep it compatible
`scripts/az_roc_verify.py` calls `lookup_contractor(client, prov.provider_name)`. Keep the
exact signature: `lookup_contractor(client, business_name, *, search_url=...) -> AzRocMatch | None`.
The `client: httpx.Client` parameter is now UNUSED by the implementation (Playwright manages
its own browser) — keep it in the signature for call-site compatibility; a leading underscore
or a `# noqa`-style "intentionally unused" note is fine. Do not change `az_roc_verify.py`.

### §2.2 Behaviour
`lookup_contractor` should: launch a headless Chromium page, navigate to `search_url`, fill
the search box with `business_name`, click Search, wait for the results table, read the
table HTML, parse it, and return the best match as an `AzRocMatch` — or `None` if no results.
"Best match": prefer a row whose business name equals `business_name` case-insensitively;
otherwise the first ACTIVE row; otherwise the first row; `None` if the table is empty.
Populate `AzRocMatch.raw` with the parsed row dict so the consumer can stash it in
`attributes['az_roc']`.

A per-call browser launch is acceptable for v1 — `az_roc_verify.py` already throttles
>=2.0s between calls and this is a one-time ~120-220-row pass. Add a short module docstring
note that a reused module-level browser is the optimization if throughput ever matters.
Wrap browser launch/teardown so a crash on one lookup doesn't leak a process. On ANY
exception (timeout, navigation error, no table), log a warning and return `None` — the
consumer treats `None` as "no match" and must not crash.

### §2.3 Factor a pure parser
Extract `_parse_results_table(html: str) -> list[dict]` (or `-> list[AzRocMatch]`) as a
PURE function — no Playwright, no network — that takes the results-table HTML and returns
the structured rows, handling the `rowspan` business blocks and skipping `data-label="line"`
separator rows. This is the unit-tested core (§3); the Playwright navigation around it stays
thin and untested.

### §2.4 Dependency
Add `playwright` to the project's dependency manifest (match whatever's there —
`pyproject.toml` or `requirements.txt`). Note in the close-out that a one-time
`playwright install chromium` is required on any machine that RUNS `az_roc_verify.py`.
CI does NOT need the browser binary as long as the tests stay offline (§3) — but CI does
need the `playwright` package importable, so it belongs in the standard dependency set,
not an optional extra.

## §3 Tests — new file `tests/test_az_roc_client.py`

Build a synthetic HTML fixture from the §1 DOM spec — save it under `tests/fixtures/`
(e.g. `az_roc_results_sample.html`): a small results `<table>` with at least one normal
single-license row, one multi-license business using `rowspan`, and one
`data-label="line"` separator row. (If you can reach the live portal, base the fixture on
a real snippet; otherwise the documented structure is sufficient.)

Test `_parse_results_table` against the fixture:
- a single-license row parses to the right license number / status / classification / name
- a multi-license `rowspan` business associates BOTH license rows with the same business
- `data-label="line"` separator rows are skipped (not parsed as data)
- empty / no-results table -> empty list

Test the best-match selection logic (exact-name preference, ACTIVE fallback, None on empty)
— factor that into a pure helper too if it makes testing cleaner.

Do NOT write a test that drives a live browser or hits the network — Playwright navigation
stays untested (or behind a skip marker). Tests must be offline + deterministic.

After: `python -m pytest -q` (stays green, count = baseline + your new tests) +
`python -m ruff check app/contrib/az_roc_client.py tests/test_az_roc_client.py` (clean).

## §4 What NOT to do

1. Do NOT modify `scripts/az_roc_verify.py` — signature compatibility (§2.1) means it
   needs zero changes.
2. Do NOT add a test that hits the live AZ ROC site or the network.
3. Do NOT change `AzRocMatch`'s fields — the consumer's `_merge_az_roc_attrs` depends on
   `dataclasses.asdict` over the current shape.
4. No schema migrations — this is a scraper client, no DB schema involved.
5. Do NOT touch anything outside the §-scope-lock files.

## §5 Close-out (§13)

Report: §13.1 what changed, §13.2 files touched, §13.3 pytest delta + ruff status,
§13.4 deviations + rationale (especially: did the live DOM match §1, and the
playwright-dependency / `playwright install chromium` note), §13.5 operator commit
instructions (PowerShell-safe `-m` body — no embedded double-quotes per gotcha #16).
HALT after — single bounded build, one commit.
```

---

## Operator instructions

1. **Decide first:** are you OK adding `playwright` + a browser-binary install to the
   project? If yes, continue. If you'd rather do the manual stopgap (brief Option D),
   skip this dispatch.
2. Confirm the working tree is clean Windows-side.
3. Paste the fenced block into a fresh Cursor chat. Single bounded build — one HALT, one commit.
4. After Cursor's HALT: review the diff + the new test file, run `playwright install chromium`
   yourself once, then commit with Cursor's PowerShell-safe body.

After this lands, task #6 is closed and `scripts/az_roc_verify.py` can produce real
matches whenever Phase 5.3 (`home-property-services`) runs.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat (post-`ca5489a`,
2026-05-15). Lives at `outputs/cursor_dispatch_az_roc_client_playwright.md` — brand-new
`outputs/` file, safe under the parallel-chat scope lock. Implements Option A from
`outputs/az_roc_client_build_or_fallback_brief.md`.*
