# P4 Recap Layer Design

P4 is the post-match review layer. It does not generate predictions, change
model weights, settle bets, write scores, or open betting.

## Scope

The MVP provides:

- single-match recap reports
- market odds versus model probability comparison
- EV signal review
- prediction hit/miss review
- settlement status summary
- data quality warnings
- read-only API endpoints
- CLI output for operations checks
- frontend recap home page
- frontend model performance page
- frontend EV signal performance page
- frontend daily/shareable recap report page

## Data Sources

P4 reads existing tables only:

```text
matches
odds_snapshots
predictions
ev_signals
bets
ops_log
```

No migration is required for the MVP. Recaps are computed in real time.

## Availability Rule

A full match recap is available only when:

```text
status IN ('finished','completed')
result_home IS NOT NULL
result_away IS NOT NULL
```

Otherwise the API returns:

```json
{"available": false, "reason": "match_not_finished_or_result_missing"}
```

## Market Review

The market section uses `play_type='had'`.

- open odds: earliest HAD snapshot
- close odds: last HAD snapshot before kickoff
- fallback close odds: latest HAD snapshot, with warning `no_pre_kickoff_close_odds`
- implied probabilities: normalized `1 / odds`

HAD mapping:

```text
3 = home
1 = draw
0 = away
```

## Model Review

The model section only uses pre-kickoff predictions:

```text
predictions.created_at <= matches.kickoff_at
```

Post-kickoff predictions are ignored. If no auditable pre-kickoff prediction is
available, the recap is still generated with `has_prediction=false`.

## EV Review

EV signals are marked as hit/miss when their play type can be evaluated from
the match result. `research_only=true` is reported as a research signal, never
as a betting recommendation.

## Settlement Review

The settlement section returns aggregate counts only:

```text
settled_bets
won_bets
lost_bets
void_bets
open_bets
settlement_status
```

It does not expose `user_id`, `bet_id`, or internal user data.

## API

```text
GET /api/recaps/matches/{match_id}
GET /api/recaps/recent?limit=20
GET /api/recaps/summary
```

Existing placeholder endpoints under `/api/recap/*` remain unchanged.

## Frontend Product Pages

```text
/recaps
/recaps/{match_id}
/recaps/model
/recaps/ev
/recaps/daily
```

The frontend aggregates existing recap API responses. It does not write data,
call a model, or hard-code scores/prediction conclusions.

- `/recaps` shows summary cards and recent finished match recaps.
- `/recaps/{match_id}` shows result, market, model, EV, settlement, data quality, and summary sections.
- `/recaps/model` shows model hit/miss, market agreement, and recent match table.
- `/recaps/ev` shows EV research signal performance and safety text.
- `/recaps/daily` groups finished matches by day and generates copyable report text.

## CLI

```bash
PYTHONPATH=. python -m api.recap_runner --match-id 500-1359172
PYTHONPATH=. python -m api.recap_runner --summary
```

## Safety

P4 does not:

- enable betting
- write or correct scores
- edit bets, users, balances, odds, predictions, EV rows, or model weights
- expose internal ids
- turn research-only EV into betting advice
- change P1/P3 weights
- depend on P3 being complete
