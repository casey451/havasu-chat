# river_scene_pull

`app/contrib/river_scene_pull.py` (~215 lines)

## Purpose

**Orchestration layer** for the River Scene magazine lane: sitemap discovery → per-article HTML fetch/parse ( **`river_scene`** primitives ) → **duplicate detection** → **`Contribution`** creation → optional **auto-approval** into **`Event`** via **`approve_contribution_as_event`**. **`scripts/river_scene_pull.py`** is documented as a thin CLI wrapper around **`run_pull`**.

## Public surface

**`run_pull(start_date: date, *, dry_run: bool, http_client: httpx.Client | None = None) -> int`** — Exit-style return code: **`0`** success (even when individual URLs fail but **no** hard fetch errors — see below), **`1`** when **`fetch_sitemap_urls`** raises before iteration completes.

**Side effects (when not dry-run):**

- Creates **`Contribution`** rows through **`contribution_store.create_contribution`** with payloads from **`normalize_to_contribution`**.
- For **`payload.source == "river_scene_import"`**, attempts **`approve_contribution_as_event`** with **`EventApprovalFields`** derived from payload + parsed **`RiverSceneEvent`** (venue, URL, **`source_url`**, times).

**`dry_run: True`** — Still walks URLs and increments **`imported`** counter when a row *would* insert, but skips **`create_contribution`** / approval (loop **`continue`** after overlap flagging).

**Injection seam:** Optional **`http_client`** for tests / callers; default builds **`httpx.Client`** with **`REQUEST_TIMEOUT`**, **`USER_AGENT`**, **`follow_redirects=True`** from **`river_scene`**.

## Inputs and outputs

**`start_date`** — Passed through to printed summary only (**informational** in current body implementation); filtering logic lives in **`fetch_and_parse_event(..., today=date.today())`** for skip-past behavior.

**Counters printed at end:** **`fetched_urls`**, **`imported`**, **`auto_approved`**, **`auto_approval_failed`**, **`skipped_duplicate`**, **`skipped_past_or_unparseable`**, **`flagged_seed_overlap`**, **`errors`**.

**Return code nuance.** Inner **`body`** returns **`1 if errors else 0`** where **`errors`** counts per-URL fetch/parse failures — duplicate skips and auto-approval failures do **not** flip the exit code to 1 unless paired with those error increments.

## Internal structure

**`_norm_title` / `_find_seed_overlap`** — Legacy **seed-event** fuzzy collision detection (`difflib.SequenceMatcher` ratio > 0.85 on same calendar date); prefixes **`submission_notes`** with warning banner.

**`_duplicate_rs_article_import`** — Normalizes article URL via **`contribution_store.normalize_submission_url`**, checks:

1. **`Contribution.source_url`** / **`Event.source_url`**
2. Legacy **`NULL source_url`** contributions matching **`submission_url`**
3. Legacy events matching **`event_url`** when **`source_url`** NULL

**Main loop:** Session-per-URL (`SessionLocal()` context) for duplicate check; separate session inside **`normalize_to_contribution`** path for create/approve.

## Conventions

**Auto-approval is best-effort.** Exceptions log **`warning`** to stderr, increment **`auto_approval_failed`**, but leave contribution pending if approval fails.

**River Scene source gate.** Auto-approval block keyed off **`payload.source == "river_scene_import"`** — other sources won't hit **`approve_contribution_as_event`** here.

**Stdout/stderr CLI ergonomics** — Uses **`print`** / **`print(..., file=sys.stderr)`** for operator visibility.

## Known limitations

**Session churn** — Opens/closes many DB sessions per sitemap URL; acceptable for batch CLI scale.

**Seed overlap heuristic** — Title normalization strips non-alphanumeric; may false-positive/negative vs human judgment.

**Exit code vs partial failures** — Operators should read printed counters, not rely solely on process exit.

## Configuration

Inherited from **`river_scene`** (timeouts, user agent) and **`GOOGLE_*`** only indirectly if downstream approval triggers enrichment elsewhere — **not** inside **`run_pull`** itself.

## Related

**Dependencies:**

- **`docs/components/river_scene.md`** — fetch/parse/normalize primitives.
- **`docs/components/approval_service.md`** — **`approve_contribution_as_event`** path.

**CLI:** **`scripts/river_scene_pull.py`**.

**Tests:** **`tests/test_phase8_10_river_scene.py`** (imports **`run_pull`**, **`_duplicate_rs_article_import`**).

**Maintenance docs:** **`docs/maintainability/end_to_end_creation.md`**, **`docs/maintainability/river_scene_*`**.
