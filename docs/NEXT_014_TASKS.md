# NEXT 014 Tasks

These items must not drift again.

## 014-A Scheduler Integration

Current 014-A status:

```text
settlement_smoke must PASS before enabling any automatic settlement schedule
automatic scheduling is not enabled yet
```

Goal:

```text
results_sync runs every hour
settlement_runner runs every 30 minutes
```

Acceptable implementation options:

```text
APScheduler in API
independent settlement-runner service
Zeabur cron / external scheduler
```

Acceptance:

```text
no manual once command required
logs are visible
failures emit error logs
```

Concrete plan:

```text
results_sync: run every hour
settlement_runner: run every 30 minutes
recommended implementation: independent API scheduler service or APScheduler inside API
required logging: ops_log table or equivalent structured error log before production enablement
precondition: python -m api.settlement_smoke run returns PASS
```

## 014-B P1-C Four Backtest Numbers

Must provide:

```text
market_rps
dc_rps
blended_rps
best_w_dc
```

Current status:

```text
pending paid historical odds source / THE_ODDS_API_KEY
```

## 014-C Test Data Cleanup

Clean only test data:

```text
test_user_*
codex_blocker_*
test-settlement-*
test bets
```

Safe SQL must only target test prefixes:

```sql
DELETE FROM bets WHERE legs::text LIKE '%test-settlement-%';
DELETE FROM matches WHERE match_id LIKE 'test-%';
DELETE FROM users WHERE username LIKE 'test_user_%' OR username LIKE 'codex_blocker_%';
```
