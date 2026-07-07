"""READ-ONLY: fingerprint the Postgres cluster a given DATABASE_URL resolves to.

Closes the recurring "is the GitHub-Actions DB the same as the web app's DB?"
question (repo .env / web app use Railway's INTERNAL host
``postgres.railway.internal``; the Actions secret uses the PUBLIC proxy
``…proxy.rlwy.net``). If both endpoints front the SAME Postgres cluster, the
``system_identifier`` from ``pg_control_system()`` — a value initdb assigns once,
unique per cluster — is identical. This script prints that fingerprint for
whatever DATABASE_URL resolves in the current environment.

  * In CI (``db-identity-probe`` workflow) it hits the public-proxy prod DB — the
    **Actions path**.
  * The **web-app path** exposes the same fingerprint at ``GET /health`` →
    ``db_identity`` (added alongside this script); compare the two.

WRITES NOTHING — SELECTs only. Each probe is independently guarded so a role that
can't read ``pg_control_system()`` still yields the ``inet_server_*`` fallback the
task allows.

    .venv\\Scripts\\python.exe scripts/db_identity_probe.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402


def _sanitized_host() -> dict[str, str | int | None]:
    """Host + port from DATABASE_URL, never the credentials."""
    url = os.getenv("DATABASE_URL", "")
    if not url:
        return {"host": None, "port": None}
    parts = urlsplit(url)
    return {"host": parts.hostname, "port": parts.port}


def probe() -> dict[str, object]:
    """Read-only cluster fingerprint. Missing keys => that probe was not permitted."""
    out: dict[str, object] = {"database_url": _sanitized_host()}
    with SessionLocal() as db:
        # Cluster identity — the definitive fingerprint (superuser or granted role).
        try:
            sysid = db.execute(text("SELECT system_identifier FROM pg_control_system()")).scalar()
            out["system_identifier"] = str(sysid) if sysid is not None else None
        except Exception as exc:  # pragma: no cover - permission-dependent
            out["system_identifier_error"] = type(exc).__name__
        # Server endpoint + database (readable by any role) — the task's fallback.
        for label, sql in (
            ("current_database", "SELECT current_database()"),
            ("inet_server_addr", "SELECT inet_server_addr()::text"),
            ("inet_server_port", "SELECT inet_server_port()"),
            ("server_version", "SELECT current_setting('server_version')"),
            ("event_count", "SELECT count(*) FROM events"),
        ):
            try:
                out[label] = db.execute(text(sql)).scalar()
            except Exception as exc:  # pragma: no cover
                out[f"{label}_error"] = type(exc).__name__
    return out


def main() -> int:
    result = probe()
    print(json.dumps(result, indent=2, default=str))
    print(
        "\nCompare `system_identifier` (or inet_server_addr/port) with the web app's "
        "GET /health -> db_identity. Equal => same Postgres cluster."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
