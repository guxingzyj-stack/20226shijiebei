# P3 FIFA MatchData Auto Enable Plan

P3 now has two tracks:

- P3-A club recent form: remains `WAIT` because compliant full coverage club performance data is still missing.
- P3-B FIFA MatchData: becomes the rolling in-tournament data layer for official World Cup match performance.

## Principle

P3-FIFA may automatically accumulate data and report maturity, but it must not
automatically change production model weights.

```text
production_w_p3=0
production_w_gbm=0
BETTING_ENABLED=false
requires_user_approval_before_production_use=true for candidate stages
```

## Stages

### WAIT

No auditable FIFA MatchData sample exists.

```json
{
  "p3_mode": "fifa_matchdata",
  "p3_status": "WAIT",
  "candidate_w_p3": 0,
  "production_w_p3": 0
}
```

### SHADOW

At least one FIFA MatchData match has valid player rows with minutes, goals,
and assists. This stage can serve P4 recap and feature generation only.

### CANDIDATE

Candidate conditions:

```text
matches_with_fifa_data >= 16
teams_with_fifa_data >= 16
player_rows_validated > 0
result_consistency_pass=true
ops_health_status != FAIL
```

Candidate output:

```json
{
  "candidate_w_p3": 0.05,
  "production_w_p3": 0
}
```

### ACTIVE_READY

Additional conditions:

```text
matches_with_fifa_data >= 32
teams_with_fifa_data >= 32
two consecutive matchdays auto-parse successfully
P1-C Prime has sufficient samples
P3 feature evaluation does not degrade the model
user explicitly approves production use
```

Even at `ACTIVE_READY`, production weight remains zero until a separate,
explicit production change is approved.

## Commands

```bash
PYTHONPATH=. python -m model.p3_fifa_readiness
PYTHONPATH=. python -m model.p3_auto_enable_gate
```

## Safety

P3-FIFA:

- does not open betting
- does not write predictions
- does not modify scores
- does not modify `production_w_p3`
- does not modify `production_w_gbm`
- must not fabricate FIFA data
- must not turn research-only EV into betting advice
