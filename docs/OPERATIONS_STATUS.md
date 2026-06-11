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
- blocker: missing real historical market odds
- note: do not mark as `PASS` until real historical national-team market odds produce real RPS metrics.

### P3-D

- status: small-batch data ready / dry-run only
- teams: Mexico, South Africa, Germany, Curaçao
- rows: squad=40, player_stats=16, injuries=12
- production DB writes: no
- GBM: `w_gbm=0`
- note: this is not full P3-D completion and does not affect production predictions.

### Betting

- status: disabled
- required environment: `BETTING_ENABLED=false`

## Safe Commands

```bash
python -m api.health_report
python -m api.scheduler_observe
python -m api.cleanup_test_data dry-run
python -m model.p1c_acceptance_report
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
