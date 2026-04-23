# Voice audit waivers — 2026-04-23

Companion to `voice_audit_results_2026-04-23.json` (git SHA f982941,
post-remediate run at 50cf425). Two samples waived per §9.5 threshold
policy: "Every FAIL is either remediated via prompt tuning or waived
with a written rationale recorded alongside the audit results artifact."

---

## t3-02 — WAIVED (Tier 1 template scope)

**Sample:** "What time does the BMX track open Saturday?"
**Auditor verdict:** FAIL §8.2 — response lists Tue/Wed/Thu hours,
no acknowledgment of Saturday gap.

**Waiver rationale:** `route_meta.tier_used = "1"` — this is a Tier 1
template response, not Tier 3 LLM synthesis. `system_prompt.txt`
governs Tier 3 output only; Tier 1 renders from `tier1_templates.py`
hardcoded paths. The day-specific gap-handling fix belongs in
`tier1_templates.py` and is scoped to a follow-on Tier 1 templates
phase. A known-issues entry will be filed separately. Voice
fundamentals are not implicated — this is a template rendering omission,
not a voice spec violation.

**Resolution path:** Tier 1 templates phase (follow-on). Re-evaluate
in Phase 8.12 v2 audit.

---

## t3-24 — WAIVED (retrieval dependency + catalog composition)

**Sample:** "What should I do Saturday?"
**Auditor verdict:** FAIL §8.4 Option 3 — response gives single-provider
specifics (Altitude) without landscape framing opener or competing
alternatives; defaults to children's venue for a general query.

**Waiver rationale:** Two rounds of `system_prompt.txt` patching
shifted the structural shape of the response but did not clear the
auditor. The underlying causes are retrieval-dependent:

1. **Content mix:** The 25-provider seed catalog skews heavily toward
   children's activities. With no non-children providers dominating
   the context window for a general "what to do" query, the model
   defaults to the most available category regardless of prompt
   instruction.
2. **No event data in context:** The owner's stated priority — surface
   non-recurring events first for "what should I do" queries (Desert
   Storm, car shows, marathons) — requires Phase 8.9 event ranking to
   surface event data in the Tier 3 context window. Prompt instructions
   to "prioritize events" cannot act on events that aren't retrieved.
3. **Voice fundamentals are clean:** firsthand voice, no hallucination,
   no community-credit phrasing, no §8.1 blocklist violations. The
   failure is structural (Option 3 format) and content (catalog
   composition), not voice-fundamental.

**Resolution path:** Phase 8.9 (event ranking) will provide
non-recurring event data for explicit rec queries. Phase 8.11 (bulk
import) will diversify available providers beyond kids activities.
Phase 8.12 v2 audit will re-evaluate this query class against the
expanded catalog with event retrieval active.
