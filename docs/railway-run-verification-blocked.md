# Railway verification — CLI unauthorized (handoff for Claude)

**Context:** After adding `DATABASE_URL=${{ Postgres.DATABASE_URL }}` on the Havasu chat service, two `railway run` verification commands were requested. The agent environment could not complete them because the Railway CLI session was not authenticated.

---

## What happened

Both verification commands failed **before** Python executed: the Railway CLI reported an unauthorized / expired OAuth session.

```text
Unauthorized. Please run `railway login` again.
```

A second attempt also reported token refresh failure (`invalid_grant`).

**Result:** No stdout from the intended Python checks—nothing validated `DATABASE_URL` in `railway run` or `from app.db.database import DATABASE_URL`.

---

## Owner steps (run locally)

1. From the linked project directory (e.g. repo root for **Havasu chat**):

   ```powershell
   railway login
   ```

2. Re-run the two verification commands (exact strings from the owner’s checklist).

---

## Expected outputs (after successful login)

### Command 1 — environment in `railway run` subprocess

```powershell
railway run .\.venv\Scripts\python.exe -c "import os; url = os.environ.get('DATABASE_URL', ''); print('DATABASE_URL set:', bool(url)); print('scheme:', url.split(':')[0] if url else 'none'); print('host fragment:', url.split('@')[1].split('/')[0] if '@' in url else 'none')"
```

**Expected:**

- `DATABASE_URL set: True`
- `scheme:` `postgresql` or `postgres`
- `host fragment:` Postgres hostname, e.g. `postgres.railway.internal:5432` (internal) or a `*.proxy.rlwy.net`-style host (public proxy)

### Command 2 — `app.db.database` resolution

```powershell
railway run .\.venv\Scripts\python.exe -c "from app.db.database import DATABASE_URL; print('resolved URL scheme:', DATABASE_URL.split(':')[0]); print('is sqlite:', DATABASE_URL.startswith('sqlite'))"
```

**Expected:**

- `resolved URL scheme:` `postgresql` or `postgres`
- `is sqlite: False`

---

## Failure signals

If either command shows:

- `DATABASE_URL set: False`, empty URL, or `scheme: none`
- `resolved URL scheme: sqlite` or `is sqlite: True`

…then the reference may not be resolving in `railway run`, or another issue is overriding resolution—needs investigation with **actual** command output pasted from the owner’s machine.

---

## Constraints

- No population / seed scripts were run from the blocked agent session.
- This file documents **agent-environment** failure only; it does not assert that Railway or the new variable is misconfigured.

---

*File: `docs/railway-run-verification-blocked.md`*
