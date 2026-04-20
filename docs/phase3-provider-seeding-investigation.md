# How Phase 1.3 providers got onto Railway — investigation

Read-only codebase review (no changes). Complements `docs/phase3-concierge-data-inference-archive.md`.

---

## Question

Handoff says `seed_providers` is owner-invoked / manual, not auto-run on deploy — but production has Phase 1.3 provider data. Which path applied?

- **A.** Manual run against production (forgotten or undocumented).
- **B.** Startup hook, migration, or deploy script auto-seeding providers.
- **C.** Some other in-repo script path.

---

## Conclusion (summary)

**Not (B) for `seed_providers`.** Nothing in this repo calls `seed_providers()` except `python -m app.db.seed_providers` (module `__main__`) and tests. Provider rows are **not** created by app startup, Alembic, `Procfile`, or `nixpacks.toml`.

**There is a Railway startup hook that seeds data — but only LHC seed *events* when the database has zero events.** It never inserts providers.

**Therefore:** production providers are consistent with **(A)** manual / owner-invoked **`python -m app.db.seed_providers`** (or equivalent `railway run` / one-off with prod `DATABASE_URL`). **(C)** in-repo writers of the Phase 1.3 provider set are that module (and tests only).

**Handoff nuance:** `seed_providers` is indeed not auto-run on deploy; **`run_seed_if_empty` *is* auto on Railway** for **events** on an **empty** DB only — a separate mechanism from Phase 1.3 providers.

---

## 1. `app/main.py` — lifespan / startup

`init_db()` runs every boot. `run_seed_if_empty` runs **only when** `RAILWAY_ENVIRONMENT` is set (Railway). It is **not** `seed_providers`.

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("ADMIN_PASSWORD loaded: %s", bool(os.getenv("ADMIN_PASSWORD")))
    init_db()
    # Auto-seed empty DB on Railway only (local/tests use manual seed or fixtures).
    if os.getenv("RAILWAY_ENVIRONMENT"):
        await asyncio.to_thread(run_seed_if_empty)
    task = asyncio.create_task(_hourly_cleanup_loop())
    # ...
```

Source: `app/main.py` (lifespan block).

---

## 2. `app/db/seed.py` — `run_seed_if_empty`

If **any** `Event` row exists, return immediately. Otherwise `run_seed()` inserts the **`REAL_SEED_EVENTS`** list (LHC community events with `__seed__:lhc_*` tags) — **events only**, no `Provider` inserts.

```python
def run_seed_if_empty() -> None:
    """If there are no events (e.g. fresh production DB), run the full seed once.

    Intended to be called from app startup on Railway (`RAILWAY_ENVIRONMENT` set in main.py).
    """
    with SessionLocal() as db:
        if db.query(Event).count() > 0:
            return
    run_seed(skip_init=True)
```

Source: `app/db/seed.py`.

---

## 3. Alembic migrations

- Reviewed `alembic/versions/`: **no** migration calls `seed_providers` or embeds provider row inserts via Python seed helpers.
- `e8a1c2d3e401_add_providers_table.py` is **schema-only** (`op.create_table("providers", ...)`).
- Other `op.execute` usage (e.g. `d4b7e2f1c902`) is `UPDATE` for `verified` flags, not provider seed data.

---

## 4. Deploy / container boot

| Artifact | Content |
|----------|---------|
| `Procfile` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` — no seed command |
| `nixpacks.toml` | `pip install -r requirements.txt` + same uvicorn start — no seed script |
| `Dockerfile` | Not present in repo |

---

## 5. `grep` — who calls `seed_providers`

Callable **`seed_providers(`** appears only in:

- `app/db/seed_providers.py` (definition + `if __name__ == "__main__"`),
- `tests/test_seed_providers.py`,
- `tests/test_backfill_program_providers.py` (fixtures).

**Not** called from `main.py`, admin router, migrations, or `scripts/` as a deploy hook.

**Related admin routes (not provider master seed):**

- `POST /admin/reseed` — deletes `created_by == "seed"` events and re-runs `run_seed()` (events + embeddings).
- `POST /admin/programs-reseed` — `scripts.seed_from_havasu_instructions` import from instructions markdown (separate from Phase 1.3 master provider list).

---

## Local DB reference counts (steps 5 & 6)

Command prefix: `.venv\Scripts\python.exe` from repo root on Windows.

### Programs

| Metric | Count |
|--------|------:|
| `programs` | 98 |
| `show_pricing_cta == True` | 59 |
| `provider_id` not null | 98 |

### Providers & `field_history`

| Metric | Count |
|--------|------:|
| `providers` | 25 |
| `FieldHistory` with `state == 'established'` | 875 |

*These numbers reflect the developer’s local SQLite (or whatever `DATABASE_URL` points to when the command ran), not Railway.*
