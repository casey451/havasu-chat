# Static UI extraction strategy (`app/static/index.html`) — decision

**Date:** 2026-05-06 (Slice 58).  
**Author:** Claude design pass + Casey approval.  
**Status:** Implemented (campaign closed 2026-05-06; see §10 Outcome).

## §1 Current shape (as-shipped)

`app/static/index.html` is a monolithic front-end artifact containing all three layers inline:

- **Structure:** chat shell markup (`header`, `#log`, composer form, footer links) plus calendar modal markup.
- **Styling:** a single inline `<style>` block with layout, bubbles, chips, feedback buttons, calendar grid/day detail cards, responsive + safe-area behavior.
- **Behavior:** a single inline `<script>` with two IIFEs:
  - chat IIFE: onboarding chips, send/receive flow for `/api/chat`, tier-3 feedback thumbs (`/api/chat/feedback`), onboarding API (`/api/chat/onboarding`), event share-link copy, dynamic DOM rendering.
  - calendar IIFE: `/events` fetch and in-memory date map, month nav, date-cell highlighting, selected-day detail rendering, event card keyboard/click handlers, event injection back into chat, `window.havasuChatCalendar` bridge.

This is functional and deploy-simple, but edit-risk scales poorly as UI behaviors grow.

## §2 Why extraction now

- **Single-file blast radius:** tiny UI changes touch a broad file section and can accidentally couple CSS/JS/markup edits.
- **Review ergonomics:** difficult diffs; logic and styling changes intermixed.
- **Reusability pressure:** calendar/chat helpers are not module-scoped reusable units.
- **Testing trajectory:** future front-end test seams are clearer when behavior is split into modules.

## §3 Options

### Option A — Keep vanilla stack; extract into split assets (recommended)

Move to `app/static/` multi-file layout while preserving server contract and runtime behavior:
- `index.html` (markup shell)
- `styles/*.css` (or one `index.css`)
- `js/chat.js`, `js/calendar.js`, shared helpers module(s)
- load via `<link>` + `<script type="module">`

**Pros:** lowest blast radius; no framework migration; preserves current API and deploy model; incremental slices possible.  
**Cons:** still custom vanilla architecture; requires lightweight module conventions.

### Option B — SPA framework rewrite (React/Vue/Svelte)

Full framework migration with bundler/toolchain.

**Pros:** stronger component model and ecosystem.  
**Cons:** highest blast radius; toolchain/deploy complexity jump; large rewrite risk for currently-working UI.

### Option C — Lightweight reactive layer (Alpine.js / htmx)

Adopt minimal framework primitives while retaining mostly server-hosted static layout.

**Pros:** smaller change than full SPA; cleaner state binding in hotspots.  
**Cons:** introduces new dependency model and mixed paradigms; still requires migration planning for existing imperative JS.

### Option D — Vanilla ES modules only (no CSS strategy change)

Extract JS into modules but leave CSS inline in `index.html`.

**Pros:** easy first step; immediate logic cleanup.  
**Cons:** leaves major maintainability burden in style layer; only partial win.

### Option E — Status quo

Keep monolith file, no extraction.

**Pros:** zero engineering cost now.  
**Cons:** ongoing maintenance drag and growing edit-risk as features continue to land.

## §4 Recommendation

**Option A (vanilla + split assets)** as the lowest-blast-radius move.

Rationale:
1. Preserves behavior and deployment shape while reducing single-file coupling.
2. The file is currently served as a static `FileResponse`, so unlike Slice 51's `main.py` extraction into Jinja2 templates, this move keeps a fully static deploy model with no templating layer.
3. Supports incremental migration slices (JS split first, CSS split second, final cleanup).
4. Avoids framework/tooling overhead that is not currently required for product velocity.

## §5 Implementation sketch (post-decision campaign)

*(slice numbers shown are placeholders; assigned when the campaign begins)*

