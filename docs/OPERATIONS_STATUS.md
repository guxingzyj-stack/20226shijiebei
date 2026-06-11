# Operations Status

Current production posture:

- Read-only prediction, odds, EV, leaderboard, and recap skeleton features are open.
- Betting remains closed: `BETTING_ENABLED=false`.
- API scheduler has been enabled and is waiting for real `ops_log` observation.
- P1-C historical market backtest numbers are still pending.
- P3 real manual data import is pending.
- P4 real recap output is waiting for more finished matches.

## Safe Commands

```bash
python -m api.health_report
python -m api.scheduler_observe
python -m api.cleanup_test_data dry-run
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
- Do not run real `settlement_runner once` for this task.
- Do not write fake scores to real `500-` matches.
- Do not scrape external football data sites.
