# Phase 6.1.2 — Voice audit runner (delivery report)

**Date:** 2026-04-21  
**Scope:** Implement standalone `scripts/run_voice_audit.py` and update `docs/phase-6-1-2-audit-runner-proposal.md` per owner redlines. No edits to `tier1_templates.py`, `tier3_handler.py`, `unified_router.py`, or `prompts/`.

**Status:** Runner built; **`--dry-run`** emits a **full per-sample enumeration** (Tier 1: `user_query` + `assistant_text` from `try_tier1`; Tier 3: full `user_query` only — see below; Reference: full goldens). Full UTF-8 transcript: `docs/phase-6-1-2-dry-run-transcript-2026-04-21.txt`. Full **`--execute --confirm`** paid run remains **6.1.3**.

---

## Tier 1 matrix count — justification

The proposal table names **multiple seeded entities** for several sub-intents (three HOURS providers, three PHONE providers, two LOCATION targets, two WEBSITE targets including Bridge City Combat, two COST programs, Flips / Universal for AGE, etc.). The **~25–40** figure is an **upper bound** over “wide” local seeds, not a guarantee on every SQLite snapshot.

The first implementation pass effectively collapsed some of those cells (e.g. a single LOCATION / WEBSITE row), which produced **17** auditable Tier 1 rows and **zero** explicit matrix skips — that was **too aggressive** versus the proposal wording.

**Current runner (post-fix):**

- **HOURS_LOOKUP:** 3 rows — Footlite, Altitude, Iron Wolf (preferred ordering when present).
- **TIME_LOOKUP:** 2 rows — **hours path** resolves **Altitude** when that row has hours (matrix); **program schedule path** uses a provider **without** hours but with `schedule_start_time` (often *not* Altitude, because Altitude always satisfies TIME via the hours branch in `try_tier1` — documented in `matrix_note`).
- **PHONE_LOOKUP:** 3 rows — Footlite, Bridge City Combat, Flips.
- **LOCATION_LOOKUP:** 2 rows — Iron Wolf + Altitude (each matrix cell attempted).
- **WEBSITE_LOOKUP:** 2 matrix targets — **Bridge City Combat** then **Altitude**. In the stock seed, Bridge has **no** `website` → one **`branch_present_not_auditable`** row (`t1-WEBSITE-bridge-city-combat`); Altitude renders successfully.
- **COST_LOOKUP:** 2 rows — Altitude Open Jump + Iron Wolf Junior Golf Clinic.
- **AGE_LOOKUP:** up to **3** rows — prefers **Flips** then **Universal … Sonics** when those providers have an **active** program with `age_min`/`age_max` (same filter as `try_tier1`). In this DB, Flips programs carry no ages and Universal’s programs are all **`is_active=False`**, so the runner correctly falls through to the next providers that *do* satisfy production `try_tier1` (Iron Wolf, Aquatic Center, BMX in the captured run).
- **DATE_LOOKUP + NEXT_OCCURRENCE:** up to **two distinct providers** with future live `Event` rows linked by `provider_id` — **four** auditable lines when two such providers exist (`t1-DATE` / `t1-NEXT` + `t1-DATE-p2` / `t1-NEXT-p2`).
- **OPEN_NOW:** up to **four** distinct providers whose `hours` string parses for `_open_now_from_hours`, **Altitude first** when eligible.

On the migrated local seed used for the transcript: **24** Tier 1 auditable + **1** not-auditable (Bridge WEBSITE) ⇒ **25** Tier 1 matrix outcomes, matching the intent of the proposal (explicit seed-dependent skip for WEBSITE).

---

## Tier 3 and dry-run

**Dry-run does not call `route()`** — that would invoke Tier 2/3 LLMs and spend tokens. So Tier 3 samples in `--dry-run` list **full `user_query` + tags** only; `assistant_text` appears after **`--execute`**.

---

## `--execute` / seed gaps

If `DATE_LOOKUP` / `NEXT_OCCURRENCE` log `branch_present_not_auditable`, note in **6.1.3** as a **seed/linkage gap** (handoff §1b: `NEXT_OCCURRENCE` fires in production). `meta.future_live_events_null_provider_count` in the JSON supports that narrative.

---

## Git

**Not committed** pending explicit owner approval (“approved, commit and push”).

---

## Canonical dry-run transcript

See **`docs/phase-6-1-2-dry-run-transcript-2026-04-21.txt`** (UTF-8). Regenerate anytime:

```text
.\.venv\Scripts\python.exe -c "import subprocess, pathlib; r=subprocess.run(['.venv/Scripts/python.exe','scripts/run_voice_audit.py','--dry-run'], capture_output=True, text=True, encoding='utf-8'); pathlib.Path('docs/phase-6-1-2-dry-run-transcript-2026-04-21.txt').write_text(r.stdout, encoding='utf-8')"
```

Or interactively: `.\.venv\Scripts\python.exe scripts/run_voice_audit.py --dry-run` with a UTF-8 terminal (`PYTHONIOENCODING=utf-8` on Windows).