| Slice | Scope | Notes |
|------|-------|-------|
| 59 | Extract JS into ES modules (`chat.js`, `calendar.js`, `shared.js`) | keep behavior parity; no API changes |
| 60 | Extract CSS into `app/static/styles/index.css` | preserve selectors and visual output |
| 61 | Final shell cleanup + naming conventions + docs sync | remove dead inline remnants |

Each slice runs parity verification (UI smoke + existing API interactions).

## §6 Alternatives rejected

- Framework rewrite now (Option B): disproportionate risk for current needs.
- Partial JS-only extraction as end-state (Option D): leaves CSS monolith debt.
- Do nothing (Option E): known maintenance burden remains.

## §7 Decision

Approved Option A on 2026-05-06. Extraction proceeds via JS-first (Slice 61), then CSS, then shell cleanup.

## §8 Verification posture for eventual extraction slices

- No server API contract changes (`/api/chat`, `/api/chat/onboarding`, `/api/chat/feedback`, `/events`).
- Visual parity checks across chat send/receive, onboarding chips, tier-3 thumbs feedback, calendar open/select/inject flow.
- Preserve keyboard + accessibility handlers already present in modal/event cards.

## §10 Outcome

Campaign closed 2026-05-06 in four ships matching the §5 sketch. End state: chat UI is a clean three-file vanilla structure (markup shell + JS modules with explicit imports + standalone stylesheet); no inline anything; no global-namespace bridge.

| # | Slice | Subject | SHA | Backlog |
|---|---|---|---|---|
| Precursor | — | docs(decision): record Option A approval (Slice 58 §7) | `7d57876` | (this doc §7) |
| 1/3 | 61 | refactor(static): extract JS to ES modules | `65f71e8` | #33 |
| 2/3 | 63 | refactor(static): extract CSS to /static/styles | `17b679e` | #34 |
| 3/3 (close) | 65 | refactor(static): bridge refactor + IIFE drop | `b4b83f9` | #35 |

**Surprises vs the §5 sketch:**

- **Slice 61 needed an `app.mount("/static", StaticFiles(...))` addition to `app/main.py`** that the sketch didn't predict. Step 0 audit found only `FileResponse(_STATIC_DIR / "index.html")` usage at `/`; the static directory wasn't otherwise exposed. Mount added in the same substantive commit; subsequent slices (63 CSS, 65 module reshape) inherited the mount with no further `app/main.py` changes.
- **Slice 61 had to preserve calendar.js's IIFE wrapper** (the §5 sketch implied uniform "convert IIFE to module" for both halves). Original line 887 of the inline script had a top-level `if (!overlay || !btn) return;` early-return guard that cannot live at module top level. Slice 61 kept the IIFE; Slice 65 closed the gradualism with `function initCalendar()` returning the API object or null.
- **Slice 65's bridge refactor needed an `import` in chat.js** rather than just a window-global rename. The sketch said "shell cleanup + bridge refactor" without committing to the import mechanism; the implementation chose ES module `import { havasuChatCalendar } from "./calendar.js"` to capture the dependency explicitly (rather than e.g. a custom event or attribute on `<body>`).
- **No `shared.js` materialized.** Slice 61's Step 0 audit found zero shared helpers between the chat and calendar IIFEs, so the campaign shipped without that file. The §5 sketch had implicitly anticipated one.
- **Pytest baseline unchanged at 965 across all four ships.** The campaign touched zero Python and zero tests.

**Backwards compatibility:** any external code depending on `window.havasuChatCalendar` (devtools snippets, browser extensions, unknown user JS) breaks post-Slice-65. Internal-app surface; acceptable per Casey's call at campaign approval.

**Pre-flight discipline across the campaign:** each implementation slice gated on Casey's production-verification of the previous one. Slice 61 cleared 2026-05-06; Slice 63 cleared 2026-05-06; Slice 65 cleared 2026-05-06. The discipline isolated regression-attribution variables — any post-deploy issue in slice N traces to slice N alone, not to the cumulative campaign.
