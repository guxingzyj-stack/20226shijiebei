#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

DB_NAME="${POSTGRES_DB:-worldcup}"
DB_USER="${POSTGRES_USER:-worldcup_app}"
API_URL="${API_HEALTH_URL:-http://localhost:8000/api/health}"
WEB_URL="${WEB_HEALTH_URL:-http://localhost:8080/}"

echo "== HTTP health =="
echo -n "api ${API_URL}: "
curl -fsS "${API_URL}" >/tmp/worldcup_api_health.json
cat /tmp/worldcup_api_health.json
echo

echo -n "web ${WEB_URL}: "
curl -fsS -o /dev/null -w "%{http_code}\n" "${WEB_URL}"

echo "== PostgreSQL =="
docker compose -f "${ROOT_DIR}/docker-compose.yml" exec -T postgres \
  psql -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -c "SELECT 1;"

echo "== crawler recent crawl_runs =="
docker compose -f "${ROOT_DIR}/docker-compose.yml" exec -T postgres \
  psql -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -c \
  "SELECT id, started_at, ok, source, matches_seen, rows_written, left(coalesce(error,''), 160) AS error FROM crawl_runs ORDER BY id DESC LIMIT 5;"

echo "== odds_snapshots freshness =="
docker compose -f "${ROOT_DIR}/docker-compose.yml" exec -T postgres \
  psql -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -c \
  "SELECT max(fetched_at) AS latest_odds_snapshot FROM odds_snapshots;"
