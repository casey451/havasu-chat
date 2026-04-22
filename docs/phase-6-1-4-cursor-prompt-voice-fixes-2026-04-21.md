# Cursor prompt — Phase 6.1.4 (voice fixes + verification audit)

Canonical Markdown copy (2026-04-21). Paste into a new Cursor agent turn to run Phase 6.1.4.

**Prerequisite:** Phase 6.1.3 artifacts committed (`Phase 6.1.3: voice audit execution + report`). Owner decisions recorded in `docs/phase-6-1-3-owner-review-6-1-4-plan-2026-04-21.md`.

**Goal:** Implement **accepted** voice fixes; **reject** the `t3-25` finding (no change for that sample). Re-run `scripts/run_voice_audit.py --execute --confirm --yes` and confirm prior FAILs clear (or document any residual).

---

## Pre-flight (read-only)

1. `git log --oneline -3` — confirm the 6.1.3 commit landed.
2. `pytest -q` — confirm clean baseline (expect ~679+ passing tests per session baseline).
3. View current content of `app/chat/tier1_templates.py` HOURS render logic.
4. View current content of `prompts/system_prompt.txt` (relevant §8.2 section, if present).
5. View current content of `prompts/tier2_formatter.txt`.
6. Check for existing `_short_provider_display_name` (or similar helper) — confirm signature/behavior before reusing.

Hard gate: report output from these checks, then proceed without waiting.

---

## Owner decisions (authoritative)

| ID | Action | Primary target |
|----|--------|----------------|
| `t1-HOURS-03` | **ACCEPT** + MODIFY | `tier1_templates.py` — conditional **"is open"** vs **"'s open"** using a helper (e.g. `_short_provider_display_name`); rule: **> 2 words OR > 18 chars** → `"is open"`; else contraction allowed. Re-verify `t1-HOURS-01`, `t1-HOURS-02`, `t1-HOURS-03` strings. **Regression flag:** implementation may change HOURS response for providers besides Iron Wolf, including Footlite (e.g. `t1-HOURS-01`). Verification audit will surface any regression; if a previously-PASS sample flips to MINOR/FAIL after the rule is applied, **STOP** and report — the rule may need re-tuning. |
| `t3-01` | **ACCEPT** | `prompts/system_prompt.txt` — ban **don't-know + redirect + follow-up question** in one reply; one move only. |
| `t3-24` | **ACCEPT** + MODIFY | **`prompts/tier2_formatter.txt`** (not Tier 3 `system_prompt.txt`) — when user query matches **explicit-rec triggers** (handoff §8.4: e.g. "what should I do", "pick one", …), formatter must produce **§8.4 Option 3**: **one** committed pick + short **because**, **no** multi-venue menu, **no** trailing "what sounds good?" / open questions. |
| `t3-25` | **REJECT** | **No code change** for this finding — owner: response already matches handoff Option 3 shape (imperative + reason). Optional later: light "what to skip" pattern in `system_prompt.txt` only if owner reopens. |

**Deferred (document only, not 6.1.4):** Router option to **skip Tier 2 → Tier 3** for explicit-rec class; Tier 3 **context_builder** investigation for current date / "this weekend" resolution (`docs/known-issues.md` or phase note — **do not** block 6.1.4 on these).

---

## Implementation tasks

1. **`tier1_templates.py`** — Implement conditional HOURS (and any shared copy path) per rule above; keep changes minimal; add or reuse a small helper if needed.

2. **`prompts/system_prompt.txt`** — Add concise §8.2 rule + example for `t3-01` class failure (no double-move).

3. **`prompts/tier2_formatter.txt`** — Add explicit-rec / Option 3 block for formatter outputs; align wording with handoff §8.4 (single pick, rationale, optional skip — optional skip may be one line max if included).

4. **Tests:** Extend or add tests so HOURS conditional behavior is covered (at least one long-name vs short-name case). Tier 2 formatter: add/adjust tests if a test harness exists for formatter prompts or golden outputs; otherwise document manual verification.

5. **Do not** change `unified_router.py` for deferred router work unless owner explicitly expands scope.

---

## Verification

After edits:

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe scripts/run_voice_audit.py --dry-run
.\.venv\Scripts\python.exe scripts/run_voice_audit.py --execute --confirm --yes
```

Cost note: verification `--execute` run will incur roughly **~$0.20** in Haiku audit calls (similar to 6.1.3). Under the **$2.00** hard ceiling; no additional owner approval required given prior authorization at similar cost. If costs appear materially higher than expected, **STOP** and report.

- Expect **`t3-25`** may still show FAIL if auditor disagrees again — **document** in a short `docs/phase-6-1-4-verification-note.md` if owner wants to track auditor variance; do **not** chase `t3-25` further without owner direction.
- Expect **`t1-HOURS-03`**, **`t3-01`**, **`t3-24`** verdicts to improve to PASS (or MINOR only if auditor nitpicks).

Save new JSON as usual; optionally append date to results filename if runner overwrites.

---

## Commit (after verification)

One commit, suggested message:

```
Phase 6.1.4: voice fixes for HOURS, Tier 3 §8.2, Tier 2 explicit-rec
```

Body: bullet list of files touched + note deferred items.

---

## Scope fence

- **In scope:** `tier1_templates.py`, `prompts/system_prompt.txt`, `prompts/tier2_formatter.txt`, targeted tests.
- **Out of scope:** Router Tier 2 bypass, `context_builder.py` date injection (defer), `known-issues.md` unless owner asks, voice audit runner changes, amending 6.1.3 JSON.

---

## Acceptance

- `t3-25` unchanged by requirement (REJECT).
- Three accepted areas addressed in code/prompts.
- Tests green (`pytest` relevant subset or full).
- Verification audit run completed; results summarized for owner.

---

## STOP gates

- Tests fail after implementation → **STOP.** Report failing tests. Do **not** proceed to verification audit.
- Verification audit shows **NEW FAILs** that were not present in the original 6.1.3 results → **STOP.** Document and report before committing.
