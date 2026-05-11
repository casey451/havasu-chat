# Cursor Brief — Provider.slug field + backfill migration

> **Operator note:** paste this brief to a fresh Cursor chat. Sequential single-lane work; no parallel agents on this file set. Authored 2026-05-13 by Cowork primary; parallel-eligible with the ChatGPT Provider profile UX spec (different file set) and the CC rate-limiter §8 decisions memo (read-only, no file overlap).

---

## §0 Baseline confirmation (do this FIRST and report before touching code)

Before any edits, confirm and report:

1. `git log --oneline -3` — top of `main` should be `11b248f` (cold-pitch) on `597d9cb` (BACKLOG/STATE) on `aea87b8` (lint).
2. `git status` — should be clean.
3. `python -m pytest -q --collect-only 2>&1 | tail -3` — collected count should be **1429** tests.
4. `python -m alembic heads` — should be **single head `e7f8a9b0c1d2`**.
5. `python -m alembic current` — may differ from head; not blocking, just report it.

If any of those don't match, **halt and report**. Do not proceed.

If everything matches, proceed. Report each value back so the primary can confirm baseline before reviewing your work.

---

## §1 Why this lane exists

The Provider profile page route is `/provider/<slug>`. Provider currently has no `slug` column (`app/db/models.py:31` Provider class — confirm by reading lines 31–125). This lane adds the column, backfills it from `provider_name` for existing rows, makes new rows ingest with `slug` populated, and ships tests pinning the behavior. Purely additive; zero behavior change for current chat-route runtime since no application code reads `slug` yet.

