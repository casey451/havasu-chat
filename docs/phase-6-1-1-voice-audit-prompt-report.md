# Phase 6.1.1 — Voice audit prompt file (delivery report)

**Date:** 2026-04-21  
**Scope:** Establish `prompts/voice_audit.txt` per Phase 6.1.1 workflow. No audit execution, no application code, no commit (owner will approve separately).

---

## Path taken

**Path B** — `prompts/voice_audit.txt` was **missing**; **`HAVASU_CHAT_MASTER.md`** contains **§7 VOICE AUDIT PROMPT** with explicit file destination `prompts/voice_audit.txt` and legacy **PROMPT 4 — VOICE AUDIT** text. No other prompt file in `prompts/` served as a voice-audit substitute.

---

## Rationale

1. **Authoritative spec:** Audits must score against **`HAVA_CONCIERGE_HANDOFF.md` §8 (Voice Specification, locked)** — not master §7 alone. Master §7 predates locked §8 in places (e.g. 1–2 sentences vs 1–3; blanket “no follow-up questions” vs intake/correction in §8.8–§8.9).

2. **Structured output for 6.1.2:** The new prompt requires **PASS / MINOR / FAIL**, **§8 subsection citations** for MINOR/FAIL, **empty `voice_rules_cited` for PASS**, **`suggested_rewrite` null if PASS**, and **JSON-only** responses for downstream aggregation — replacing master’s human-oriented PASS / NEEDS FIX / CUT layout.

3. **MINOR vs FAIL tiebreaker:** Explicit instruction to **prefer MINOR** when ambiguous and **reserve FAIL** for §8.2 hard-rule breaks, wrong Option 3 when `explicit_rec_query`, or clearly wrong mode patterns — reduces false FAIL noise in batch audits.

4. **Closing reinforcement:** Owner requested keeping the explicit lines that **PASS** must use `voice_rules_cited: []` and `suggested_rewrite: null` — minor redundancy for clearer model compliance.

---

## Artifacts

| Artifact | Path |
|----------|------|
| Voice audit system prompt (final) | `prompts/voice_audit.txt` |
| Read-first pre-flight + excerpts | `docs/phase-6-1-1-voice-audit-read-first-pass.md` |
| Revised draft archive | `docs/phase-6-1-1-voice-audit-prompt-draft-revised.md` |

---

## Final file contents (`prompts/voice_audit.txt`)

The on-disk file matches the approved draft from `docs/phase-6-1-1-voice-audit-prompt-draft-revised.md` (fenced body), including Unicode punctuation preserved from that source (e.g. curly quotes around “PROMPT 4”, “no follow-up questions”, “don’t know + keep going”). **Canonical reference:** open `prompts/voice_audit.txt` in the repo; it is **30 lines** as of this write.

Summary of sections:

- Canonical rules pointer to handoff §8.1–§8.9; intake/correction exception to blanket “no follow-ups” from §8.2.
- Input shape: JSON per sample (`sample_id`, `tier`, `intent_or_mode`, `user_query`, `assistant_text`, optional `tags`).
- Objective: judge `assistant_text` vs §8; PROMPT-4-style heuristics only where consistent with §8.
- Verdict definitions: PASS, MINOR, FAIL.
- MINOR vs FAIL tiebreaker paragraph.
- Rule citation: PASS → `voice_rules_cited` is `[]`; MINOR/FAIL → cite §8.x (Option 2/3 for §8.4 when relevant).
- Output: single JSON object schema + explicit PASS rails + optional JSON array for batched samples.

---

## Deferred to Phase 6.1.2

- **Audit runner:** Python (or script) that loads Tier 1 templates + curated ~30 Tier 3 samples, builds JSON payloads, calls Haiku with `prompts/voice_audit.txt` as system (or equivalent), collects JSON results.
- **Rendering harness:** Inline display for human review (per 6.1 plan).
- **Invocation details:** Model id, temperature, max_tokens, caching, rate limits, logging — not fixed in 6.1.1.
- **Aggregation / report generation:** Rollup into `docs/phase-6-1-voice-audit-report.md` is **6.1.3**; 6.1.2 may still define intermediate file shapes.
- **Validation:** Optional JSON schema or pytest for malformed auditor output.

---

## Git

**No commit** in this step — per owner instruction: commit and push only after explicit **“approved, commit and push.”**
