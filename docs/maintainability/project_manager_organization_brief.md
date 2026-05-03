<!--
PURPOSE: Onboarding brief for a project manager (e.g. Claude) with no prior
context on havasu-chat — what the product is, how the repo is meant to work,
organization risks as features accumulate, and a phased plan to stay out of
deep technical/process debt.

AUDIENCE: PM orchestrating work with Casey (owner) and implementation sessions
(Cursor, Claude coding, contractors). Read after docs/STATE.md and
docs/BACKLOG.md if you need live status; this file is stable “how we stay
organized” guidance.
-->

# Project manager brief — organization and scaling (zero prior context)

## 1. What you are managing

**Hava** is a conversational concierge backend for Lake Havasu City, Arizona: **FastAPI**, **SQLAlchemy**, **Postgres** in production (**Railway**), **SQLite** possible locally. It exposes chat (`POST /api/chat` is the sole chat entry after legacy route removal), public contribution intake, admin review UIs, and static assets. Chat is routed through a **Tier 1 / 2 / 3** pipeline (deterministic → structured SQL retrieval → grounded LLM); prompts live under `prompts/`; orchestration centers on `app/chat/unified_router.py`.

**Canonical architecture spine:** `HAVA_CONCIERGE_HANDOFF.md` (repo root). **Voice:** `docs/persona-brief.md`. **Repo map and doc index:** `docs/maintainability/project_index.md`.

## 2. Why organization matters now

The codebase will gain **many features**. Without discipline, teams dig holes that are hard to escape: duplicate specs (doc vs doc vs code), orphaned scripts, results committed next to source, unclear ownership of subsystems, and “tribal knowledge” in chat logs instead of **STATE** and **BACKLOG**.

This repo already invested in **canonical docs** and pruned historical markdown to reduce noise. The remaining risk is not lack of prose — it is **inconsistent enforcement**: root directory used as a scratch pad, `scripts/` mixing tools with run artifacts, thin **component documentation** relative to `app/chat/` surface area, and **gaps** called out in `project_index.md` §5 (no dedicated Railway layout page, no single API reference doc).

## 3. Authoritative process (do not bypass)

Casey and assistants operate under **`docs/WORKING_AGREEMENT.md`**: halt-and-report between steps, **no push without explicit approval**, UTF-8 commit messages without BOM, **component docs** (`docs/components/<name>.md`) updated **in the same commit** as behavior or public contract changes, and **`docs/STATE.md`** updated only at verified session close-out (not mid-flight). New Cursor sessions: **`docs/CURSOR_ORIENTATION.md`** and **`docs/CURSOR_NEW_CHAT_PLAN.md`** (Mode A vs B, read order).

**PM implication:** Schedule work in **small shippable slices** with explicit close-out (STATE / BACKLOG / POST_SHIP checklist when applicable). Avoid “big bang” reorganizations that mix twenty concerns in one branch.

## 4. Current-state truth (where to look)

| Question | Source |
|----------|--------|
| Production URL, deploy tip, recent ships, queued snapshot | `docs/STATE.md` |
| OPEN / DEFERRED / RESOLVED work, ship log | `docs/BACKLOG.md` |
| Stack, key files, tiers at a glance | `docs/PROJECT.md` |
| “Where does X live?” | `docs/maintainability/project_index.md` |
| Ops, env, checks | `docs/runbook.md` |
| Deferred bugs / spec-vs-code | `docs/known-issues.md` (edit only via its stated process) |

After any push to production, **`origin/main`** (or dashboard commit) should match **Railway** deployed revision — **`docs/STATE.md`** describes this expectation.

## 5. Organization plan (phased — recommended PM backlog)

Treat this as a **program** with gates, not one heroic PR.

### Phase A — Single source of truth (first)

- Ensure **`docs/STATE.md`** and **`docs/BACKLOG.md`** stay aligned with **git** and production after each ship.
- Resolve **doc vs code drift** when found (example class: operator docs still referencing removed HTTP paths).
- **Exit:** A new contributor can answer “what is deployed?” and “what is OPEN?” from those two files only.

### Phase B — Filesystem contract

- **Repo root:** Reserve for project spine (README, Procfile, requirements, alembic, handoff file, top-level packages). Operational clutter (logs, local DBs, ad-hoc PNGs) should live under a **documented** convention — e.g. ignored `local/` or `artifacts/`, and/or **`relay/`** for session scratch (see `relay/README.md`).
- **`scripts/`:** Separate **committed tools** from **generated outputs**; use or extend **`scripts/output/`** (gitignored) where appropriate; document in **`scripts/README.md`** what produces what. Decide explicitly which JSON/baseline files remain **tracked** and why.
- **Docs root:** Session transcripts and non-canonical dumps belong in **`docs/archive/`** (or equivalent) with a one-line rule in orientation or project index — not mixed with normative specs.

- **Exit:** Root and `scripts/` read as intentional; no silent “dump zone.”

### Phase C — Documentation depth where the code is complex

- Grow **`docs/components/`** for subsystems that change often (tier2 stack, contrib/River Scene, admin), tied to **`WORKING_AGREEMENT`** same-commit rule.
- Fill **`project_index.md` §5** gaps over time: **Railway service/env matrix**, **HTTP API sketch** (routes + auth), optional **CI query-battery** story — each as its own small ship, not a monolith.

- **Exit:** “Where does behavior X live?” has one indexed path; deploy story is not scattered-only.

### Phase D — Engineering gates (when ready)

- **CI:** lint + tests on PR (pytest may be awkward on some Windows dev machines; CI is the honest gate).
- **Formatting policy:** pick one tool and scope; avoid whole-repo cosmetic churn in feature PRs.

- **Exit:** Main stays verifiable; regressions are visible.

## 6. What the PM should avoid

- **Mega-refactors** that reorganize the tree and change behavior in one go.
- **Parallel specs** — one topic, one canonical doc; others link or defer (handoff §5 already defers “what’s next” to BACKLOG/STATE).
- **Silent commits** — anything that changes contracts ships with component doc + BACKLOG/STATE updates per agreement.
- **Assuming pytest ran** in every environment; note gaps and assign verification.

## 7. Suggested first actions (week one)

1. Read **`docs/STATE.md`**, **`docs/WORKING_AGREEMENT.md`**, **`docs/BACKLOG.md`**, **`docs/maintainability/project_index.md`**.
2. Open a **single BACKLOG epic** (or numbered item) titled e.g. “Repo hygiene & documentation hierarchy” with checkboxes for Phases A–D.
3. Land **Phase A** fixes first (truth + drift), then **Phase B** (root/scripts/docs archive policy) in **separate** approved commits.
4. Stand up a **lightweight recurring review** (monthly or per milestone): root listing, `scripts/` tracked files, STATE vs Railway, OPEN backlog count vs narrative.

## 8. Success criteria (six months out)

- New features land with **clear subsystem home**, **updated or new component doc** when contracts change, and **BACKLOG/STATE** reflecting reality.
- Onboarding a new developer or PM takes **one reading path** (orientation → STATE → BACKLOG → project index → components), not archaeology across chat logs.
- The team has **not** accumulated untracked root junk as “normal,” and **scripts/** does not become a graveyard of one-off outputs without a rule.

---

*This brief summarizes organization intent for PM-led execution; live priorities remain in **`docs/BACKLOG.md`** and **`docs/STATE.md`**.*
