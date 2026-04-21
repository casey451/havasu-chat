# Phase 4.7 — completion report (Tier 3 anti-hallucination)

**Status:** Prompt change complete — **no commit** pending explicit owner approval.

---

## Pre-flight checks

```
Pre-flight checks:
  Check 1 (4.6 commit in history): PASS — `c2800a8 Phase 4.6: Voice cleanup - day-aware hours + external delegation` in last 20 commits.
  Check 2 (external-delegation rule present): PASS — `prompts/system_prompt.txt` lines 12–14 contain catalog-gap + CVB / golakehavasu.com / search pointer language (Phase 4.6).
  Check 3 (voice battery script): PASS — `scripts/run_voice_spotcheck.py` present and runnable.
```

---

## Rule added (verbatim)

Inserted in the **Hard rules** block **immediately after** the Phase 4.6 catalog-gap GOOD example (live music line) and **before** the “Contribution invitations…” bullet (Phase 3.2.2).

```
  Anti-hallucination (catalog truth): never name specific businesses, events, vendors, venues, days, times, addresses, or give a "worth it" verdict on something that is not backed by the Context rows you were given. You may still point to real external resources you did not invent (CVB at https://www.golakehavasu.com/, a tight web search) per the catalog-gap rule above — use those instead of filling in local specifics from general knowledge.
  BAD: "Yeah, the Saturday farmers market at London Bridge is worth it — it's the main weekend draw." (invents a vendor, day, and place not in Context)
  GOOD: "I don't have a farmers market in the catalog — try https://www.golakehavasu.com/ or local listings to see what's running this season."
```

---

## Phase 4.6 preservation

- The **catalog gaps** bullet (lines 12–14) and its BAD/GOOD pair are **unchanged**.
- No other Hard rules bullets were removed or edited.

**Note:** The older “Explicit recommendation triggers” GOOD example still names “Saturday farmers market at London Bridge” as an in-Context pick; the new rule clarifies that picks and “worth it” judgments must be **Context-backed** — when they are not, use gap + external pointer instead.

---

## Test expectation updates

**None** — `pytest` green with no assertion changes.

---

## Verification

| Check | Result |
|--------|--------|
| `pytest` | **530 passed** |
| `scripts/run_query_battery.py` | **116 / 120** |
| `scripts/run_voice_spotcheck.py` | **20 / 20** successful (smoke OK; 20 `## Query` sections; no `HTTP ERROR` in output) |
| Battery output | `scripts/output/voice_spotcheck_2026-04-20T21-54.md` |

**Pre-deploy caveat:** Production responses in that file still reflect **pre–4.7** deploy until Railway ships this commit; rerun after deploy to validate Q4.

---

## Commit workflow (when you approve)

Message, verbatim:

```text
Phase 4.7: Anti-hallucination rule for Tier 3
```

**Files to commit:** `prompts/system_prompt.txt` only.
