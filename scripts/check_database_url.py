r"""Verify a DATABASE_URL points at the real havasu-chat prod data.

Read-only: SELECT counts only, writes nothing, never prints the URL.

Usage (PowerShell, from repo root):
    .venv\Scripts\python.exe scripts/check_database_url.py
then paste the same URL you put in the GitHub secret (input is hidden).
"""

import getpass
import sys

from sqlalchemy import create_engine, text

url = getpass.getpass("Paste DATABASE_URL (hidden): ").strip().strip('"').strip("'")
if not url:
    print("No URL given.")
    sys.exit(1)

try:
    engine = create_engine(url)
    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM providers")).scalar()
        with_primary = conn.execute(
            text("SELECT count(*) FROM providers WHERE primary_category IS NOT NULL")
        ).scalar()
        sample = conn.execute(
            text(
                "SELECT provider_name, primary_category FROM providers "
                "WHERE primary_category IS NOT NULL LIMIT 5"
            )
        ).fetchall()
        legacy_cat = conn.execute(
            text("SELECT count(*) FROM providers WHERE category IS NOT NULL")
        ).scalar()
        google_cat = conn.execute(
            text(
                "SELECT count(*) FROM providers WHERE google_primary_category IS NOT NULL"
            )
        ).scalar()
        subcat = conn.execute(
            text("SELECT count(*) FROM providers WHERE subcategory IS NOT NULL")
        ).scalar()
        try:
            alembic = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:  # noqa: BLE001
            alembic = "(no alembic_version table)"
except Exception as exc:  # noqa: BLE001
    print(f"Connection/query FAILED: {type(exc).__name__}: {exc}")
    sys.exit(1)

print(f"providers total:                 {total}")
print(f"providers with primary set:      {with_primary}")
print(f"providers with legacy category:  {legacy_cat}")
print(f"providers with google primary:   {google_cat}")
print(f"providers with subcategory:      {subcat}")
print(f"alembic version:                 {alembic}")
for name, cat in sample:
    print(f"  e.g. {name}  [{cat}]")

if with_primary == 0:
    print("\n-> This is NOT the prod data (or categories were never backfilled here).")
    print("   In Railway: check the environment selector (production), the Postgres")
    print("   service the app is attached to, and use DATABASE_PUBLIC_URL if present.")
else:
    print("\n-> Looks like real data. If this is the exact value in the GitHub secret,")
    print("   re-paste it carefully (no quotes, no 'DATABASE_URL=' prefix).")
