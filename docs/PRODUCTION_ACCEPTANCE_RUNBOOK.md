# Production Acceptance Runbook

This runbook is for production acceptance only. Do not paste or commit `DATABASE_URL`, `JWT_SECRET`, tokens, passwords, or API keys.

## 1. Service Names

The following service names must use the actual names shown in the Zeabur console:

- P0 crawler 服务：以 Zeabur 实际服务名为准
- P1 model-worker 服务：以 Zeabur 实际服务名为准
- P2 API 服务：以 Zeabur 实际服务名为准
- P2 Web 服务：以 Zeabur 实际服务名为准
- PostgreSQL 服务：以 Zeabur 实际服务名为准

Do not assume any hard-coded Zeabur service name.

## 2. Production Execution Steps

Run these commands inside the matching Zeabur container terminal. Codex does not have Zeabur console access and does not run production operations.

### P1 model-worker container

```bash
python -m model.cli acceptance-report
```

### P2 API container

```bash
python -m api.acceptance_report
python -m api.results_sync dry-run
python -m api.settlement_runner dry-run
```

### Optional settlement closed-loop smoke

Only run a production settlement smoke after manual SQL review. The current code does not provide a dangerous default `--test-only` writer.

If a test match is required, it must use:

```text
match_id = test-settlement-<timestamp>
match_num = TEST001
home_team = 测试主队
away_team = 测试客队
```

Test bets may only reference `test-` prefixed `match_id` values.

## 3. Production Database Prohibited Actions

Never write fake scores to real matches. Real matches include but are not limited to:

- `match_id` values starting with `500-`
- real Jingcai match numbers such as `周四001` or `周五003`

These real match fields may only be written by `results_sync` from real results:

```text
result_home
result_away
ht_home
ht_away
status
```

Also prohibited:

- Do not set `BETTING_ENABLED=true` before settlement acceptance passes.
- Do not test against real user balances.
- Do not output `DATABASE_URL` or `JWT_SECRET`.
- Do not connect to real betting or purchase flows.

## 4. Safe Cleanup SQL

Before deletion, confirm the target rows are test-only and do not include real users or real matches.

```sql
DELETE FROM bets WHERE legs::text LIKE '%test-settlement-%';
DELETE FROM matches WHERE match_id LIKE 'test-%';
DELETE FROM users WHERE username LIKE 'test_user_%' OR username LIKE 'codex_blocker_%';
```

These statements intentionally only target test prefixes.

## 5. Scheduler Deployment

Deploy scheduler code with scheduling disabled first:

```text
ENABLE_API_SCHEDULER=false
BETTING_ENABLED=false
```

Run inside the P2 API container:

```bash
python -m api.apply_migrations
python -m api.acceptance_report
```

After acceptance passes and settlement smoke has already returned `PASS`, enable scheduling in the Zeabur API service environment:

```text
ENABLE_API_SCHEDULER=true
RESULTS_SYNC_INTERVAL_MINUTES=60
SETTLEMENT_RUNNER_INTERVAL_MINUTES=30
OPS_HEALTH_CHECK_INTERVAL_MINUTES=30
OPS_HEALTH_STALE_THRESHOLD_MINUTES=90
ODDS_STALE_THRESHOLD_MINUTES=30
OPS_ALERT_ENABLED=false
OPS_ALERT_WEBHOOK_URL=
RUN_SCHEDULER_ON_STARTUP=false
BETTING_ENABLED=false
```

Redeploy the API service, then observe logs and `ops_log` through:

```bash
python -m api.acceptance_report
```

Do not enable betting as part of scheduler rollout.

If `RUN_SCHEDULER_ON_STARTUP=true`, the API scheduler runs these jobs once at
startup and then on their intervals:

```text
results_sync
settlement_runner
ops_health_check
```

The watchdog can also be run manually:

```bash
python -m api.ops_health_check
python scripts/run_daily_ops_check.py
```

It writes `ops_log.job_name='ops_health_check'` with status `ok`, `warn`, or
`fail`. A no-op settlement state because there are no open bets is `WARN`; it is
not proof that real bet settlement has passed.

The daily runner is pure Python and is intended for production containers where
shell HTTP/database clients may be unavailable. Do not run debug shell tracing
because it may expand environment variables. The runner prints
`DATABASE_URL_SET=true/false` only.

## 6. 014-C Operations Closeout

Current status:

