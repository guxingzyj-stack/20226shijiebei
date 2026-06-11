# Production Current Status

Production read-only version is stable. `BETTING_ENABLED` remains `false`. P1-C is still waiting on historical market odds. P3-D has a small-batch real CSV dry-run for four teams, but this is not full feature-model production enablement.

## 1. Public Endpoints

- Web: https://worldcup2026.zeabur.app
- API: https://fifa2026.zeabur.app
- API health probe: `PASS`
- Public probe summary: `PASS`

## 2. Services

- `wc-p0-odds-crawler`: running, user-confirmed after database rotation
- `wc-p1-model-worker`: running, user-confirmed after database rotation
- `wc-p2-api`: running, user-confirmed after database rotation
- `wc-p2-web`: read-only UI live

## 3. Database

- PostgreSQL backup: `PASS`
- backup file recorded: `worldcup_20260611_201447.sql`
- backup size recorded: `8,078,281 bytes`
- `odds_snapshots` present in backup: yes
- migrations 001-007: applied
- public endpoint `43.130.69.126:32644`: closed, `TcpTestSucceeded=False`
- password rotation: user confirmed

## 4. Scheduler

- `settlement_runner`: `PASS`
- `results_sync`: `PASS`
- `ENABLE_API_SCHEDULER=true`
- `RUN_SCHEDULER_ON_STARTUP=false`

## 5. Model / EV Safety

- latest public probes: `PASS`
- leaderboard exposes ROI: yes
- leaderboard exposes internal id: no
- leaderboard test user count: 0
- Mexico EV model version aligned: true
- Mexico unprotected high EV count: 0
- Germany EV model version aligned: true
- EV over 15% remains research-only and excluded from suggestions.

## 6. Cleanup

- cleanup before: bets=6, matches=2, users=8
- cleanup run: `PASS`
- cleanup after: bets=0, matches=0, users=0
- cleanup must remain test-prefix scoped.

## 7. Security Rotation

- PostgreSQL public port closed: `PASS`
- PostgreSQL password reset: user confirmed
- three service `DATABASE_URL` values updated: user confirmed
- three services redeployed: user confirmed
- public probes after rotation: `PASS`

No real connection strings, passwords, tokens, or backup contents are stored in this repository.

## 8. P1-C WAIT

- status: `WAIT`
- blocker: missing real historical national-team market odds
- tooling: `python -m model.p1c_acceptance_report`
- current result must not be recorded as `PASS`.

## 9. P3-D Small-Batch Dry-Run

- status: small-batch data ready / dry-run only
- teams: Mexico, South Africa, Germany, Curaçao
- rows: squad=40, player_stats=16, injuries=12
- source/retrieved_at/confidence coverage: complete for included rows
- production DB writes: no
- tooling: `python -m model.p3_acceptance_report --real-dry-run`
- GBM remains `w_gbm=0`.

## 10. Betting Status

- `BETTING_ENABLED=false`
- real betting: not provided
- simulated betting: closed until future explicit approval

## 11. Remaining Blockers

- P1-C real historical market odds source and backtest numbers
- P3-D full reviewed real team/player/injury CSV with reliable numeric performance data
- real-match settlement observation after actual completed matches
- continued scheduler observation

## 12. Next Recommended Tasks

1. Acquire or prepare compliant P1-C historical national-team market odds.
2. Prepare reviewed P3-D real CSV with source, retrieved_at, and confidence metadata.
3. Re-run `python -m ops.next_phase_acceptance`.
4. Keep `BETTING_ENABLED=false`.
