# Railway production URL + DB diagnosis (scripts vs live HTTP)

Single reference: **which hostname matches the linked Postgres** and **why `web-production-bbe17` showed 27 events** while `railway run` showed 43.

**Scope:** Read-only investigation (no DB writes, no Railway config changes from this doc).

---

## Security note

If `railway variable list --json` was run where logs are retained, **rotate** any exposed credentials (Postgres password, `ADMIN_PASSWORD`, `OPENAI_API_KEY`, `SENTRY_DSN`, etc.). Below repeats **only redacted** connection shapes.

---

## Canonical public URL (use this for HTTP smoke tests)

When the repo is linked with `railway status` showing **Project: Havasu chat**, **Environment: production**, **Service: Havasu chat**, Railway’s generated app URL is:

**`https://havasu-chat-production.up.railway.app`**

CLI derivation:

```bash
railway domain --json -s " Havasu chat"
```

(Service name may include a **leading space** in CLI output — include it in quotes if the bare name fails.)

### Quick health check

```bash
curl -sS https://havasu-chat-production.up.railway.app/health
```

**After Phase 3.0 event load:** expect `event_count` **43**.

Example:

```json
{"status":"ok","db_connected":true,"event_count":43}
```

### Do not confuse with

**`https://web-production-bbe17.up.railway.app`** — during diagnosis, `/health` returned **`event_count`: 27**; that host is **not** the same database as the linked **Havasu chat** Phase 3.0 Postgres. Use **bbe17** only if you have independently verified it maps to the same Railway service and `DATABASE_URL` as `havasu-chat-production`.

---

## 1. `railway run` — database the CLI uses

**Command (from repo root):**

```bash
railway run .\.venv\Scripts\python.exe -c "from app.db.database import SessionLocal, DATABASE_URL; from app.db.models import Event; s = SessionLocal(); total = s.query(Event).count(); print('DATABASE_URL host:', DATABASE_URL.split('@')[1].split('/')[0] if '@' in DATABASE_URL else 'unknown'); print('database name:', DATABASE_URL.rsplit('/', 1)[1].split('?')[0] if '/' in DATABASE_URL else 'unknown'); print('events count:', total); s.close()"
```

**Observed output:**

```text
DATABASE_URL host: crossover.proxy.rlwy.net:41265
database name: railway
events count: 43
```

Scripts use the **public Postgres proxy** above, dbname **`railway`**, **43** events.

---

## 2. HTTP — `web-production-bbe17` hostname

**Base:** `https://web-production-bbe17.up.railway.app`

| Request | Result |
|---------|--------|
| `GET /health` | `{"status":"ok","db_connected":true,"event_count":27}` |
| `GET /debug-db-info` | `{"detail":"Not Found"}` — **404** |
| `HEAD /admin` | **405** — `allow: GET` |

This hostname’s `/health` **does not** match the 43-event DB used by linked `railway run`.

---

## 3. `railway variable list` — redacted summary

**CLI:** `railway status` → **Project:** Havasu chat · **Environment:** production · **Service:** Havasu chat.

### App service (`production`, default)

| Variable | Redacted shape |
|----------|----------------|
| `DATABASE_URL` | `postgresql://***:***@crossover.proxy.rlwy.net:41265/railway` |

### Postgres service (`production`, `-s Postgres`)

| Variable | Redacted shape |
|----------|----------------|
| `DATABASE_URL` (internal) | `postgresql://***:***@postgres.railway.internal:5432/railway` |
| `DATABASE_PUBLIC_URL` | `postgresql://***:***@crossover.proxy.rlwy.net:41265/railway` |

App `DATABASE_URL` and Postgres `DATABASE_PUBLIC_URL` match on **host `crossover.proxy.rlwy.net`**, **port `41265`**, **dbname `railway`**. Internal URL uses **`postgres.railway.internal:5432`** (same DB, private path).

---

## 4. Railway environments

```bash
railway environment list
```

**Observed:** `production (linked)` (only environment listed in that snapshot).

---

## Root cause (short)

- **`railway run` + linked `DATABASE_URL`** → **43** events on **`crossover.proxy.rlwy.net:41265` / `railway`**.
- **`web-production-bbe17`** → **27** events → **different deployment/project** than the linked **Havasu chat** app for this repo.

For smoke tests against the DB you populated via `railway run`, use **`https://havasu-chat-production.up.railway.app`**.

---

## Related

- `docs/phase3-0-http-smoke-test-web-production-bbe17.md` — historical smoke against **bbe17** (27 events); wrong host for current linked service
