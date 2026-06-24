# Phase 5 — retire `desert_base` lineage: ANALYSIS + DEFERRAL (no deletion)

**Date:** 2026-06-23 · **Status:** **DEFERRED — Casey-gated, post-soak.** No code/template
deleted. This note is the deliverable; there is intentionally **no deletion PR**.

## Why Phase 5 does not run autonomously

FIX_SPEC §5 is conditional: *"only if still forked post-deploy … repoint those routes to the
Lake base and delete the dead lineage."* Tracing it into the code shows the desert lineage is
**not dead** — it is the **deliberate instant-rollback path**, and deleting it now would be both
destructive and a direct reversal of an explicit prior decision:

- `app/core/theme.py:37` — `FALLBACK_THEME = "desert"`.
- `app/core/theme.py:66` — `base_template_for()` defaults to `desert_base.html`.
- `theme_default()` reads `THEME_DEFAULT`; prod is set to **`lake`** (the Phase-8 flip was an
  **env** change), so **rollback = `railway variables --set THEME_DEFAULT=desert`** — instant,
  no deploy. Deleting the desert templates removes that rollback.
- Dozens of templates still `extends "desert_base.html"`; ~18 routes theme-switch.

**Established decision (project memory, 2026-06-19):** *"cleanup PR deletes desert_*/the flag —
do NOT prep until post-soak confirm — premature delete kills rollback. Casey chose 'wait for
soak'."* Phase 5 is exactly that cleanup. Per CLAUDE.md ("on a genuine judgment call, STOP and
ask") and the no-destructive-changes fence, this stays a **Casey-gated** action.

## The good news: the user-facing problem is already solved by the flip

The audit's "headers/footers differ page to page" was the **stale desert deploy**. On prod
(`THEME_DEFAULT=lake`), **every public page renders the one Lake header + footer**
(`_partials/site_header.html` + `_partials/site_footer.html`). The desert fork now only appears
under an explicit `?theme=desert` / rollback. So there is **no live inconsistency to fix** — only
dead-weight templates that must survive until rollback is no longer needed.

## Recommended sequencing (when Casey green-lights post-soak)

1. **Soak + manual AT + desktop eyeball** confirm lake is solid (Casey's existing gate).
2. Flip `FALLBACK_THEME`/code default to `lake` and **keep `?theme=desert` working** for one more
   cycle (so rollback still exists briefly).
3. Once confident, delete `desert_base.html` + `*_sandstone`/`*_desert` variants, repoint the
   theme switch, drop the flag. One header + one footer, single lineage.
4. `pytest` green; the theme-parity tests added in Phases 1–4 (nav parity, titles, claim search,
   labels) guard the lake surface through the cutover.

**Action for Casey:** confirm soak is complete, then say "do the desert cleanup" — that becomes a
focused follow-up PR. Until then, Phases 1–4 stand on their own and the rollback path is intact.
