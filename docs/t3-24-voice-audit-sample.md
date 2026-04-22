# Voice audit sample `t3-24` (Phase 6.1.3)

Reference summary. Source artifacts: `docs/phase-6-1-3-voice-audit-report.md`, `scripts/voice_audit_results_2026-04-21.json`, `docs/known-issues.md`.

## What `t3-24` is

`t3-24` is an **ID in the Phase 6.1.3 paid voice-audit matrix** (Tier-3-style open-ended row in the spreadsheet naming). The canonical row text and verdict live in `docs/phase-6-1-3-voice-audit-report.md` and `scripts/voice_audit_results_2026-04-21.json`. The matrix labels the row **`tier3`**, but the **same JSON** shows the live path was **`route_meta.tier_used`: `"2"`** (Tier 2), which matters for fixes.

## Query

**What should I do Saturday?**

Tagged in the audit payload as **`explicit_rec_query`**.

## Response (assistant text from that run)

```
Saturday's got some solid options depending what you're in the mood for.

If you want to bounce around, Altitude Trampoline Park opens at 9am with 90-minute or 120-minute jump sessions ($19–$24). It's a huge 22,000+ sq ft park with trampolines, dodgeball, and more.

For something more chill, Havasu Lanes does open bowling from noon to 9pm, and then switches to Rock & Bowl (cosmic bowling with black lights and party vibes) from 6pm to close. That's a fun Saturday night move.

If you've got kids 6+, The Tap Room Jiu Jitsu runs youth wrestling at 9am.

What sounds good to you?
```

## Auditor's reason for FAIL

- **Rule:** §8.4
- **Verdict summary:** The sample is **`explicit_rec_query`** but the answer follows **Option 2** (several suggestions + an open question) instead of **Option 3** (one strong, committed recommendation with rationale).
- **Notes (auditor):** Option 3 requires **one** confident pick when `explicit_rec_query` is true; this reply **lists three activities** and ends with an **open question** (“menu” vs “direct pick”).

Structured fields: `scripts/voice_audit_results_2026-04-21.json` under `verdicts` for `sample_id` `t3-24`.

## What “deferred at root” means for this case

Here it means **not fully solved by prompt tweaks alone**; the **underlying issue is routing / architecture**, not just Tier 3 copy.

- **`docs/known-issues.md`** logs this class of query as **Tier 2 retrieve-then-generate** when the parser is confident, which tends to produce **Option 2-style lists**; **§8.4** wants **Option 3** for explicit-rec. The **durable** fix called out there is **router-level**: detect explicit-rec triggers and **skip Tier 2 → Tier 3** (or equivalent), rather than only tightening `tier2_formatter.txt`.
- Follow-up docs (`phase-6-1-3-owner-review`, paste-for-owner supplement) stress that **`t3-24` was actually Tier 2 output**, so treating it only as `system_prompt.txt` was **mis-scoped** for a complete fix.
- **`docs/phase-6-1-4-verification-note-2026-04-21.md`** still records **`t3-24` as FAIL** after 6.1.4 work—so the session resume listing **`t3-24` deferred at root** means: **left for a later router / explicit-rec bypass (and/or Phase 7 revisit), not closed by the 6.1.4 prompt pass.**
