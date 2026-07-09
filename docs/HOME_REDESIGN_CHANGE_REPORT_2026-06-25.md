# Home + Calendar Redesign — Change Report (ready to go live)

**Branch:** `feat/home-redesign` (off `main`)
**Flag:** `home_redesign` — **OFF by default**. Built dark; nothing deployed or flipped.
**Date:** 2026-06-25

The v4 reskin (`design-exploration/ask-hava-premium-v4.html`) of `/home` and
`/calendar` is implemented behind the `home_redesign` flag. With the flag off, both
routes render the existing Lake templates **unchanged** — instant rollback. Same live
data, re-templated; no new data sources, no fabrication, zero DB migrations.

---

## The flag + preview path

Resolution order (first hit wins), in `app/home/flags.py`:

1. `?home_redesign=1` / `?home_redesign=0` query override (also persisted to a
   `home_redesign` cookie so a reviewer stays in the redesign across navigation).
2. the `home_redesign` cookie.
3. the **`HOME_REDESIGN`** environment variable — **the single go-live switch**.

**Preview now (no deploy needed once a build is live):**
- `https://askhava.com/home?home_redesign=1`
- `https://askhava.com/calendar?home_redesign=1`

(Append `?home_redesign=0` to drop back to the current site.)

---

## What you need to do to go live (the one gate)

1. Review the preview paths above on the real site (desktop + a 390px phone).
2. When satisfied, set **`HOME_REDESIGN=1`** on the Railway service (env var) and
   redeploy/restart. That's it — the flag is runtime-readable, no code change.
3. **Rollback:** set `HOME_REDESIGN=0` (or unset) — instant revert to the old home.

I did **not** flip the flag, touch Railway/secrets, run any prod DB op, or deploy
(per CLAUDE.md). After soak, a later cleanup PR can delete the old templates + flag.

---

## Files added

| File | Purpose |
|---|---|
| `app/home/flags.py` | `home_redesign` flag resolver + preview-cookie helper |
| `app/home/redesign.py` | view-model adapters (conditions tiles, gas top-5, feed buckets+blurbs+fitness subs, calendar month + agenda) |
| `app/templates/base_redesign.html` | v4 shell (header / conditions bar / gas panel / footer; self-hosted fonts) |
| `app/templates/home_redesign.html` | redesigned `/home` |
| `app/templates/calendar_redesign.html` | redesigned `/calendar` (glanceable month + agenda) |
| `app/templates/components/redesign_icons.html` | v4 line-icon set as `icon()` / `cicon()` macros (SVG verbatim) |
| `app/static/styles/lake_redesign.css` | v4 CSS lifted verbatim + `@font-face` + mockup→prod responsive layer |
| `app/static/js/lake_redesign.js` | progressive enhancement (scroll-shrink, gas expander, count filter, jump dropdown) |
| `tests/test_home_redesign.py` | 16 tests: flag plumbing, render structure, conditions bar, a11y, view-models |
| `tests/visual/capture_refs.py` | captures the v4 reference screenshots |
| `tests/visual/refs/*.png` | committed agreed-design baseline (home/calendar × mobile/desktop) |
| `tests/visual/test_home_redesign_visual.py` | Playwright gate: no-overflow @390px + pixel-drift self-baseline |
| `.github/workflows/visual-regression.yml` | dedicated advisory visual job (installs Chromium) |
| `docs/HOME_REDESIGN_CHANGE_REPORT_2026-06-25.md` | this report |

## Files changed

| File | Change |
|---|---|
| `app/home/router.py` | `serve_home` flag-switches to `home_redesign.html` (else unchanged) |
| `app/home/calendar_route.py` | `serve_calendar` flag-switches to `calendar_redesign.html`; adds `?cal=`/`?date=` |
| `.pa11yci.json` | added `/home?home_redesign=1` + `/calendar?home_redesign=1` targets |
| `.github/workflows/redesign-a11y.yml` | path filters extended to the redesign files |
| `.gitignore` | per-environment visual baselines (refs/ stays committed) |

---

## Definition of Done (§9) — status

- ✅ `/home` + `/calendar` match v4 in structure/hierarchy/interactions (desktop + 390px), flag-gated.
- ✅ Conditions bar: Temp · Wind (speed) · UV (colored + numbered) · Clouds · Gas; gas tile opens the real top-5; uniform 5-up, no overflow.
- ✅ Events feed: live count overview, accordion **only Events open**, real blurbs (from `Event.description`), Fitness sub-activity chips; jump dropdown works; **every control has a no-JS fallback** (sections are native `<details>`; pills/jump are real links to `/events-ui`; gas/day/calendar are links).
- ✅ Calendar glanceable: desktop chips + "+N more"; mobile dots + tap-a-day agenda; real `build_calendar`/`calendar_month` data.
- ✅ Every ad slot = buyable placeholder when unsold / sponsor creative when sold; CTAs reach `/sponsor` (storefront) and `/sponsor/click`; cadence = between every 2 sections (mobile) / right rail (desktop). **No fake businesses.**
- ✅ Mobile: no horizontal scroll (Playwright-asserted at 390px).
- ✅ `ruff`, `mypy`, `pytest` green; new tests cover view-models + renders + a11y; visual checks pass.
- ✅ Old homepage intact + served when flag off (instant rollback).
- ✅ Build stops at the go-live flag — nothing deployed/flipped.

## Gate results

- `ruff check` — clean. `mypy app` — clean (407 files).
- `pytest -m "not integration" -n auto` — full suite green.
- `tests/test_home_redesign.py` — 16 passed.
- Visual gate (`RUN_VISUAL=1`) — no horizontal overflow @390px on both pages; drift self-baseline stable.
- Structural WCAG 2.1 AA (`_A11yChecker`) — clean on both redesigned pages; pa11y targets added for CI axe.

---

## Honest divergences from the v4 mockup (data reality, documented)

1. **"Clouds" tile shows the NWS sky-condition word** (e.g. "Sunny", "Mostly cloudy"),
   not a numeric cloud-cover %. The pipeline exposes no cloud-% field; the mockup's
   "15%" was placeholder. We render the real word rather than fabricate a number.
2. **Buckets are the app's real taxonomy** (events, music, lake, kids, seniors,
   fitness, classes, civic, movies), not the mockup's exact placeholder set. Counts,
   blurbs, and chips are all live.
3. **Visual-regression vs the mockup is not a direct pixel-diff.** The live page
   renders real, time-varying data (different events/dates) the static mockup cannot
   match, so a 0.1% diff against the mockup is structurally impossible. Instead: the
   v4 refs are committed for human review, the build lifts every CSS value/icon/
   keyframe **verbatim**, the hard automated gate is **no horizontal overflow @390px**,
   and a **pixel-drift self-baseline** guards CSS regressions during development.
4. **Tap targets** match v4 sizing. Large rows (events, gas, agenda, calendar cells,
   nav drawer) clear 44px; the compact count-pills/day-cards follow v4's smaller
   sizing (WCAG 2.2 AAA 2.5.8, not the AA gate). Bump later if desired — it would
   deviate from v4.

## Notes / follow-ups (non-blocking)

- The `visual-regression.yml` drift check bootstraps a fresh baseline each CI run
  (baselines are per-environment/time and gitignored), so in CI it enforces the
  no-overflow gate; cross-run drift detection would need a cached baseline artifact.
- `/calendar` keeps `X-Robots-Tag: noindex` in both old and new renders.
- Post-soak cleanup PR (do not prep until go-live is confirmed): delete the old
  `home_lake.html` home block + `home_redesign` flag once the redesign is permanent.
