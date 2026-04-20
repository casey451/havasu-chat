# Running `alembic upgrade head` with Railway CLI

## Commands tried

From the project root `havasu-chat`:

### `railway run alembic upgrade head`

**Result:** failed with `'alembic' is not recognized as an internal or external command`.

On Windows, the `alembic` console script is often not on `PATH`, even when the package is installed.

### `railway run python -m alembic upgrade head`

**Result:** failed with `Python was not found` (Microsoft Store stub under `WindowsApps`, not a real Python install).

---

## How `railway run` works

`railway run` executes the command **on your local machine** and injects environment variables from your **linked Railway project** (for example `DATABASE_URL`). It does **not** by itself run inside the deployed container.

You still need a working **local** Python installation and project dependencies so Alembic can run.

---

## Recommended steps

1. Install **Python 3** (e.g. from [python.org](https://www.python.org/downloads/)) and ensure it is on `PATH`, or call it by full path.
2. In the project directory, install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Run migrations using the module form (reliable on Windows):

   ```bash
   railway run python -m alembic upgrade head
   ```

If you use a virtual environment, activate it first, then use that environment’s `python` in the `railway run` command.

---

## Summary

Migrations cannot run until a real Python interpreter is available locally (with `alembic` installed from `requirements.txt`). After that, prefer `railway run python -m alembic upgrade head` over calling the `alembic` executable directly on Windows.
