# Phase 6.1.3 — Owner review & 6.1.4 plan (2026-04-21)

Authoritative audit artifacts: `scripts/voice_audit_results_2026-04-21.json`, `docs/phase-6-1-3-voice-audit-report.md`.

---

## 1. `t1-HOURS-03` (MINOR) — Iron Wolf possessive awkwardness

**Auditor catch:** *"Iron Wolf Golf & Country Club's open 9am–9pm on Monday."* — possessive-`s` on a long multi-word name reads awkward. Short names (*"Altitude's open…"*) work; long proper nouns break cadence.

**Decision: ACCEPT with MODIFY on fix direction.**

- Prefer a **conditional contraction rule**: if provider short display name (via `_short_provider_display_name` or equivalent) is **> 2 words** or **> 18 chars**, use **"is open"**; otherwise allow **"'s open"** to preserve §8.1 voice on short names.
- **Verify** `t1-HOURS-01` (Footlite) and `t1-HOURS-02` (Altitude) after implementation — auditor inconsistency may reflect different shortened names.

**6.1.4 target:** `app/chat/tier1_templates.py` (HOURS_LOOKUP).

---

## 2. `t3-01` (FAIL) — "I don't have X but ask me Y" double-move

**Auditor:** §8.2 — don't-know + keep going; single redirect or single clarify, not both.

**Decision: ACCEPT** the voice fix in `prompts/system_prompt.txt` (few-shot / explicit rule).

**Follow-up (not 6.1.4 scope):** Investigate whether Tier 3 context always surfaces **today** / **resolved "this weekend"** (`app/chat/context_builder.py`). Log in `docs/known-issues.md` or a later phase if the model hedges despite good context.

---

## 3. `t3-24` (FAIL) — Option 2 vs Option 3; **Tier 2**, not Tier 3

**Facts:** `route_meta.tier_used: "2"`. Response produced by **Tier 2 formatter**, not `system_prompt.txt` (Tier 3).

**Decision: ACCEPT** the voice issue (§8.4 Option 3 + §8.2 trailing question).

**Fix strategy (owner):**

- **6.1.4 (pragmatic):** **`prompts/tier2_formatter.txt`** — when query matches explicit-rec triggers (per handoff §8.4), produce **single-pick Option 3** voice (no three-venue menu, no trailing "what sounds good?").
- **Deferred (architectural):** Router-level **skip Tier 2 → Tier 3** for explicit-rec class — cleaner long-term; log as deferred decision.

---

## 4. `t3-25` (FAIL) — Option 3 framing

**Auditor:** Wants explicit *"I'd recommend this because…"*; current text is single-venue + imperative + reason (*"Take the kids… It's the quickest way…"*).

**Decision: REJECT** the FAIL as mis-scored vs handoff §8.4 Option 3 example (imperative + reason, no "I'd recommend because" boilerplate).

**Optional later:** MODIFY with light **"what to skip"** optional pattern in `system_prompt.txt` — not required for 6.1.4 unless owner revisits.

**6.1.4 target:** No change for `t3-25` unless owner overrides.

---

## Summary checklist (6.1.4)

| # | sample_id | Verdict | Owner action | Primary fix location |
|---|-----------|---------|--------------|----------------------|
| 1 | `t1-HOURS-03` | MINOR | **ACCEPT** + conditional contraction | `tier1_templates.py` |
| 2 | `t3-01` | FAIL | **ACCEPT** + context follow-up note | `system_prompt.txt` |
| 3 | `t3-24` | FAIL | **ACCEPT**, fix **Tier 2 formatter** (not Tier 3 system prompt) | `prompts/tier2_formatter.txt` |
| 4 | `t3-25` | FAIL | **REJECT** (auditor over-score vs handoff) | *(none)* |

**Net:** 3 of 4 findings drive code/prompt edits; 1 is pushback.

---

## Meta (future)

- **Auditor variance:** Consider dual-run on borderline samples in a future runner revision (6.1.4+).
- **Tier 2 vs Tier 3 routing:** Correct fix locus for `t3-24` is critical; supplement to narrative report was validated.

---

## Phase boundary (owner vote)

**(c)** — Close **6.1.3** with a **dedicated commit** of audit artifacts first; then a **separate 6.1.4** prompt for fixes + verification audit. Keeps review course-correction easy before code lands.

See companion Cursor prompts:

- `docs/phase-6-1-3-cursor-prompt-commit-close.md`
- `docs/phase-6-1-4-cursor-prompt-voice-fixes.md`