This is gating work for the Provider profile page implementation (which itself is gated on the ChatGPT-drafted UX spec that's in flight in a separate lane right now). Ship this clean so the profile-page lane doesn't have to think about slug schema.

---

## §2 Reference: existing `_slug()` implementation to reuse

`app/contrib/parks_rec_loader.py:140`:

```python
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "untitled"
```

This is the pattern. It is currently a private helper in a loader module. **Extract it to a shared util** in this lane (see §4.1) and have both the migration and the model-side default-derivation call into the shared util. The loader's existing call site (`parks_rec_loader.py`) should keep working — it imports the new util instead of the local `_slug`. Verify by running `python -m pytest tests/ -q -k parks_rec` post-edit.

Note: `app/contrib/scrape_runner.py:67` has a different helper `_slug_now()` that's timestamp-based for filenames — **leave that one alone**, it's a different concern.

---

## §3 Slug semantics (what value a row should end up with)

For an existing Provider row, `slug` is derived from `provider_name` at migration time:

1. `base = _slug(provider_name)` — e.g. "Acme Plumbing, LLC" → `acme-plumbing-llc`.
2. **Collision handling.** If `base` is already in use by another Provider, append `-2`, `-3`, etc. — lowest unused integer ≥ 2. Implemented in the migration loop: track a set of slugs already assigned during the same migration run, and SELECT the existing slug values once at the start.
3. **Length cap.** If `base` exceeds 96 characters, truncate to 96 (then trim trailing hyphens). The collision suffix `-N` then appends after the truncated base; total can go to ~100 chars max. Column type: `String(120)` for headroom.
4. **Empty / null `provider_name`** should not happen (the column is `nullable=False`), but defensively: `_slug(None)` returns `"untitled"`; collisions on `untitled` get `-2`, `-3` like any other.

For new Provider rows created via the ingest paths, the same derivation runs at insert time. See §5 for which paths get the change.

---

## §4 File changes

### §4.1 New file: `app/utils/slug.py`

Create the directory `app/utils/` if it doesn't exist. New file with module docstring + two public functions:

```python
"""Shared slug utilities.

Pulled out of app/contrib/parks_rec_loader.py:_slug (which retains an import
re-export for back-compat) when Provider.slug landed 2026-05-13. The slug
shape is intentionally simple: ASCII alphanumerics + hyphens, lowercase,
no leading/trailing hyphens, "untitled" fallback for empty input.

Tests: tests/test_slug_util.py
"""

from __future__ import annotations

import re


def slugify(value: str | None) -> str:
    """Convert a free-text string to a URL-safe slug.

    Mirrors the historical _slug() helper in parks_rec_loader. Strips
    non-alphanumerics, collapses runs to single hyphens, trims hyphens
    from the ends, lowercases, and falls back to "untitled" for empty
    or non-alphanumeric input.
    """
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "untitled"


def make_unique_slug(base: str, used: set[str], *, max_length: int = 96) -> str:
    """Return ``base`` truncated to ``max_length`` if not in ``used``,
    otherwise append the lowest integer suffix ``-N`` (N ≥ 2) that yields
    an unused slug. Adds the chosen slug to ``used`` in-place.

    The truncation strips trailing hyphens left by the cut. The suffix
    is appended AFTER truncation; final length can exceed ``max_length``
    by the suffix width (e.g. 96 + len("-12") = 99). Callers that need
    a hard cap should pre-shrink ``max_length`` accordingly.
    """
    base = base[:max_length].rstrip("-") or "untitled"
    if base not in used:
        used.add(base)
        return base
    n = 2
    while True:
        candidate = f"{base}-{n}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        n += 1
```

### §4.2 Edit `app/contrib/parks_rec_loader.py`

Replace the local `_slug` definition (line 140) with a re-export so existing callers in that file continue to work without changes:

```python
# At the top with the other imports:
from app.utils.slug import slugify as _slug
```

Delete the existing local `def _slug(s: str) -> str:` block. The `re` import may become unused — if no other use remains in the file, drop the `import re` line at the top. (Run `python -m ruff check app/contrib/parks_rec_loader.py` after to confirm; auto-fix if possible.)

### §4.3 Edit `app/db/models.py` — Provider class

Add `slug` column to the Provider class. Anchored Edit only — do not rewrite the class. Insert immediately after the `district` column (currently at lines 98–101 per the directory-pivot schema commit `6f6ef79`; verify line offset at step 0 since the file may have moved):

```python
    # Directory pivot V1 follow-up (2026-05-13): URL-safe slug derived from
    # provider_name. Used as the route key for /provider/<slug>. Backfilled
    # by the f1a2b3c4d5e6 migration; new rows get a slug via the ingest
    # paths (see app/db/seed_helpers.py and scripts/ingest). Unique across
    # all providers; collision handling appends -2, -3, etc.
    slug: Mapped[str | None] = mapped_column(
        String(120), nullable=True, unique=True, index=True
    )
```

**Important — nullable in the model, NOT NULL after backfill.** The column is declared `nullable=True` in the model to match the migration's first stage; the migration's third stage flips the production constraint to NOT NULL after backfill completes. The model annotation stays `str | None` because the migration's NOT NULL flip happens at the DB layer; touching the model annotation later (when the backfill ticket for `category_id` lands) is when we'd revisit the annotation. **Don't change the annotation to `str` in this lane.**

### §4.4 New file: `alembic/versions/<rev>_provider_slug.py`

Generate a new migration with a unique revision id (pick a 12-char hex like `f1a2b3c4d5e6` — does not exist on disk; verify before writing).

```python
"""Add Provider.slug column + backfill from provider_name.

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-05-13 <fill at write time>

Adds a URL-safe slug column to providers, backfills from provider_name
with collision handling, and flips the NOT NULL constraint after the
backfill. See app/utils/slug.py for the slug shape.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "f1a2b3c4d5e6"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def _slugify(value):
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "untitled"


def _make_unique(base, used, max_length=96):
    base = base[:max_length].rstrip("-") or "untitled"
    if base not in used:
        used.add(base)
        return base
    n = 2
    while True:
        candidate = f"{base}-{n}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        n += 1


def upgrade() -> None:
    # Stage 1: add column nullable
    with op.batch_alter_table("providers") as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(length=120), nullable=True))
        batch_op.create_index("ix_providers_slug", ["slug"], unique=True)

    # Stage 2: backfill from provider_name with collision handling
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, provider_name FROM providers ORDER BY id")).fetchall()
    used: set[str] = set()
    for row in rows:
        slug = _make_unique(_slugify(row.provider_name), used)
        conn.execute(
            sa.text("UPDATE providers SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": row.id},
        )

    # Stage 3: flip NOT NULL constraint
    with op.batch_alter_table("providers") as batch_op:
        batch_op.alter_column("slug", existing_type=sa.String(length=120), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("providers") as batch_op:
        batch_op.drop_index("ix_providers_slug")
        batch_op.drop_column("slug")
```

Notes for Cursor:
- Use `batch_alter_table` for SQLite-friendliness (same pattern as the `e7f8a9b0c1d2` migration).
- The slug helpers are duplicated inside the migration file because Alembic migrations should not depend on application-layer modules (so old migrations keep working even if `app/utils/slug.py` is later moved or renamed). This is the project standard — confirm by reading the top of one or two existing migrations to verify pattern.
- Stage 2's SELECT is `ORDER BY id` for deterministic ordering (so collision suffixes get assigned to the same rows on every run — matters for reproducible test fixtures).
- The `_slugify` inside the migration uses positional args, no type annotations, to avoid any Python-version brittleness across the project's migration history.

### §4.5 Update ingest paths so new rows get `slug` populated

Search the codebase for where new Provider rows are inserted. Candidates (verify each one creates Provider rows — some may only update existing rows):

- `scripts/places_enrichment.py` — Places enrichment script
- `scripts/places_discovery.py` — Places discovery script
- `app/contrib/parks_rec_loader.py` — Parks & Rec ingestor
- `app/contrib/river_scene_pull.py` — River Scene scraper
- `app/contrib/river_scene.py` — related scrape entry
- `app/contrib/enrichment.py` — contribution-enrichment path
- `scripts/ingest/ingest_enrichment_csv.py` — CSV upsert
- Any seed scripts that create Providers from fixtures

For each path that does `Provider(...)` construction or `INSERT INTO providers`, add slug derivation using `app.utils.slug.slugify` + a collision check against existing slugs. **Do not duplicate `make_unique_slug` per call site** — if any call site needs uniqueness, factor a single shared helper (suggestion: `app/db/seed_helpers.py::derive_provider_slug(session, provider_name) -> str` that queries existing slugs and returns a unique one). If you find only one call site that creates new rows in production, this can be done at that one site; if you find multiple, prefer the helper.

**Out of scope:** updating any historical Alembic migrations that themselves seed Provider rows. Migrations should be immutable history; if any old migration seeds Providers without slug, leave it — Stage 2 of THIS migration will backfill those rows the next time `alembic upgrade head` runs.

Report which ingest paths you found and what you changed in each. If a path doesn't create new rows (only updates), call it out and leave it alone.

### §4.6 Tests

Two new test files. Use the project's pytest fixtures (no Alembic-spawning needed — `init_db()` already runs migrations).

**`tests/test_slug_util.py`** (new) — unit tests for `app/utils/slug.py`:

- `test_slugify_basic_strings` — `"Acme Plumbing"` → `"acme-plumbing"`, `"Hello, World!"` → `"hello-world"`, `"  trim me  "` → `"trim-me"`.
- `test_slugify_empty_input` — `None`, `""`, `"!!!"` all → `"untitled"`.
- `test_slugify_unicode_stripped` — `"Café Olé"` → `"caf-ol"` (non-ASCII removed; this is the documented behavior, not a bug — call it out in a test comment).
- `test_make_unique_slug_no_collision` — empty `used` set, base `"acme"` returns `"acme"`, set now contains `"acme"`.
- `test_make_unique_slug_collision_appends_2` — `used={"acme"}`, base `"acme"` returns `"acme-2"`, set adds `"acme-2"`.
- `test_make_unique_slug_collision_skips_to_next` — `used={"acme", "acme-2", "acme-3"}`, base `"acme"` returns `"acme-4"`.
- `test_make_unique_slug_truncation` — base of 200 chars gets truncated to 96 chars, trailing hyphens stripped, collision suffix appends after.

**`tests/test_provider_slug_migration.py`** (new) — integration tests that exercise the migration's backfill behavior. Pattern: use the existing `init_db()` fixture (it runs the full alembic chain), insert Provider rows in a test session, then directly invoke the backfill SQL or assert the slug column ends up populated. Look at `tests/test_directory_schema.py` for the exact fixture pattern this project uses (that's the analog for the schema commit).

