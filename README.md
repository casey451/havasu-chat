# Havasu Chat — Hava

Conversational concierge backend for Lake Havasu City, Arizona. FastAPI + SQLAlchemy + Postgres (production on Railway; SQLite for local dev). The single chat entry is `POST /api/chat`, which routes through a Tier 1 / Tier 2 / Tier 3 pipeline (deterministic templates → structured SQL retrieval → grounded LLM).

## Run locally

```bash
uvicorn app.main:app --reload
```

Tests: `python -m pytest -q`.

## Where to look

| If you want to know... | Read |
|---|---|
| What's deployed and what's queued | `docs/STATE.md`, `docs/BACKLOG.md` |
| How we collaborate (commit, push, halt-and-report) | `docs/WORKING_AGREEMENT.md` |
| Architecture (tiers, data model, key flows) | `HAVA_CONCIERGE_HANDOFF.md` |
| Where things live in the tree | `docs/maintainability/project_index.md` |
| Hava's voice | `docs/persona-brief.md` |
| New to the repo as a Cursor / Claude session | `docs/CURSOR_ORIENTATION.md`, `docs/CURSOR_NEW_CHAT_PLAN.md` |

## Repo root convention

The repo root holds **project spine** only: top-level packages (`app/`, `tests/`, `prompts/`, `scripts/`, `alembic/`, `docs/`), build/deploy config (`Procfile`, `nixpacks.toml`, `requirements.txt`, `alembic.ini`, `pytest.ini`), tooling config (`.gitignore`, `.gitattributes`, `.cursorrules`), and the architecture spine doc (`HAVA_CONCIERGE_HANDOFF.md`).

**Operational clutter** — local SQLite dev DBs (`*.db`), script run logs (`*.log`, `sentinel_ids*.txt`), local environment overrides (`.env`), Python bytecode caches — is allowed at the root or under packages but must be **gitignored**. It never gets tracked.

**Live-session captures** (HALT transcripts, sanity-check outputs from owner ↔ assistant relay) belong in `relay/` (gitignored except for `relay/README.md`).

See `docs/maintainability/project_manager_organization_brief.md` for the broader hygiene program (Backlog #18 Phases A-D).
