#!/usr/bin/env bash
# 041-RUN production DB / runner settlement-loop safety check.
#
# Run location:
# - wc-p2-api container, usually /app.
#
# Safety boundaries:
# - Does not enable BETTING_ENABLED.
# - Does not run migrations.
# - Does not manually UPDATE match results.
# - Does not manually UPDATE bets/users/balances.
# - Does not modify code.
# - If open/pending bets exist, does not auto-run settlement_runner once.
# - If no open/pending bets exist, runs one no-op settlement_runner verification.

set -euo pipefail

echo ""
echo "============================================================"
echo "041-RUN Production Check"
echo "============================================================"
TIME_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
DATABASE_URL_SET="false"
if [ -n "${DATABASE_URL:-}" ]; then
  DATABASE_URL_SET="true"
fi
echo "time_utc=${TIME_UTC}"
echo "pwd=$(pwd)"
echo "PYTHONPATH=${PYTHONPATH:-}"
echo "BETTING_ENABLED=${BETTING_ENABLED:-unset}"
echo "DATABASE_URL_SET=${DATABASE_URL_SET}"
echo ""

if [ "${BETTING_ENABLED:-false}" = "true" ]; then
  echo "ERROR: BETTING_ENABLED=true detected. Stop."
  exit 2
fi

export PYTHONPATH="${PYTHONPATH:-.}"

echo ""
echo "=== Step 1: API Health ==="
curl -sS https://fifa2026.zeabur.app/api/health
echo ""

echo ""
echo "=== Step 2: Latest 6 ops_log entries ==="
psql -U root -d worldcup -c "SELECT job_name,status,started_at,finished_at,error FROM ops_log ORDER BY id DESC LIMIT 6;"
echo ""

echo ""
echo "=== Step 3: Latest odds snapshot timestamp ==="
psql -U root -d worldcup -c "SELECT max(fetched_at) AS latest_odds_snapshot FROM odds_snapshots;"
echo ""

echo ""
echo "=== Step 4: Result consistency report ==="
python -m api.result_consistency_report
echo ""

echo ""
echo "=== Step 5: Finished/completed matches missing results ==="
psql -U root -d worldcup -c "SELECT match_id,match_num,home_team,away_team,kickoff_at,status,result_home,result_away,ht_home,ht_away FROM matches WHERE status IN ('finished','completed') AND (result_home IS NULL OR result_away IS NULL) ORDER BY kickoff_at;"
echo ""

echo ""
echo "=== Step 6: Non-finished matches with result populated ==="
psql -U root -d worldcup -c "SELECT match_id,match_num,home_team,away_team,kickoff_at,status,result_home,result_away FROM matches WHERE status NOT IN ('finished','completed') AND (result_home IS NOT NULL OR result_away IS NOT NULL) ORDER BY kickoff_at;"
echo ""

echo ""
echo "=== Step 7: First 12 matches snapshot ==="
psql -U root -d worldcup -c "SELECT match_id,match_num,home_team,away_team,kickoff_at,status,result_home,result_away FROM matches ORDER BY kickoff_at LIMIT 12;"
echo ""

echo ""
echo "=== Step 8: Bets status counts ==="
psql -U root -d worldcup -c "SELECT status, COUNT(*) FROM bets GROUP BY status ORDER BY status;"
echo ""

OPEN_PENDING_COUNT=$(psql -U root -d worldcup -t -A -c "SELECT COALESCE(COUNT(*),0) FROM bets WHERE status IN ('open','pending');" | tr -d '[:space:]')

echo "open_pending_count=${OPEN_PENDING_COUNT}"

if [ "${OPEN_PENDING_COUNT}" = "0" ]; then
  echo ""
  echo "=== Step 9: Safe no-op settlement_runner ==="
  python -m api.settlement_runner once
  echo ""

  echo ""
  echo "=== Step 10: Post-settlement bets status ==="
  psql -U root -d worldcup -c "SELECT status, COUNT(*) FROM bets GROUP BY status ORDER BY status;"
  echo ""

  echo ""
  echo "=== Step 11: Latest 5 settlement_runner ops_log ==="
  psql -U root -d worldcup -c "SELECT job_name,status,started_at,finished_at,summary,error FROM ops_log WHERE job_name='settlement_runner' ORDER BY id DESC LIMIT 5;"
  echo ""

  echo ""
  echo "=== Step 12: P1-C' evaluable finished matches count ==="
  psql -U root -d worldcup -c "SELECT COUNT(*) AS evaluable_finished_matches FROM matches WHERE status IN ('finished','completed') AND result_home IS NOT NULL AND result_away IS NOT NULL;"
  echo ""

  echo ""
  echo "================================================------------"
  echo "041-RUN preliminary conclusion"
  echo "================================================------------"
  echo "settlement_runner_noop_verified=true"
  echo "bet_settlement_pass=false"
  echo "reason=no_open_bets_to_settle"
  echo "next_action=paste full output back for PASS/WARN/FAIL report"
else
  echo ""
  echo "=== Step 9: SKIP automatic settlement_runner ==="
  echo "open/pending bets exist. Do NOT auto-run settlement_runner."
  echo "Paste Step 8 output back before deciding whether to run settlement_runner once."
  echo ""

  echo ""
  echo "=== Step 10: P1-C' evaluable finished matches count ==="
  psql -U root -d worldcup -c "SELECT COUNT(*) AS evaluable_finished_matches FROM matches WHERE status IN ('finished','completed') AND result_home IS NOT NULL AND result_away IS NOT NULL;"
  echo ""

  echo ""
  echo "================================================------------"
  echo "041-RUN preliminary conclusion"
  echo "================================================------------"
  echo "settlement_runner_noop_verified=false"
  echo "bet_settlement_pass=not_checked"
  echo "reason=open_or_pending_bets_exist"
  echo "next_action=paste bets status output back before running settlement_runner once"
fi

echo ""
echo "=== Final safety reminder ==="
echo "No migration executed by this script."
echo "No manual UPDATE executed by this script."
echo "BETTING_ENABLED must remain false."
