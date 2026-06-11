# 014-D Production Operations Acceptance Closeout

This document is an operations closeout checklist. It does not record any production command execution by Codex, and it must not be read as proof that unobserved production jobs have passed.

Do not paste `DATABASE_URL`, database passwords, JWT secrets, tokens, or backup files into chat.

## 1. Current Service Status

```text
P0 crawler: running
P1 model-worker: running
P2 API/Web: running
API scheduler: started
BETTING_ENABLED: false
Betting: closed
Read-only features: open
```

Read-only features include match pages, odds, predictions, EV display, leaderboard, and the recap skeleton. Real betting and real lottery purchase flows are not connected.

## 2. Scheduler Observation Status

Current observed state:

```text
settlement_runner: automatic scheduler success has been observed
results_sync: waiting for automatic scheduler observation
```

Do not write or say that `results_sync` has passed until production logs or `python -m api.scheduler_observe` show an ok `results_sync` ops_log row.

Run inside the Zeabur API container:

```bash
python -m api.scheduler_observe
```

Pass condition:

```text
latest settlement_runner ops_log has status=ok
latest results_sync ops_log has status=ok
result: PASS
```

If settlement_runner has ok but results_sync has no ok record yet:

```text
result: WAIT
```

If either job has error, or an expected observed job becomes stale:

```text
result: FAIL
```

## 3. Database Backup Status

Before migration, cleanup, restore, or host movement, create a PostgreSQL backup.

Linux:

```bash
bash deploy/backup_postgres.sh
```

Windows PowerShell:

```powershell
.\deploy\backup_postgres.ps1
```

Backup target:

```text
backups/worldcup_YYYYMMDD_HHMMSS.sql
```

Core table:

```text
odds_snapshots
```

Non-regenerable data:

```text
odds time series
```

After the user runs the backup, record locally:

```text
backup_file:
backup_size:
backup_time:
```

Do not commit backup files. Do not send backup files, `DATABASE_URL`, or database passwords to chat.

## 4. Test Data Cleanup Status

Do not automatically clean production data. First run dry-run only:

```bash
python -m api.cleanup_test_data dry-run
```

Allowed cleanup scopes:

```text
users.username LIKE 'test_user_%'
users.username LIKE 'codex_blocker_%'
matches.match_id LIKE 'test-%'
bets.legs::text LIKE '%test-%'
```

The expected test match family includes:

```text
test-settlement-*
```

If dry-run shows any non-test-prefix data, do not run cleanup.

Only after dry-run confirms test-only rows:

```bash
python -m api.cleanup_test_data run --confirm CLEAN_TEST_DATA
```

## 5. Betting Open Status

```text
BETTING_ENABLED: false
Betting: closed
Recommendation: do not open betting
```

Do not set `BETTING_ENABLED=true` during 014-D. Results sync has not yet been observed as ok, and P1-C historical market backtest numbers are still pending.

## 6. Health Report

Run inside the Zeabur API container:

```bash
python -m api.health_report
```

Review:

```text
database
matches count
odds_snapshots count
latest odds fetched_at
latest model_version
latest prediction count
latest ev_signals count
betting_enabled
api_scheduler_enabled
open_bets_count
test_users_count
test_matches_count
result
```

The health report is read-only. It does not run settlement, results sync, cleanup, or migrations.

## 7. Formal Service Commands

API service:

```text
ENTRYPOINT:
uvicorn

CMD:
api.main:app --host 0.0.0.0 --port 8080
```

model-worker service:

```text
ENTRYPOINT:
python

CMD:
-m model.model_worker
```

Web service:

```text
Use nginx / Dockerfile default command.
Do not leave temporary acceptance commands as the production command.
```

## 8. Required Environment Variables

API:

```text
BETTING_ENABLED=false
ENABLE_API_SCHEDULER=true
RUN_SCHEDULER_ON_STARTUP=false
RESULTS_SYNC_INTERVAL_MINUTES=60
SETTLEMENT_RUNNER_INTERVAL_MINUTES=30
CORS_ORIGINS=https://worldcup2026.zeabur.app,http://localhost:5173
```

Web:

```text
VITE_API_BASE_URL=https://fifa2026.zeabur.app
VITE_BETTING_ENABLED=false
```

model-worker:

```text
DATABASE_URL exists in the deployment environment
PYTHONUNBUFFERED=1
```

Do not write real secret values into this document.

## 9. Remaining Blockers

```text
results_sync automatic scheduler ok record has not yet been observed
BETTING_ENABLED remains false
P1-C historical market backtest numbers are still pending
P3 real player data import is still pending
P4 real recap requires more finished matches
```

Do not claim:

```text
results_sync has passed
betting can open
P2 settlement is fully automatic end-to-end
```

unless production evidence exists.

## 10. Next Operations Checklist

1. Run `python -m api.scheduler_observe` in the Zeabur API container at the next observation window.
2. If result is `WAIT`, continue observing until both jobs have ok rows.
3. Run `python -m api.health_report` and record the non-secret summary.
4. Run `python -m api.cleanup_test_data dry-run`.
5. If dry-run shows only test-prefix rows, optionally run `python -m api.cleanup_test_data run --confirm CLEAN_TEST_DATA`.
6. Run a PostgreSQL backup and record `backup_file`, `backup_size`, and `backup_time` locally.
7. Keep `BETTING_ENABLED=false`.
