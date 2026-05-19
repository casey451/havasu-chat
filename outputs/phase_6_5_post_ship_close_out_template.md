# Phase 6.5 Post-Ship Close-Out Template

> **What this is:** the reusable Cowork-primary rhythm for closing out Phase 6.5 (homepage rebuild + 8 themed group tiles + Today in Havasu conditions strip placeholder + What's on at this venue region hook) when Cursor returns with its §12 final report. Pre-positioned 2026-05-20 so the close-out cycle is fast when Phase 6.5 ships. Mirrors the Phase 7.5 close-out template shape but specific to 6.5's UI-completion deliverables.
>
> **Author:** Cowork primary, 2026-05-20.
>
> **Instantiate as:** `outputs/phase_6_5_close_out.md` when Cursor returns with its §12 report.

---

## §1 Pre-flight verification (do this BEFORE declaring ship)

```powershell
# 1. Confirm Cursor did NOT git-commit (constraint per wrapper)
git status --short
# Expected: M lines on app/templates/home.html + provider_profile.html + maybe home/router.py + ?? lines for new themed_tile.html + conditions_strip.html + venue_events_region partial + new CSS files + new tests/test_phase6_homepage*.py / test_phase6_venue_events_region.py

# 2. Confirm alembic head UNCHANGED (Phase 6.5 ships no migration)
python -m alembic current
# Expected: c9d0e1f2a3b4 (head; same as pre-6.5; matches Phase 7's alembic head)
python -m alembic heads
# Expected: c9d0e1f2a3b4 (SINGLE head; multi-head trap avoided)

# 3. Confirm pytest passes
python -m pytest -q
# Expected: 2133+ passed (Phase 7 baseline) + 12-18 net-new from 6.5 = ~2145-2151 passed
# Ruff clean per Cursor's §12 claim

# 4. Acceptance-gate spot-check (UI rendering — operator browser)
python -m fastapi run app.main:app
# Then in browser:
# - / (homepage) — verify hero with search bar (Phase 6.4 preserved) + 8 themed group tiles + Today in Havasu strip placeholder
# - / — verify snowbird-panel-include anchor still renders Phase 7's panel (logged-in Oct-Apr; absent otherwise)
# - /group/<slug> — verify tile clicks navigate correctly
# - /provider/<slug> — verify What's on at this venue region anchor exists but absent (no events yet; Phase 9 fills)
```

---

## §2 Acceptance-gate verification

Per `outputs/cursor_dispatch_prompt_phase_6_5.md` §"Expected files touched" + master plan §4 Phase 6 deliverables:

| Gate | Status | Verification |
|---|---|---|
| (a) Homepage rebuild (hero + 8 themed group tiles + Today in Havasu strip placeholder) | ✅ / ❌ | Visit `/` in browser; verify all 4 elements render. Phase 6.4's `<!-- search-bar-include -->` anchor preserved in hero (search bar still works). Phase 7's `<!-- snowbird-panel-include -->` anchor preserved (snowbird panel renders for logged-in Oct-Apr users). |
| (b) 8 themed group tiles content | ✅ / ❌ | 4 themed-group tiles (Eat & Drink + Health & Fitness + On the Water + Home & Auto) link to `/group/<slug>` (6.4 routes); 4 solo-category tiles link to `/category/<slug>` for Events / Outdoors-parks-trails / Lodging & VR / Public-civic-resources. Tile counts pulled from `app/groups/themed_groups.py` helpers. |
| (c) Conditions strip placeholder | ✅ / ❌ | "Today in Havasu" element renders below hero with "Conditions data coming soon — Phase 8" copy. No real data wired. Phase 8 fills this in. New CSS at `app/static/styles/components/conditions_strip.css`. |
| (d) "What's on at this venue" region hook on profile | ✅ / ❌ | `<!-- venue-events-region-anchor -->` exists in `app/templates/provider_profile.html`; region conditional on `entity.events relationship non-empty`; renders absent when no events tied (which is all entities at this point; Phase 9 wires the data). |
| Phase 6.4 search bar still works | ✅ / ❌ | `<!-- search-bar-include -->` anchor preserved; search input + Ask Hava pill both still in hero. Anchored-extension approach (not wholesale rewrite). |
| Phase 7 snowbird panel still works | ✅ / ❌ | `<!-- snowbird-panel-include -->` anchor preserved; panel renders for logged-in Oct-Apr users; absent otherwise. |
| Tests | ✅ ≥12-18 new tests pass; full suite green | New `tests/test_phase6_homepage.py` + `tests/test_phase6_venue_events_region.py` |
| Ruff | ✅ clean | |
| Alembic head | ✅ unchanged at `c9d0e1f2a3b4` (no migration shipped) | `python -m alembic current` |

**All gates met:** Phase 6.5 is SHIPPED. Proceed to §3.

---

## §3 Substantive findings + deviation triage

Common Phase 6.5 deviations to expect (per dispatch wrapper §"DEVIATION INVITATIONS"):

| Deviation type | Default disposition |
|---|---|
| Themed tile partial shape (single shared vs 8 separate) | **Accept** if Cursor picked one consistent approach; flag if inconsistent across the 4 themed + 4 solo tiles |
| Tile count source (`themed_groups.py` helpers vs direct EntityCategory count) | **Accept** if reads cleanly; flag if it duplicates Phase 6.4's helper surface |
| Conditions strip placeholder copy | **Accept** ("Conditions data coming soon — Phase 8" or similar); flag if Cursor went static-stub instead of honest-empty (the wrapper said honest-empty was recommended) |
| Venue-events empty state shape (region absent vs single-line placeholder copy) | **Accept** either choice; both are defensible. Cleanest = region absent (no clutter; Phase 9 fills with real events) |
| Homepage section ordering | **Accept** if hero → tiles → conditions strip → snowbird panel flow makes sense |
| Tile layout (2-col mobile / 4-col desktop) | **Accept** standard Tailwind-equivalent CSS grid |
| Wholesale-rewrite vs anchored-extension of home.html | **REVERSE if wholesale** — wrapper said anchored-extension; preserving 6.4's `<!-- search-bar-include -->` + 7's `<!-- snowbird-panel-include -->` is critical |
| Touching `<!-- snowbird-panel-include -->` anchor region (Phase 7's) | **REVERSE** — Cursor 6.5 should preserve, not touch, that anchor; gotcha #18 home.html anchor coordination |

**Red flag:** if Cursor wholesale-rewrote `home.html` (lost the anchors), the Phase 6.4 search bar + Phase 7 snowbird panel break. Re-dispatch with explicit anchor-preservation guidance.

**Yellow flag:** if Cursor added themed group tile #5 (e.g., a "Things to Do" tile pointing at a placeholder `/group/things-to-do/coming-soon`), Cursor pulled forward Phase 9 scope. The wrapper said default = 4+4 (4 themed + 4 solo); Things to Do is Phase 9. **Discuss** — could accept if the placeholder is operator-decide; could reverse + defer to Phase 9.

---

## §4 Commit batch recommendation (Rule 8)

**Single substantive commit + 0-1 fixup commits.**

```powershell
# Stage Cursor's 6.5 changes (verify nothing unexpected)
git status --short
# Expect: M lines on home.html + provider_profile.html + maybe home/router.py + home.css
# Plus ?? lines for new themed_tile.html + conditions_strip.html + new CSS files + new tests

git add app/templates/home.html `
        app/templates/provider_profile.html `
        app/templates/components/themed_tile.html `
        app/templates/components/conditions_strip.html `
        app/static/styles/components/themed_tile.css `
        app/static/styles/components/conditions_strip.css `
        app/static/styles/home.css `
        app/api/routes/home.py `
        tests/test_phase6_homepage.py `
        tests/test_phase6_venue_events_region.py

git commit `
  -m "feat(phase6.5): homepage rebuild + 8 themed group tiles + conditions strip placeholder + venue-events region hook" `
  -m "Per master plan sec4 Phase 6 + outputs/cursor_dispatch_prompt_phase_6_5.md. (a) Homepage rebuild via anchored extension on home.html: preserves Phase 6.4 <!-- search-bar-include --> anchor + search bar + Ask Hava pill in hero; preserves Phase 7 <!-- snowbird-panel-include --> anchor + panel; ADDS Browse section with 8 themed group tiles + ADDS Today in Havasu conditions strip placeholder + ADDS new anchor comments <!-- conditions-strip-anchor --> + <!-- themed-tiles-anchor --> for Phase 8 + future references. (b) 8 tiles: 4 themed (Eat & Drink + Health & Fitness + On the Water + Home & Auto -> /group/<slug>) + 4 solo (Events + Outdoors + Lodging & VR + Public Civic -> /category/<slug>). New app/templates/components/themed_tile.html partial (~50 lines; reusable across all 8 tiles); tile counts from app/groups/themed_groups.py + direct EntityCategory count. (c) Conditions strip placeholder: new app/templates/components/conditions_strip.html (~30 lines) with 'Conditions data coming soon -- Phase 8' copy; honest empty pattern. New app/static/styles/components/conditions_strip.css. Phase 8 fills the data wiring. (d) Venue-events region hook on provider_profile.html: new <!-- venue-events-region-anchor --> + Jinja conditional rendering region only when entity.events relationship non-empty; absent until Phase 9 events scraper subsystem fills it. Pytest <PRE> -> <POST> (+<DELTA> net-new across 2 new test files). Alembic head unchanged at c9d0e1f2a3b4 (no Phase 6.5 migration). Ruff clean. <DEVIATIONS_NARRATIVE>"
```

---

## §5 STATE.md + master plan ledger updates

### STATE.md prepend (top of "Recently shipped")

```markdown
- **Phase 6.5 — Homepage rebuild + 8 themed group tiles + Today in Havasu conditions strip placeholder + "What's on at this venue" region hook SHIPPED on origin (2026-05-XX, post-Phase-6.4 + post-Phase-7).** Completion of the Phase 6 Tier 1 UI lane. Commit `<SHA>` (single feat + close-out chain). **(a) Homepage rebuild** via anchored extension on `home.html`: preserves Phase 6.4's `<!-- search-bar-include -->` anchor (search bar + Ask Hava pill in hero) + Phase 7's `<!-- snowbird-panel-include -->` anchor (snowbird panel for logged-in Oct-Apr users). Adds Browse section with 8 themed group tiles + "Today in Havasu" conditions strip placeholder ("Conditions data coming soon — Phase 8" — honest-empty pattern). New anchor comments `<!-- conditions-strip-anchor -->` + `<!-- themed-tiles-anchor -->` for Phase 8 + future references. **(b) 8 tiles:** 4 themed (Eat & Drink + Health & Fitness + On the Water + Home & Auto → `/group/<slug>` from Phase 6.4) + 4 solo (Events + Outdoors-parks-trails + Lodging & VR + Public-civic-resources → `/category/<slug>`). Tile counts pulled from `app/groups/themed_groups.py` + direct `EntityCategory` count. **(c) Conditions strip placeholder** at new `app/templates/components/conditions_strip.html`. Phase 8 fills the data wiring (lives at the `<!-- conditions-strip-anchor -->`). **(d) "What's on at this venue" region hook** on `provider_profile.html`: new `<!-- venue-events-region-anchor -->` + Jinja conditional rendering region only when `entity.events` non-empty; absent until Phase 9 events scraper subsystem fills it. Pytest `<PRE>` → `<POST>` (+`<DELTA>` net-new across `tests/test_phase6_homepage.py` + `tests/test_phase6_venue_events_region.py`). **Alembic head unchanged at `c9d0e1f2a3b4`** (no Phase 6.5 migration). Ruff clean. Close-out at `outputs/phase_6_5_close_out.md`. **Phase 6 lane COMPLETE** — 6.1 + 6.2 + 6.3 + 6.4 + 6.5 all SHIPPED. Next: **Phase 8a** (conditions + alerts; fills the strip placeholder) + **Phase 9** (events scraper + Things to Do themed group + venue-events region fill). **CI:** ✅ green at SHIP.
```

### master_build_plan.md §4 Phase 6 ship-line append

Append below the existing Phase 6.4 entry under "Shipped (incremental)":

```markdown
- **Phase 6.5 — Homepage rebuild + 8 themed group tiles + conditions strip placeholder + venue-events region hook (2026-05-XX, commit `<SHA>`):** Fifth sub-phase of Phase 6 shipped — **Phase 6 lane COMPLETE**. Anchored extension on `home.html` preserves Phase 6.4 + Phase 7 anchors + adds Browse section with 4 themed-group tiles (`/group/<slug>`) + 4 solo-category tiles (`/category/<slug>`) + Today in Havasu conditions strip placeholder (Phase 8 fills) + venue-events region hook on `provider_profile.html` (Phase 9 fills). New partials at `app/templates/components/themed_tile.html` + `conditions_strip.html`. New CSS at `app/static/styles/components/themed_tile.css` + `conditions_strip.css`. Pytest `<PRE>` → `<POST>` (+`<DELTA>` net-new). Alembic head unchanged at `c9d0e1f2a3b4`. Ruff clean. Close-out at `outputs/phase_6_5_close_out.md`. **Phase 6 lane COMPLETE** — Tier 1 UI surface fully delivered.
```

---

## §6 Post-ship verification

```powershell
git push origin main
git log --oneline -5
python -m alembic current  # c9d0e1f2a3b4 (head)
python -m pytest --collect-only -q | tail -3  # ~2145-2151 collected
ruff check app/ tests/
```

CI sanity (GitHub Actions runs automatically on push) — expect ✓ green within ~5 min.

---

## §7 Carries forward

- **Phase 8a dispatch** still ready (wrapper SHA-patched at `outputs/cursor_dispatch_prompt_phase_8.md`). Phase 8a now has TWO empty placeholders to fill: (1) the Today in Havasu conditions strip Phase 6.5 ships; (2) the chat conditions-awareness from Phase 7. Phase 8a's wrapper already covers both.
- **Phase 9 dispatch** still ready (wrapper at `outputs/cursor_dispatch_prompt_phase_9.md`; SHA slots pending Phase 8 ship). Phase 9 fills the venue-events region anchor Phase 6.5 just shipped.
- **Phase 7.5 dispatch** may still be in flight or shipped. The HALT 3 flag-flip gate is independent of Phase 6.5.
- **Operator action items walkthrough** still queued (~75 min total per `outputs/operator_action_items_walkthrough.md`).
- **AirNow API key registration + USGS/Nixle browser-verify** are Phase 8 prereqs; not blocked by Phase 6.5 ship.

**Phase 6 lane COMPLETE** is the headline ledger event. Tier 1 UI surface is fully delivered: unified Hava card grammar + category landing pages for all 12 active slugs + district chip + ranking + seasonal hours + map view + boat-access mode + 4 themed group landing pages + search bar + homepage rebuild + 8 themed group tiles + conditions strip placeholder + venue-events region hook.

---

*Authored by Cowork primary at the post-`cc73a06` session (2026-05-20; during Cursor 7.5's HALT 3 polish-lane grind window). Lives at `outputs/phase_6_5_post_ship_close_out_template.md`. Instantiate as `outputs/phase_6_5_close_out.md` when Cursor returns with its §12 report. Phase 6 lane COMPLETE at 6.5 SHIP — this template is the closure artifact for that arc.*