- `test_provider_slug_column_exists_after_migration` — after `init_db()`, the `providers.slug` column exists with the correct type and NOT NULL constraint.
- `test_provider_slug_backfilled_from_provider_name` — insert a Provider with `provider_name="Acme Plumbing"` (use a route that bypasses slug derivation, OR construct the model directly with `slug=None` if your harness allows it — see how `tests/test_directory_schema.py` handles similar cases), then run the backfill logic and assert the row ends up with `slug="acme-plumbing"`. If the harness always derives slug at insert time, instead test the migration's `upgrade()` against a fresh DB with pre-existing un-slugged rows by snapshotting the migration logic into the test (acceptable).
- `test_provider_slug_collision_suffixed` — insert two Providers with the same `provider_name`, run backfill, assert one ends up `acme` and the other `acme-2`.
- `test_provider_slug_unique_constraint` — attempt to insert two Providers with `slug="acme"` directly; assert IntegrityError on the second.

If any of those tests can't be cleanly expressed against the project's existing test harness, fall back to lighter assertions (e.g. just test the `slugify` + `make_unique_slug` helpers exhaustively in unit tests, and add ONE integration test pinning that the column exists). Report which tests landed and why if you took fallback shortcuts.

---

## §5 What to do, in order

1. §0 baseline confirmation. Report values.
2. Create `app/utils/__init__.py` (empty if not already present) and `app/utils/slug.py` per §4.1.
3. Edit `app/contrib/parks_rec_loader.py` per §4.2 (re-export shim + drop dead `import re` if unused).
4. Edit `app/db/models.py` per §4.3 (anchored insert after `district` column).
5. Create migration file per §4.4. Verify revision id doesn't already exist.
6. Update ingest paths per §4.5. Report which paths were touched.
7. Write tests per §4.6. Report which tests landed.
8. Run `python -m pytest -q` end-to-end. Report final count (expected: 1429 + however many tests you added).
9. Run `python -m ruff check .` and `python -m ruff check --fix .` if any issues. Report.
10. Run `python -m alembic upgrade head` against a fresh dev DB to confirm migration applies cleanly. Report.
11. Report final HEAD diff summary (which files touched, line counts).

