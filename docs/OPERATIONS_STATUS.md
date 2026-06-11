# Operations Status

Current production posture:

- Production read-only version is stable.
- Read-only prediction, odds, EV, leaderboard, and recap skeleton features are open.
- Betting remains closed: `BETTING_ENABLED=false`.
- GBM remains zero-weight and does not affect P1 production predictions.

## Production Status Summary

### Scheduler

- `settlement_runner`: `PASS`
- `results_sync`: `PASS`
- stale threshold: latest `ops_log` older than 90 minutes is `FAIL` in `api.health_report`
- `/api/health` exposes `scheduler_last_seen`, `scheduler_last_seen_age_minutes`, and `scheduler_stale`

### 019 Emergency Repair

- backup: `PASS`
- migrations 001-007: `PASS`
- cleanup: `PASS`
- public probes: `PASS`

### 023 Security Closeout

- PostgreSQL public port closed: `PASS`
- password rotated: user confirmed
- `wc-p0-odds-crawler`, `wc-p1-model-worker`, `wc-p2-api` `DATABASE_URL` updated: user confirmed
- three services redeployed: user confirmed
- public probe after rotation: `PASS`

### P1-C

- status: `WAIT`
- blocker: 500.com trade date page returned current/future rows for requested 2022 dates; valid historical market odds CSV is still missing
- note: do not mark as `PASS` until real historical national-team market odds produce real RPS metrics.

### P1-C Prime

- status: framework ready / `WAIT`
- blocker: waiting for at least 30 evaluable finished matches
- command: `python -m model.p1c_prime_acceptance_report`
- note: any `best_w_dc` produced later is candidate evidence only and must not automatically update production fusion weights.

### P3-D

- status: WAIT
- official profile coverage: 48 / 48 teams
- players: 1,248 official FIFA squad rows
- rows: squad=1248, player_stats=1248, injuries=1248
- production DB writes: no
- GBM: `w_gbm=0`
- full tournament complete teams: 0 / 48
- teams with numeric recent stats: 0 / 48
- performance files: no committed `data/p3/real_performance_*.csv` yet
- GBM gray readiness: false, `w_gbm=0`
- note: FIFA official squad/profile data is complete, but recent minutes/goals/assists/xG/xA are still missing. This does not affect production predictions. Continue with `python -m model.p3_data_audit --write-backlog`.

### Betting

- status: disabled
- required environment: `BETTING_ENABLED=false`

### Result State Guard

- `closed` means sale closed / stop selling, not match finished.
- P0 odds crawler must not set `status=finished` from `data-isend`.
- `closed` matches remain visible in upcoming lists and remain eligible for model-worker prediction while waiting for real results.
- `finished` / `completed` is settlement- and recap-ready only when `result_home` and `result_away` are both present.
- Diagnostic command: `python -m api.result_consistency_report`

## Safe Commands

```bash
python -m api.health_report
python -m api.result_consistency_report
python -m api.scheduler_observe
python -m api.cleanup_test_data dry-run
python -m model.p1c_acceptance_report
python -m model.p1c_prime_acceptance_report
python -m model.p3_acceptance_report --real-dry-run
python -m ops.next_phase_acceptance
```

Cleanup writes require explicit confirmation:

```bash
python -m api.cleanup_test_data run --confirm CLEAN_TEST_DATA
```

## Backup First

Before cleanup, restore, migration, or host movement:

```bash
bash deploy/backup_postgres.sh
```

`odds_snapshots` is not reproducible after the fact and must be protected first.

## Do Not Do

- Do not set `BETTING_ENABLED=true`.
- Do not run real `settlement_runner once` for a docs-only task.
- Do not write fake scores to real `500-` matches.
- Do not scrape external football data sites.
- Do not mark P1-C as `PASS` without real historical national-team market odds.
- Do not mark full P3-D as complete without full reviewed real CSV data and reliable numeric performance fields.
- Do not enable GBM weight from sample or header-only P3 data.