```text
Read-only features are open.
BETTING_ENABLED=false.
Scheduler is enabled and waiting for real ops_log observation.
P1-C historical market backtest numbers are still pending.
P3 real data import is pending.
P4 real recap waits for more finished matches.
```

Always back up PostgreSQL before cleanup, restore, migration, or host movement:

```bash
bash deploy/backup_postgres.sh
```

On Windows self-hosting:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/backup_postgres.ps1
```

`odds_snapshots` is not reproducible and must be treated as the highest-priority backup table.

Read-only health checks:

```bash
curl -sS https://fifa2026.zeabur.app/api/health
python -m api.health_report
python -m api.ops_health_check
python scripts/run_daily_ops_check.py
python -m api.result_consistency_report
python -m api.scheduler_observe
python -m api.cleanup_test_data dry-run
```

`/api/health` should include `scheduler_last_seen`, `scheduler_last_seen_age_minutes`,
`scheduler_stale`, `latest_ops_health_check_at`, `ops_health_status`, and
`ops_health_blockers`. If latest `ops_log` is older than 90 minutes,
`api.health_report` must return `FAIL`.

Normal daily operation no longer requires running the full 041 SQL bundle. Use
`/api/health` first. If it shows `FAIL`, run the Python daily runner and
`python -m api.ops_health_check` inside the API container, then inspect `ops_log`.

Sale closed / stop selling is not a match result. The crawler may write `closed`,
but only `results_sync` may mark a real match `finished` after full-time scores are
available. `finished` rows with missing `result_home` or `result_away` must be
treated as not ready for settlement, recap, and P1-C Prime calibration.

If old data contains `finished/completed` rows with both full-time scores still
`NULL`, first inspect the exact target list:

```bash
python -m api.result_consistency_report repair-finished-null --dry-run
```

Only after the dry-run target list is confirmed safe, downgrade those rows to
`closed`:

```bash
python -m api.result_consistency_report repair-finished-null --confirm REPAIR_FINISHED_NULL
```

This repair command does not write scores. It only updates rows matching
`status IN ('finished','completed') AND result_home IS NULL AND result_away IS NULL`.

Test data cleanup requires explicit confirmation:

```bash
python -m api.cleanup_test_data run --confirm CLEAN_TEST_DATA
```

Cleanup scope is limited to:

```text
users.username LIKE 'test_user_%'
users.username LIKE 'codex_blocker_%'
matches.match_id LIKE 'test-%'
bets.legs::text LIKE '%test-%'
```

Do not run real `settlement_runner once` as part of this closeout. Do not write fake scores to real `500-` matches.

## 7. Simulated Betting Open Gate

`BETTING_ENABLED` must remain `false` unless all gate checks pass and the user
explicitly confirms opening simulated betting.

Required gate checks:

```text
scheduler_stale=false
ops_health_status=OK, or WARN only for allowed blockers
finished/completed rows with NULL full-time result = 0
scheduled/closed rows with result populated = 0
test-environment settlement E2E = PASS
production/internal real open bet settlement = PASS
settlement idempotency = PASS
leaderboard exposes no internal id and includes roi
no test users remain in the public leaderboard
explicit user confirmation = yes
```

Allowed temporary watchdog blockers:

```text
no_open_bets_to_settle
insufficient_finished_matches
closed_prediction_pending
```

Disallowed blockers:

```text
scheduler_stale
odds_stale
finished_null_count
non_finished_with_result
settlement_runner_error
```

The current gate evidence is tracked in:

```text
docs/BETTING_OPEN_GATE_REPORT.md
```

Do not treat a no-op settlement runner execution as proof that real open-bet
settlement works.

## 8. Official Result Fallback

`results_sync` remains the primary result path. If it cannot populate a verified
finished result, use the controlled fallback instead of manual SQL.

Prepare a reviewed CSV:

```text
data/results/official_results_verified.csv
```

Run dry-run first:

```bash
PYTHONPATH=. python -m api.official_result_fallback --csv data/results/official_results_verified.csv --dry-run
```

Only after the target list is reviewed:

```bash
PYTHONPATH=. python -m api.official_result_fallback --csv data/results/official_results_verified.csv --confirm APPLY_OFFICIAL_RESULTS
```

Requirements:

```text
source_url required
verified_by required
dry-run required before confirm
ops_log job_name=official_result_fallback
existing results are not overwritten
no manual SQL score update
```

See:

```text
docs/OFFICIAL_RESULT_FALLBACK_RUNBOOK.md
```
