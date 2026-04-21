# Phase 6.1.3 — Task 1: Env inspection (read-only)

**Date:** 2026-04-21  
**Scope:** Confirm local setup for `ANTHROPIC_API_KEY` before paid audit. No secrets or values captured.

**STOP:** Task 2 (audit execution) does not run until the owner replies with **“key is set, proceed with 6.1.3.”**

---

## 1. `.env` at repo root

**Result:** **`EXISTS`**

(Check: `Test-Path .env` in PowerShell, equivalent to `test -f .env`.)

---

## 2. `git check-ignore`

```text
.gitignore:1:.env	.env
exit=0 (ignored)
```

`.env` is ignored by Git.

---

## 3. Keys in `.env` (names only — no values)

From lines matching `^[A-Za-z][A-Za-z0-9_]*=`:

| Key name |
|----------|
| `ADMIN_PASSWORD` |
| `OPENAI_API_KEY` |

**`ANTHROPIC_API_KEY` is not present** in `.env` at inspection time. Add `ANTHROPIC_API_KEY=...` (or rely on a host-injected env var) before the audit.

---

## 4. `.gitignore` and `env`

Relevant line:

```1:1:.gitignore
.env
```

`.env` is listed explicitly.

---

## 5. `app/bootstrap_env.py` — path and loading

```python
# Project root = parent of `app/`
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DOTENV_PATH = _PROJECT_ROOT / ".env"
_LOADED = False


def ensure_dotenv_loaded() -> None:
    """Parse `.env` if present. Existing ``os.environ`` keys are never overwritten."""
    global _LOADED
    if _LOADED:
        return
    load_dotenv(dotenv_path=_DOTENV_PATH, override=False)
    _LOADED = True
```

- **Path:** Repo-root **`.env`** (`<project>/.env`), resolved from `app/bootstrap_env.py` via `parent.parent`.
- **Mechanism:** `python-dotenv` `load_dotenv(dotenv_path=..., override=False)` — **does not override** variables already set in the process environment (Railway / CI / shell wins).

### Does this run before `scripts/run_voice_audit.py` needs the key?

`scripts/run_voice_audit.py` imports `SessionLocal` from `app.db.database`. `app/db/database.py` calls `ensure_dotenv_loaded()` at import time, so **importing `SessionLocal` loads `.env` once** before Tier 3 and audit code run. No separate `bootstrap_env` import is required in the script for that path.

**Caveat:** With `override=False`, if `ANTHROPIC_API_KEY` is already set in the environment (even empty), `.env` will not replace it.

---

## Summary table

| Check | Result |
|--------|--------|
| `.env` exists | Yes |
| `.env` gitignored | Yes (`.gitignore` line 1) |
| `ANTHROPIC_API_KEY` in `.env` key list | **No** (only `ADMIN_PASSWORD`, `OPENAI_API_KEY` at inspection) |
| App `.env` path | Repo root `.env` via `bootstrap_env` |
| Loaded before audit script work | Yes, via `app.db.database` → `ensure_dotenv_loaded()` |

---

## Owner next step

Add `ANTHROPIC_API_KEY` to `.env` (or configure it in Cursor’s environment for agents). Then reply: **`key is set, proceed with 6.1.3.`** to run Task 2 (pre-flight, `--execute --confirm --yes`, transcript, narrative report; commits held until review).
