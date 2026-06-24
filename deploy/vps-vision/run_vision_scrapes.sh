#!/usr/bin/env bash
#
# Run the Ask Hava vision image scrapers against a SELF-HOSTED model.
#
# Designed for a VPS cron / systemd timer where VISION_BASE_URL points at a local
# Ollama (or other OpenAI-compatible) server on localhost -- so there is no OpenAI
# token spend and nothing is exposed to the network.
#
# Each source is run independently and a failure is non-fatal (best-effort feed).
# Ingested rows land PENDING in the /admin review queue -- none of these sources
# are auto-approve, so vision output never reaches users unreviewed, and the
# senior step does NOT touch the live senior loader.
#
# Required environment (see havasu-vision.env.example):
#   DATABASE_URL      prod Postgres connection string
#   VISION_BASE_URL   e.g. http://127.0.0.1:11434/v1
#   VISION_MODEL      e.g. qwen2.5vl:3b
# Optional:
#   VISION_API_KEY, PARKS_REC_FLYER_MAX, SENIOR_FLYER_MAX,
#   HAVASU_REPO_DIR (default: two levels up from this script),
#   HAVASU_PY       (default: $HAVASU_REPO_DIR/.venv/bin/python)

set -uo pipefail

HAVASU_REPO_DIR="${HAVASU_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PY="${HAVASU_PY:-$HAVASU_REPO_DIR/.venv/bin/python}"

cd "$HAVASU_REPO_DIR" || { echo "FATAL: cannot cd to $HAVASU_REPO_DIR"; exit 1; }

run() {
  echo "[$(date -u +%FT%TZ)] running: $*"
  if ! "$PY" "$@"; then
    echo "[$(date -u +%FT%TZ)] WARN: command failed (continuing): $*"
  fi
}

echo "[$(date -u +%FT%TZ)] vision scrape start (repo=$HAVASU_REPO_DIR model=${VISION_MODEL:-unset})"
run scripts/parks_rec_calendar_pull.py --apply
run scripts/parks_rec_calendar_pull.py --source flyers --apply
run scripts/senior_flyers_pull.py --apply
echo "[$(date -u +%FT%TZ)] vision scrape done"
