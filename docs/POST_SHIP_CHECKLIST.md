# Post-ship checklist

This document is the closing-discipline runbook for every ship on Hava. It complements `docs/WORKING_AGREEMENT.md`, which defines what a ship is and how the pre-ship halt-and-report process works. This file defines what happens after the substantive commit lands.

The goal is to keep the canonical state docs (`STATE.md`, `BACKLOG.md`, component docs under `docs/components/`) aligned with the actual repo so a fresh Claude or Cursor session can read those docs and trust them.

## What counts as a ship

A "ship" is any substantive commit (or multi-commit sequence) that goes through the WORKING_AGREEMENT.md halt-and-report gates and pushes to origin/main. This includes:

- Code changes (features, fixes, refactors)
- Doc changes that affect external readers (component docs, working-agreement updates, BACKLOG opens/closes)
- Migrations and schema changes
- New components introduced

It does NOT include:

- Local-only edits that don't get committed
- WIP commits parked on feature branches
- The trailing STATE.md update commit itself — that's metadata, not a ship; see WORKING_AGREEMENT.md "STATE.md update discipline"

## Checklist

Run after the substantive commit(s) push successfully and `/health` verifies. Each item is independent — a ship may need any subset:

### 1. STATE.md update (always)

A separate commit, after the substantive ship and verification. Updates:

- `## Production` → `Deployed commit:` field — set to the substantive ship's tip SHA, not this metadata commit's SHA
- `## Recent commits` — prepend new entries; trim list to roughly 10 entries
- `## Recently shipped` — describe what changed in user-visible or architectural terms; reference the commit hash(es)
- `## Queued / open work` — adjust if the ship closed or opened items

Subject convention: `STATE.md: record <short ship description>` (e.g. `STATE.md: record component-doc-currency ship`).

This commit does not appear in STATE.md's own "Recent commits" or "Deployed commit" — it's a metadata commit on its own. See WORKING_AGREEMENT.md "STATE.md update discipline."

### 2. BACKLOG.md update (when applicable)

Update if the ship:

- **Closes a backlog item** — change status to RESOLVED or CLOSED, add resolution paragraph referencing the commit
- **Opens a new item** — append using existing format
- **Defers an item** — change status to DEFERRED, note the precondition

Skip if no backlog item moved.

If a Ship log entry is appropriate, append at the bottom — don't edit existing Ship log entries.

Subject convention: `BACKLOG.md: <verb> <item description>` (e.g. `BACKLOG.md: close formatter completeness item`).

### 3. Component doc update (when applicable)

If the ship modified code in a component that has `docs/components/<name>.md`:

- Doc updates ship in the **same commit** as the code change, not as a follow-up. See WORKING_AGREEMENT.md "Component doc currency."
- If the change is internal-only (no behavior change, no public contract change), no doc update is needed — but the commit message body must state the explicit no-update reasoning (e.g., "no doc update — internal refactor with no behavior change").

If the ship introduced a new component (new `app/chat/<name>.py` or similar), a new `docs/components/<name>.md` ships in the same commit as the component's introduction.

### 4. Production verification (always)

Per WORKING_AGREEMENT.md "Verification":

- **User-visible behavior changes** — multi-sample for LLM-mediated paths (single happy roll is not sufficient); deterministic checks for deterministic paths
- **Non-user-visible changes** (test additions, payload-shape changes, internal refactors, doc-only ships) — test coverage may be sufficient; note any deferred verification in BACKLOG.md

A verification failure halts the ship — decide between revert and follow-up explicitly. Don't paper over by altering criteria post-hoc.

### 5. `/health` check (always)

After Railway deploy:

```
curl https://havasu-chat-production.up.railway.app/health
```

Expected: HTTP 200, `{"status":"ok","db_connected":true,"event_count":<N>}`.

Note any drift in `event_count` — small drift is fine (catalog grows), large drift or absence is a finding.

If `/health` fails, halt — don't proceed to STATE.md update until production state is understood.

## What does NOT need updating per ship

These docs are stable and don't drift per ship — leave them alone unless their actual content changes:

- **`docs/PROJECT.md`** — architecture, stack, key files. Updates only when architecture changes (new tier, new entity type, new chat pipeline phase).
- **`docs/WORKING_AGREEMENT.md`** — collaboration discipline. Updates only when the agreement itself changes, and those updates are their own ships per the doc's "Evolving the agreement" section.
- **`docs/START_HERE.md`** — Claude session onboarding. Stable; updates only when the orientation framing changes.
- **`docs/CURSOR_ORIENTATION.md`** — Cursor session onboarding. Stable; updates rare.
- **`docs/POST_SHIP_CHECKLIST.md`** — this document. Updates only when the discipline itself changes.

The split is intentional: per-ship docs (STATE, BACKLOG, components) carry state and update frequently. Stable docs carry agreements and orientation, and update rarely. If you find yourself updating a stable doc on a per-ship basis, the doc has probably accumulated state it shouldn't be carrying — fix the doc shape, not the symptom.

## Edge cases

**Multi-commit ships.** When a ship is several commits (e.g., a working-agreement update plus the first instance of the new discipline plus a STATE.md trailing commit), STATE.md's "Deployed commit" anchors on the most recent substantive commit, not the trailing metadata. Substantive commits appear in "Recent commits"; the STATE.md update commit does not.

**Reverted ships.** If reverted before STATE.md updates, the STATE.md update never happens — the revert undoes the ship. If reverted after STATE.md was updated, the revert itself is a new ship and gets its own STATE.md update.

**Hot-fixes.** Same checklist applies. The discipline doesn't change for urgent fixes — verification gates exist to catch bad ships, not to slow good ones.

**Doc-only ships.** All five checklist items still apply, including `/health`. User-visible behavior verification is typically not required, but the test suite (if affected) and `/health` should still verify the deploy is healthy.

**Partial ships.** If a ship lands code but the matching component doc update was missed, the next commit is `<component>.md: catch up to <prior ship SHA>` with the explicit gap noted in the body. Don't pretend the gap didn't exist.

## Where to find more

- `docs/WORKING_AGREEMENT.md` — pre-ship discipline (halt-and-report, byte verification, BOM-free commits, fenced diffs, STATE.md update discipline, component doc currency)
- `docs/STATE.md` — what "current state" looks like in practice
- `docs/BACKLOG.md` — what "open work" looks like in practice
- `docs/components/` — what component docs look like in practice