---

## §6 What NOT to do

- **Don't run `git add` or `git commit`.** Report when you're done; the operator commits.
- **Don't modify the `category_id` backfill story** — that's a separate ticket; this lane only handles `slug`.
- **Don't change the existing `Provider.category` string column** behavior.
- **Don't touch the chat-route runtime** — nothing in `app/chat/` should change.
- **Don't add a Pydantic schema field for `slug` yet** — that comes in the Provider profile page lane.
- **Don't `git commit --amend` anything** (Rule 12 of dispatch protocol).
- **If you discover existing seed data that would collide unexpectedly** (e.g. dozens of Providers all named "TBD"), report it as a finding; don't change the migration to silently work around — that's an operator decision.

---

## §7 Final report format

When you're done, paste back a single message with these sections:

1. **Baseline values** (HEAD, pytest count, alembic head, alembic current — from §0)
2. **Files touched** (paths + net line counts)
3. **Migration revision id chosen** + `down_revision`
4. **Ingest paths discovered and modified** (or "none found needing change")
5. **Tests added** (count + brief description of each)
6. **Final pytest count** (expected to be original 1429 + tests added)
7. **`python -m alembic upgrade head` result** (success / failure + any output)
8. **Ruff status** (clean / autofixes applied / remaining issues)
9. **Pragmatic deviations** — anything you adapted from this brief (e.g., different file location, different test shape) with the rationale. Be transparent; deviations are fine if reasonable.
10. **Anything that surprised you** or that the operator should know before they commit.
