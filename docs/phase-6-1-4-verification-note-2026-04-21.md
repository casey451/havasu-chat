# Phase 6.1.4 — verification note (2026-04-21)

## Pre-flight (executed)

- `git log --oneline -3`: `c899bfb` Phase 6.1.3…, `a51c162` Revert…, `549e777` …
- `pytest -q`: **679 passed** before edits; **681 passed** after (+2 HOURS template tests).
- `_short_provider_display_name` in `app/chat/tier1_templates.py`: splits on em dash, ≤36 chars keeps full prefix else first token.

## Code / prompt changes (final tree)

- `app/chat/tier1_templates.py` — Day-aware HOURS: possessive `'{short_name}'s open'` only when short display name has **≤2 words and ≤18 chars**; else `HOURS_LOOKUP_DAY_LONG` / `HOURS_LOOKUP_DAY_CLOSED_LONG` (`… is open …` / `… is closed …`).
- `prompts/system_prompt.txt` — §8.2 one-move rule + BAD/GOOD for don’t-know + redirect + follow-up (no second round of extra bullets — see below).
- `prompts/tier2_formatter.txt` — Explicit-rec trigger list aligned to handoff §8.4 strings; Option 3 block (single pick, no menu, no trailing questions).
- `tests/test_tier1_templates.py` — Long-name vs short-name HOURS cases.

## Voice audit — pass 1 (canonical for this phase)

Saved as `scripts/voice_audit_results_2026-04-21-phase614-verify.json` (identical to `scripts/voice_audit_results_2026-04-21-pass1.json`). The repo’s tracked `scripts/voice_audit_results_2026-04-21.json` from Phase 6.1.3 was **not** overwritten.

Pass 2 results were discarded after a **new FAIL** on `t3-07` (see below).

Summary: **52 PASS / 0 MINOR / 3 FAIL / 0 ERROR** (vs 6.1.3: 51 / 1 / 3 / 0).

- **Cleared:** `t1-HOURS-03` → **PASS** (Iron Wolf uses `is open` phrasing). Footlite (`t1-HOURS-01`) and Altitude Monday (`t1-HOURS-02`) remain **PASS** with `is open` (Footlite 4 words; Altitude short name before em dash is 3 words → non-possessive path).
- **Still FAIL:** `t3-01` — model still produced redirect + “or let me know…” in one reply (Tier 3). **Deferred:** `context_builder` should inject **today** / resolved **“this weekend”** so the model does not hedge on dates; auditor may also treat any “I don’t have the date” + URL as §8.2 violation until wording stabilizes.
- **Still FAIL:** `t3-24` — Tier 2 output is closer to a single pick; auditor cited Option 3 framing / “community-credit anchor” (subjective bar).
- **Still FAIL:** `t3-25` — per owner **REJECT**; do not chase.

## Voice audit — pass 2 (discarded for canonical JSON)

Second `--execute` after extra prompt tightening caused **new FAIL `t3-07`** (trailing question + worse shape vs pass 1). Per STOP gate, those prompt edits were **reverted**; pass 1 JSON kept as canonical.

**Cost:** two full execute runs ≈ **2× ~$0.20** Haiku audit spend (order-of-magnitude).

## Commit

**Not committed** — pending owner review per instructions.
