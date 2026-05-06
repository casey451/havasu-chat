# bootstrap_env

`app/bootstrap_env.py` (~21 lines)

## Purpose

Load the local `.env` once, before any `app/` module that reads environment variables at import time runs. The file exists as a separate module (rather than inline in `app/main.py`) so the call to `ensure_dotenv_loaded()` can sit at the top of `app/main.py` ahead of every other `app.*` import — that ordering is what makes module-level env reads (`os.getenv("DATABASE_URL")`, `os.getenv("ADMIN_PASSWORD")`, etc.) see the local values during dev. In Railway / CI, env vars are already injected by the platform; the loader is `override=False` so platform values always win over `.env`.

## Public surface

**`ensure_dotenv_loaded() -> None`** — Idempotent. Parses `<repo>/.env` if present and merges keys into `os.environ` without overwriting existing keys. Subsequent calls are no-ops (guarded by a module-level `_LOADED` flag).

There are no other exports. Module-private constants (`_PROJECT_ROOT`, `_DOTENV_PATH`, `_LOADED`) drive the behavior.

## Inputs and outputs

**Input:** `.env` at the project root (`Path(__file__).resolve().parent.parent / ".env"`). Missing file is fine — `python-dotenv`'s `load_dotenv` returns `False` and the function still marks itself loaded.

**Output:** Side effects only. Returns `None`. Touches `os.environ` (only for keys not already set) and the module-level `_LOADED` flag.

## Conventions

**`override=False`.** Platform-injected env vars (Railway, GitHub Actions secrets, container env) are never clobbered by a stale local `.env`. This is the load-bearing property — without it, a developer's accidentally-committed dev key would override the production value.

**Idempotent via `_LOADED`.** Safe to call from multiple entry points (the FastAPI app, scripts, tests). Once it has run, `_LOADED = True` and subsequent calls return immediately.

**Repo-root resolution via `Path(__file__).parent.parent`.** Works regardless of CWD — `python -m` from anywhere, scripts run from `scripts/`, pytest from the repo root all resolve to the same `.env`.

**Call before any module-level env read.** `app/main.py` invokes `ensure_dotenv_loaded()` immediately after importing it, before any other `app.*` import. Reordering would break the contract: `app/db/database.py` and several other modules read `os.getenv` at import time.

## Known limitations and design notes

**No `.env` schema validation.** Anything in the file lands in `os.environ` (subject to the override rule). Typos in keys silently fail (`DATABSE_URL=` instead of `DATABASE_URL=` looks fine to this loader).

**Single `.env` file.** No layered `.env.local` / `.env.development` support. If layering is ever needed, this is the place to add it; current scope doesn't warrant the complexity.

**Process-wide flag.** `_LOADED` is a module global, so the load happens once per Python process. A test that wants to swap in a different `.env` after import has to re-set the flag and call again — not a supported flow; tests use `monkeypatch.setenv` instead.

**Dev-only utility.** In production (Railway), `.env` is absent and the function is effectively a no-op. The cost of calling it is one missing-file check per process startup.

## Configuration

No environment configuration of its own. The function is the configuration mechanism.

## Related

**Direct callers:**

- `app/main.py` — invokes at the top of the module, before every other `app.*` import (load-bearing).

**Direct dependencies:**

- `python-dotenv` — `load_dotenv` from third-party `dotenv` package.

**Cross-references:**

- `pyproject.toml` — `[tool.ruff.lint.per-file-ignores]` carves out `app/main.py` for E402 specifically because of the `ensure_dotenv_loaded()`-before-imports ordering. The per-file ignore is the reason this module exists as a separate import target rather than inline code (Slice 49).
- `docs/maintainability/railway_layout.md` — env-var matrix; explains why platform-injected values must win.
- `docs/components/database.md` — one of the modules that reads env at import time (`DATABASE_URL`).
