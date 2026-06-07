#!/usr/bin/env bash
# Rehearse an Alembic migration against the VPS staging Postgres BEFORE it ever
# reaches prod via a merge to main. Implements HANDOFF #6 of the VPS rollout.
#
#   restore latest prod backup -> staging  ->  alembic upgrade head  ->  (optional
#   downgrade reversibility check)  ->  (optional concurrent-chat smoke)
#
# Run on the VPS from the repo checkout:
#   /opt/hava/havasu-chat/scripts/rehearse_migration.sh
#   /opt/hava/havasu-chat/scripts/rehearse_migration.sh --check-downgrade --smoke
#
# SAFETY: this script DROPS AND RECREATES the target schema, so it hard-refuses
# any STAGING_DATABASE_URL that is not unmistakably a staging database (the URL
# must contain "staging"). It can never touch prod.
set -euo pipefail

# --- locate repo + load env -------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-/opt/hava/.env.vps}"
BACKUP_DIR="${BACKUP_DIR:-/opt/hava/backups}"

# Pull STAGING_DATABASE_URL from .env.vps if present (without leaking it to logs).
if [ -f "${ENV_FILE}" ]; then
  # shellcheck disable=SC1090
  set -a; source "${ENV_FILE}"; set +a
fi

# --- args -------------------------------------------------------------------
CHECK_DOWNGRADE=0
RUN_SMOKE=0
BACKUP_FILE=""
for arg in "$@"; do
  case "$arg" in
    --check-downgrade) CHECK_DOWNGRADE=1 ;;
    --smoke) RUN_SMOKE=1 ;;
    --backup=*) BACKUP_FILE="${arg#*=}" ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# --- guards -----------------------------------------------------------------
: "${STAGING_DATABASE_URL:?set STAGING_DATABASE_URL (in ${ENV_FILE} or env)}"

# Hard fence: refuse anything that isn't clearly a staging DB. The staging
# container's database is "havasu_staging"; prod is "railway". This is the line
# that makes the DROP SCHEMA below safe.
case "${STAGING_DATABASE_URL}" in
  *staging*) : ;;
  *) echo "REFUSING: STAGING_DATABASE_URL does not contain 'staging' — not a staging DB." >&2
     echo "          (guard against rehearsing against prod). Aborting." >&2
     exit 1 ;;
esac

# Pick the newest backup if one wasn't named.
if [ -z "${BACKUP_FILE}" ]; then
  BACKUP_FILE="$(ls -1t "${BACKUP_DIR}"/hava_prod_*.sql.gz 2>/dev/null | head -n1 || true)"
fi
[ -n "${BACKUP_FILE}" ] && [ -f "${BACKUP_FILE}" ] || {
  echo "No backup found (looked for ${BACKUP_DIR}/hava_prod_*.sql.gz or --backup=PATH)." >&2
  exit 1
}

cd "${REPO_ROOT}"
ALEMBIC=("${ALEMBIC_BIN:-alembic}")
echo "==> repo:    ${REPO_ROOT}"
echo "==> backup:  ${BACKUP_FILE}"
echo "==> target:  staging (URL redacted)"

# --- 1. reset + restore -----------------------------------------------------
echo "==> [1/3] resetting staging schema + restoring backup"
psql "${STAGING_DATABASE_URL}" -v ON_ERROR_STOP=1 \
  -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
gunzip -c "${BACKUP_FILE}" | psql "${STAGING_DATABASE_URL}" -v ON_ERROR_STOP=1 -q

# The restore replays whatever alembic_version the backup carried. Show it.
echo -n "    restored alembic_version: "
psql "${STAGING_DATABASE_URL}" -tAc \
  "SELECT version_num FROM alembic_version" 2>/dev/null || echo "(none — fresh)"

# --- 2. upgrade head (the rehearsal) ---------------------------------------
echo "==> [2/3] alembic upgrade head"
DATABASE_URL="${STAGING_DATABASE_URL}" "${ALEMBIC[@]}" upgrade head

if [ "${CHECK_DOWNGRADE}" -eq 1 ]; then
  echo "==> [2b] downgrade -1 then re-upgrade (reversibility check)"
  DATABASE_URL="${STAGING_DATABASE_URL}" "${ALEMBIC[@]}" downgrade -1
  DATABASE_URL="${STAGING_DATABASE_URL}" "${ALEMBIC[@]}" upgrade head
fi

# --- 3. optional smoke ------------------------------------------------------
if [ "${RUN_SMOKE}" -eq 1 ]; then
  echo "==> [3/3] concurrent-chat smoke against staging"
  PORT="${SMOKE_PORT:-8099}"
  DATABASE_URL="${STAGING_DATABASE_URL}" \
    "${PYTHON_BIN:-python}" -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT}" \
    >/tmp/hava_staging_uvicorn.log 2>&1 &
  UVICORN_PID=$!
  # Always tear the server down, even on smoke failure.
  trap 'kill "${UVICORN_PID}" 2>/dev/null || true' EXIT
  # Wait for /health (up to ~30s).
  for _ in $(seq 1 30); do
    if curl -fsS -m 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  "${PYTHON_BIN:-python}" scripts/smoke_concurrent_chat.py \
    --base-url "http://127.0.0.1:${PORT}" --duration-seconds "${SMOKE_SECONDS:-60}"
else
  echo "==> [3/3] smoke skipped (pass --smoke to run scripts/smoke_concurrent_chat.py)"
fi

echo "==> REHEARSAL OK — migration applied cleanly on staging."
echo "    Safe to merge to main (which deploys + runs 'alembic upgrade head' on prod)."
