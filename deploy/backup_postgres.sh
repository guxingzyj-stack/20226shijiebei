#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
BACKUP_DIR="${ROOT_DIR}/backups"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: .env not found. Copy .env.example to .env first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

DB_NAME="${POSTGRES_DB:-worldcup}"
DB_USER="${POSTGRES_USER:-worldcup_app}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/worldcup_${TIMESTAMP}.sql"

mkdir -p "${BACKUP_DIR}"

echo "Backing up PostgreSQL database '${DB_NAME}' to ${OUT_FILE}"
docker compose -f "${ROOT_DIR}/docker-compose.yml" exec -T postgres \
  pg_dump -U "${DB_USER}" -d "${DB_NAME}" --no-owner --no-privileges > "${OUT_FILE}"

echo "Backup complete: ${OUT_FILE}"
