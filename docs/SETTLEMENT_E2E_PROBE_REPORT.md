# Settlement E2E Probe Report

This document tracks the production internal settlement probe. It does not
enable public betting.

## 1. Probe CLI

Dry-run:

```bash
PYTHONPATH=. python -m api.settlement_e2e_probe --dry-run
```

Confirm:

```bash
PYTHONPATH=. python -m api.settlement_e2e_probe --confirm RUN_SETTLEMENT_E2E_PROBE
```

Optional:

```bash
PYTHONPATH=. python -m api.settlement_e2e_probe --match-id 500-1359172 --stake 1 --dry-run
```

## 2. Current Gate Status

```text
settlement_e2e_test_env: PASS
production_internal_bet_settlement: NOT_RUN
settlement_idempotency: NOT_RUN
leaderboard_safety: NOT_RUN
recommend_open_betting: no
```

## 3. Safety Rules

The probe:

- requires `BETTING_ENABLED=false`
- requires an existing finished/completed match with a full-time result
- requires result consistency to be clean
- blocks when non-probe open/pending bets exist
- creates only `__internal_settlement_probe__`
- creates only one probe bet labelled `__internal_settlement_probe_bet__`
- uses the latest server-side HAD home-win odds
- runs `settlement_runner` twice to verify idempotency
- deletes the probe bet and probe user
- writes `ops_log.job_name='settlement_e2e_probe'`

Do not run the confirm command unless the dry-run output has no blockers.

## 4. Post-Run Verification

Run:

```bash
PYTHONPATH=. python -m api.ops_health_check
PYTHONPATH=. python -m api.result_consistency_report
```

Public read-only checks:

```bash
curl -sS https://fifa2026.zeabur.app/api/leaderboard
curl -sS https://fifa2026.zeabur.app/api/health
```

Expected:

```text
leaderboard_no_internal_id=true
leaderboard_no_probe_user_pollution=true
scheduler_stale=false
```

## 5. Betting Gate

Even if the probe passes, keep:

```text
BETTING_ENABLED=false
recommend_open_betting=no
```

Remaining requirements before public simulated betting:

- two consecutive match days with automatic result sync working
- `finished+NULL=0`
- `scheduler_stale=false`
- ops health has no `FAIL`
- explicit user confirmation to open betting
