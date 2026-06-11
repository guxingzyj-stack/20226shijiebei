# P1-C Prime Prospective Calibration

P1-C historical market backtest is frozen / `WAIT`.

Reason:

```text
The Odds API: not adopted
manual historical CSV: not adopted
500.com 2022 trade date page: returned current/future rows, not real 2022 historical rows
```

P1-C Prime is the replacement path. It evaluates the system prospectively using production data that already exists before kickoff:

```text
matches
odds_snapshots
predictions
results synced after real matches finish
```

## Commands

```bash
python -m model.p1c_prime status
python -m model.p1c_prime run --dry-run
python -m model.p1c_prime_acceptance_report
```

## Selection Policy

For each finished match:

- `matches.status` must be `finished`, `completed`, `已完赛`, or `完赛`.
- 90-minute `result_home` / `result_away` must exist.
- `kickoff_at` must exist.
- Market odds use the last valid `had` odds snapshot with `fetched_at <= kickoff_at`.
- `hhad` is counted separately but is not used as ordinary 1X2 market odds.
- Prediction uses the latest prediction with `created_at <= kickoff_at`.
- If prediction creation time is missing, `leakage_risk=true` and the report cannot PASS.

## Metrics

When at least 30 evaluable finished matches exist and there is no leakage risk:

```text
market_rps
dc_rps
blended_rps
best_w_dc
```

Blend search:

```text
w_dc in [0.00, 1.00], step=0.05
blended = w_dc * dc_prob + (1 - w_dc) * market_prob
```

## Current State

Current expected result before enough real matches finish:

```text
result: WAIT
blocker: insufficient_finished_matches / waiting_for_finished_matches
```

`best_w_dc` is candidate evidence only. It must not automatically update production fusion weights. Any production weight change requires explicit user approval.

`BETTING_ENABLED=false` remains mandatory.
