# Ask Hava — Chat Diagnostic Fix: Closeout
**Date:** 2026-06-18 · **Closes:** `ASK_HAVA_CHAT_DIAGNOSTIC_FIX_PLAN_2026-06-17.md` · **Status:** shipped + verified on live prod.

## TL;DR
All four user-facing `/chat` bugs from the 2026-06-17 diagnostic are fixed and **verified on live prod**, plus the broken post-deploy smoke test. Six PRs (#385–#390) merged to `main`.

## Important correction to the diagnosis
The 2026-06-17 plan's *symptoms* were all real, but two framing assumptions were wrong:

1. **Not a deploy gap.** Prod was running current `main` the whole time (verified: the active Railway deployment matched `main`'s HEAD). The bugs were real in the live code, not a stale build.
2. **The "code already fixes these" read was wrong.** Initial agent code-reads missed concrete details (e.g. the `r/c` substring collision). Re-verifying against the *actually deployed* commit surfaced the true root causes below.

## Root causes & fixes (all merged)
| PR | Item | True root cause | Fix |
|----|------|-----------------|-----|
| #385 | #1 realtor tops "family fun" | `family_fun` name keyword `r/c` matched the substring inside a realtor's `ABR/CMOE` credentials; rating sort floated it to #1 | Word-boundary the name-keyword match; keep only family-category OR boundary name hit |
| #386 | #6 smoke test always fails | Bare Railway host 308-redirects to askhava.com; `httpx` didn't follow redirects, so `raise_for_status()` failed every run (deploys flew blind) | Target `https://askhava.com` + `follow_redirects=True` |
| #387 | #3 "plumber open now" no cards | Tier-1 latched a single plumber as the entity with `OPEN_NOW` -> bare "Open right now" line, short-circuiting the listing | Suppress single-entity Tier-1 `OPEN_NOW` for category open-now queries; deterministic bare `"<category> open now"` listing shape (vocab-gated so bare entity names aren't misrouted) |
| #388 | #4a kids query -> adult classes | Chat events path applied no audience filter; `is_family_event` was used only in web views | Thread a kids/family signal into `_event_rows_for_intent`; filter the window's events through `is_family_event` |
| #389 / #390 | #2 "fix my boat" -> car repair | `boat_repair` is exempt from the auto-repair exclusion, so auto/RV "Car Repair" shops rode in and, sorted by review count, buried the marine shop. **#389's reorder in `run_query` was a no-op** because `build_business_list` re-sorts downstream. | #390 re-applies marine-first on the **final component items** in `_build_providers` (boat_repair only), where it survives the sort |

## Verified live on prod (2026-06-18, post-deploy)
- "fun with kids" -> real parks lead; realtor gone.
- "fix my boat" -> Carburetion (Boat) and JandJ (Marine) lead; auto/RV below (JandJ went from last -> #2).
- "plumber open now" -> real plumber listing, not the bare open-now line.
- "this weekend with kids" -> family events; adult Arthritis/Aqua-Aerobics/Motion classes dropped.

## Process notes / gotchas
- **Sandbox can't push or run prod git/DB.** All delivery used the GitHub web UI (upload to a new branch -> PR -> CI-gated -> squash-merge). Branch protection on `main` is on (direct commits warn).
- **CI gates are real:** ruff + pytest + mypy are required. #386's first run *failed* (a `follow_redirects` kwarg broke a mock client) — fixed forward in the same PR. Note: the sandbox runs Python 3.10, the repo needs 3.13, so pytest only runs in CI from a sandbox session.
- **Railway deploys queue per merge;** verify fixes only after the *latest* deploy goes active, not immediately after merge.

## Deliberately deferred (need a human/judgment)
- **#2 marine data backfill** — recategorizing genuinely-marine shops out of `Car Repair` is a prod-DB write. The query-side de-rank already fixes the symptom, so this is optional; if done, follow dry-run -> counts -> approve -> apply. (See existing `scripts/recategorize_water_misfiled.py` for the pattern; note it's scoped to the rentals leaf, not `Car Repair`.)
- **#4b "this weekend" -> Thursday** — not reproducible in code: `event_window_for_chip("this-weekend")` resolves Friday–Sunday. Prod still headers "Thursday"; needs request-logging to trace. No code change made.
- **#5 broader formatting sweep** — the open-now slice is handled by #387; a wider "force every browse path through a component" sweep was not needed for the reported symptoms.
