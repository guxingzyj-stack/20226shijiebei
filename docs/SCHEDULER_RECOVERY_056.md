# Scheduler Recovery 056

Status: code hardening added. Production rescue must be executed inside the
Zeabur `wc-p2-api` container or the Zeabur console; do not fake production
evidence in this repository.

## Problem

After API redeploys, the scheduler could appear configured but stop producing
fresh `ops_log` rows. That leaves later finished matches stuck as `closed` with
empty `result_home/result_away`.

## Required Production Environment

```text
ENABLE_API_SCHEDULER=true
RUN_SCHEDULER_ON_STARTUP=true
BETTING_ENABLED=false
RESULTS_SYNC_INTERVAL_MINUTES=60
SETTLEMENT_RUNNER_INTERVAL_MINUTES=30
OPS_HEALTH_CHECK_INTERVAL_MINUTES=30
```

`BETTING_ENABLED` must remain `false`.

## What Changed

On API startup, when `RUN_SCHEDULER_ON_STARTUP=true`, the API now runs these jobs
immediately and records their normal `ops_log` rows:

```text
results_sync
settlement_runner
ops_health_check
```

The interval scheduler is still registered for later runs. Startup failures are
sanitized, printed as scheduler startup errors, and exposed in `/api/health` as:

```json
{
  "scheduler_stale": true,
  "scheduler_startup_error": "results_sync startup failed: ..."
}
```

No database URL, password, token, or key should appear in the error string.

## Production Rescue Checklist

Run these only in the production API container or an environment that uses the
same internal production database connection. Do not run migrations for this
rescue.

```bash
curl -sS https://fifa2026.zeabur.app/api/health
PYTHONPATH=. python -m api.results_sync once
PYTHONPATH=. python -m api.result_consistency_report
PYTHONPATH=. python -m api.result_overdue_report
PYTHONPATH=. python -m api.ops_health_check
```

Then inspect the delayed matches:

```sql
SELECT match_id, match_num, home_team, away_team, kickoff_at, status, result_home, result_away, ht_home, ht_away
FROM matches
WHERE match_id IN ('500-1359182', '500-1359189')
ORDER BY kickoff_at;
```

Inspect finished rows that are not settlement-ready:

```sql
SELECT match_id, match_num, home_team, away_team, status, result_home, result_away
FROM matches
WHERE status IN ('finished', 'completed')
  AND (result_home IS NULL OR result_away IS NULL);
```

Inspect closed/scheduled matches overdue for result backfill:

```sql
SELECT match_id, match_num, home_team, away_team, kickoff_at, status, result_home, result_away
FROM matches
WHERE status IN ('closed', 'scheduled')
  AND result_home IS NULL
  AND result_away IS NULL
  AND kickoff_at < NOW() - INTERVAL '3 hours'
ORDER BY kickoff_at;
```

Inspect odds freshness. The deployed schema commonly uses `fetched_at`; if a
specific environment has `captured_at`, use that column instead.

```sql
SELECT MAX(fetched_at) AS latest_odds_snapshot FROM odds_snapshots;
```

If `results_sync` cannot obtain verified results, use the documented official
fallback CSV process. Do not manually update scores with ad hoc SQL.

`results_sync` now prints and records `skipped_reasons`. If the command reports
`matches_seen > 0` and `finished_updated = 0`, inspect:

```text
not_finished_status
missing_result_score
match_id_not_found
already_finished_with_result
row_error
```

If `result_overdue_report` suggests `NEEDS_VERIFIED_FALLBACK`, use the verified
fallback CSV flow with `source_url`, `verified_by`, and `retrieved_at`.

## Deployment Acceptance

Within one minute after every `wc-p2-api` deploy or restart:

```text
api logs contain api_scheduler_started
api logs contain scheduler_job_finished job_name=results_sync
api logs contain scheduler_job_finished job_name=settlement_runner
api logs contain scheduler_job_finished job_name=ops_health_check
/api/health scheduler_last_seen is within 5 minutes
/api/health scheduler_stale=false
/api/health scheduler_startup_error=null
ops_log has fresh results_sync ok
ops_log has fresh settlement_runner ok
```

If any item fails, the deployment is not complete.

## Halftime Scores

`results_sync` parses halftime scores only when the upstream result source
provides them, for example through `data-half-score` or an explicit second score
in the row. If the source does not provide halftime scores, `ht_home/ht_away`
remain `NULL`.

Never infer halftime from full-time score. HAFU settlement treats missing
halftime as void/not-ready according to the existing settlement rules.

## Safety

```text
Do not enable betting.
Do not write fake scores.
Do not manually UPDATE result_home/result_away.
Do not modify bets/users/balance.
Do not change P1/P3 production weights.
Do not print DATABASE_URL or secrets.
```
