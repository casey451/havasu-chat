# Static UI extraction strategy (`app/static/index.html`) — decision

**Date:** 2026-05-06 (Slice 58).  
**Author:** Claude design pass + Casey approval.  
**Status:** Draft -> Decided after Casey's call.

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

Casey's call recorded here after review.

## §8 Verification posture for eventual extraction slices

- No server API contract changes (`/api/chat`, `/api/chat/onboarding`, `/api/chat/feedback`, `/events`).
- Visual parity checks across chat send/receive, onboarding chips, tier-3 thumbs feedback, calendar open/select/inject flow.
- Preserve keyboard + accessibility handlers already present in modal/event cards.
