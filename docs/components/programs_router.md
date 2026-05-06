# programs_router

`app/programs/router.py` (~376 lines)

## Purpose

FastAPI **`APIRouter`** for **`/programs*`** HTTP surface: JSON **CRUD-style** listings and creates under **`ProgramCreate` / `ProgramRead`**, plus **Session AA-2** **HTML** parent submission (`GET`/`POST` **`/programs/submit`**) that builds `Program` rows pending admin activation. The router is mounted from **`app/main.py`** via **`app.include_router(programs_router)`** with **no prefix** — routes are literally **`/programs`**, **`/programs/submit`**, **`/programs/{program_id}`**.

This module is **user-facing HTML + JSON** — XSS discipline applies on the form renderer (stdlib **`html.escape`** on echoed values).

## Public surface

**`router: APIRouter`** — Sole export. Consumers attach routes through **`include_router`**.

There is no Python callable API beyond HTTP handlers.

## Route inventory

| Route | Method | Rate limit | Purpose |
|-------|--------|------------|---------|
| `/programs` | POST | **5/minute** (`slowapi`) | JSON body **`ProgramCreate`** → insert **`Program`** → **`ProgramRead`**. Uses **`_program_from_create`**: **`verified = (payload.source == "admin")`**. |
| `/programs` | GET | — | Active programs only: **`is_active == True`**, newest **`created_at`** first; **`list[ProgramRead]`**. |
| `/programs/submit` | GET | — | Renders parent submission **HTML** form (`HTMLResponse`). |
| `/programs/submit` | POST | **3/minute** | **`Form(...)`** fields assembled into a dict → **`ProgramCreate`** validation → **`Program`** insert with **`source="parent"`**, **`verified=False`**, **`is_active=False`** (forced after validation). Success HTML thanks page. |
| `/programs/{program_id}` | GET | — | Fetch by UUID string PK; **404** if missing; **`ProgramRead`**. |

**Route-order note:** **`/programs/submit`** handlers are declared **before** **`/programs/{program_id}`** so the literal path wins over the dynamic segment (comment in source).

## Inputs and outputs

**JSON POST `/programs`** — Request body is **`ProgramCreate`** (`Content-Type: application/json`). Response **`ProgramRead`** (includes **`schedule_*`** serialized as **`HH:MM`** via schema serializer).

**HTML POST `/programs/submit`** — Multipart form fields mirror program shape (`title`, `description`, `schedule_days` multi-value checkboxes, `schedule_start_time` / `schedule_end_time` strings, optional contacts). Empty optional strings normalized to **`None`** before model validation. **`source`** and **`is_active`** are injected server-side in the raw dict (`parent` / `false`) but **`program_submit`** **re-applies** **`source="parent"`**, **`verified=False`**, **`is_active=False`** on the ORM row regardless of Pydantic coercion.

**GET `/programs`** — No body; returns **`list[ProgramRead]`**.

## Internal structure

1. **`_PROGRAM_DAYS_ORDER`** — Canonical weekday order for checkbox rendering (`monday` … `sunday`).

2. **`_program_from_create`** — Maps **`ProgramCreate`** → **`Program`** ORM for the JSON create path; copies schedule times as **`time`** objects; sets **`verified`** from **`source == "admin"`** only.

3. **`_submit_form_html` / `_submit_success_html`** — Inline HTML + CSS strings; **`inp()`** helper emits escaped input **`value`** / **`placeholder`**; **`textarea`** body escaped; error banner escaped.

4. **`program_submit`** — Local **`_maybe_int`** / **`_nonempty`** helpers; **`ProgramCreate(**raw)`** in **`try/except`** → on validation failure returns **400** + re-rendered form with **`str(exc)`** as error (user-visible Pydantic message).

## Conventions

**slowapi requires `Request` parameter** on limited routes — both **`create_program`** and **`program_submit`** accept **`request: Request`** as first arg after the decorator order FastAPI expects.

**Parent path never self-verifies.** HTML flow bypasses **`_program_from_create`** and constructs **`Program`** directly so **`verified`** cannot become **`True`** via tampered JSON through this endpoint.

**Tier limits differ** — public HTML submit is **stricter (3/min)** than JSON create **(5/min)**; tune together if abuse patterns shift.

## Known limitations and design notes

**No cookie auth on JSON POST `/programs`.** Unlike admin routes, program creation is not gated — threat model assumes low-volume honest API use plus rate limits.

**No CSRF token on `/programs/submit`.** Same posture as other simple public forms in the project; cookie-less GET form reduces classic CSRF surface but state-changing POST remains uncaptioned.

**404 only on GET by id.** Missing UUID returns FastAPI **`HTTPException`**; HTML paths don’t expose ID guessing UX.

**Embedding always `None` on parent submit.** JSON path can pass **`embedding`** from **`ProgramCreate`**; HTML path omits it.

## Configuration

None in-module. **`DATABASE_URL`** / session via **`Depends(get_db)`**.

## Related

**Direct callers:** **`app/main.py`** mounts **`programs_router`** (not edited in Slice 66; mount remains the integration point).

**Direct dependencies:**

- **`app.core.rate_limit.limiter`**
- **`app.db.database.get_db`**, **`app.db.models.Program`**
- **`app.schemas.program.{ProgramCreate, ProgramRead}`**

**Cross-references:**

- **`docs/components/schema_program.md`** — validators and wire-format **`HH:MM`** serialization.
- **`docs/maintainability/http_api.md`** — route inventory snapshot.
- **`docs/components/rate_limit.md`** — limiter semantics.
