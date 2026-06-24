# Phase 5 — retire the `desert_base` lineage: EXECUTED (Casey-approved 2026-06-24)

**Status:** **DONE.** Casey chose "delete desert now (full Phase 5)" — accepting the loss of the
`THEME_DEFAULT=desert` instant-rollback — so the legacy desert lineage was deleted and Lake is now
the one and only theme.

## What changed

- **`app/core/theme.py`** — Lake is the only valid theme: `VALID_THEMES = {"lake"}`,
  `FALLBACK_THEME = "lake"`, `base_template_for()` always returns `base_lake.html`,
  `theme_default()`/`resolve_request_theme()` always resolve `lake`. So `?theme=desert`, a stale
  `desert` cookie, or `THEME_DEFAULT=desert` all normalize away to `lake`. **This is the rollback
  loss: there is no desert to fall back to.**
- **Template selection simplified** in every route — the `_t()`/`_tname()`/`_dir_template()`
  helpers and the ~24 inline `theme == "lake"` ternaries now resolve to the lake template directly
  (no dead desert branch).
- **Deleted:** `desert_base.html`, `home_sandstone.html`, `events_sandstone.html`, and the 37
  per-page desert twins (`about.html`, `account*.html`, `gas_prices.html`, `not_found.html`,
  `privacy_doc.html`, `provider_profile.html`, `search.html`, `today.html`, … — every non-`_lake`
  page template) + 4 orphaned `desert_*.css` files.
- **Converted to lake (kept):** `chat.html`, `mode_sandstone.html`, and the 6 `admin_*.html`
  pages now `extends "base_lake.html"` (base_lake mirrors desert_base's block contract, so this was
  a one-line change each; their content CSS stays). These had no `_lake` twin and are still
  rendered (`/chat`, `/night`+`/family`, `/admin/*`).

## Result

Every public page renders **one** header + **one** footer (`_partials/site_header.html` +
`_partials/site_footer.html`); `desert_base.html` no longer exists; no route references it.
~140 obsolete desert-shell tests were removed (they tested the deleted templates / "desert is the
default"); the lake surface is covered by the `test_lake_*` suites + the Phase 1–4 parity tests.

**Gates:** `ruff check .` clean · full `pytest -n auto` green.

## Rollback note (changed by this phase)

The instant `THEME_DEFAULT=desert` rollback is **gone** (by Casey's choice). To revert Lake now,
revert this branch's merge and redeploy. The `THEME_DEFAULT` env var is inert.

## Optional cosmetic follow-ups (not blocking)

- A few content CSS files keep a `desert_` prefix (`desert_chat.css`, `desert_home.css`,
  `desert_movies.css`, `desert_portal.css`) — still loaded by the converted lake pages, just a
  misnomer now; rename when convenient.
- `desert.css` remains in the static-asset registry (`app/core/static_assets.py`) and a few
  cache/a11y tests; prune if it's confirmed unused by any surviving page.
