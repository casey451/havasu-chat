"""Regenerate docs/COMPLETE_PROJECT_HANDOFF.md from project-handoff + HAVASU_CHAT_MASTER."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PREAMBLE = r"""# Complete Havasu Chat — Project Handoff (Single-File Bundle)

**Generated:** Auto — run `python scripts/build_complete_handoff.py` after editing sources.
**Purpose:** One file for cold handoff: (1) full **events-search** narrative (`docs/project-handoff.md`) and (2) **verbatim** `HAVASU_CHAT_MASTER.md` (3-tier spec, build plan, prompts, tests, **all §9 seed YAML**).

## How to use

1. Read this preamble.
2. **Pack A** — Legacy shipped app (search, admin, sessions, env, history).
3. **Appendix** — Master spec for **programs/businesses** tiered chat (Track B).

**Sources:** `docs/project-handoff.md` + repo root `HAVASU_CHAT_MASTER.md`.

## Workspace rules (see `.cursorrules` in repo root)

- One phase at a time on the Lake Havasu roadmap; do not skip ahead.
- Session state in memory unless migrated.
- Phase 8.5 search/intent rules live in `app/core/intent.py` and `app/chat/router.py`.

## Track B implementation snapshot

| Step | File | Status |
|------|------|--------|
| 1 | `app/chat/normalizer.py` | Done |
| 2 | `app/chat/entity_matcher.py` | Done |
| 3 | `app/chat/intent_classifier.py` | Not done |
| 4 | `app/chat/tier1_templates.py` | Partial |
| 5–12 | tier2/3, context, router, API, analytics, tests | Not done |

Create `prompts/system_prompt.txt` and `prompts/voice_audit.txt` from Appendix §5 and §7. Add `anthropic` when building Tier 3 (owner approval).

---

# PACK A — Legacy events app handoff

*(Contents of `docs/project-handoff.md` follow.)*

---
"""

APPENDIX_HDR = """

---

# APPENDIX — FULL HAVASU_CHAT_MASTER.md

*(Verbatim `HAVASU_CHAT_MASTER.md` from repository root.)*

---
"""


def main() -> None:
    handoff = (ROOT / "docs" / "project-handoff.md").read_text(encoding="utf-8")
    master = (ROOT / "HAVASU_CHAT_MASTER.md").read_text(encoding="utf-8")
    out = ROOT / "docs" / "COMPLETE_PROJECT_HANDOFF.md"
    out.write_text(PREAMBLE + handoff + APPENDIX_HDR + master, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
