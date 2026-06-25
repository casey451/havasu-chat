#!/usr/bin/env bash
#
# Nightly logical backup of the prod Postgres to the VPS's idle local disk.
#
# Read-only against prod: a `pg_dump` takes a consistent snapshot and writes
# nothing back. Output is a compressed custom-format dump (`pg_restore`-able).
# Old dumps are pruned past the retention window. Best-effort + loud on failure
# so the watchdog/journal surfaces a broken backup.
#
# Required environment (systemd EnvironmentFile):
#   DATABASE_URL     prod Postgres connection string (already on the box for the
#                    vision scraper, in /etc/havasu/havasu-vision.env)
# Optional:
#   BACKUP_DIR       where dumps land (default /var/backups/havasu)
#   RETENTION_DAYS   delete dumps older than this many days (default 14)
#   PG_DUMP          path to pg_dump (default: first on PATH; must be >= server major)

set -uo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/havasu}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
PG_DUMP="${PG_DUMP:-pg_dump}"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "FATAL: DATABASE_URL is unset" >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%d-%H%M%S)"
out="$BACKUP_DIR/havasu-$stamp.dump"
tmp="$out.partial"

echo "[$(date -u +%FT%TZ)] db-backup: dumping prod -> $out"
# -Fc: compressed custom format. Write to .partial then atomically rename so a
# crash never leaves a truncated file that looks like a good backup.
if "$PG_DUMP" -Fc --no-owner --no-privileges "$DATABASE_URL" -f "$tmp"; then
  mv -f "$tmp" "$out"
  sz="$(du -h "$out" | cut -f1)"
  echo "[$(date -u +%FT%TZ)] db-backup: OK ($sz) $out"
else
  rc=$?
  rm -f "$tmp"
  echo "[$(date -u +%FT%TZ)] db-backup: FAILED (pg_dump exit $rc)" >&2
  exit "$rc"
fi

# Prune old dumps (only our own naming; never touches anything else).
deleted="$(find "$BACKUP_DIR" -maxdepth 1 -name 'havasu-*.dump' -type f -mtime "+$RETENTION_DAYS" -print -delete | wc -l)"
echo "[$(date -u +%FT%TZ)] db-backup: pruned $deleted dump(s) older than ${RETENTION_DAYS}d; kept:"
ls -1t "$BACKUP_DIR"/havasu-*.dump 2>/dev/null | head -5 | sed 's/^/  /'
