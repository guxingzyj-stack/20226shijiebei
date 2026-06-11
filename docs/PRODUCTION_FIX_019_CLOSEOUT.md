# Production Fix 019 Closeout

This document records the non-secret closeout state for the 019 production repair flow. It does not contain database URLs, passwords, tokens, or backup contents.

## Current Status

```text
019 emergency production repair: PASS
023 production security closeout: PASS
betting: disabled
P1-C historical market backtest: WAIT
P3-D real data readiness: WAIT
```

## Evidence Summary

### Backup

```text
backup_file: worldcup_20260611_201447.sql
backup_size: 8,078,281 bytes
contains_odds_snapshots: yes
```

### Migration

```text
001_model_core.sql: applied
002_betting_core.sql: applied
003_ev_research_only.sql: applied
004_ops_log.sql: applied
005_p3_features.sql: applied
006_ev_model_version.sql: applied
007_ev_suggestion_eligible.sql: applied
```

### Scheduler

```text
settlement_runner: PASS
results_sync: PASS
```

### Cleanup

```text
before: bets=6, matches=2, users=8
run: PASS
after: bets=0, matches=0, users=0
```

Cleanup protections remain mandatory:

```text
Never delete match_id LIKE '500-%'
Never delete non-test users
Run requires --confirm CLEAN_TEST_DATA
Run is transaction wrapped; failure rolls back
```

### Probe Summary

```text
result: PASS
leaderboard test_user_count: 0
exposes_internal_id: False
Mexico ev_model_version_aligned: True
Mexico unprotected_high_ev_count: 0
Germany ev_model_version_aligned: True
```

Saved JSON probes can be summarized locally without network or database access:

```powershell
$env:PYTHONPATH="."; python -m ops.probe_summary --mexico .\probe_mexico.json --germany .\probe_germany.json --leaderboard .\probe_leaderboard.json
```

Do not commit `probe_*.json`.

## Security Rotation Completed / User Confirmed

The database public endpoint was exposed during emergency operations, and connection material may have appeared in screenshots. The security rotation is now recorded as complete based on user confirmation and public probe evidence.

Non-sensitive evidence:

```text
public endpoint checked: 43.130.69.126:32644
Test-NetConnection expected result: TcpTestSucceeded: False
PostgreSQL password reset: user confirmed
wc-p0-odds-crawler DATABASE_URL updated to internal connection: user confirmed
wc-p1-model-worker DATABASE_URL updated to internal connection: user confirmed
wc-p2-api DATABASE_URL updated to internal connection: user confirmed
three services redeployed: user confirmed
public probes after rotation: PASS
```

Do not write the new connection string into this repository or chat. Zeabur services should use the internal host connection, not the temporary public endpoint.

## Post-019 Next Phase Status

```text
P1-C historical market backtest: WAIT until real national-team historical market odds are available.
P3-D real feature data: WAIT until reviewed real CSV rows are supplied.
GBM: w_gbm remains 0.
Betting: remains disabled.
```

These WAIT states do not change the 019 safety evidence. They should not be rewritten as `PASS` until the corresponding real data is available and acceptance reports produce non-fabricated results.
