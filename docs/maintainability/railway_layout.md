<!--
PURPOSE: Single reference for the Hava production deployment on Railway — process
types, environment variables, database wiring, and deploy flow. Consolidates facts
previously spread across the runbook, Procfile, nixpacks.toml, and app boot code.

AUDIENCE: Operators and contributors who need a single place to answer "how is
this app deployed and what does Railway inject?"

This is not a substitute for `docs/runbook.md` (incident playbooks) or
`HAVA_CONCIERGE_HANDOFF.md` (product architecture).
-->

# Railway layout — Hava production

Production URL (canonical in `docs/STATE.md`): **`https://havasu-chat-production.up.railway.app`**

Deploy trigger: pushes to **`main`** on the GitHub repo linked to the Railway project (auto-deploy). Build and start commands are declared in-repo (`nixpacks.toml`, `Procfile`) — Railway picks these up via Nixpacks.

## Deployment basics

| Topic | Value |
|-------|--------|
| **Production URL** | `https://havasu-chat-production.up.railway.app` |
| **Build / install** | `pip install -r requirements.txt` (see `nixpacks.toml` `[phases.install]`) |
| **Start command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (identical in `Procfile` and `nixpacks.toml` `[start]`) |
| **Process type** | Single **web** process (no separate worker in repo config) |
| **Platform-injected** | **`PORT`** — bound by uvicorn; do not hardcode a listen port in app code |

## Process types

- **Web:** one uvicorn process. `Procfile` and `nixpacks.toml` both start **`uvicorn app.main:app --host 0.0.0.0 --port $PORT`**. There is no `release` phase or second process type in the repository; migrations run at **app boot** (see below).

## Database

- **Resolution:** `app/db/database.py` — `get_database_url()` reads **`DATABASE_URL`** from the environment. If unset or empty, the app uses a **local SQLite** file at the project root (`events.db` / `sqlite:///...`). On Railway, **`DATABASE_URL`** must be set to the Railway Postgres connection string.
- **Engine kwargs:** SQLite URLs get `check_same_thread=False` in `connect_args`. Postgres (and other non-sqlite) URLs use `pool_pre_ping=True` (see `_engine_kwargs`).
- **Migrations / schema:** `init_db()` in `app/db/database.py` is invoked from the FastAPI **lifespan** in `app/main.py` at startup. It runs Alembic `upgrade` or `stamp` head depending on whether `alembic_version` and existing tables are present (see code for the full branch logic).

## Environment variables (matrix)

### Required for production (typical)

| Variable | Role |
|----------|------|
| **`DATABASE_URL`** | Postgres connection string on Railway; without it the app falls back to bundled SQLite (wrong for production). |
| **`ANTHROPIC_API_KEY`** | Tier 2 / Tier 3 / optional LLM router (Anthropic); tiers degrade gracefully if unset but chat quality suffers. |
| **`OPENAI_API_KEY`** | Hint extractor (`app/chat/hint_extractor.py`) — gpt-4.1-mini call for session hint extraction. Without it, hint extraction returns None and the pipeline continues. (Sole OpenAI caller in app code today; see Backlog #17 for the helper-extraction trigger.) |
| **`ADMIN_PASSWORD`** | Cookie auth for admin HTML/API (`app/admin/auth.py`). |

### Optional / feature flags

| Variable | Role |
|----------|------|
| **`USE_LLM_ROUTER`** | When truthy (`1`, `true`, `yes`, `on`), enables optional Haiku routing (`app/chat/llm_router.py`). Default off in production per component doc notes. |
| **`OPENAI_MODEL`** | Overrides default OpenAI model (code defaults e.g. `gpt-4.1-mini` where used). |
| **`GOOGLE_PLACES_API_KEY`** | Contribution enrichment / Places client; optional — enrichment degrades if unset. |
| **`RATE_LIMIT_DISABLED`** | Truthy values (`1`, `true`, `yes`, `on`; case-insensitive) disable slowapi rate-limit checks for the whole process. Used by `tests/conftest.py` for test isolation. See `app/core/rate_limit.py`. |

### Platform-injected

| Variable | Role |
|----------|------|
| **`PORT`** | Listen port for the web process (Railway sets this; matches Procfile / nixpacks `$PORT`). |

### Script / smoke / ops (examples)

| Variable | Role |
|----------|------|
| **`HAVASU_SMOKE_BASE`**, **`HAVASU_SMOKE_WAIT`** | Smoke scripts (e.g. `scripts/smoke_phase52_contributions.py`) default base URL and wait. |
| **`CLEANUP_MIN_RS_CONTRIBUTIONS`**, **`CLEANUP_MIN_RS_EVENTS`** | Floors for `scripts/cleanup_non_river_scene.py` (default `71`). |

## `.env` loading

`app/bootstrap_env.py` calls `load_dotenv(..., override=False)` once. **Existing `os.environ` keys are never overwritten** — so Railway- and CI-injected variables always win over a local `.env` file.

## Health checks

- **Route:** `GET /health` (`app/main.py`).
- **JSON shape (typical):** `{"status": "ok", "db_connected": true|false, "event_count": <int>}`. On DB errors, the handler may still return **200** with `db_connected: false` and `event_count: 0` (see `docs/runbook.md` quick reference).

## Deploy flow (high level)

1. **Push** to `main` → Railway **build** (`pip install -r requirements.txt`).
2. **Boot** → uvicorn loads `app.main:app`.
3. **Lifespan** → `init_db()` runs Alembic as needed.
4. **Serve** on **`PORT`**.
5. **Verify** — `GET /health` and spot-check chat/admin as appropriate (`docs/POST_SHIP_CHECKLIST.md`, runbook).

## What this doc does NOT cover

- **Sentry** integration is NOT currently wired in app code (`sentry-sdk[fastapi]` is in `requirements.txt` but no SDK init found in `app/main.py`). If Sentry is added later, document the `SENTRY_DSN` env var and any per-route scoping here.
- **slowapi** rate-limit policies and per-route limits — see `app/core/rate_limit.py` and runbook §1.6.
- **Multi-replica** behavior, sticky sessions, or horizontal scaling — not part of current Railway config in-repo.
- **Backup / restore** conventions for Postgres — operator responsibility; not specified here.
- **Exact Railway dashboard** clicks — use Railway UI for service linking, env editor, and deploy logs.

## Related docs

- `docs/runbook.md` — operational playbooks, diagnostics, SQL snippets.
- `docs/STATE.md` — current production URL and deploy verification discipline.
- `Procfile`, `nixpacks.toml` — authoritative start/install strings for this repo.
- `app/db/database.py`, `app/bootstrap_env.py`, `app/main.py` — source of truth for DB URL, `.env`, lifespan/`init_db`, `/health`.
