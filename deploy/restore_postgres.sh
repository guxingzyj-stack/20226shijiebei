#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
BACKUP_FILE="${1:-}"

if [[ -z "${BACKUP_FILE}" ]]; then
  echo "Usage: bash deploy/restore_postgres.sh backups/worldcup_YYYYmmdd_HHMMSS.sql" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "ERROR: backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi

DB_NAME="${POSTGRES_DB:-worldcup}"
DB_USER="${POSTGRES_USER:-worldcup_app}"

echo "WARNING: this will restore ${BACKUP_FILE} into database '${DB_NAME}'."
echo "Make sure you have taken a fresh backup before restoring."
read -r -p "Type RESTORE to continue: " CONFIRM
if [[ "${CONFIRM}" != "RESTORE" ]]; then
  echo "Restore cancelled."
  exit 0
fi

docker compose -f "${ROOT_DIR}/docker-compose.yml" exec -T postgres \
  psql -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 < "${BACKUP_FILE}"

echo "Restore complete."
