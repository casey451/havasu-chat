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

## Analytics (Plausible)

Pageviews and a small set of custom events are sent to [Plausible](https://plausible.io) when the `PLAUSIBLE_DOMAIN` env var is set. When unset (local dev), the script tag is omitted entirely — no pixels fire and no consent banner is required.

**To enable in production:**

1. Casey creates the site at `https://plausible.io/sites` (domain = `havachat.com` or whatever the deployed host is).
2. Set `PLAUSIBLE_DOMAIN` in Railway → Variables to the same value.
3. Redeploy. Every page rendered through Jinja gets `<script defer data-domain="…" src="https://plausible.io/js/script.outbound-links.js">` injected via `app/templates/_partials/plausible.html`.

The `script.outbound-links.js` variant auto-captures clicks on external links (sponsor sites, provider websites) — no extra wiring needed.

**Custom events** (defined in `app/static/js/chat-new.js`):

| Event | Props | Fired when |
|---|---|---|
| `Chat Query Sent` | `length_bucket`: `short` (< 20 chars) / `medium` (20–100) / `long` (> 100) | User submits a chat query — fired before the network request so unload-during-submit doesn't drop the event. |
| `Chat Card Tap` | `card_type`: `business_list` / `event` / `card_row` / `single_card` | User taps any rendered chat card (delegated listener on the thread, walks up to the nearest `[data-card-type]`). |
| `Sponsor Click` | `slot` (e.g. `marquee`, `biz_spotlight`), `id` | User clicks a sponsor surface — either a stamped `[data-sponsor-slot]` element or an `a[href^="/sponsor/click"]` link. Fires alongside the server-side `/sponsor/click` redirect so click attribution stays double-bookkept. |

**PII rule:** custom events ship structural metadata only — never the user's query text, business name, phone number, or any other PII. That's load-bearing for the cookieless / GDPR-compliant posture; don't expand props without revisiting the consent question.
